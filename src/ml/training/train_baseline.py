"""
Entrena el modelo de propensión a aceptar una opción de pago (XGBoost).

Validación temporal en 3 folds, no 2, para evitar reutilizar el mismo mes para
decidir hiperparámetros, calibrar el umbral de F1 Y reportar la métrica final
(lo que infla el F1 reportado — hallazgo de la revisión técnica de este repo):

  - FIT (sep-oct 2023): ajusta el modelo.
  - CALIB (nov 2023): early-stopping, objetivo de Optuna y calibración del
    umbral óptimo de F1. Se puede "tocar" tantas veces como haga falta.
  - REPORT (dic 2023): NUNCA se usa para ninguna decisión. Se toca una sola
    vez, al final, para reportar la métrica honesta.

Una vez validada la metodología sobre REPORT, el modelo final que se guarda
(el que se usa para calificar la muestra OOT) se reentrena con los 3 meses
combinados (FIT+CALIB+REPORT), para no desperdiciar datos en el modelo que de
verdad se despliega — el número de árboles se fija en el `best_iteration`
hallado durante la calibración, sin volver a mirar REPORT para decidirlo.

Búsqueda de hiperparámetros con Optuna (opcional, --tune): optimiza F1 sobre
el mismo split FIT->CALIB, nunca sobre REPORT.
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

FIT_MONTHS = [202309, 202310]
CALIB_MONTH = 202311
REPORT_MONTH = 202312

DEFAULT_PARAMS = dict(
    n_estimators=600,
    max_depth=8,
    learning_rate=0.0408,
    subsample=0.958,
    colsample_bytree=0.883,
    min_child_weight=10,
    reg_lambda=7.12,
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


def fit_and_eval(params, X_fit, y_fit, X_calib, y_calib):
    """Ajusta con early-stopping sobre CALIB y calibra el umbral sobre CALIB.
    CALIB puede reutilizarse libremente (tuning, threshold); REPORT nunca entra aquí."""
    model = xgb.XGBClassifier(
        **params,
        tree_method="hist",
        enable_categorical=True,
        eval_metric="logloss",
        early_stopping_rounds=30,
        random_state=42,
    )
    model.fit(X_fit, y_fit, eval_set=[(X_calib, y_calib)], verbose=False)
    y_prob = model.predict_proba(X_calib)[:, 1]
    threshold, f1_calib = best_threshold(y_calib, y_prob)
    return model, y_prob, threshold, f1_calib


def tune(X_fit, y_fit, X_calib, y_calib, n_trials=25):
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
        _, _, _, f1_calib = fit_and_eval(params, X_fit, y_fit, X_calib, y_calib)
        return f1_calib

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    print(f"\nMejor F1 en búsqueda (sobre CALIB={CALIB_MONTH}): {study.best_value:.4f}")
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

    fit_mask = train_full["fecha_var_rpta_alt"].isin(FIT_MONTHS)
    calib_mask = train_full["fecha_var_rpta_alt"] == CALIB_MONTH
    report_mask = train_full["fecha_var_rpta_alt"] == REPORT_MONTH

    X_fit, y_fit = train_full.loc[fit_mask, feature_cols], train_full.loc[fit_mask, TARGET]
    X_calib, y_calib = train_full.loc[calib_mask, feature_cols], train_full.loc[calib_mask, TARGET]
    X_report, y_report = train_full.loc[report_mask, feature_cols], train_full.loc[report_mask, TARGET]

    print(f"FIT:    {X_fit.shape} ({FIT_MONTHS})")
    print(f"CALIB:  {X_calib.shape} ({CALIB_MONTH})")
    print(f"REPORT: {X_report.shape} ({REPORT_MONTH}) -- se toca una sola vez, al final")

    if args.tune:
        params = tune(X_fit, y_fit, X_calib, y_calib, n_trials=args.n_trials)
    else:
        params = DEFAULT_PARAMS

    mlflow.set_experiment("propension_opciones_pago")
    with mlflow.start_run(run_name="xgb_tuned" if args.tune else "xgb_baseline"):
        mlflow.log_params(params)
        mlflow.log_param("fit_months", FIT_MONTHS)
        mlflow.log_param("calib_month", CALIB_MONTH)
        mlflow.log_param("report_month", REPORT_MONTH)
        mlflow.log_param("n_features", len(feature_cols))
        mlflow.log_param("tuned", args.tune)

        # --- Calibración: decide n_arboles (best_iteration) y umbral, solo con FIT/CALIB ---
        calib_model, _, threshold, f1_calib = fit_and_eval(params, X_fit, y_fit, X_calib, y_calib)
        n_estimators_final = calib_model.best_iteration + 1
        mlflow.log_metric("f1_calib", f1_calib)
        mlflow.log_metric("threshold", threshold)
        mlflow.log_param("n_estimators_final", n_estimators_final)

        # --- Reporte honesto: modelo de calibración evaluado UNA VEZ sobre REPORT ---
        y_prob_report = calib_model.predict_proba(X_report)[:, 1]
        f1_report = f1_score(y_report, (y_prob_report >= threshold).astype(int))
        auc_report = roc_auc_score(y_report, y_prob_report)
        precision_report = precision_score(y_report, (y_prob_report >= threshold).astype(int))
        recall_report = recall_score(y_report, (y_prob_report >= threshold).astype(int))

        mlflow.log_metric("f1_report", f1_report)
        mlflow.log_metric("auc_report", auc_report)
        mlflow.log_metric("precision_report", precision_report)
        mlflow.log_metric("recall_report", recall_report)

        print(f"\nF1 en CALIB ({CALIB_MONTH}, usado para tuning/umbral): {f1_calib:.4f}")
        print(f"F1 en REPORT ({REPORT_MONTH}, tocado una sola vez, métrica honesta): {f1_report:.4f}")
        print(f"AUC: {auc_report:.4f} | Precision: {precision_report:.4f} | Recall: {recall_report:.4f} | "
              f"Umbral: {threshold:.2f}")

        # --- Modelo final para desplegar/calificar OOT: reentrenado con TODOS los meses
        # disponibles (FIT+CALIB+REPORT), sin volver a mirar REPORT para decidir nada
        # (n_estimators y threshold ya quedaron fijos arriba). ---
        final_params = {**params, "n_estimators": n_estimators_final}
        final_model = xgb.XGBClassifier(
            **final_params, tree_method="hist", enable_categorical=True, random_state=42,
        )
        X_all = pd.concat([X_fit, X_calib, X_report])
        y_all = pd.concat([y_fit, y_calib, y_report])
        final_model.fit(X_all, y_all, verbose=False)

        importances = pd.Series(final_model.feature_importances_, index=feature_cols).sort_values(ascending=False)
        print("\nTop 15 features (modelo final):")
        print(importances.head(15))

        mlflow.xgboost.log_model(final_model, name="model")

        os.makedirs(MODELS, exist_ok=True)
        final_model.save_model(f"{MODELS}/xgb_baseline.json")
        cat_categories = {c: X_all[c].cat.categories.tolist() for c in CAT_COLS}
        with open(f"{MODELS}/feature_config.json", "w") as f:
            json.dump({
                "feature_cols": feature_cols,
                "cat_cols": CAT_COLS,
                "cat_categories": cat_categories,
                "params": final_params,
                "threshold": threshold,
                "fit_months": FIT_MONTHS,
                "calib_month": CALIB_MONTH,
                "report_month": REPORT_MONTH,
                "f1_calib": f1_calib,
                "f1_report": f1_report,
                "auc_report": auc_report,
            }, f, indent=2)
        print(f"\nModelo final (entrenado con FIT+CALIB+REPORT) guardado en {MODELS}/xgb_baseline.json")


if __name__ == "__main__":
    main()
