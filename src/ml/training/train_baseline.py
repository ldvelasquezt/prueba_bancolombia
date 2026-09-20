"""
Entrena el modelo de propensión a aceptar una opción de pago (XGBoost).

Validación temporal: entrena con sep-nov 2023 y valida con dic 2023 (el mes más
reciente disponible), simulando el escenario real de pronóstico a un mes. El
umbral de decisión se calibra maximizando F1 sobre el mes de validación.

Búsqueda de hiperparámetros con Optuna (opcional, --tune): optimiza F1 sobre el
mismo split temporal, sin usar folds aleatorios (evita fuga temporal).
"""
import argparse
import json
import os

import mlflow
import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

DATA = "data/processed"
MODELS = "models"

ID_COLS = ["nit_enmascarado", "num_oblig_orig_enmascarado", "num_oblig_enmascarado"]
DATE_COLS = ["fecha_var_rpta_alt", "mes_prev"]
TARGET = "var_rpta_alt"

CAT_COLS = [
    "lag1_banca", "lag1_segmento", "lag1_producto", "lag1_producto_cons",
    "lag1_aplicativo", "lag1_rango_mora", "lag1_alter_posible1_2",
    "lag1_alter_posible2_2", "lag1_alter_posible3_2", "prevmes_marca_pago",
    "genero_cli", "estado_civil", "tipo_vivienda", "nivel_academico",
    "ocup", "sector", "declarante",
]

VALID_MONTH = 202312

DEFAULT_PARAMS = dict(
    n_estimators=500,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    reg_lambda=1.0,
)


def prep_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in CAT_COLS:
        df[c] = df[c].fillna("MISSING").astype("category")
    num_cols = df.select_dtypes(include=["float64", "int64"]).columns
    df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
    return df


def best_threshold(y_true, y_prob) -> tuple[float, float]:
    best_t, best_f1 = 0.5, -1.0
    for t in np.arange(0.05, 0.96, 0.01):
        f1 = f1_score(y_true, (y_prob >= t).astype(int))
        if f1 > best_f1:
            best_t, best_f1 = t, f1
    return best_t, best_f1


def fit_and_eval(params, X_train, y_train, X_valid, y_valid):
    model = xgb.XGBClassifier(
        **params,
        tree_method="hist",
        enable_categorical=True,
        eval_metric="logloss",
        early_stopping_rounds=30,
        random_state=42,
    )
    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)
    y_prob = model.predict_proba(X_valid)[:, 1]
    threshold, f1_valid = best_threshold(y_valid, y_prob)
    return model, y_prob, threshold, f1_valid


def tune(X_train, y_train, X_valid, y_valid, n_trials=25):
    def objective(trial):
        params = dict(
            n_estimators=trial.suggest_int("n_estimators", 200, 800, step=100),
            max_depth=trial.suggest_int("max_depth", 3, 8),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            subsample=trial.suggest_float("subsample", 0.6, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
            min_child_weight=trial.suggest_int("min_child_weight", 1, 20),
            reg_lambda=trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
        )
        _, _, _, f1_valid = fit_and_eval(params, X_train, y_train, X_valid, y_valid)
        return f1_valid

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    print(f"\nMejor F1 en búsqueda: {study.best_value:.4f}")
    print(f"Mejores params: {study.best_params}")
    return study.best_params


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="store_true", help="Ejecuta búsqueda de hiperparámetros con Optuna")
    parser.add_argument("--n-trials", type=int, default=25)
    args = parser.parse_args()

    train_full = pd.read_parquet(f"{DATA}/train_full.parquet")
    train_full = prep_features(train_full)

    feature_cols = [c for c in train_full.columns if c not in ID_COLS + DATE_COLS + [TARGET]]

    train_mask = train_full["fecha_var_rpta_alt"] < VALID_MONTH
    valid_mask = train_full["fecha_var_rpta_alt"] == VALID_MONTH

    X_train, y_train = train_full.loc[train_mask, feature_cols], train_full.loc[train_mask, TARGET]
    X_valid, y_valid = train_full.loc[valid_mask, feature_cols], train_full.loc[valid_mask, TARGET]

    print(f"Train: {X_train.shape} ({sorted(train_full.loc[train_mask, 'fecha_var_rpta_alt'].unique())})")
    print(f"Valid: {X_valid.shape} ({sorted(train_full.loc[valid_mask, 'fecha_var_rpta_alt'].unique())})")

    if args.tune:
        params = tune(X_train, y_train, X_valid, y_valid, n_trials=args.n_trials)
    else:
        params = DEFAULT_PARAMS

    mlflow.set_experiment("propension_opciones_pago")
    with mlflow.start_run(run_name="xgb_tuned" if args.tune else "xgb_baseline"):
        mlflow.log_params(params)
        mlflow.log_param("valid_month", VALID_MONTH)
        mlflow.log_param("n_features", len(feature_cols))
        mlflow.log_param("tuned", args.tune)

        model, y_prob, threshold, f1_valid = fit_and_eval(params, X_train, y_train, X_valid, y_valid)
        auc = roc_auc_score(y_valid, y_prob)
        precision = precision_score(y_valid, (y_prob >= threshold).astype(int))
        recall = recall_score(y_valid, (y_prob >= threshold).astype(int))

        mlflow.log_metric("f1_valid", f1_valid)
        mlflow.log_metric("auc_valid", auc)
        mlflow.log_metric("precision_valid", precision)
        mlflow.log_metric("recall_valid", recall)
        mlflow.log_metric("threshold", threshold)

        print(f"\nF1 (mes validación {VALID_MONTH}): {f1_valid:.4f}")
        print(f"AUC: {auc:.4f} | Precision: {precision:.4f} | Recall: {recall:.4f} | Umbral: {threshold:.2f}")

        importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
        print("\nTop 15 features:")
        print(importances.head(15))

        mlflow.xgboost.log_model(model, name="model")

        os.makedirs(MODELS, exist_ok=True)
        model.save_model(f"{MODELS}/xgb_baseline.json")
        cat_categories = {c: X_train[c].cat.categories.tolist() for c in CAT_COLS}
        with open(f"{MODELS}/feature_config.json", "w") as f:
            json.dump({
                "feature_cols": feature_cols,
                "cat_cols": CAT_COLS,
                "cat_categories": cat_categories,
                "params": params,
                "threshold": threshold,
                "valid_month": VALID_MONTH,
                "f1_valid": f1_valid,
                "auc_valid": auc,
            }, f, indent=2)
        print(f"\nModelo guardado en {MODELS}/xgb_baseline.json")


if __name__ == "__main__":
    main()
