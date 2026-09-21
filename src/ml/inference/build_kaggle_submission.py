"""
Genera el archivo de sumisión en el formato exacto de la competencia (Kaggle o
plataforma equivalente): solo `ID,var_rpta_alt`, igual que sample_submission.csv.
El entregable formal (resultado_prueba.csv) sí incluye Prob_uno; este archivo es
específicamente para subir a la plataforma de calificación.
"""
import pandas as pd

DATA = "data/submissions"
RAW = "data/raw"


def main():
    resultado = pd.read_csv(f"{DATA}/resultado_prueba.csv")
    sample = pd.read_csv(f"{RAW}/sample_submission.csv")

    assert len(resultado) == len(sample), (
        f"Conteo de filas no coincide: resultado={len(resultado)} sample={len(sample)}"
    )
    assert set(resultado["ID"]) == set(sample["ID"]), "Los IDs no coinciden con sample_submission.csv"

    kaggle = resultado[["ID", "var_rpta_alt"]].copy()
    # Mismo orden que sample_submission.csv, por prolijidad (no es requisito, pero evita dudas)
    kaggle = kaggle.set_index("ID").loc[sample["ID"]].reset_index()

    kaggle.to_csv(f"{DATA}/kaggle_submission.csv", index=False, encoding="utf-8")
    print(f"kaggle_submission.csv generado: {kaggle.shape[0]} filas")
    print(kaggle.head())
    print(kaggle["var_rpta_alt"].value_counts(normalize=True))


if __name__ == "__main__":
    main()
