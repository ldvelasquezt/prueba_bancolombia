"""
Grafo de agentes de cobranza (LangGraph).

Arquitectura: un solo grafo con nodos especializados en vez de "múltiples
agentes conversacionales independientes", porque la tarea es fundamentalmente
un pipeline de decisión con distintos tipos de responsabilidad (guardrails,
elegibilidad, scoring, decisión de negocio, redacción de respuesta), no un
problema de negociación abierta entre agentes autónomos. Esto simplifica la
trazabilidad (cada nodo registra su decisión) y evita que el LLM tenga
autoridad sobre reglas de cumplimiento, que quedan en código determinístico.

Nodos:
  1. fetch_state       -> obtiene el perfil cliente-obligación (CRM simulado)
  2. guardrails        -> detecta manipulación / contenido sensible / datos
                           incompletos ANTES de razonar con LLM
  3. eligibility       -> motor de reglas de negocio (determinístico)
  4. propension        -> score del modelo analítico (Parte 1)
  5. decide_action     -> siguiente mejor acción (NBA)
  6. respond           -> redacta la respuesta al cliente (LLM), restringida a
                           solo mencionar lo que decide_action autorizó
  7. escalate_human    -> nodo terminal para los casos que requieren un gestor

Transiciones: fetch_state -> guardrails -> (escalate_human | eligibility) ->
propension -> decide_action -> respond
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.graph.state import CollectionsState
from src.agents.llm_client import get_llm
from src.agents.policies.eligibility import MAX_DIAS_PARA_ACUERDO, evaluar_elegibilidad
from src.agents.policies.guardrails import datos_incompletos_o_contradictorios, evaluar_mensaje
from src.agents.policies.next_best_action import decidir_accion
from src.agents.tools.customer_store import CustomerStore
from src.agents.tools.propensity import get_propension


def _trace(state: CollectionsState, nodo: str, detalle: str) -> list:
    return state.get("trace", []) + [{"nodo": nodo, "detalle": detalle}]


def build_graph(store: CustomerStore | None = None):
    store = store or CustomerStore()
    llm = get_llm()

    def node_fetch_state(state: CollectionsState) -> dict:
        raw = store.get_raw(state["obligacion_id"])
        estado = store.get_estado(state["obligacion_id"])
        return {
            "raw_profile": raw,
            "estado_obligacion": estado,
            "trace": _trace(state, "fetch_state", f"Perfil {'encontrado' if raw else 'NO encontrado'}"),
        }

    def node_guardrails(state: CollectionsState) -> dict:
        g = evaluar_mensaje(state.get("mensaje_cliente"))
        razon_datos = datos_incompletos_o_contradictorios(state.get("raw_profile"))

        requiere_escalamiento = g.intento_manipulacion or g.contenido_sensible or razon_datos is not None
        razon = g.razon or razon_datos
        return {
            "requiere_escalamiento": requiere_escalamiento,
            "razon_escalamiento": razon,
            "trace": _trace(state, "guardrails", razon or "Sin banderas de riesgo"),
        }

    def node_eligibility(state: CollectionsState) -> dict:
        estado = state["estado_obligacion"]
        decision = evaluar_elegibilidad(estado)
        return {
            "decision_elegibilidad": decision,
            "trace": _trace(state, "eligibility",
                             f"Elegibles: opciones={[a.value for a in decision.opciones_pago_elegibles]}, "
                             f"acuerdo={decision.acuerdo_pago_elegible}"),
        }

    def node_propension(state: CollectionsState) -> dict:
        prop = get_propension(store, state["obligacion_id"])
        return {
            "propension": prop,
            "trace": _trace(state, "propension", f"Score={prop}"),
        }

    def node_decide_action(state: CollectionsState) -> dict:
        accion = decidir_accion(state["estado_obligacion"], state["decision_elegibilidad"], state["propension"])
        return {
            "accion": accion,
            "trace": _trace(state, "decide_action", f"{accion.tipo} | {accion.justificacion}"),
        }

    def node_respond(state: CollectionsState) -> dict:
        accion = state["accion"]
        if accion.tipo == "sin_oferta":
            prompt = (
                "El cliente no es elegible para ninguna oferta ahora. Explica de forma empática, "
                f"sin prometer nada, el motivo: {accion.justificacion}"
            )
        elif accion.tipo == "acuerdo_pago":
            prompt = (f"Ofrece al cliente un acuerdo de pago con compromiso dentro de los próximos "
                      f"{MAX_DIAS_PARA_ACUERDO} días, de forma cordial y clara.")
        else:
            prompt = (f"Explica al cliente, de forma clara, por qué la alternativa "
                      f"'{accion.alternativa.value}' es la más adecuada para su obligación en mora.")

        try:
            respuesta = llm.invoke([
                {"role": "system", "content": "Eres un asistente de cobranza de Bancolombia. Sé empático, "
                                                "claro y NUNCA ofrezcas nada que no esté explícitamente "
                                                "autorizado en la instrucción."},
                {"role": "user", "content": prompt},
            ])
            contenido = respuesta.content
            if not isinstance(contenido, str):
                contenido = str(contenido)
            return {
                "respuesta_agente": contenido,
                "trace": _trace(state, "respond", "Respuesta generada"),
            }
        except Exception as exc:  # el LLM (timeout, rate-limit, API caída) no debe romper el flujo
            return {
                "respuesta_agente": (
                    "Tuvimos un inconveniente técnico generando la respuesta. Un gestor humano "
                    "se pondrá en contacto contigo para continuar."
                ),
                "requiere_escalamiento": True,
                "razon_escalamiento": f"Fallo del LLM en el nodo respond: {exc}",
                "trace": _trace(state, "respond", f"LLM falló, se degrada a escalamiento: {exc}"),
            }

    def node_escalate(state: CollectionsState) -> dict:
        return {
            "respuesta_agente": (
                "Este caso requiere la atención de un gestor humano. Te vamos a contactar a la "
                "brevedad para continuar con tu solicitud."
            ),
            "trace": _trace(state, "escalate_human", state.get("razon_escalamiento") or "Escalado"),
        }

    graph = StateGraph(CollectionsState)
    graph.add_node("fetch_state", node_fetch_state)
    graph.add_node("guardrails", node_guardrails)
    graph.add_node("eligibility", node_eligibility)
    graph.add_node("propension", node_propension)
    graph.add_node("decide_action", node_decide_action)
    graph.add_node("respond", node_respond)
    graph.add_node("escalate_human", node_escalate)

    graph.set_entry_point("fetch_state")
    graph.add_edge("fetch_state", "guardrails")
    graph.add_conditional_edges(
        "guardrails",
        lambda s: "escalate_human" if s.get("requiere_escalamiento") else "eligibility",
        {"escalate_human": "escalate_human", "eligibility": "eligibility"},
    )
    graph.add_edge("eligibility", "propension")
    graph.add_edge("propension", "decide_action")
    graph.add_edge("decide_action", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("escalate_human", END)

    return graph.compile()
