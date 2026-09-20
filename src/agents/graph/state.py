"""Estado compartido del grafo de agentes de cobranza."""
from __future__ import annotations

from typing import Optional, TypedDict


class TraceEvent(TypedDict):
    nodo: str
    detalle: str


class CollectionsState(TypedDict, total=False):
    obligacion_id: str
    mensaje_cliente: Optional[str]

    # Poblado por node_fetch_state
    raw_profile: Optional[dict]
    estado_obligacion: Optional[object]  # EstadoObligacion

    # Poblado por node_guardrails
    requiere_escalamiento: bool
    razon_escalamiento: Optional[str]

    # Poblado por node_eligibility / node_propension
    decision_elegibilidad: Optional[object]  # DecisionElegibilidad
    propension: Optional[float]

    # Poblado por node_decide_action
    accion: Optional[object]  # AccionRecomendada

    # Poblado por node_respond
    respuesta_agente: Optional[str]

    trace: list[TraceEvent]
