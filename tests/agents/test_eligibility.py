"""Pruebas unitarias del motor de reglas de negocio (determinístico)."""
from datetime import date

from src.agents.policies.eligibility import (
    EstadoObligacion, RestriccionCliente, TipoAlternativa, evaluar_elegibilidad,
)


def test_sin_historial_todas_las_preaprobadas_son_elegibles():
    estado = EstadoObligacion(
        obligacion_id="X1", dias_mora=30,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO, TipoAlternativa.REDUCCION_CUOTA],
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    assert decision.opciones_pago_elegibles == [TipoAlternativa.AMPLIACION_PLAZO, TipoAlternativa.REDUCCION_CUOTA]
    assert decision.acuerdo_pago_elegible is True


def test_cooldown_bloquea_nueva_opcion_de_pago():
    estado = EstadoObligacion(
        obligacion_id="X2", dias_mora=40,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO],
        ultima_alternativa_aplicada=TipoAlternativa.AMPLIACION_PLAZO,
        fecha_ultima_alternativa_aplicada=date(2024, 1, 10),
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))  # < 3 meses de cooldown
    assert decision.opciones_pago_elegibles == []
    assert any("Cooldown" in r for r in decision.razones_bloqueo)


def test_cooldown_vencido_vuelve_a_habilitar():
    estado = EstadoObligacion(
        obligacion_id="X3", dias_mora=40,
        alternativas_preaprobadas=[TipoAlternativa.AMPLIACION_PLAZO],
        ultima_alternativa_aplicada=TipoAlternativa.AMPLIACION_PLAZO,
        fecha_ultima_alternativa_aplicada=date(2023, 10, 1),
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))  # 4 meses después
    assert decision.opciones_pago_elegibles == [TipoAlternativa.AMPLIACION_PLAZO]


def test_maximo_tres_opciones_preaprobadas():
    estado = EstadoObligacion(
        obligacion_id="X4", dias_mora=40,
        alternativas_preaprobadas=[
            TipoAlternativa.AMPLIACION_PLAZO, TipoAlternativa.REDUCCION_CUOTA,
            TipoAlternativa.RENEGOCIACION_TASA, TipoAlternativa.REESTRUCTURACION,
        ],
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    assert len(decision.opciones_pago_elegibles) == 3
    assert any("truncan" in r for r in decision.razones_bloqueo)


def test_restriccion_legal_bloquea_todo():
    estado = EstadoObligacion(
        obligacion_id="X5", dias_mora=200,
        alternativas_preaprobadas=[TipoAlternativa.REESTRUCTURACION],
        restriccion=RestriccionCliente(en_proceso_judicial=True),
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    assert decision.tiene_alguna_oferta is False


def test_acuerdo_vigente_no_ofrece_otro():
    estado = EstadoObligacion(obligacion_id="X6", dias_mora=15, tiene_acuerdo_vigente=True)
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    assert decision.acuerdo_pago_elegible is False


def test_mora_excesiva_bloquea_gestion():
    estado = EstadoObligacion(
        obligacion_id="X7", dias_mora=400,
        alternativas_preaprobadas=[TipoAlternativa.REESTRUCTURACION],
    )
    decision = evaluar_elegibilidad(estado, hoy=date(2024, 2, 1))
    assert decision.tiene_alguna_oferta is False
