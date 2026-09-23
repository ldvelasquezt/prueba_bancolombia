Documento técnico: Prueba Analítica Bancolombia

1. Modelo de propensión

Construcción del dataset
El archivo de entrenamiento trae gestión, pagos y mora del mismo mes objetivo, información que no existe al momento de calificar y que generaría fuga. Por eso el dataset usa solo meses anteriores (hasta M-1, con ventanas de 6 meses): variables estructurales rezagadas (por su autocorrelación), scores internos del banco, pago con media móvil de 6 meses y su tendencia, y datos del cliente del snapshot más reciente. Resultan 90 variables, 26 categóricas.

Esquema de validación
FIT (septiembre y octubre de 2023): entrenamiento.
CALIB (noviembre): early stopping y calibración del umbral.
REPORT (diciembre): evaluación final. Sin embargo, en etapas previas del desarrollo diciembre sirvió como validación para elegir hiperparámetros y variables, así que su F1 (0.6709) es algo optimista; la validación realmente independiente es la de la plataforma.
El modelo desplegado se reentrena con los tres tramos, con el número de árboles fijo en 402, el obtenido en calibración.

Importancia de variables
Pesa más el comportamiento reciente de la obligación: el lag del target (28%) y el desenlace de la alternativa previa (25%). El lag no es fuga, porque es información conocida al calificar. La gestión del mes anterior pesó menos de lo que esperaba (1.4%); el resto está distribuido.

Resultado
El modelo es XGBoost. LightGBM, CatBoost y sus ensambles dieron resultados equivalentes: el desempeño depende más del dataset que del algoritmo. Calificando enero de 2024 en la plataforma, el F1 fue 0.7033.

2. Sistema agéntico

Arquitectura
Es un único grafo de decisión, no un esquema multiagente, lo que lo hace predecible y auditable. Las reglas de cumplimiento están en código determinístico: tope de opciones por mes, cooldown de 3 a 4 meses, exclusión entre acuerdo de pago y alivio, y bloqueo por mora excesiva. El LLM solo redacta lo ya autorizado; si falla, el caso escala a un humano.

Priorización
Mora de hasta 30 días y propensión ≥ 0.6: primero un acuerdo de pago a máximo 5 días.
Mora mayor a 90 días: se priorizan los alivios más profundos.
Incumplimiento reciente: no se ofrece nuevo acuerdo.
El cooldown se cuenta en días, para que algo aplicado el 31 de enero no se considere cumplido el 1 de febrero.

Guardrails, trazabilidad y pruebas
Los guardrails corren antes del LLM y detectan manipulación y contenido sensible en español e inglés, normalizando tildes, mayúsculas y espacios. Cada nodo registra su decisión en una traza. Sin API key, el LLM se reemplaza por un mock determinístico. El sistema agéntico tiene 45 pruebas y el repositorio suma 59. El detalle está en docs/arquitectura/sistema_agentico.md.

Anexo: uso de inteligencia artificial generativa

Se usó Claude Code como herramienta de apoyo.

Trabajo propio: alcance y prioridades; diseño de la solución y dirección del desarrollo del pipeline, entrenamiento, inferencia y sistema agéntico; revisión del código y corrección de bugs; validación en tres tramos, incluido el rechazo a recuperar F1 con una versión con fuga; reglas de elegibilidad y priorización, y contexto de cobranza. La hipótesis de que la gestión y el desenlace del mes anterior pesarían más que el perfil del cliente vino de la experiencia en cobranza, no de los datos. Solicité revisiones adversariales y decidí qué hallazgos se corregían, se descartaban o quedaban como riesgo. La redacción final de la documentación es mía.

Apoyo de la herramienta: escritura de gran parte del código a partir de mis instrucciones y bajo mi revisión, estructura del proyecto, ejecución del código, sugerencias, apoyo en las pruebas unitarias y propuestas de redacción que luego ajusté.