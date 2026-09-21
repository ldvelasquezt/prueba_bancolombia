# Documento Técnico — Prueba Analítica Bancolombia

## 1. Parte 1 — Analítica

`trtest` tiene columnas contemporáneas a `var_rpta_alt`; el OOT confirma que no están disponibles al calificar. Features usan solo M-1/M-2/M-3: estructurales rezagadas desde `trtest`; scores del banco y pago con media móvil 6m, volatilidad y tendencia (las tablas de apoyo cubren ene-dic 2023 completo); cliente vía `merge_asof` backward.

Validación en 3 folds (no 2): FIT (sep–oct) ajusta; CALIB (nov) calibra umbral/tuning; REPORT (dic) se toca una sola vez. Con 2 folds el mismo mes calibraba y reportaba, inflando F1 ~4.5 puntos; en 3, bajó a 0.6556.

Con contexto de negocio colombiano se agregó lag de gestión/promesas anterior (PTP kept rate, contacto) y el **desenlace de la alternativa previa** más el lag del target (y_{t-1}, válido: describe M-1 ya cerrado) — este último explica el 31% de la importancia, sobre cualquier otra variable.

Resultado final: F1=0.6709, AUC=0.7225 (XGBoost). Optuna no superó los defaults. LightGBM, CatBoost y sus ensambles convergen a F1 0.667–0.671, con la misma caída CALIB→REPORT (~0.03) sin importar el algoritmo — el techo es de información, no de modelo.

## 2. Parte 2 — Multiagente

Grafo único (LangGraph), no agentes autónomos: fetch_state → guardrails → [escalate_human | eligibility] → propension → decide_action → respond. Elegibilidad (tope de opciones/mes, cooldown 3–4 meses, exclusión mutua acuerdo/opción, mora >360 días bloquea todo) y priorización son código determinístico sin LLM, con 41 pruebas. El LLM solo redacta lo autorizado; si falla, degrada a escalamiento en vez de propagar la excepción.

Guardrails corren antes del LLM (evita circularidad): manipulación/inyección y contenido sensible sobre texto normalizado, en español e inglés.

Revisión adversarial: fallback de acuerdo tras incumplimiento por cooldown, exclusión mutua acuerdo/opción, guardrails evadibles (acentos/inglés), fallo de LLM sin manejo de errores — los 4 corregidos y testeados.

## 3. Decisiones y supuestos

- Umbral óptimo de F1, no de negocio, por ausencia de costos FP/FN.
- `master_customer_data` vía join as-of (~76% nulos con join exacto por mes).
- Propensión del agéntico viene precalculada en el perfil sintético (stand-in); no invoca el modelo real por falta de historial.
- Elegibilidad fuera del LLM: cumplimiento normativo no depende del "criterio" de un modelo de lenguaje.

## 4. Riesgos

- Verificación post-generación del LLM en `respond` es hoy solo instrucción de prompt, no chequeo programático.
- F1_report proviene de un mes (diciembre); sensible a estacionalidad de fin de año.
- Dependencia de `prob_*` sin monitoreo de drift.
- **Propensión vs. uplift**: solo se observa aceptación en clientes ya contactados por la política pasada — el modelo aprende esa política, no al cliente. Parte habría pagado igual (self-cure); usar el score sin champion-challenger puede destruir valor.
- **Regulatorio**: `REESTRUCTURACION` implica reclasificación de riesgo/provisión (Circular Básica); el motor la marca (`requiere_flujo_contable`) sin decidirla — es de Riesgo/Contabilidad. Falta tratamiento de datos bajo Ley 1266.

## 5. Conclusiones

El pipeline evita fuga verificable y reporta una métrica honesta (F1=0.6709; 0.667–0.671 probando también LightGBM, CatBoost y ensambles) tras separar calibración de reporte. La variable más predictiva es el desenlace de la gestión anterior, no el perfil del cliente. Que ni más features, ni tuning, ni cambiar de algoritmo movieran la métrica sugiere un techo de información (transaccional, buró externo, contactabilidad), no de modelo. Queda ~4-5 puntos bajo el benchmark (0.714) — brecha reconocida, no oculta. El agéntico mantiene decisiones de negocio en código determinístico y auditable, usa el LLM solo para redactar, con degradación segura. La revisión adversarial encontró y corrigió bugs reales.

---

*Los anexos siguientes no cuentan contra el límite de 4.000 caracteres del cuerpo principal.*

## Anexo A — Datos/atributos adicionales sugeridos (opcional)

- **Ingresos/egresos verificados** (extractos transaccionales, no solo autorreportados): alto valor predictivo, costo medio — probablemente ya disponibles internamente en Bancolombia.
- **Historial de contactabilidad** (canal, efectividad de llamadas/WhatsApp): bajo costo, ya existe en CRM, mejora el NBA del sistema agéntico.
- **Score de buró externo** (Cifin/Datacrédito): alto valor, costo de licenciamiento por consulta.
- **Estacionalidad de ingresos por sector/ocupación** (primas, cosechas): bajo costo, derivable de los datos ya entregados agregando por `sector`/`ocup` y mes.

## Anexo B — Declaración de uso de Inteligencia Artificial Generativa

Todo el código (pipeline de datos, entrenamiento, inferencia, sistema agéntico) y las pruebas se generaron con asistencia de Claude (Claude Code, modelo Sonnet) en una sesión interactiva guiada por el candidato. El candidato dirigió el alcance, las prioridades y el orden de construcción, y decidió cuándo profundizar. Ejecutó además una revisión adversarial propia sobre el código generado, que encontró y llevó a corregir la fuga metodológica del F1 (paso de 2 a 3 folds temporales) y los bugs del sistema agéntico descritos en la Sección 2; el candidato validó o rechazó cada hallazgo de esa revisión antes de aceptarlo.

Actividades donde se usó IA generativa: generación de código, diseño arquitectónico del grafo de agentes, documentación técnica, generación y ejecución de pruebas, e ideación de escenarios de prueba.

Decisiones tomadas directamente por el candidato: alcance del proyecto, metodología de validación temporal (3 folds FIT/CALIB/REPORT), reglas de negocio de elegibilidad y priorización de acciones, y la aceptación o rechazo de cada corrección propuesta por la revisión adversarial.
