"""
Construye el dataset de modelamiento evitando fuga de información.

Dos hallazgos clave:

1. En `prueba_op_base_pivot_var_rpta_alt_enmascarado_trtest.csv`, columnas como
   `cant_gestiones`, `rpc`, `promesas_cumplidas`, `pago_mes`, `marca_alt_rank`,
   e incluso las "estructurales" (mora, saldo, producto, opciones preaprobadas)
   son CONTEMPORÁNEAS al mes de `var_rpta_alt`: describen la obligación durante
   el mismo mes que se quiere pronosticar.
2. El archivo OOT (`..._oot.csv`) confirma que esta info contemporánea NO está
   disponible al momento de calificar: solo trae los IDs y el mes objetivo.

Por lo tanto todos los features —estructurales y de comportamiento— se
construyen exclusivamente con información del mes ANTERIOR (M-1):
  - Los propios atributos "estructurales" de la obligación se obtienen
    reutilizando `trtest` como fuente histórica (la fila de la obligación en el
    mes M-1 aporta su mora/saldo/producto de esa fecha, ya conocidos al cierre
    de M-1). Para el mes M-1=diciembre 2023 (mes_prev del OOT), esta info
    también está disponible en `trtest`, que cubre hasta esa fecha.
  - Scores existentes del banco (`probabilidad_oblig_base_hist`), comportamiento
    de pago (`maestra_cuotas_pagos_mes_hist`) y perfil del cliente
    (`master_customer_data`), todos anclados al mes M-1.
"""
import pandas as pd

RAW = "data/raw"
OUT = "data/processed"

ID_COLS = ["nit_enmascarado", "num_oblig_orig_enmascarado", "num_oblig_enmascarado"]

# Columnas "estructurales" de trtest, reutilizadas SOLO como fuente de lag (mes M-1)
STRUCTURAL_COLS = [
    "banca", "segmento", "producto", "producto_cons", "aplicativo",
    "min_mora", "max_mora", "dias_mora_fin", "rango_mora",
    "vlr_obligacion", "vlr_vencido", "saldo_capital", "endeudamiento",
    "cant_alter_posibles",
    "alter_posible1_2", "alter_posible2_2", "alter_posible3_2",
]

PROB_COLS = ["nit_enmascarado", "num_oblig_enmascarado", "fecha_corte",
             "lote", "prob_propension", "prob_alrt_temprana", "prob_auto_cura"]

CUOTAS_COLS = ["nit_enmascarado", "num_oblig_enmascarado", "fecha_corte",
               "valor_cuota_mes", "pago_total", "porc_pago", "marca_pago"]

CUSTOMER_COLS = ["nit_enmascarado", "genero_cli", "edad_cli", "estado_civil",
                  "tipo_vivienda", "num_hijos", "personas_dependientes",
                  "nivel_academico", "ocup", "sector", "declarante",
                  "total_ing", "tot_activos", "tot_pasivos", "egresos_mes",
                  "tot_patrimonio", "smmlv", "year", "month"]


def prev_yyyymm(x: pd.Series) -> pd.Series:
    y = x // 100
    m = x % 100
    return (y * 100 + m - 1).where(m != 1, (y - 1) * 100 + 12)


def build_lag_struct(trtest_full: pd.DataFrame) -> pd.DataFrame:
    """Usa cada fila de trtest como fuente de lag estructural para el mes siguiente."""
    lag = trtest_full[ID_COLS + ["fecha_var_rpta_alt"] + STRUCTURAL_COLS].copy()
    lag = lag.rename(columns={"fecha_var_rpta_alt": "mes_prev"})
    lag = lag.rename(columns={c: f"lag1_{c}" for c in STRUCTURAL_COLS})
    lag = lag.drop_duplicates(subset=ID_COLS + ["mes_prev"], keep="last")
    return lag


