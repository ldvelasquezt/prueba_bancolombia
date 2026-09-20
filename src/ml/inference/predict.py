"""
Genera resultado_prueba.csv para la muestra OOT (enero 2024) usando el modelo
baseline y el umbral calibrados en train_baseline.py.
"""
import json

import numpy as np
import pandas as pd
import xgboost as xgb

DATA = "data/processed"
MODELS = "models"
OUT = "data/submissions"


def main():
    with open(f"{MODELS}/feature_config.json") as f:
        config = json.load(f)
    feature_cols = config["feature_cols"]
    cat_cols = config["cat_cols"]
    cat_categories = config["cat_categories"]
    threshold = config["threshold"]

    model = xgb.XGBClassifier()
    model.load_model(f"{MODELS}/xgb_baseline.json")

    oot = pd.read_parquet(f"{DATA}/oot_full.parquet")

    for c in cat_cols:
        oot[c] = oot[c].fillna("MISSING")
        categories = cat_categories[c]
        oot.loc[~oot[c].isin(categories), c] = "MISSING"
        oot[c] = pd.Categorical(oot[c], categories=categories)
    num_cols = oot.select_dtypes(include=["float64", "int64"]).columns
    oot[num_cols] = oot[num_cols].replace([np.inf, -np.inf], np.nan)

    X_oot = oot[feature_cols]
    prob_uno = model.predict_proba(X_oot)[:, 1]
    var_rpta_alt = (prob_uno >= threshold).astype(int)

    submission = pd.DataFrame({
        "ID": (
            oot["nit_enmascarado"].astype(str) + "#" +
            oot["num_oblig_orig_enmascarado"].astype(str) + "#" +
            oot["num_oblig_enmascarado"].astype(str)
        ),
        "var_rpta_alt": var_rpta_alt,
        "Prob_uno": prob_uno.round(5),
    })

    import os
    os.makedirs(OUT, exist_ok=True)
    submission.to_csv(f"{OUT}/resultado_prueba.csv", index=False, encoding="utf-8")

    print(f"Sumisión generada: {OUT}/resultado_prueba.csv ({submission.shape[0]} filas)")
    print(submission["var_rpta_alt"].value_counts(normalize=True))
    print(submission.head())


if __name__ == "__main__":
    main()
