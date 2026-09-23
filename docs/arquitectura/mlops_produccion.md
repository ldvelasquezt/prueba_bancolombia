# Cómo pondría este modelo a producción — Parte 1

Acá  se cuenta cómo operaría el modelo de propensión si hubiera que sacarlo del prototipo.


## El ciclo, de un vistazo

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
  [3] Entrenamiento / reentrenamiento ── por drift o por calendario
        │
        ▼
  [4] Registro de modelos ── versión, métricas, aprobación
        │
        ▼
  [5] Inferencia ── batch mensual + fallback on-demand
        │
        ▼
  [6] Consumo ── priorización por lotes + sistema agéntico (Parte 2)
        │
        ▼
  [7] Monitoreo ── drift, deriva de negocio, alertas
        │ (y eso vuelve a alimentar el paso 3)
```

## 1. Preparación de datos

El equivalente productivo de `build_dataset.py` sería un job batch mensual en Airflow,
Databricks Jobs o lo que ya use el banco, disparado al cierre contable del mes. Necesita
que M-1 esté cerrado, con mora, pagos y gestión consolidados; si se dispara antes, se
contamina con datos del mes que está prediciendo.

Las features (`lag1_*`, `prob_*_roll6m`, `lag1_var_rpta_alt`) las materializaría en un
feature store versionado por mes de corte, en vez de recalcularlas en cada scoring. Así se
puede auditar qué vio el modelo en cada corrida.

La validación de esquema y de ausencia de fuga ya está escrita en `tests/ml/`. En
producción sería un gate obligatorio del pipeline: si se cuela una columna con fecha de
corte igual o posterior al mes objetivo, revienta y no alcanza a entrenar.

Con las fuentes de arriba pondría un contrato de datos. Ya me pasó con
`master_customer_data`, que no se refresca completa cada mes y tocó resolverlo con un join
"as of"; si una tabla cambia de esquema o de frecuencia, el pipeline tiene que fallar
ruidoso.

## 2. Entrenamiento y reentrenamiento

El reentrenamiento va por calendario fijo, trimestral, más lo que dispare el monitoreo.
Cualquiera fuera de esas dos vías queda con su justificación escrita.

La validación en tres tramos (FIT, CALIB y REPORT) se queda como está. También volvería a
correr la comparación contra LightGBM y CatBoost en cada
reentrenamiento que valga la pena, porque el ganador de hoy no tiene por qué seguir siéndolo.

Cada corrida quedaría en MLflow Model Registry o equivalente, con sus métricas sobre
REPORT, sus parámetros y un hash del feature set que usó.

## 3. Aprobación y despliegue

Antes de aprobar, un comité de Riesgo y Analítica revisaría el reporte de validación
completo, incluyendo el análisis de sesgo de selección y el de propensión contra uplift.

El modelo iría como microservicio de inferencia aparte, con su propio versionado y
rollback. Y uno nuevo correría en modo shadow, calculando predicciones que nadie usa,
durante al menos un ciclo completo de cobranza antes de reemplazar al vigente.

## 4. Inferencia

Batch mensual, alineado al ciclo de priorización que ya existe: calcular `Prob_uno` para
toda la cartera en mora al cierre de cada mes, como una variable más del motor de
priorización por lotes.

Para el sistema agéntico expondría el score como tabla o API de solo lectura, que el nodo
`propension` consulta por obligación.

Las obligaciones nuevas son caso aparte, y son bastantes (se ve en los nulos de `lag1_*`).
A esas les daría un score de menor confianza y un indicador de cobertura de features, para
que quien lo consuma sepa cuándo confiar menos.

## 5. Monitoreo

Seguiría la distribución de las features que más pesan (`lag1_var_rpta_alt`,
`prob_propension_roll6m`, la mora) mes contra mes frente a la de entrenamiento, con alerta
si se desvía de un umbral.

El desempeño real solo se sabe un mes después, cuando llega el `var_rpta_alt` verdadero.

Los umbrales de alerta los ajustaría por mes y no fijos para todo el año: hay
estacionalidad, y en mi desarrollo diciembre se comportó distinto en los tres algoritmos
que probé.

También vigilaría los scores que ya trae el banco. Si `prob_propension` u otra cambia de
metodología sin avisar, el pipeline tiene que darse cuenta.

## 6. Gobierno de datos

Igual que en la Parte 2: cualquier cambio a la definición de la variable respuesta, o a las
reglas de negocio que la originan, necesita aprobación de Riesgo, con versionado y
changelog auditable.
