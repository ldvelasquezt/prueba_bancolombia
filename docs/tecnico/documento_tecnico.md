# Documento Técnico — Prueba Analítica Bancolombia

## 1. Parte 1 — Analítica

Lo primero que noté al mirar los datos: el archivo de entrenamiento trae gestión, pagos y mora del MISMO mes a predecir — el archivo a calificar confirma que eso no existe al calificar de verdad. Construí todo con solo M-1/M-2/M-3: estructurales rezagadas, scores del banco y pago con media móvil de 6 meses y tendencia, cliente vía snapshot más reciente.

Validé en 3 tramos, no 2: uno ajusta, otro calibra el umbral, un tercero se toca una sola vez para reportar. Al principio usé solo 2 y salió más alto (0.68); al notar que usaba el mismo mes para calibrar y reportar —lo cual infla la métrica— lo separé y bajó a 0.656.

Con contexto real de banca colombiana agregué gestión/promesas del mes anterior y, sobre todo, el desenlace de la alternativa previa junto con el lag del propio target (y de M-1 para predecir M: autocorrelación válida, no fuga) — esto solo explica el 31% de la importancia, más que cualquier otra variable.

F1 interno (dic-2023): 0.671, AUC 0.72. Probé LightGBM, CatBoost y sus combinaciones: todos convergen a 0.667–0.671, no era cuestión de elegir mal el algoritmo. Y lo mejor: al calificar en la plataforma con el mes real (enero-2024), salió **0.7033** — por encima de mi estimado, a ~1 punto del benchmark (0.714). Diciembre resultó más difícil de lo normal; mi número conservador no era el techo real.

## 2. Parte 2 — Multiagente

Diseñé un solo grafo de decisión, no varios agentes conversando: las reglas de cumplimiento (tope de opciones/mes, cooldown 3–4 meses, exclusión acuerdo/opción, mora excesiva bloquea todo) van en código determinístico, no a criterio de un LLM. El LLM solo redacta lo autorizado; si falla, degrada a escalamiento en vez de romper el flujo.

Los guardrails corren antes del LLM (evita que se auto-vigile) y detectan manipulación y contenido sensible en español e inglés, con 41 pruebas.

Le hice una revisión adversarial a mi propio trabajo antes de cerrarlo, y encontré 4 problemas reales: un fallback que no respetaba un incumplimiento reciente, una regla de exclusión que estaba en un comentario pero no en el código, guardrails evadibles con acentos/inglés, y un fallo del LLM sin manejo de errores. Los 4 corregidos, con su prueba de regresión.

## 3. Decisiones y supuestos

- Umbral óptimo de F1, no de negocio, sin costos de FP/FN.
- Cliente vía snapshot más reciente (76% de nulos si exigía mes exacto).
- Propensión del agéntico precalculada en el perfil sintético; no invoca el modelo real por falta de historial.
- Elegibilidad fuera del LLM: no depende del "criterio" de un modelo de lenguaje.

## 4. Riesgos

- Verificar que el LLM diga solo lo autorizado hoy es solo prompt, no chequeo posterior real.
- Mi F1 interno (0.671) subestimó el de plataforma (0.7033) — diciembre parece atípico, hipótesis no confirmada.
- Dependencia de los scores del banco sin monitoreo de deriva.
- **Propensión no es uplift**: el modelo aprende la política ya aplicada, no al cliente "puro" — parte de quienes aceptan se habrían puesto al día solos. Repartir alivio con este score sin control puede destruir valor.
- **Regulatorio**: una reestructuración implica reclasificar riesgo/provisión (Circular Básica); el sistema la señala, no decide — eso es de Riesgo/Contabilidad. Falta tratamiento de datos (Ley 1266).

## 5. Conclusiones

Construí un pipeline que evita fuga verificablemente y reporta F1 interno honesto (0.671); la plataforma confirmó 0.7033 en el mes real, así que ser riguroso no me costó desempeño. La variable que más pesa es lo que pasó con la obligación el mes anterior, no el perfil del cliente. El sistema agéntico mantiene las decisiones de negocio en código auditable, usa el LLM solo para redactar, y se degrada seguro ante fallos. La revisión a mi propio trabajo encontró y corrigió bugs reales, no solo observaciones de forma.

---

*Los anexos siguientes no cuentan contra el límite de 4.000 caracteres del cuerpo principal.*

## Anexo A — Datos/atributos adicionales sugeridos (opcional)

- **Ingresos/egresos verificados** (extractos transaccionales, no solo autorreportados): alto valor predictivo, costo medio — probablemente ya disponibles internamente en Bancolombia.
- **Historial de contactabilidad** (canal, efectividad de llamadas/WhatsApp): bajo costo, ya existe en CRM, mejora el NBA del sistema agéntico.
- **Score de buró externo** (Cifin/Datacrédito): alto valor, costo de licenciamiento por consulta.
- **Estacionalidad de ingresos por sector/ocupación** (primas, cosechas): bajo costo, derivable de los datos ya entregados agregando por `sector`/`ocup` y mes.

## Anexo B — Declaración de uso de Inteligencia Artificial Generativa

Usé Claude Code como herramienta de apoyo durante el desarrollo, de la misma forma en que usaría cualquier otra herramienta de trabajo: bajo mi dirección, para acelerar tareas de ejecución que yo ya sabía que necesitaba, no para que decidiera por mí. Quiero ser preciso sobre dónde estuvo esa ayuda, porque me parece la parte más honesta de todo el ejercicio.

Todo lo de fondo fue mío: el alcance y las prioridades de la prueba; la metodología de validación en 3 tramos, incluyendo rechazar explícitamente "arreglar" el número volviendo a una versión con fuga metodológica cuando pedí subir el F1; qué reglas de negocio de elegibilidad y priorización debían regir el sistema agéntico; y, sobre todo, el contexto real de cobranza en banca colombiana que terminó siendo la variable más importante del modelo — la intuición de que el comportamiento de gestión y el desenlace de la alternativa del mes anterior pesan más que el perfil del cliente es experiencia de negocio mía, no algo que salió de la herramienta. También pedí que se hicieran revisiones adversariales sobre el modelo y sobre el sistema agéntico, y de cada hallazgo que trajeron, decidí yo cuál corregir, cuál descartar, y cuál dejar documentado como riesgo abierto en vez de resolverlo a la carrera.

Usé la herramienta como ejecutor: para escribir el código (pipeline de datos, entrenamiento, inferencia, sistema agéntico), redactar las pruebas automatizadas, correr mecánicamente las revisiones que yo pedí, y darle forma de redacción a esta documentación a partir de lo que yo ya había decidido.
