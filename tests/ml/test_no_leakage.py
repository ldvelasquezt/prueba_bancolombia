"""
Pruebas de integración sobre los datasets ya construidos
(`data/processed/train_full.parquet` y `oot_full.parquet`). Se saltan
(`skip`, no fallan) si esos archivos no existen -- dependen de los datos
crudos del banco, que no se versionan (ver data/README.md). En un entorno con
los datos, corren `python -m src.ml.data.build_dataset` primero.
"""
import os

import pandas as pd
import pytest

from src.ml.data.build_dataset import GESTION_COLS, ID_COLS, RESULTADO_ALT_COLS, STRUCTURAL_COLS

DATA = "data/processed"

# Columnas crudas contemporáneas al mes que describen (gestión/desenlace del
# PROPIO mes objetivo). Nunca deberían aparecer sin el prefijo lag1_/lag2_ en el
# dataset final -- si aparecen "pelonas", es que se coló una fuga.
COLUMNAS_CONTEMPORANEAS_PROHIBIDAS = set(STRUCTURAL_COLS + GESTION_COLS + RESULTADO_ALT_COLS)

requiere_datos = pytest.mark.skipif(
    not os.path.exists(f"{DATA}/train_full.parquet"),
    reason="data/processed/train_full.parquet no existe (datos crudos no disponibles en este entorno)",
)


@requiere_datos
def test_sin_columnas_contemporaneas_sin_prefijo_lag():
    train = pd.read_parquet(f"{DATA}/train_full.parquet")
    columnas_crudas_presentes = COLUMNAS_CONTEMPORANEAS_PROHIBIDAS & set(train.columns)
    assert not columnas_crudas_presentes, (
        f"Columnas contemporáneas al mes objetivo sin prefijo lag1_/lag2_: {columnas_crudas_presentes}"
    )


@requiere_datos
def test_oot_no_tiene_target():
    oot = pd.read_parquet(f"{DATA}/oot_full.parquet")
    assert "var_rpta_alt" not in oot.columns


@requiere_datos
def test_train_y_oot_comparten_el_mismo_esquema_de_features():
    """El modelo se entrena y se aplica sobre las mismas columnas; si train y
    oot difieren (más allá del target), `predict.py` fallaría o, peor,
    silenciosamente usaría columnas distintas."""
    train = pd.read_parquet(f"{DATA}/train_full.parquet")
    oot = pd.read_parquet(f"{DATA}/oot_full.parquet")
    solo_en_train = set(train.columns) - set(oot.columns)
    assert solo_en_train <= {"var_rpta_alt"}, f"Columnas en train ausentes de oot: {solo_en_train}"


@requiere_datos
def test_id_mas_fecha_es_unico_en_train():
    train = pd.read_parquet(f"{DATA}/train_full.parquet")
    duplicados = train.duplicated(subset=ID_COLS + ["fecha_var_rpta_alt"]).sum()
    assert duplicados == 0, f"{duplicados} filas duplicadas por (obligación, mes) en train_full"


@requiere_datos
def test_id_es_unico_en_oot():
    oot = pd.read_parquet(f"{DATA}/oot_full.parquet")
    duplicados = oot.duplicated(subset=ID_COLS).sum()
    assert duplicados == 0, f"{duplicados} obligaciones duplicadas en oot_full"


@requiere_datos
def test_mes_prev_es_siempre_anterior_a_fecha_var_rpta_alt():
    """Chequeo directo de la regla de negoción: mes_prev debe ser exactamente
    un mes calendario antes de fecha_var_rpta_alt, nunca igual ni posterior."""
    train = pd.read_parquet(f"{DATA}/train_full.parquet")
    y = train["fecha_var_rpta_alt"] // 100
    m = train["fecha_var_rpta_alt"] % 100
    esperado = (y * 100 + m - 1).where(m != 1, (y - 1) * 100 + 12)
    assert (train["mes_prev"] == esperado).all()