def enrich(df: pd.DataFrame, lag_struct: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(lag_struct, on=ID_COLS + ["mes_prev"], how="left")
    # La obligación no aparecía en trtest el mes anterior: puede indicar que apenas
    # entró en mora, o que no estaba en gestión directa/aliados el mes pasado. Se
    # deja como señal explícita en vez de dejarlo como nulo "silencioso".
    df["obligacion_nueva_en_panel"] = df["lag1_dias_mora_fin"].isna().astype(int)

    prob = pd.read_csv(f"{RAW}/prueba_op_probabilidad_oblig_base_hist_enmascarado_completa.csv",
                        usecols=PROB_COLS)
    prob = prob.rename(columns={"fecha_corte": "mes_prev"})
    prob = prob.drop_duplicates(subset=["nit_enmascarado", "num_oblig_enmascarado", "mes_prev"], keep="last")
    df = df.merge(prob, on=["nit_enmascarado", "num_oblig_enmascarado", "mes_prev"], how="left")

    cuotas = pd.read_csv(f"{RAW}/prueba_op_maestra_cuotas_pagos_mes_hist_enmascarado_completa.csv",
                          usecols=CUOTAS_COLS)
    # fecha_corte viene en formato YYYYMMDD en esta tabla (a diferencia de YYYYMM en las demás)
    cuotas["fecha_corte"] = cuotas["fecha_corte"] // 100
    cuotas = cuotas.rename(columns={
        "fecha_corte": "mes_prev",
        "valor_cuota_mes": "prevmes_valor_cuota",
        "pago_total": "prevmes_pago_total",
        "porc_pago": "prevmes_porc_pago",
        "marca_pago": "prevmes_marca_pago",
    })
    cuotas = cuotas.drop_duplicates(subset=["nit_enmascarado", "num_oblig_enmascarado", "mes_prev"], keep="last")
    df = df.merge(cuotas, on=["nit_enmascarado", "num_oblig_enmascarado", "mes_prev"], how="left")

    # master_customer_data no refresca a todos los clientes cada mes (~30% de la base
    # por corte), así que un merge exacto por mes deja ~76% de nulos. En su lugar se usa
    # un join "as of": el snapshot más reciente disponible en o antes de mes_prev, que
    # sigue sin usar ninguna información posterior al mes que se pronostica.
    customer = pd.read_csv(f"{RAW}/prueba_op_master_customer_data_enmascarado_completa.csv",
                            usecols=CUSTOMER_COLS)
    customer["mes_prev"] = customer["year"] * 100 + customer["month"]
    customer = customer.drop(columns=["year", "month"]).drop_duplicates(
        subset=["nit_enmascarado", "mes_prev"], keep="last"
    )
    customer = customer.sort_values("mes_prev")
    df = df.sort_values("mes_prev")
    df = pd.merge_asof(df, customer, on="mes_prev", by="nit_enmascarado", direction="backward")

    df["prevmes_endeudamiento_ratio"] = df["tot_pasivos"] / df["total_ing"].replace(0, pd.NA)
    df["lag1_vencido_sobre_obligacion"] = df["lag1_vlr_vencido"] / df["lag1_vlr_obligacion"].replace(0, pd.NA)

    return df


def main():
    trtest_full = pd.read_csv(
        f"{RAW}/prueba_op_base_pivot_var_rpta_alt_enmascarado_trtest.csv",
        usecols=ID_COLS + ["fecha_var_rpta_alt", "var_rpta_alt"] + STRUCTURAL_COLS,
    )
    lag_struct = build_lag_struct(trtest_full)

    train = trtest_full[ID_COLS + ["fecha_var_rpta_alt", "var_rpta_alt"]].copy()
    train["mes_prev"] = prev_yyyymm(train["fecha_var_rpta_alt"])

    oot = pd.read_csv(f"{RAW}/prueba_op_base_pivot_var_rpta_alt_enmascarado_oot.csv",
                       usecols=ID_COLS + ["fecha_var_rpta_alt"])
    oot["mes_prev"] = prev_yyyymm(oot["fecha_var_rpta_alt"])

    train = enrich(train, lag_struct)
    oot = enrich(oot, lag_struct)

    # El primer mes de trtest (agosto 2023) no tiene mes anterior disponible -> se descarta
    n_before = len(train)
    train = train[train["fecha_var_rpta_alt"] != train["fecha_var_rpta_alt"].min()].reset_index(drop=True)
    print(f"Filas descartadas por no tener mes_prev disponible (primer mes): {n_before - len(train)}")

    print("\nCobertura de nulos tras los merges (train):")
    print(train.isna().mean().sort_values(ascending=False).head(15))

    train.to_parquet(f"{OUT}/train_full.parquet", index=False)
    oot.to_parquet(f"{OUT}/oot_full.parquet", index=False)
    print(f"\ntrain_full: {train.shape} -> {OUT}/train_full.parquet")
    print(f"oot_full:   {oot.shape} -> {OUT}/oot_full.parquet")


if __name__ == "__main__":
    main()
