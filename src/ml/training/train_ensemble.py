"""
Prueba XGBoost, LightGBM, CatBoost y su ensamble (promedio de probabilidades)
sobre el mismo split temporal honesto (FIT/CALIB/REPORT) usado en
train_baseline.py, para ver si algún modelo o combinación supera el F1 de
XGBoost solo. REPORT se toca UNA sola vez al final, igual que en
train_baseline.py.
"""
import json

import catboost as cb
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

from src.ml.training.train_baseline import (
    CAT_COLS, DATE_COLS, ID_COLS, TARGET, DEFAULT_PARAMS, FIT_MONTHS, CALIB_MONTH, REPORT_MONTH,
    best_threshold,
)

DATA = "data/processed"
MODELS = "models"


def load_split():
    train_full = pd.read_parquet(f"{DATA}/train_full.parquet")
    feature_cols = [c for c in train_full.columns if c not in ID_COLS + DATE_COLS + [TARGET]]

    fit_mask = train_full["fecha_var_rpta_alt"].isin(FIT_MONTHS)
    calib_mask = train_full["fecha_var_rpta_alt"] == CALIB_MONTH
    report_mask = train_full["fecha_var_rpta_alt"] == REPORT_MONTH

    return train_full, feature_cols, fit_mask, calib_mask, report_mask


def prep_xgb(df, feature_cols):
    df = df.copy()
    for c in CAT_COLS:
        df[c] = df[c].fillna("MISSING").astype("category")
    num_cols = [c for c in feature_cols if c not in CAT_COLS]
    df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
    return df


def prep_lgb(df, feature_cols):
    df = df.copy()
    for c in CAT_COLS:
        df[c] = df[c].fillna("MISSING").astype("category")
    num_cols = [c for c in feature_cols if c not in CAT_COLS]
    df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
    return df


def prep_cb(df, feature_cols):
    df = df.copy()
    for c in CAT_COLS:
        df[c] = df[c].fillna("MISSING").astype(str)
    num_cols = [c for c in feature_cols if c not in CAT_COLS]
    df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)
    return df


def main():
    train_full, feature_cols, fit_mask, calib_mask, report_mask = load_split()

    print(f"FIT={fit_mask.sum()} CALIB={calib_mask.sum()} REPORT={report_mask.sum()}\n")

    y_fit = train_full.loc[fit_mask, TARGET]
    y_calib = train_full.loc[calib_mask, TARGET]
    y_report = train_full.loc[report_mask, TARGET]

    results = {}
    probs_calib = {}
    probs_report = {}

    # --- XGBoost (mismos params que train_baseline.py) ---
    xdf = prep_xgb(train_full, feature_cols)
    Xf, Xc, Xr = xdf.loc[fit_mask, feature_cols], xdf.loc[calib_mask, feature_cols], xdf.loc[report_mask, feature_cols]
    xgb_model = xgb.XGBClassifier(**DEFAULT_PARAMS, tree_method="hist", enable_categorical=True,
                                    eval_metric="logloss", early_stopping_rounds=30, random_state=42)
    xgb_model.fit(Xf, y_fit, eval_set=[(Xc, y_calib)], verbose=False)
    probs_calib["xgb"] = xgb_model.predict_proba(Xc)[:, 1]
    probs_report["xgb"] = xgb_model.predict_proba(Xr)[:, 1]

    # --- LightGBM ---
    ldf = prep_lgb(train_full, feature_cols)
    Lf, Lc, Lr = ldf.loc[fit_mask, feature_cols], ldf.loc[calib_mask, feature_cols], ldf.loc[report_mask, feature_cols]
    lgb_model = lgb.LGBMClassifier(
        n_estimators=800, max_depth=-1, num_leaves=64, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8, min_child_samples=30, reg_lambda=5.0,
        random_state=42, verbosity=-1,
    )
    lgb_model.fit(Lf, y_fit, eval_set=[(Lc, y_calib)],
                  callbacks=[lgb.early_stopping(40, verbose=False)],
                  categorical_feature=CAT_COLS)
    probs_calib["lgb"] = lgb_model.predict_proba(Lc)[:, 1]
    probs_report["lgb"] = lgb_model.predict_proba(Lr)[:, 1]

    # --- CatBoost ---
    cdf = prep_cb(train_full, feature_cols)
    Cf, Cc, Cr = cdf.loc[fit_mask, feature_cols], cdf.loc[calib_mask, feature_cols], cdf.loc[report_mask, feature_cols]
    cat_idx = [feature_cols.index(c) for c in CAT_COLS]
    cb_model = cb.CatBoostClassifier(
        iterations=1200, depth=7, learning_rate=0.04, l2_leaf_reg=5.0,
        cat_features=cat_idx, random_state=42, verbose=False,
        early_stopping_rounds=50, eval_metric="Logloss",
    )
    cb_model.fit(Cf, y_fit, eval_set=(Cc, y_calib))
    probs_calib["cb"] = cb_model.predict_proba(Cc)[:, 1]
    probs_report["cb"] = cb_model.predict_proba(Cr)[:, 1]

    # --- Evaluar cada modelo individual (umbral calibrado en CALIB, reportado en REPORT) ---
    for name in ["xgb", "lgb", "cb"]:
        t, f1_c = best_threshold(y_calib, probs_calib[name])
        f1_r = f1_score(y_report, (probs_report[name] >= t).astype(int))
        auc_r = roc_auc_score(y_report, probs_report[name])
        results[name] = {"threshold": t, "f1_calib": f1_c, "f1_report": f1_r, "auc_report": auc_r}
        print(f"{name:6s} | umbral={t:.2f} | F1 calib={f1_c:.4f} | F1 report={f1_r:.4f} | AUC report={auc_r:.4f}")

    # --- Ensambles: promedio simple de probabilidades ---
    combos = [("xgb", "lgb"), ("xgb", "cb"), ("lgb", "cb"), ("xgb", "lgb", "cb")]
    for combo in combos:
        name = "+".join(combo)
        blend_calib = np.mean([probs_calib[m] for m in combo], axis=0)
        blend_report = np.mean([probs_report[m] for m in combo], axis=0)
        t, f1_c = best_threshold(y_calib, blend_calib)
        f1_r = f1_score(y_report, (blend_report >= t).astype(int))
        auc_r = roc_auc_score(y_report, blend_report)
        results[name] = {"threshold": t, "f1_calib": f1_c, "f1_report": f1_r, "auc_report": auc_r}
        print(f"{name:14s} | umbral={t:.2f} | F1 calib={f1_c:.4f} | F1 report={f1_r:.4f} | AUC report={auc_r:.4f}")

    best_name = max(results, key=lambda k: results[k]["f1_report"])
    print(f"\nMejor combinación por F1 report: {best_name} -> {results[best_name]}")

    with open(f"{MODELS}/ensemble_comparison.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
