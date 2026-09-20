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
construyen exclusivamente con información de meses ANTERIORES (M-1, M-2, M-3):
  - Los propios atributos "estructurales" de la obligación se obtienen
    reutilizando `trtest` como fuente histórica (la fila de la obligación en el
    mes M-1 aporta su mora/saldo/producto de esa fecha, ya conocidos al cierre
    de M-1). Para el mes M-1=diciembre 2023 (mes_prev del OOT), esta info
    también está disponible en `trtest`, que cubre hasta esa fecha.
  - Scores existentes del banco (`probabilidad_oblig_base_hist`) y
    comportamiento de pago (`maestra_cuotas_pagos_mes_hist`): además del valor
    de M-1, se agregan promedios móviles de 3 meses y tendencia (M-1 vs M-3)
    para capturar deterioro/mejora reciente, no solo el último corte.
  - Perfil del cliente (`master_customer_data`), anclado al snapshot más
    reciente disponible en o antes de M-1.
"""
import pandas as pd

RAW = "data/raw"
OUT = "data/processed"

ID_COLS = ["nit_enmascarado", "num_oblig_orig_enmascarado", "num_oblig_enmascarado"]
ID_COLS_SHORT = ["nit_enmascarado", "num_oblig_enmascarado"]

# Columnas "estructurales" de trtest, reutilizadas SOLO como fuente de lag (mes M-1)
STRUCTURAL_COLS = [
    "banca", "segmento", "producto", "producto_cons", "aplicativo",
    "min_mora", "max_mora", "dias_mora_fin", "rango_mora",
    "vlr_obligacion", "vlr_vencido", "saldo_capital", "endeudamiento",
    "cant_alter_posibles",
    "alter_posible1_2", "alter_posible2_2", "alter_posible3_2",
]

PROB_VALUE_COLS = ["prob_propension", "prob_alrt_temprana", "prob_auto_cura"]
CUOTAS_VALUE_COLS = ["porc_pago", "pago_total"]

CUSTOMER_COLS = ["nit_enmascarado", "genero_cli", "edad_cli", "estado_civil",
                  "tipo_vivienda", "num_hijos", "personas_dependientes",
                  "nivel_academico", "ocup", "sector", "declarante",
                  "total_ing", "tot_activos", "tot_pasivos", "egresos_mes",
                  "tot_patrimonio", "smmlv", "year", "month"]


def prev_yyyymm(x: pd.Series) -> pd.Series:
    y = x // 100
    m = x % 100
    return (y * 100 + m - 1).where(m != 1, (y - 1) * 100 + 12)


def next_yyyymm(x: pd.Series) -> pd.Series:
    y = x // 100
    m = x % 100
    return (y * 100 + m + 1).where(m != 12, (y + 1) * 100 + 1)


def build_lag_struct(trtest_full: pd.DataFrame) -> pd.DataFrame:
    """Usa cada fila de trtest como fuente de lag estructural para el mes siguiente."""
    lag = trtest_full[ID_COLS + ["fecha_var_rpta_alt"] + STRUCTURAL_COLS].copy()
    lag = lag.rename(columns={"fecha_var_rpta_alt": "mes_prev"})
    lag = lag.rename(columns={c: f"lag1_{c}" for c in STRUCTURAL_COLS})
    lag = lag.drop_duplicates(subset=ID_COLS + ["mes_prev"], keep="last")
    return lag


def build_mora_trend(lag_struct: pd.DataFrame) -> pd.DataFrame:
    """lag2_dias_mora_fin: la misma tabla de lag, recorrida para describir el mes
    mes_prev-1, y así poder calcular la tendencia de la mora entre mes_prev y mes_prev-1."""
    lag2 = lag_struct[ID_COLS + ["mes_prev", "lag1_dias_mora_fin"]].copy()
    lag2 = lag2.rename(columns={"lag1_dias_mora_fin": "lag2_dias_mora_fin"})
    lag2["mes_prev"] = next_yyyymm(lag2["mes_prev"])  # esta fila describe mes_prev-1 del target
    lag2 = lag2.drop_duplicates(subset=ID_COLS + ["mes_prev"], keep="last")
    return lag2


def load_hist_with_rolling(path: str, date_col: str, date_is_yyyymmdd: bool,
                            value_cols: list[str], id_keys: pd.DataFrame,
                            exact_rename: dict, prefix: str,
                            passthrough_rename: dict | None = None) -> pd.DataFrame:
    """Carga una tabla histórica (prob o cuotas) UNA sola vez, filtra a las
    obligaciones relevantes y devuelve, por (ids, mes_prev):
      - el valor exacto del mes (renombrado según `exact_rename`)
      - el promedio móvil de 3 meses y la tendencia (mes_prev vs mes_prev-2)
      - columnas de paso directo sin promediar (p.ej. categóricas como marca_pago),
        vía `passthrough_rename`
    """
    passthrough_rename = passthrough_rename or {}
    usecols = ID_COLS_SHORT + [date_col] + value_cols + list(passthrough_rename.keys())
    hist = pd.read_csv(f"{RAW}/{path}", usecols=usecols)
    if date_is_yyyymmdd:
        hist[date_col] = hist[date_col] // 100
    hist = hist.rename(columns={date_col: "mes_prev"})

    hist = hist.merge(id_keys, on=ID_COLS_SHORT, how="inner")
    hist = hist.drop_duplicates(subset=ID_COLS_SHORT + ["mes_prev"], keep="last")
    hist = hist.sort_values(ID_COLS_SHORT + ["mes_prev"]).reset_index(drop=True)

    # Nota de rendimiento: groupby().transform(lambda ...) es extremadamente lento en
    # tablas de varios millones de filas (invoca la lambda por cada grupo). Se usa en su
    # lugar groupby().rolling()/.shift() vectorizados en C, ~100x más rápido aquí.
    g = hist.groupby(ID_COLS_SHORT, sort=False)
    n_id_levels = len(ID_COLS_SHORT)
    for c in value_cols:
        roll = g[c].rolling(3, min_periods=1).mean()
        hist[f"{prefix}_{c}_roll3m"] = roll.droplevel(list(range(n_id_levels))).reindex(hist.index)
        hist[f"{prefix}_{c}_trend2m"] = hist[c] - g[c].shift(2)

    hist = hist.rename(columns={**exact_rename, **passthrough_rename})
    keep = ID_COLS_SHORT + ["mes_prev"] + list(exact_rename.values()) + list(passthrough_rename.values())
    keep += [f"{prefix}_{c}_roll3m" for c in value_cols] + [f"{prefix}_{c}_trend2m" for c in value_cols]
    return hist[keep]


def enrich(df: pd.DataFrame, lag_struct: pd.DataFrame, mora_trend: pd.DataFrame,
           prob_hist: pd.DataFrame, cuotas_hist: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(lag_struct, on=ID_COLS + ["mes_prev"], how="left")
    # La obligación no aparecía en trtest el mes anterior: puede indicar que apenas
    # entró en mora, o que no estaba en gestión directa/aliados el mes pasado. Se
    # deja como señal explícita en vez de dejarlo como nulo "silencioso".
    df["obligacion_nueva_en_panel"] = df["lag1_dias_mora_fin"].isna().astype(int)

    df = df.merge(mora_trend, on=ID_COLS + ["mes_prev"], how="left")
    df["mora_trend_1m"] = df["lag1_dias_mora_fin"] - df["lag2_dias_mora_fin"]

    df = df.merge(prob_hist, on=ID_COLS_SHORT + ["mes_prev"], how="left")
    df = df.merge(cuotas_hist, on=ID_COLS_SHORT + ["mes_prev"], how="left")

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
    mora_trend = build_mora_trend(lag_struct)

    train = trtest_full[ID_COLS + ["fecha_var_rpta_alt", "var_rpta_alt"]].copy()
    train["mes_prev"] = prev_yyyymm(train["fecha_var_rpta_alt"])

    oot = pd.read_csv(f"{RAW}/prueba_op_base_pivot_var_rpta_alt_enmascarado_oot.csv",
                       usecols=ID_COLS + ["fecha_var_rpta_alt"])
    oot["mes_prev"] = prev_yyyymm(oot["fecha_var_rpta_alt"])

    id_keys = pd.concat([train[ID_COLS_SHORT], oot[ID_COLS_SHORT]]).drop_duplicates()

    prob_hist = load_hist_with_rolling(
        "prueba_op_probabilidad_oblig_base_hist_enmascarado_completa.csv",
        date_col="fecha_corte", date_is_yyyymmdd=False,
        value_cols=PROB_VALUE_COLS, id_keys=id_keys,
        exact_rename={c: c for c in PROB_VALUE_COLS}, prefix="prob",
    )
    cuotas_hist = load_hist_with_rolling(
        "prueba_op_maestra_cuotas_pagos_mes_hist_enmascarado_completa.csv",
        date_col="fecha_corte", date_is_yyyymmdd=True,
        value_cols=CUOTAS_VALUE_COLS, id_keys=id_keys,
        exact_rename={"porc_pago": "prevmes_porc_pago", "pago_total": "prevmes_pago_total"},
        prefix="cuotas",
        passthrough_rename={"valor_cuota_mes": "prevmes_valor_cuota", "marca_pago": "prevmes_marca_pago"},
    )

    train = enrich(train, lag_struct, mora_trend, prob_hist, cuotas_hist)
    oot = enrich(oot, lag_struct, mora_trend, prob_hist, cuotas_hist)

    # El primer mes de trtest (agosto 2023) no tiene mes anterior disponible -> se descarta
    n_before = len(train)
    train = train[train["fecha_var_rpta_alt"] != train["fecha_var_rpta_alt"].min()].reset_index(drop=True)
    print(f"Filas descartadas por no tener mes_prev disponible (primer mes): {n_before - len(train)}")

    print("\nCobertura de nulos tras los merges (train):")
    print(train.isna().mean().sort_values(ascending=False).head(20))

    train.to_parquet(f"{OUT}/train_full.parquet", index=False)
    oot.to_parquet(f"{OUT}/oot_full.parquet", index=False)
    print(f"\ntrain_full: {train.shape} -> {OUT}/train_full.parquet")
    print(f"oot_full:   {oot.shape} -> {OUT}/oot_full.parquet")


if __name__ == "__main__":
    main()
