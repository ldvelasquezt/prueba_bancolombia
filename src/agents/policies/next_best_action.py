"""
Selección de la siguiente mejor acción (NBA) — combina la decisión determinística
de elegibilidad (policies/eligibility.py) con el score de propensión del modelo
analítico de la Parte 1, para decidir QUÉ ofrecer y con qué prioridad.

Reglas de priorización (documentadas y ajustables, no aprendidas):
  1. Si no hay ninguna oferta elegible -> no ofrecer nada, explicar la razón.
  2. Mora temprana (<= 30 días) + propensión alta (>= 0.6) -> priorizar acuerdo
     de pago (compromiso a máx. 5 días): es la gestión más liviana y rápida.
  3. Si hay varias opciones de pago preaprobadas elegibles, se elige la de mayor
     "profundidad" de alivio ajustada a la severidad de la mora: mora avanzada
     prioriza reestructuración/renegociación de tasa; mora moderada prioriza
     ampliación de plazo o reducción de cuota.
  4. Si el cliente incumplió un acuerdo reciente, no se le vuelve a ofrecer un
     acuerdo de pago en el mismo ciclo (se prioriza una opción de pago formal).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.agents.policies.eligibility import (
    MAX_DIAS_PARA_ACUERDO, DecisionElegibilidad, EstadoObligacion, TipoAlternativa,
)

MORA_TEMPRANA_DIAS = 30
PROPENSION_ALTA = 0.6

PRIORIDAD_MORA_AVANZADA = [TipoAlternativa.REESTRUCTURACION, TipoAlternativa.RENEGOCIACION_TASA,
                            TipoAlternativa.AMPLIACION_PLAZO, TipoAlternativa.REDUCCION_CUOTA]
PRIORIDAD_MORA_MODERADA = [TipoAlternativa.AMPLIACION_PLAZO, TipoAlternativa.REDUCCION_CUOTA,
                            TipoAlternativa.RENEGOCIACION_TASA, TipoAlternativa.REESTRUCTURACION]


@dataclass
class AccionRecomendada:
    tipo: str  # "acuerdo_pago" | "opcion_pago" | "sin_oferta"
    alternativa: TipoAlternativa | None
    justificacion: str


def decidir_accion(estado: EstadoObligacion, decision: DecisionElegibilidad,
                    propension: float | None) -> AccionRecomendada:
    if not decision.tiene_alguna_oferta:
        motivo = "; ".join(decision.razones_bloqueo) or "Sin alternativas ni acuerdos elegibles."
        return AccionRecomendada("sin_oferta", None, motivo)

    propension = propension if propension is not None else 0.0

    ofrecer_acuerdo_primero = (
        decision.acuerdo_pago_elegible
        and not estado.acuerdo_incumplido_reciente
        and estado.dias_mora <= MORA_TEMPRANA_DIAS
        and propension >= PROPENSION_ALTA
    )
    if ofrecer_acuerdo_primero:
        return AccionRecomendada(
            "acuerdo_pago", None,
            f"Mora temprana ({estado.dias_mora} días) y propensión alta ({propension:.2f}): "
            f"se prioriza un acuerdo de pago a máx. {MAX_DIAS_PARA_ACUERDO} días sobre una "
            f"opción de pago formal."
        )

    if decision.opciones_pago_elegibles:
        prioridad = PRIORIDAD_MORA_AVANZADA if estado.dias_mora > 90 else PRIORIDAD_MORA_MODERADA
        elegidas = set(decision.opciones_pago_elegibles)
        mejor = next((alt for alt in prioridad if alt in elegidas), decision.opciones_pago_elegibles[0])
        return AccionRecomendada(
            "opcion_pago", mejor,
            f"De {len(decision.opciones_pago_elegibles)} opción(es) preaprobada(s) elegible(s), "
            f"se selecciona '{mejor.value}' según severidad de mora ({estado.dias_mora} días) "
            f"y propensión ({propension:.2f})."
        )

    if decision.acuerdo_pago_elegible and not estado.acuerdo_incumplido_reciente:
        return AccionRecomendada(
            "acuerdo_pago", None,
            "No hay opciones de pago elegibles en este momento; se ofrece un acuerdo de pago "
            "como alternativa de gestión temprana."
        )

    motivo = "; ".join(decision.razones_bloqueo)
    if estado.acuerdo_incumplido_reciente:
        motivo = (motivo + "; " if motivo else "") + (
            "Se descarta el acuerdo de pago porque el cliente incumplió uno recientemente."
        )
    return AccionRecomendada("sin_oferta", None, motivo or "Sin alternativas ni acuerdos elegibles.")
