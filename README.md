# Prueba Analítica Bancolombia — Propensión a Opciones de Pago + Sistema Agéntico

Repositorio para la prueba analítica: (1) modelo de propensión a la aceptación de
opciones de pago con prácticas de MLOps, y (2) prototipo de sistema agéntico para
gestión proactiva/reactiva de clientes en mora.

## Estructura del repositorio

```
data/                  Datos (raw/ no versionado; ver data/README.md)
  raw/                 Archivos entregados por el banco
  interim/             Datos intermedios de limpieza/unión
  processed/           Datasets de train/valid/test/oot listos para modelar
  submissions/         resultado_prueba.csv y sumisiones históricas (entregable)

notebooks/             Exploración y análisis (EDA, prototipos rápidos)

src/
  ml/                  Parte 1 — pipeline de Machine Learning
    data/              Carga, limpieza, joins de las fuentes crudas
    features/          Ingeniería de variables
    training/          Entrenamiento, validación, tracking (MLflow)
    inference/         Scoring / generación de resultado_prueba.csv
    monitoring/         Drift de datos/modelo, métricas en producción
  agents/              Parte 2 — sistema agéntico
    graph/             Definición del grafo de agentes (LangGraph)
    tools/             Herramientas (consulta elegibilidad, políticas, CRM simulado)
    policies/          Reglas de negocio de elegibilidad y escalamiento

tests/
  ml/                  Pruebas del pipeline analítico
  agents/              Pruebas funcionales/integración/seguridad/robustez de agentes

docs/
  tecnico/             Documento técnico (máx. 4000 caracteres)
  arquitectura/        Diagramas y propuesta de arquitectura de producción
  presentacion/        Material de apoyo para la sustentación ejecutiva

configs/               Configuración (hiperparámetros, umbrales, rutas) — sin secretos
mlruns/                Tracking local de MLflow (no versionado)
```

## Entregables mapeados a este repo

1. **Documento técnico** → `docs/tecnico/`
2. **Presentación ejecutiva** → `docs/presentacion/` (material de apoyo; no se entrega el .pptx)
3. **Archivo de resultados** (`resultado_prueba.csv`) → `data/submissions/`
4. **Código y repositorio** → todo este repo
5. **Arquitectura y operación en producción** → `docs/arquitectura/`

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
