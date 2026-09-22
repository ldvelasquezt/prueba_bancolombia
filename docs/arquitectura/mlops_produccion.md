# Arquitectura de producción — Parte 1 (Modelo de propensión)

Esto es cómo pondría a operar en producción el modelo que construí, si tuviera que llevarlo más allá del prototipo. **No implementé nada de esto** — es la propuesta que pide el enunciado, pensada con la misma lógica de rigor que apliqué durante el desarrollo.

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

- **Orquestación**: un job batch mensual (Airflow, Databricks Jobs o similar), disparado al cierre contable del mes, no antes — mi pipeline depende de que M-1 esté cerrado (mora, pagos, gestión ya consolidados). Si se dispara antes de tiempo, se contamina exactamente el mismo problema que pasé la mitad del desarrollo evitando.
- **Feature store**: las features que construí (`lag1_*`, `prob_*_roll6m`, `lag1_var_rpta_alt`, etc.) se materializarían versionadas por mes de corte, no recalculadas al vuelo en cada scoring. Eso me permitiría auditar exactamente qué datos vio el modelo en cada corrida, algo que hoy hago manualmente revisando `build_dataset.py`.
- **Validación de esquema y de fuga automatizada**: ya escribí pruebas para esto (`tests/ml/`), pero en producción las correría como un gate obligatorio del pipeline, no como algo que reviso a mano: si alguna columna con fecha de corte posterior o igual al mes objetivo se cuela en el feature set, el pipeline debe fallar antes de entrenar, no después.
- **Contrato de datos** con las fuentes upstream (core, CRM, buró): si una tabla cambia de esquema o de frecuencia sin aviso —como me pasó con `master_customer_data`, que no se refresca completa cada mes y me obligó a resolverlo con un join "as of"— el pipeline tiene que fallar de forma visible, no silenciosa.

## 3. Entrenamiento y reentrenamiento

- **Disparadores**: calendario fijo (por ejemplo trimestral) y deriva detectada en monitoreo (sección 6) — nunca reentrenamiento improvisado sin dejar registro de por qué se hizo.
- **Metodología de validación**: mantendría el mismo esquema de 3 tramos (FIT/CALIB/REPORT) que usé en el desarrollo. Ya viví lo que pasa cuando no se respeta esto —el número se infla— así que no lo negociaría ni siquiera bajo presión de mostrar un número más alto.
- **Selección de algoritmo**: me quedé con XGBoost después de comparar contra LightGBM y CatBoost (`models/ensemble_comparison.json`), pero en producción correría esa misma comparación en cada reentrenamiento relevante — no doy por sentado que el ganador de hoy siga siendo el mejor si la naturaleza de los datos cambia.
- **Registro de modelos**: cada corrida quedaría versionada (MLflow Model Registry o equivalente) con sus métricas sobre REPORT, sus parámetros, y un hash de la versión del feature set usado. Nada pasa a producción sin ese registro completo.

## 4. Aprobación y despliegue

- **Aprobación humana como filtro**: ningún modelo entra a producción solo porque "el número subió". Antes de aprobar, un comité de Riesgo y Analítica revisaría el reporte de validación completo, incluyendo el análisis de sesgo de selección y propensión-vs-uplift que dejé documentado — ese es justamente el tipo de pregunta que no quiero que se salte nadie.
- **Despliegue independiente**: serviría el modelo como un microservicio de inferencia separado del resto del pipeline y del sistema agéntico de la Parte 2, con versión y rollback propios.
- **Shadow antes de reemplazar**: un modelo nuevo correría en modo *shadow* (calculando predicciones sin que se usen operativamente) durante al menos un ciclo completo de cobranza antes de reemplazar al vigente.

## 5. Inferencia en producción

- **Modo principal**: batch mensual, alineado al ciclo de priorización existente — calcularía `Prob_uno` para toda la cartera en mora al cierre de cada mes, como una variable adicional al motor de priorización por lotes que ya tiene el banco.
- **Cómo lo consumiría el sistema agéntico**: expondría el score como una tabla o API de solo lectura que el nodo `propension` de mi grafo de agentes (Parte 2) consultaría por obligación. Hoy ese nodo usa un valor precalculado de un perfil sintético, precisamente como *stand-in* explícito de esta integración real.
- **Obligaciones nuevas**: una obligación sin historial suficiente (ya vi cuánta gente cae en esta categoría al revisar los nulos de `lag1_*`) recibiría un score de menor confianza, y expondría también un indicador de cobertura de features, no solo la probabilidad puntual — para que quien use el score sepa cuándo confiar menos en él.

## 6. Monitoreo en producción

- **Deriva de datos**: seguiría la distribución de las features clave (`lag1_var_rpta_alt`, `prob_propension_roll6m`, mora) mes a mes contra la de entrenamiento, con alerta si se desvía más allá de un umbral.
- **Deriva de desempeño**: calcularía F1/AUC reales un mes después de cada corrida, en cuanto se conozca el `var_rpta_alt` real — no esperaría al siguiente reentrenamiento programado para enterarme de que el modelo se degradó.
- **Estacionalidad, porque ya la viví**: en mi desarrollo, diciembre mostró una caída sistemática de F1 frente a noviembre, en los tres algoritmos que probé. Por eso pondría umbrales de alerta ajustados por mes, no uno fijo todo el año — un modelo que "empeora" en diciembre puede ser normal, no una falla.
- **Dependencia de los scores del banco**: si `prob_propension` u otras variables que ya existían en el banco cambian de metodología sin avisar, el pipeline tiene que detectarlo antes de que degrade silenciosamente mi modelo.

## 7. Gobierno de datos y cumplimiento

- Igual que en la Parte 2: cualquier cambio a la definición de la variable respuesta o a las reglas de negocio que la originan necesita aprobación de Riesgo, con versionado y changelog auditable.
- Los datos personales del feature set (perfil del cliente) deben tratarse conforme a la Ley 1266 (Habeas Data financiero) durante todo el ciclo, no solo en el punto de contacto con el cliente.
