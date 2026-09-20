"""
EDA ligero — solo lo esencial para entender la variable respuesta, el balance de
clases, nulos clave y la viabilidad de los joins. No es un análisis exhaustivo.
"""
import pandas as pd

RAW = "../data/raw"

# 1) Variable respuesta y balance de clases (trtest)
usecols_trtest = [
    "nit_enmascarado", "num_oblig_orig_enmascarado", "num_oblig_enmascarado",
    "fecha_var_rpta_alt", "var_rpta_alt", "banca", "segmento", "producto",
    "min_mora", "max_mora", "dias_mora_fin", "cant_alter_posibles",
]
df = pd.read_csv(f"{RAW}/prueba_op_base_pivot_var_rpta_alt_enmascarado_trtest.csv",
                  usecols=usecols_trtest)

print("=== Shape trtest ===")
print(df.shape)

print("\n=== Balance de clases (var_rpta_alt) ===")
print(df["var_rpta_alt"].value_counts(normalize=True))

print("\n=== Rango de fechas (fecha_var_rpta_alt) ===")
print(sorted(df["fecha_var_rpta_alt"].unique()))

print("\n=== Nulos en columnas clave ===")
print(df[usecols_trtest].isna().mean().sort_values(ascending=False))

print("\n=== Distribución cant_alter_posibles (máx 3 opciones/mes) ===")
print(df["cant_alter_posibles"].value_counts().sort_index())

# 2) Muestra OOT (a calificar) — mismo grano, sin var_rpta_alt
oot = pd.read_csv(f"{RAW}/prueba_op_base_pivot_var_rpta_alt_enmascarado_oot.csv")
print("\n=== Shape OOT ===")
print(oot.shape)
print(oot["fecha_var_rpta_alt"].unique())

# 3) Viabilidad de join con la tabla de probabilidades existentes (score del banco)
prob_cols = ["nit_enmascarado", "num_oblig_enmascarado", "fecha_corte"]
prob = pd.read_csv(f"{RAW}/prueba_op_probabilidad_oblig_base_hist_enmascarado_completa.csv",
                    usecols=prob_cols, nrows=2_000_000)
merged_check = df.merge(
    prob, on=["nit_enmascarado", "num_oblig_enmascarado"], how="left", indicator=True
)
print("\n=== Cobertura de join trtest <-> prob (muestra 2M filas de prob) ===")
print(merged_check["_merge"].value_counts(normalize=True))

# 4) Sample submission — confirmar formato de ID
sample = pd.read_csv(f"{RAW}/sample_submission.csv")
print("\n=== Sample submission ===")
print(sample.head())
print(sample.shape)
