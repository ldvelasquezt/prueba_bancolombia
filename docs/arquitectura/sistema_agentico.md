# Arquitectura del sistema agéntico de cobranza

## 1. Por qué un grafo

Es un solo grafo de decisión en LangGraph con nodos especializados, no varios agentes
conversacionales coordinándose entre sí.

Esto no es una negociación abierta entre partes: es un pipeline donde cada paso tiene una
responsabilidad distinta (seguridad, cumplimiento, scoring, priorización, redacción).
Modelarlo como agentes autónomos habría sumado complejidad de coordinación y, peor, habría
dejado las reglas de cumplimiento al criterio de un LLM.

## 2. Qué hay en `src/agents/`

```
policies/
  eligibility.py       Reglas de negocio. Determinístico, sin LLM
  next_best_action.py  Decide qué ofrecer: opción de pago o acuerdo de pago
  guardrails.py        Manipulación, contenido sensible y datos incompletos,
                        antes de invocar el LLM
tools/
  customer_store.py    CRM simulado con los perfiles sintéticos
  propensity.py        Wrapper del score de propensión de la Parte 1
graph/
  state.py             El estado que comparten los nodos
  collections_graph.py La definición del grafo
llm_client.py           Claude real si hay API key, MockLLM si no
run_demo.py             Demo de punta a punta sobre los escenarios sintéticos
```

## 3. El flujo

```
fetch_state -> guardrails -> [escalate_human | eligibility] -> propension
            -> decide_action -> respond
```

**fetch_state** trae el perfil cliente-obligación. En producción vendría del CRM y del core.

**guardrails** corre antes de cualquier llamado al LLM. Detecta manipulación o prompt
injection, contenido sensible, datos incompletos y restricciones legales. Si algo se
dispara, va derecho a `escalate_human`.

**eligibility** aplica las reglas del negocio: tope de opciones preaprobadas, cooldown de 3
a 4 meses después de aplicar una opción, nada de acuerdo si ya hay uno vigente, y mora
excesiva o restricción legal bloquean todo. Los dos últimos chequeos están acá además de en
guardrails, como defensa en profundidad. Este nodo reporta la elegibilidad en bruto de cada
canal; cuál ofrecer cuando ambos aplican lo decide `decide_action`.

**propension** consulta el score. En producción sería el modelo de la Parte 1 por endpoint.

**decide_action** escoge la acción combinando elegibilidad, propensión y severidad de mora,
con reglas explícitas en `next_best_action.py`.

**respond** es el único nodo que usa el LLM, y solo para redactar. Por system prompt le
indico que comunique únicamente lo que `decide_action` autorizó. Eso hoy vive en el system
prompt; nadie revisa después el texto que sale.

**escalate_human** es el nodo terminal para lo que el sistema no debe resolver solo.

## 4. Conexión con la Parte 1

El punto de integración es `tools/propensity.py`. En producción llamaría al servicio de
inferencia de `src/ml/inference/predict.py` con las mismas features por obligación
(`lag1_*`, `prob_*`, `prevmes_*`).

Acá no lo hace: los perfiles son sintéticos y no tienen historial, así que el score va
precalculado en el perfil. Lo dejo dicho para que la sustitución sea transparente.

## 5. Seguridad y trazabilidad

Cada nodo agrega un evento a `state["trace"]` con lo que decidió. En producción eso sería
un log de auditoría inmutable.

Las reglas de negocio están fuera del LLM: elegibilidad y priorización son código
determinístico con pruebas unitarias. El LLM recibe la acción ya decidida y la redacta.

Los guardrails también quedaron fuera del LLM. El mismo prompt que intenta manipular al
redactor le llegaría también al clasificador, así que los guardrails son reglas simples y
auditables sobre el texto de entrada, no otra llamada al modelo.

Cuando hay ambigüedad, el sistema escala. Se prefiere un falso escalamiento a una oferta mal
hecha.

## 6. Pruebas (`tests/agents/`)

| Tipo | Archivo | Qué cubre |
|---|---|---|
| Elegibilidad | `test_eligibility.py` | Cooldown, tope de opciones, restricciones legales, acuerdo vigente, mora excesiva |
| Priorización | `test_next_best_action.py` | Mora temprana con propensión, incumplimiento reciente bloqueando el acuerdo, severidad de mora |
| Seguridad | `test_guardrails.py` | Prompt injection, incluida la evasión con acentos, mayúsculas, espacios e inglés. Contenido sensible y datos incompletos |
| End-to-end | `test_graph_scenarios.py` | Los 9 escenarios del enunciado sobre el grafo completo |

Los tests de integración corren con `MockLLM`, sin `ANTHROPIC_API_KEY`, para que sean
reproducibles en cualquier entorno.

## 7. Lo que propondría para producción (no implementado)

### Despliegue

El grafo contenerizado como servicio (FastAPI + LangGraph) en Kubernetes con autoscaling, y
el modelo de la Parte 1 como microservicio aparte, con versión y rollback propios.

### LLMOps

- Versionaría los prompts y los evaluaría offline contra un golden set antes de desplegar.
- Pediría trazas completas de cada ejecución (LangSmith o equivalente): inputs, decisiones
  por nodo, tokens, latencia, costo.
- Pondría los evals de guardrails como gate de CI.
- Muestrearía conversaciones para revisión humana, y eso retroalimenta guardrail y prompt.
- **Verificación después de generar el texto.** Un chequeo programático, no otro LLM, que
  confirme que la respuesta solo menciona la alternativa y el plazo autorizados, sin montos
  ni promesas por fuera. Es la brecha más importante antes de poner un LLM real de cara al
  cliente.
- Fallos del LLM envueltos para escalar a un gestor humano, con reintentos acotados y
  circuit breaker.

### Monitoreo

Tasa de escalamiento a humano por motivo, con alerta si sube de golpe. Distribución de
acciones recomendadas contra las aceptadas. Latencia y disponibilidad de cada tool, con
fallback a escalamiento si algo no responde.

### Seguridad de la información

Enmascaramiento o tokenización antes de que los datos lleguen al LLM, control de acceso por
rol a las trazas, y tratamiento conforme a la Ley 1266 de 2008. El CRM simulado no hace
nada de esto todavía.

### Cumplimiento contable

`policies/eligibility.py` marca con `requiere_flujo_contable` las alternativas (hoy solo
`REESTRUCTURACION`) que bajo la Circular Básica Contable y Financiera implican reclasificar
riesgo y provisión, no solo cambiar plazo o cuota. El motor la señala para que se active el
flujo de aprobación de Riesgo y Contabilidad, que es quien decide.

### Gobierno de cambios

Cualquier cambio a `policies/eligibility.py` debería pasar por aprobación de riesgo y
cumplimiento, con changelog auditable, separado del ciclo de despliegue del prompt.
