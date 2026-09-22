# Arquitectura del sistema agéntico de cobranza

## 1. Por qué diseñé un grafo, no "agentes autónomos" negociando entre sí

Decidí construir **un solo grafo de decisión (LangGraph) con nodos especializados**, en vez de varios agentes conversacionales independientes coordinándose entre sí. Mi razón: esta tarea es un **pipeline de decisión con responsabilidades distintas** (seguridad, cumplimiento normativo, scoring analítico, priorización de negocio, redacción de respuesta), no un problema de negociación abierta entre partes. Modelarlo como agentes autónomos me habría añadido complejidad de coordinación sin ningún beneficio real, y —lo más importante— habría dejado reglas de cumplimiento normativo bajo el "criterio" de un LLM, que es exactamente lo que quería evitar desde el diseño.

## 2. Componentes (`src/agents/`)

```
policies/
  eligibility.py       Motor de reglas de negocio (determinístico, sin LLM)
  next_best_action.py  Prioriza qué ofrecer (opción de pago vs. acuerdo de pago)
  guardrails.py        Detección de manipulación / contenido sensible / datos
                        incompletos, ANTES de invocar el LLM
tools/
  customer_store.py    CRM simulado (perfiles sintéticos)
  propensity.py        Wrapper del score de propensión (Parte 1)
graph/
  state.py             Estado compartido del grafo
  collections_graph.py Definición del grafo LangGraph
llm_client.py           Wrapper LLM: Claude real si hay API key, MockLLM si no
run_demo.py              Demo end-to-end sobre los escenarios sintéticos
```

## 3. Flujo del grafo

```
fetch_state -> guardrails -> [escalate_human | eligibility] -> propension
            -> decide_action -> respond
```

- **fetch_state**: obtiene el perfil cliente-obligación (en producción: CRM + core bancario).
- **guardrails**: corre ANTES de cualquier llamado al LLM. Detecta intentos de manipulación/prompt injection, contenido sensible, y datos incompletos o restricciones legales activas. Si algo dispara, va directo a `escalate_human` sin pasar por reglas de negocio ni por el LLM — así lo diseñé a propósito.
- **eligibility**: aplica las reglas mínimas del negocio (tope de opciones preaprobadas, cooldown de 3-4 meses tras aplicar una opción, acuerdo no ofrecible si ya hay uno vigente, mora excesiva o restricción legal bloquea todo). Dejé los chequeos de mora excesiva y restricción legal también aquí como defensa en profundidad: hoy `guardrails` ya intercepta esos casos antes, pero quise que `eligibility` los bloqueara igual por si algún día se invoca desde otro punto de entrada o el guardrail cambia. `eligibility` reporta la elegibilidad "en bruto" de cada canal por separado; cuál de los dos ofrecer cuando ambos son elegibles lo decide `decide_action`, no este nodo.
- **propension**: consulta el score de propensión (en producción, el modelo que construí en la Parte 1, vía un endpoint de inferencia).
- **decide_action**: selecciona la siguiente mejor acción combinando elegibilidad + propensión + severidad de mora — reglas explícitas que escribí en `next_best_action.py`, no aprendidas por ningún modelo.
- **respond**: el único nodo que usa el LLM, y solo para **redactar** —nunca para decidir. Le instruyo por system prompt que comunique exclusivamente lo que `decide_action` autorizó, pero soy consciente de que hoy eso es solo una instrucción de prompt, no una verificación programática posterior sobre el texto generado (lo dejo como limitación explícita en la sección 7).
- **escalate_human**: nodo terminal para los casos que decidí que el sistema no debe resolver solo.

## 4. Cómo lo conecté con la Parte 1 (mi modelo analítico)

`tools/propensity.py` es el punto de integración: en producción llamaría al servicio de inferencia que entrené en `src/ml/inference/predict.py`, con las mismas features (`lag1_*`, `prob_*`, `prevmes_*`) que construí para cada obligación. En este prototipo, como los perfiles son sintéticos y no tienen 6 meses de historial real, dejé el score precalculado en el perfil como *stand-in* explícito — lo documento así para que la sustitución sea transparente y nadie la confunda con el modelo real funcionando de verdad.

## 5. Seguridad, trazabilidad y cumplimiento

