# Prueba Analítica Bancolombia — Propensión a opciones de pago + sistema agéntico

Son dos cosas: un modelo que estima qué tan probable es que un cliente en mora acepte una
opción de pago, y un prototipo de sistema agéntico que gestiona a esos clientes, tanto
cuando el banco los busca como cuando ellos escriben.

## Cómo está organizado

```
data/                  Los datos (raw/ no va a git; mirar data/README.md)
  raw/                 Lo que entregó el banco
  processed/           Train y OOT listos para modelar (tampoco va a git)
  submissions/         resultado_prueba.csv y kaggle_submission.csv
  synthetic/           Perfiles inventados para el prototipo agéntico

notebooks/             Un EDA ligero

models/                El modelo entrenado, feature_config.json y la comparación
                       entre algoritmos

src/
  ml/                  Parte 1 — el pipeline de machine learning
    data/              build_dataset.py: arma las features y une las fuentes
    training/          train_baseline.py (XGBoost) y train_ensemble.py, que lo
                       compara contra LightGBM y CatBoost
    inference/         predict.py y build_kaggle_submission.py
  agents/              Parte 2 — el sistema agéntico
    graph/             El grafo (LangGraph)
    tools/             CRM simulado y wrapper del score de propensión
    policies/          Elegibilidad, priorización (NBA) y guardrails

tests/
  agents/              41 pruebas: reglas de negocio, seguridad e integración
  ml/                  14 pruebas de contrato del dataset: esquema y ausencia de fuga

docs/
  tecnico/             El documento técnico
  arquitectura/        Un documento por cada parte de la prueba

requirements.txt       Dependencias (Python 3.12 con venv)
```

## Dónde queda cada entregable

1. **Documento técnico** → `docs/tecnico/documento_tecnico.md`
2. **Presentación ejecutiva** → va aparte, 16 diapositivas para la sustentación
3. **Archivo de resultados** → `data/submissions/resultado_prueba.csv` con ID,
   var_rpta_alt y Prob_uno. El `kaggle_submission.csv` es lo mismo en el formato de
   `sample_submission.csv`, que es el que se sube a la plataforma
4. **Código y repositorio** → todo esto
5. **Arquitectura y producción** → `docs/arquitectura/`

## Para arrancar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

El detalle del sistema agéntico está en `src/agents/README.md`. Para el pipeline de ML,
los pasos están en los docstrings de cada módulo de `src/ml/`.

## Sobre el uso de IA generativa

Está en el Anexo B de `docs/tecnico/documento_tecnico.md`.
