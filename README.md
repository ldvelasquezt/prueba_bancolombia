# Prueba Analítica Bancolombia — Propensión a Opciones de Pago + Sistema Agéntico

Repositorio para la prueba analítica: (1) modelo de propensión a la aceptación de
opciones de pago con prácticas de MLOps, y (2) prototipo de sistema agéntico para
gestión proactiva/reactiva de clientes en mora.

## Estructura del repositorio

```
data/                  Datos (raw/ no versionado; ver data/README.md)
  raw/                 Archivos entregados por el banco
  processed/           Datasets de train/oot listos para modelar (no versionado)
  submissions/         resultado_prueba.csv (entregable), kaggle_submission.csv
  synthetic/           Perfiles sintéticos para el prototipo agéntico

notebooks/             EDA ligero

models/                Modelo entrenado (xgb_baseline.json), feature_config.json,
                       comparación de modelos (ensemble_comparison.json)

src/
  ml/                  Parte 1 — pipeline de Machine Learning
    data/              build_dataset.py: features sin fuga, joins de fuentes crudas
    training/          train_baseline.py (XGBoost), train_ensemble.py (comparación
                       contra LightGBM/CatBoost)
    inference/         predict.py (resultado_prueba.csv), build_kaggle_submission.py
  agents/              Parte 2 — sistema agéntico
    graph/             Grafo de agentes (LangGraph)
    tools/             CRM simulado, wrapper de propensión
    policies/          Reglas de elegibilidad, priorización (NBA) y guardrails

tests/
  agents/              41 pruebas: reglas de negocio, seguridad, integración end-to-end
  ml/                  Pendiente (ver docs/tecnico/ — riesgo declarado, no oculto)

docs/
  tecnico/             Documento técnico (máx. 4000 caracteres + anexos)
  arquitectura/        mlops_produccion.md (Parte 1) y sistema_agentico.md (Parte 2)

requirements.txt       Dependencias (Python 3.12 + venv)
```

## Entregables mapeados a este repo

1. **Documento técnico** → `docs/tecnico/documento_tecnico.md`
2. **Presentación ejecutiva** → Artifact separado (deck de 16 diapositivas, 15 min);
   no se entrega el .pptx, se usa en la sustentación
3. **Archivo de resultados** → `data/submissions/resultado_prueba.csv` (ID, var_rpta_alt,
   Prob_uno); `data/submissions/kaggle_submission.csv` es el mismo resultado en el
   formato exacto de `sample_submission.csv` (solo ID, var_rpta_alt) para subir a la
   plataforma de calificación
4. **Código y repositorio** → todo este repo
5. **Arquitectura y operación en producción** → `docs/arquitectura/` (dos documentos:
   uno por cada parte de la prueba)

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Los pasos concretos de cada pipeline (preparación de datos, entrenamiento, inferencia,
grafo de agentes) se documentan en el README de cada subcarpeta de `src/` a medida que
se implementan.

## Declaración de uso de IA generativa

Ver `docs/tecnico/` — se documentará explícitamente en qué fases se usó IA generativa
(código, arquitectura, documentación, pruebas, ideación) y qué decisiones fueron
tomadas directamente por el candidato.