- **Trazabilidad**: cada nodo agrega un evento a `state["trace"]` con el detalle de su decisión. En producción lo persistiría como log de auditoría inmutable (sección 7).
- **Reglas de negocio fuera del LLM**: elegibilidad (`test_eligibility.py`) y priorización (`test_next_best_action.py`) son código determinístico que probé unitariamente. El LLM nunca decide QUÉ ofrecer, solo CÓMO comunicarlo — aunque, como ya dije, ese "solo cómo" hoy se garantiza por instrucción de prompt, no por una verificación posterior real.
- **Guardrails antes del LLM**: puse la detección de manipulación y contenido sensible fuera del LLM a propósito, porque depender del mismo modelo para vigilarse a sí mismo sería circular — un intento de manipulación podría intentar manipular también al clasificador. La implementé con reglas simples y auditables sobre el mensaje entrante.
- **Escalamiento a humano**: por diseño, ante cualquier ambigüedad (datos faltantes, restricciones legales, contenido sensible, manipulación), hice que el sistema escale en vez de intentar resolver solo.

## 6. Pruebas (`tests/agents/`)

| Tipo | Archivo | Qué cubre |
|---|---|---|
| Unitarias (elegibilidad) | `test_eligibility.py` | Cooldown, tope de opciones preaprobadas, restricciones legales, acuerdo vigente, mora excesiva |
| Unitarias (priorización) | `test_next_best_action.py` | Mora temprana + propensión, incumplimiento reciente bloqueando acuerdo, priorización por severidad de mora |
| Seguridad | `test_guardrails.py` | Prompt injection (incl. evasión por acentos/mayúsculas/espacios/inglés), contenido sensible, datos incompletos |
| Integración end-to-end | `test_graph_scenarios.py` | Los 7+ escenarios del enunciado corridos sobre el grafo completo |

Hice que los tests de integración corran con `MockLLM` (sin necesitar `ANTHROPIC_API_KEY`), para que sean reproducibles en cualquier entorno, incluido el de evaluación de esta prueba.

## 7. Lo que propongo para producción (nada de esto está implementado)

- **Orquestación y despliegue**: contenerizar el grafo como servicio (FastAPI + LangGraph), desplegado en Kubernetes con autoscaling; el modelo de la Parte 1 servido como microservicio de inferencia independiente, con versión y rollback propios.
- **LLMOps**:
  - Versionado de prompts y evaluación offline (golden set de conversaciones) antes de cada despliegue de un cambio de prompt.
  - Trazas completas (LangSmith o equivalente) de cada ejecución del grafo: inputs, decisiones de cada nodo, tokens, latencia, costo.
  - Evals automáticos de guardrails (batería de intentos de manipulación conocidos) como gate de CI antes de cada release.
  - Human-in-the-loop: muestreo de conversaciones para revisión humana periódica, retroalimentando al guardrail y al prompt.
  - **Verificación post-generación**: antes de enviarle al cliente el texto que devuelve un LLM real, un chequeo programático (no otro LLM) que confirme que la respuesta solo menciona la alternativa/plazo autorizados por `decide_action`, sin ningún monto, descuento o promesa fuera de ese contrato. Hoy solo lo pido por prompt; para mí es la brecha más importante que hay que cerrar antes de poner un LLM real en producción.
  - Manejo explícito de fallos del LLM: la llamada debe envolverse en un bloque que escale a un gestor humano en vez de propagar la excepción, con reintentos acotados y circuit breaker.
- **Monitoreo en producción**:
  - Tasa de escalamiento a humano por motivo (alerta si sube abruptamente: puede indicar un guardrail roto o un cambio en el comportamiento de los clientes).
  - Distribución de acciones recomendadas vs. aceptadas realmente.
  - Latencia y disponibilidad de cada tool (CRM, modelo de propensión); circuit breakers y fallback a "escalar a humano" si un servicio no responde.
- **Seguridad de la información**: enmascaramiento/tokenización de datos sensibles antes de que lleguen al LLM, control de acceso por rol a las trazas de auditoría, y tratamiento de datos conforme a la **Ley 1266 de 2008 (Habeas Data financiero)** — mi CRM simulado no implementa esto todavía; en producción, ningún dato personal debería llegar al LLM sin pasar antes por una capa de anonimización auditada.
- **Cumplimiento contable/regulatorio**: hice que `policies/eligibility.py` marque con `requiere_flujo_contable` las alternativas (hoy solo `REESTRUCTURACION`) que bajo la **Circular Básica Contable y Financiera de la Superintendencia Financiera** implican reclasificación de la calificación de riesgo y de la provisión de la obligación, no solo un cambio operativo de plazo o cuota. Mi motor NO decide esa reclasificación —eso requiere criterio de Riesgo/Contabilidad y datos que este prototipo no tiene— solo la señala para que el flujo de aprobación correspondiente se active después, y nunca la aplico automáticamente vía el LLM.
- **Gobierno de cambios**: cualquier cambio a `policies/eligibility.py` debería requerir aprobación de riesgo/cumplimiento, con control de versión y changelog auditable, separado del ciclo de despliegue del LLM/prompt.
