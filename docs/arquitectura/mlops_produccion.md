# Arquitectura de producción — Parte 1 (Modelo de propensión)

Propuesta de alto nivel de cómo operaría el pipeline analítico en producción.
**Nada de esto está implementado** en el prototipo — es la propuesta de
operación, tal como pide el enunciado.

## 1. Vista general del ciclo

```
Datos crudos (core bancario, CRM, buró)
        │
        ▼
  [1] Preparación de datos ── job batch mensual
        │
        ▼
  [2] Feature store ── snapshot congelado del mes M-1
        │
        ▼
  [3] Entrenamiento / reentrenamiento ── trigger por drift o calendario
        │
        ▼
  [4] Registro de modelos ── versión, métricas, aprobación
        │
        ▼
  [5] Servicio de inferencia ── batch mensual + fallback on-demand
        │
        ▼
  [6] Consumo ── priorización por lotes + sistema agéntico (Parte 2)
        │
        ▼
  [7] Monitoreo ── drift, deriva de negocio, alertas
        │ (retroalimenta al paso 3)
```

## 2. Preparación de datos (equivalente productivo de `build_dataset.py`)

- **Orquestación**: job batch mensual (Airflow/Databricks Jobs/similar),
  disparado al cierre contable del mes, no antes — el pipeline depende de que
  M-1 esté cerrado (mora, pagos, gestión consolidados).
- **Feature store**: las features construidas (`lag1_*`, `prob_*_roll6m`,
  `lag1_var_rpta_alt`, etc.) se materializan versionadas por mes de corte, no
  se recalculan on-the-fly en cada scoring. Esto permite auditar exactamente
  qué datos vio el modelo en cada corrida, y reproducir un incidente.
- **Validación de esquema y de fuga**: antes de que el pipeline avance al
  entrenamiento, un test automatizado (ver `tests/ml/`, hoy pendiente de
  implementar) verifica que ninguna columna con fecha de corte posterior o
  igual al mes objetivo entre al feature set — el mismo chequeo que hoy se
  hace manualmente al revisar `build_dataset.py`.
- **Contrato de datos** con las fuentes upstream (core, CRM, buró): si una
  tabla fuente cambia de esquema o de frecuencia de corte sin aviso (como
  ocurrió con `master_customer_data`, que no se refresca completo cada mes),
  el pipeline debe fallar de forma visible, no silenciosa.

## 3. Entrenamiento y reentrenamiento

- **Disparadores de reentrenamiento**: (a) calendario fijo (p. ej. trimestral),
  y (b) por deriva detectada en monitoreo (sección 6) — nunca reentrenamiento
  ad-hoc sin registro.
- **Metodología de validación**: se mantiene el esquema de 3 folds temporales
  (FIT/CALIB/REPORT) usado en el desarrollo — nunca calibrar umbral e
  hiperparámetros sobre el mismo mes que se reporta como métrica de
  aceptación del modelo.
- **Selección de algoritmo**: XGBoost quedó como base tras comparar contra
  LightGBM y CatBoost (ver `models/ensemble_comparison.json`); el pipeline de
  entrenamiento en producción debería correr esa comparación en cada
  reentrenamiento relevante, no asumir que el ganador se mantiene para
  siempre — el ranking podría cambiar si la naturaleza de los datos cambia.
- **Registro de modelos**: cada corrida se versiona (MLflow Model Registry o
  equivalente) con métricas (F1/AUC/precision/recall sobre REPORT), parámetros,
  y un hash de la versión del feature set usado — nunca promover a producción
  sin ese registro completo.

## 4. Aprobación y despliegue

- **Gate de aprobación humana**: ningún modelo pasa a producción solo porque
  "el número subió" — un comité técnico (Riesgo + Analítica) revisa el
  reporte de validación, incluyendo el análisis de sesgo de selección/uplift
  documentado en el documento técnico, antes de aprobar.
- **Despliegue**: el modelo se sirve como microservicio de inferencia
  independiente del resto del pipeline (y del sistema agéntico de la Parte 2),
  con versión propia y posibilidad de rollback sin afectar otros componentes.
- **Canary / shadow**: un modelo nuevo corre en modo *shadow* (calcula
  predicciones sin que se usen operativamente) durante al menos un ciclo de
  cobranza completo antes de reemplazar al modelo vigente.

## 5. Inferencia en producción

- **Modo principal**: batch mensual, alineado al ciclo de priorización de
  cartera existente — se calcula `Prob_uno` para toda la cartera en mora al
  cierre de cada mes, y se entrega como variable adicional al motor de
  priorización por lotes ya existente en el banco.
- **Consumo por el sistema agéntico**: el score se expone como una tabla/API
  de solo lectura que el nodo `propension` del grafo de agentes (Parte 2)
  consulta por obligación — hoy ese nodo usa un valor precalculado de un
  perfil sintético como *stand-in* explícito de esta integración real.
- **Manejo de obligaciones nuevas**: una obligación sin historial suficiente
  (alta tasa de nulos en `lag1_*`, ver EDA) recibe un score con menor
  confianza; el pipeline debe exponer también un indicador de confianza/
  cobertura de features, no solo la probabilidad puntual.

## 6. Monitoreo en producción

- **Deriva de datos (data drift)**: distribución de las features clave
  (`lag1_var_rpta_alt`, `prob_propension_roll6m`, mora) mes a mes, contra la
  distribución de entrenamiento — alerta si se desvía más allá de un umbral.
- **Deriva de desempeño**: F1/AUC reales del mes, calculados un mes después
  (cuando se conoce el `var_rpta_alt` real) — nunca esperar al siguiente
  reentrenamiento programado para descubrir que el modelo se degradó.
- **Estacionalidad conocida**: dado que en el desarrollo diciembre mostró una
  caída sistemática de F1 frente a noviembre en los tres algoritmos probados,
  el monitoreo debe tener umbrales de alerta ajustados por mes/temporada, no
  un único umbral fijo todo el año.
- **Dependencia de `prob_*` del banco**: si el score de propensión ya
  existente en el banco (usado como insumo) cambia de metodología, el
  pipeline debe detectarlo (cambio abrupto en la distribución de esa
  variable) antes de que degrade silenciosamente el modelo nuevo.

## 7. Gobierno de datos y cumplimiento

- Igual que en la Parte 2: todo cambio a la definición de la variable
  respuesta o a las reglas de negocio que la originan requiere aprobación de
  Riesgo, versionado y changelog auditable.
- Los datos personales usados en el feature set (perfil del cliente) deben
  tratarse conforme a la Ley 1266 (Habeas Data financiero) durante todo el
  ciclo, no solo en el punto de contacto con el cliente.
