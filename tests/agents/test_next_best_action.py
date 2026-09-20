"""
Pruebas unitarias de la selección de siguiente mejor acción (NBA). Antes de esta
suite, `next_best_action.py` solo se ejercía indirectamente vía los escenarios
fijos del grafo, lo que dejó pasar un bug real: el fallback de acuerdo de pago
no respetaba `acuerdo_incumplido_reciente` (ver regla 4 del docstring del módulo).
"""
from datetime import date

from src.agents.policies.eligibility import EstadoObligacion, TipoAlternativa, evaluar_elegibilidad
from src.agents.policies.next_best_action import (
    MORA_TEMPRANA_DIAS, PROPENSION_ALTA, decidir_accion,
)


def test_sin_ofertas_elegibles_da_sin_oferta():
    estado = EstadoObligacion(obligacion_id="N1", dias_mora=500)
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    accion = decidir_accion(estado, decision, propension=0.9)
    assert accion.tipo == "sin_oferta"


def test_mora_temprana_y_propension_alta_prioriza_acuerdo():
    estado = EstadoObligacion(
        obligacion_id="N2", dias_mora=MORA_TEMPRANA_DIAS,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO],
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    accion = decidir_accion(estado, decision, propension=PROPENSION_ALTA)
    assert accion.tipo == "acuerdo_pago"


def test_mora_temprana_pero_propension_baja_prioriza_opcion():
    estado = EstadoObligacion(
        obligacion_id="N3", dias_mora=MORA_TEMPRANA_DIAS,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO],
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    accion = decidir_accion(estado, decision, propension=PROPENSION_ALTA - 0.01)
    assert accion.tipo == "opcion_pago"


def test_incumplimiento_reciente_bloquea_acuerdo_incluso_en_mora_temprana():
    estado = EstadoObligacion(
        obligacion_id="N4", dias_mora=MORA_TEMPRANA_DIAS,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO],
        acuerdo_incumplido_reciente=True,
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    accion = decidir_accion(estado, decision, propension=0.95)
    assert accion.tipo != "acuerdo_pago"
    assert accion.tipo == "opcion_pago"  # sigue teniendo una opción de pago elegible


def test_incumplimiento_reciente_sin_opciones_elegibles_da_sin_oferta():
    """Caso que exponía el bug: cooldown activo (sin opciones) + incumplimiento
    reciente. El fallback de acuerdo_pago NO debe activarse aquí."""
    estado = EstadoObligacion(
        obligacion_id="N5", dias_mora=40,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO],
        ultima_alternativa_aplicada=TipoAlternativa.AMPLIACION_PLAZO,
        fecha_ultima_alternativa_aplicada=date(2024, 1, 1),
        acuerdo_incumplido_reciente=True,
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))  # cooldown activo
    assert decision.opciones_pago_elegibles == []  # precondición del bug

    accion = decidir_accion(estado, decision, propension=0.9)
    assert accion.tipo == "sin_oferta"
    assert "incumpl" in accion.justificacion.lower()


def test_mora_avanzada_prioriza_reestructuracion_sobre_ampliacion():
    estado = EstadoObligacion(
        obligacion_id="N6", dias_mora=120,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO, TipoAlternativa.REESTRUCTURACION],
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    accion = decidir_accion(estado, decision, propension=0.3)
    assert accion.tipo == "opcion_pago"
    assert accion.alternativa == TipoAlternativa.REESTRUCTURACION
