# Documento Técnico — Prueba Analítica Bancolombia

## 1. Parte 1 — Analítica

`trtest` tiene columnas contemporáneas a `var_rpta_alt` (gestión, promesas, mora/saldo/producto); el OOT confirma que no están disponibles al calificar. Features usan solo M-1/M-2/M-3: estructurales rezagadas desde `trtest`; scores del banco y pago con media móvil 3m y tendencia; cliente vía `merge_asof` backward por baja frecuencia de refresco.

Validación en 3 folds (no 2): FIT (sep–oct) ajusta; CALIB (nov) decide early-stopping/umbral/tuning; REPORT (dic) se toca una sola vez. Modelo final se reentrena con los 3 meses, fijando `n_estimators` en el `best_iteration` de calibración.

Hallazgo de rigor: con 2 folds, el mismo mes calibraba umbral y reportaba F1, inflando la métrica ~4.5 puntos. Separado en 3, el F1 honesto bajó a 0.6556.

Con contexto de negocio colombiano se agregó lag de gestión/promesas anterior (PTP kept rate, contacto) y el **desenlace de la alternativa previa** más el lag del target (y_{t-1}, válido: describe M-1 ya cerrado) — este último explica el 31% de la importancia, sobre cualquier otra variable.

Resultado final: F1=0.6707, AUC=0.7224, umbral=0.34. Optuna (40 trials) no superó los defaults: el techo ya es de información, no de modelo.

## 2. Parte 2 — Multiagente

Grafo único (LangGraph), no agentes autónomos: fetch_state → guardrails → [escalate_human | eligibility] → propension → decide_action → respond. Elegibilidad (tope de opciones/mes, cooldown 3–4 meses, exclusión mutua acuerdo/opción, mora >360 días bloquea todo) y priorización son código determinístico sin LLM, con 39 pruebas. El LLM solo redacta lo que decide_action autorizó; si falla, degrada a escalamiento en vez de propagar la excepción.

Guardrails corren antes del LLM (evita circularidad): manipulación/inyección y contenido sensible sobre texto normalizado, en español e inglés.

Revisión adversarial: (1) fallback de acuerdo de pago no respetaba `acuerdo_incumplido_reciente` sin opciones por cooldown, corregido; (2) exclusión mutua acuerdo/opción reforzada; (3) guardrails con normalización unicode/inglés; (4) manejo de fallos del LLM.

## 3. Decisiones y supuestos

- Umbral óptimo de F1, no de negocio, por ausencia de costos FP/FN.
- `master_customer_data` vía join as-of por baja frecuencia de refresco (~76% nulos con join exacto).
- Propensión del agéntico viene precalculada en el perfil sintético (stand-in); no invoca el modelo real por falta de historial de 6 meses.
- Elegibilidad fuera del LLM: cumplimiento normativo no depende del "criterio" de un modelo de lenguaje.

## 4. Riesgos

- Verificación post-generación del LLM en `respond` es hoy solo instrucción de prompt, no chequeo programático — brecha declarada antes de producción.
- F1_report (0.6707) proviene de un solo mes (diciembre); sensible a estacionalidad de fin de año.
- Dependencia de `prob_*` sin monitoreo de drift.
- **Sesgo de selección y propensión vs. uplift**: solo se observa aceptación en clientes ya contactados por la política pasada, no al azar — el modelo aprende esa política, no el cliente. Propensión no es uplift: parte de quienes aceptan habrían pagado igual sin la opción (self-cure); usarlo para asignar alivio sin champion-challenger puede destruir valor.

## 5. Conclusiones

El pipeline evita fuga verificable y reporta una métrica honesta (F1=0.6707) tras separar calibración de reporte. La variable más predictiva es el desenlace de la gestión anterior, no el perfil del cliente. Que ni más features ni tuning movieran la métrica sugiere que el techo es de información disponible (transaccional, buró externo, contactabilidad), no de modelo. El agéntico mantiene decisiones de negocio en código determinístico y auditable, usa el LLM solo para redactar, con degradación segura ante fallos. La revisión adversarial encontró y corrigió bugs reales, no solo observaciones teóricas.

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
