# Arquitectura del sistema agéntico de cobranza

## 1. Decisión de diseño: un grafo, no "agentes autónomos" negociando entre sí

Se optó por **un solo grafo de decisión (LangGraph) con nodos especializados**,
en vez de varios agentes conversacionales independientes que se coordinen entre
sí. Razón: la tarea es un **pipeline de decisión con distintos tipos de
responsabilidad** (seguridad, cumplimiento normativo, scoring analítico,
priorización de negocio, redacción de respuesta), no un problema de
negociación abierta. Modelarlo como agentes autónomos habría añadido
complejidad de coordinación sin beneficio real, y —más importante— habría
puesto reglas de cumplimiento normativo bajo el "criterio" de un LLM, que es
exactamente lo que se quiere evitar.

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

- **fetch_state**: obtiene el perfil cliente-obligación (en producción: CRM +
  core bancario).
- **guardrails**: corre ANTES de cualquier llamado al LLM. Detecta (a) intentos
  de manipulación/prompt injection, (b) contenido sensible (amenazas legales,
  fraude, salud grave) y (c) datos incompletos o restricciones legales activas.
  Si algo dispara, se va directo a `escalate_human` sin pasar por reglas de
  negocio ni LLM.
- **eligibility**: aplica las reglas mínimas del negocio (máx. 3 opciones
  preaprobadas/mes, cooldown de 3-4 meses tras aplicar una opción, acuerdo de
  pago no ofrecible si ya hay uno vigente, mora excesiva o restricción legal
  bloquea todo).
- **propension**: consulta el score de propensión (en producción, el modelo de
  la Parte 1 vía un endpoint de inferencia).
- **decide_action**: selecciona la siguiente mejor acción combinando
  elegibilidad + propensión + severidad de mora (reglas explícitas y
  auditables, ver `next_best_action.py`).
- **respond**: el único nodo que usa el LLM, y solo para **redactar** —nunca
  para decidir— restringido a comunicar exclusivamente lo que `decide_action`
  autorizó.
- **escalate_human**: nodo terminal para los casos que no debe resolver el
  sistema automáticamente.

## 4. Integración con la Parte 1 (modelo analítico)

`tools/propensity.py` es el punto de integración: en producción llamaría al
servicio de inferencia entrenado en `src/ml/inference/predict.py` con las
mismas features (lag1_*, prob_*, prevmes_*) construidas para la obligación.
En este prototipo, como los perfiles son sintéticos y no tienen 6 meses de
historial real, el score viene precalculado en el perfil como *stand-in*
explícito — se documenta para que la sustitución sea transparente y no se
confunda con el modelo real.

## 5. Seguridad, trazabilidad y cumplimiento

- **Trazabilidad**: cada nodo agrega un evento a `state["trace"]` (nodo +
  detalle de la decisión). En producción esto se persistiría como log de
  auditoría inmutable (ver sección 7).
- **Reglas de negocio fuera del LLM**: elegibilidad y priorización son código
  determinístico, testeado unitariamente (`tests/agents/test_eligibility.py`).
  El LLM nunca decide QUÉ ofrecer, solo CÓMO comunicarlo.
- **Guardrails previos al LLM**: la detección de manipulación/contenido
  sensible no depende del LLM (sería circular: un intento de manipulación
  podría intentar manipular también al clasificador). Se implementa con reglas
  simples y auditables sobre el mensaje entrante.
- **Escalamiento a humano**: por diseño, ante cualquier ambigüedad (datos
  faltantes, restricciones legales, contenido sensible, manipulación) el
  sistema escala en vez de intentar resolver.

## 6. Pruebas (`tests/agents/`)

| Tipo | Archivo | Qué cubre |
|---|---|---|
| Unitarias (reglas de negocio) | `test_eligibility.py` | Cooldown, máx. 3 opciones, restricciones legales, acuerdo vigente, mora excesiva |
| Seguridad | `test_guardrails.py` | Prompt injection, contenido sensible, datos incompletos |
| Integración end-to-end | `test_graph_scenarios.py` | Los 7+ escenarios del enunciado corridos sobre el grafo completo |

Los tests de integración corren con `MockLLM` (sin necesitar `ANTHROPIC_API_KEY`),
por lo que son reproducibles en cualquier entorno, incluido el de evaluación de
esta prueba.

## 7. Mecanismos propuestos para producción (NO implementados en este prototipo)

- **Orquestación y despliegue**: contenerizar el grafo como servicio (FastAPI +
  LangGraph), desplegado en Kubernetes con autoscaling; el modelo de la Parte 1
  servido como microservicio de inferencia independiente (versión propia,
  rollback independiente del grafo de agentes).
- **LLMOps**:
  - Versionado de prompts y evaluación offline (golden set de conversaciones)
    antes de cada despliegue de un cambio de prompt.
  - Trazas completas (LangSmith o equivalente interno) de cada ejecución del
    grafo: inputs, decisiones de cada nodo, tokens, latencia, costo.
  - Evals automáticos de guardrails (batería de intentos de manipulación
    conocidos) como gate de CI antes de cada release.
  - Human-in-the-loop: muestreo de conversaciones para revisión humana
    periódica, con feedback loop hacia el guardrail y el prompt.
- **Monitoreo en producción**:
  - Tasa de escalamiento a humano por motivo (alerta si sube abruptamente:
    puede indicar guardrail roto o cambio en el comportamiento de clientes).
  - Distribución de acciones recomendadas vs. aceptadas realmente (deriva del
    modelo de propensión o de las reglas de negocio).
  - Latencia y disponibilidad de cada tool (CRM, modelo de propensión); circuit
    breakers y fallback a "escalar a humano" si un servicio no responde.
- **Seguridad de la información**: enmascaramiento/tokenización de datos
  sensibles antes de que lleguen al LLM, control de acceso por rol a las trazas
  de auditoría, retención de datos conforme a políticas de protección de datos
  personales.
- **Gobierno de cambios**: todo cambio a `policies/eligibility.py` (reglas de
  negocio) requiere aprobación de riesgo/cumplimiento, con control de versión y
  changelog auditable, separado del ciclo de despliegue del LLM/prompt.
