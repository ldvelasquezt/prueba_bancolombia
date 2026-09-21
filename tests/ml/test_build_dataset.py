"""
Pruebas unitarias del pipeline de features (`src/ml/data/build_dataset.py`),
usando DataFrames sintéticos pequeños (no dependen de los CSV crudos, así que
corren en cualquier entorno, con o sin los datos del banco). El foco es
verificar mecánicamente la regla central del pipeline: ningún feature debe
describir el mismo mes que `var_rpta_alt` (fuga de información).
"""
import pandas as pd

from src.ml.data.build_dataset import (
    ID_COLS, LAG2_COLS, RESULTADO_ALT_COLS, STRUCTURAL_COLS, GESTION_COLS,
    build_lag2, build_lag_struct, next_yyyymm, prev_yyyymm,
)


def test_prev_yyyymm_caso_normal():
    assert prev_yyyymm(pd.Series([202312])).iloc[0] == 202311


def test_prev_yyyymm_cruza_enero():
    """Enero del año actual retrocede a diciembre del año anterior."""
    assert prev_yyyymm(pd.Series([202401])).iloc[0] == 202312


def test_next_yyyymm_caso_normal():
    assert next_yyyymm(pd.Series([202311])).iloc[0] == 202312


def test_next_yyyymm_cruza_diciembre():
    assert next_yyyymm(pd.Series([202312])).iloc[0] == 202401


def _trtest_sintetico() -> pd.DataFrame:
    """Dos obligaciones, dos meses consecutivos cada una, con valores
    distinguibles por mes para poder verificar el desplazamiento (lag)."""
    filas = []
    for nit, oblig in [(1, 100), (2, 200)]:
        for mes, mora, target in [(202309, 30, 0), (202310, 45, 1)]:
            fila = {
                "nit_enmascarado": nit, "num_oblig_orig_enmascarado": oblig,
                "num_oblig_enmascarado": oblig, "fecha_var_rpta_alt": mes,
                "var_rpta_alt": target,
            }
            for c in STRUCTURAL_COLS:
                fila[c] = mora if c == "dias_mora_fin" else f"{c}_{mes}"
            for c in GESTION_COLS:
                fila[c] = mes  # valor numérico para poder rastrear el mes de origen
            for c in RESULTADO_ALT_COLS:
                fila[c] = mes if c in ("pago_mes", "porc_pago_mes") else f"{c}_{mes}"
            fila["veces_en_panel_acumulado"] = 1
            filas.append(fila)
    return pd.DataFrame(filas)


def test_build_lag_struct_desplaza_un_mes_hacia_adelante():
    """La fila de octubre (mes_prev=octubre) debe traer los valores de octubre
    como lag1_*, para ser consumida por el target de noviembre -- nunca los
    valores del propio mes que describe como si fueran del mes siguiente."""
    trtest = _trtest_sintetico()
    lag = build_lag_struct(trtest)

    fila_oct = lag[(lag["nit_enmascarado"] == 1) & (lag["mes_prev"] == 202310)]
    assert len(fila_oct) == 1
    assert fila_oct.iloc[0]["lag1_dias_mora_fin"] == 45  # el valor de octubre, no de sep.
    assert fila_oct.iloc[0]["lag1_var_rpta_alt"] == 1


def test_lag1_var_rpta_alt_es_autocorrelacion_no_fuga():
    """El target de una fila (mes M) nunca debe aparecer como lag1_var_rpta_alt
    para ESE MISMO mes M -- solo para el mes M+1 (el siguiente)."""
    trtest = _trtest_sintetico()
    lag = build_lag_struct(trtest)

    # mes_prev en `lag` es el mes que la fila describe (antes M+1); no debe haber
    # ninguna fila con mes_prev == fecha_var_rpta_alt original, mezclando target
    # del mismo mes.
    fila_sep = lag[(lag["nit_enmascarado"] == 1) & (lag["mes_prev"] == 202309)]
    assert fila_sep.iloc[0]["lag1_var_rpta_alt"] == 0  # target de septiembre, no de octubre


def test_build_lag2_retrocede_dos_meses():
    """lag2 en mes_prev=X describe el mes X-1 (build_lag2 recorre lag_struct un
    mes hacia adelante); al fusionarse con un target cuyo mes_prev es X, lag2
    aporta el mes X-1 = dos meses antes del target (M-2)."""
    trtest = _trtest_sintetico()
    lag_struct = build_lag_struct(trtest)
    lag2 = build_lag2(lag_struct)

    # La fila de lag_struct para octubre (mes_prev=202310, mora=45) se recorre un
    # mes hacia adelante -> aparece en lag2 con mes_prev=202311.
    fila = lag2[(lag2["nit_enmascarado"] == 1) & (lag2["mes_prev"] == 202311)]
    assert len(fila) == 1
    assert fila.iloc[0]["lag2_dias_mora_fin"] == 45  # mora de octubre
    assert fila.iloc[0]["lag2_var_rpta_alt"] == 1  # target de octubre


def test_todas_las_columnas_de_lag2_estan_en_lag2_cols():
    """LAG2_COLS debe ser subconjunto de las columnas que build_lag_struct lagea,
    o build_lag2 fallaría con KeyError -- lo dejamos explícito como regla."""
    lag_cols_disponibles = set(STRUCTURAL_COLS + GESTION_COLS + RESULTADO_ALT_COLS
                                + ["veces_en_panel_acumulado", "var_rpta_alt"])
    assert set(LAG2_COLS).issubset(lag_cols_disponibles)
