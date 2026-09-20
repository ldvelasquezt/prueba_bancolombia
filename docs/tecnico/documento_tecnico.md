# Documento Técnico — Prueba Analítica Bancolombia

## 1. Parte 1 — Analítica

`trtest` contiene columnas contemporáneas al mes de `var_rpta_alt` (gestión, promesas, incluso "estructurales" como mora/saldo/producto); el OOT confirma que eso no está disponible al calificar. Todos los features usan solo M-1/M-2/M-3: estructurales rezagadas desde `trtest`; scores del banco (`prob_propension`, `prob_alrt_temprana`, `prob_auto_cura`) y comportamiento de pago con media móvil 3m y tendencia; perfil de cliente vía `merge_asof` (backward) por la baja frecuencia de refresco de `master_customer_data`.

Validación temporal en 3 folds (no 2): FIT (sep–oct 2023) ajusta; CALIB (nov 2023) decide early-stopping, umbral de F1 y tuning (Optuna); REPORT (dic 2023) se toca una sola vez, al final. Modelo final (XGBoost) se reentrena con FIT+CALIB+REPORT, fijando `n_estimators` en el `best_iteration` de calibración, sin volver a mirar REPORT.

Hallazgo de rigor: con 2 folds, el mismo mes calibraba umbral y reportaba F1, inflando la métrica. Separando en 3, el F1 honesto en REPORT (0.6556) quedó ~4.5 puntos bajo el F1 en CALIB (0.6864) — ese es el costo real de tocar una métrica varias veces frente a reportarla una sola vez.

Resultado: F1=0.6556, AUC=0.6788, umbral=0.32 (dic-2023). `resultado_prueba.csv` aplica el mismo pipeline al OOT (ene-2024) con modelo/umbral ya congelados.

## 2. Parte 2 — Multiagente

Grafo único (LangGraph), no agentes autónomos negociando: fetch_state → guardrails → [escalate_human | eligibility] → propension → decide_action → respond. Elegibilidad (tope 3 opciones/mes, cooldown 3–4 meses, exclusión mutua acuerdo/opción vigente, mora >360 días bloquea todo) y priorización (NBA) son código determinístico sin LLM, con 39 pruebas. El LLM solo redacta, restringido por prompt a lo autorizado por decide_action; si falla, degrada a escalamiento humano en vez de propagar la excepción.

Guardrails corren antes del LLM (evitar circularidad): detectan manipulación/inyección y contenido sensible sobre texto normalizado (minúsculas, sin tildes, espacios colapsados), en español e inglés.

Revisión adversarial y correcciones: (1) el fallback de acuerdo de pago no respetaba `acuerdo_incumplido_reciente` sin opciones elegibles por cooldown — corregido, cubierto en `test_next_best_action.py`; (2) exclusión mutua acuerdo/opción reforzada en `eligibility.py`; (3) guardrails con normalización unicode e inglés contra evasión trivial; (4) manejo explícito de fallos del LLM en `respond`.

## 3. Decisiones y supuestos

- Umbral óptimo de F1, no de negocio, por ausencia de costos FP/FN explícitos en el enunciado.
- `master_customer_data` vía join as-of por baja frecuencia de refresco (~76% nulos con join exacto por mes).
- Propensión del prototipo agéntico viene precalculada en el perfil sintético (stand-in explícito); no invoca el modelo real, porque los perfiles no tienen historial de 6 meses.
- Elegibilidad deliberadamente fuera del LLM: cumplimiento normativo no depende del "criterio" de un modelo de lenguaje.

## 4. Riesgos

- Verificación post-generación del LLM real en `respond` es hoy solo instrucción de prompt, no chequeo programático — brecha declarada antes de producción.
- F1_report (0.6556) proviene de un solo mes (diciembre); sensible a estacionalidad de fin de año.
- Dependencia de `prob_*` del banco sin monitoreo de drift implementado.

## 5. Conclusiones

El pipeline evita fuga verificable contra el OOT y reporta una métrica honesta tras separar calibración de reporte en 3 folds. El sistema agéntico mantiene decisiones de negocio en código determinístico y auditable, usa el LLM solo para redactar, con degradación segura ante fallos y guardrails robustos a evasión trivial. La revisión adversarial encontró y corrigió bugs reales antes de cerrar el prototipo, no solo observaciones teóricas.

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
