"""
Motor de reglas de negocio de elegibilidad — determinístico, NO generativo.

Se mantiene deliberadamente fuera del LLM: las reglas de cuándo se puede
ofrecer una opción de pago o un acuerdo de pago son responsabilidad de
cumplimiento normativo, no de "criterio" del modelo de lenguaje. El agente de
IA consulta este motor como una herramienta (tool) y solo puede recomendar
lo que el motor autoriza.

Reglas mínimas (ver enunciado de negocio):
  - Máximo 3 opciones de pago preaprobadas por obligación, por mes.
  - Tras aplicar una opción de pago, la obligación entra en "cooldown" de
    3 a 4 meses (dependiendo del tipo de alternativa) antes de volver a ser
    elegible para otra opción de pago.
  - Los acuerdos de pago (compromiso de pago a máx. 5 días) se pueden
    gestionar de forma recurrente en distintas etapas de cobranza, SIEMPRE
    que el cliente no haya aceptado una opción de pago vigente y no exista
    una restricción que impida su ofrecimiento (p. ej. mora muy avanzada,
    fraude, obligación en proceso judicial).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class TipoAlternativa(str, Enum):
    AMPLIACION_PLAZO = "ampliacion_plazo"
    REDUCCION_CUOTA = "reduccion_cuota"
    RENEGOCIACION_TASA = "renegociacion_tasa"
    REESTRUCTURACION = "reestructuracion"


# Meses de cooldown por tipo de alternativa tras haber sido aplicada
COOLDOWN_MESES = {
    TipoAlternativa.AMPLIACION_PLAZO: 3,
    TipoAlternativa.REDUCCION_CUOTA: 3,
    TipoAlternativa.RENEGOCIACION_TASA: 4,
    TipoAlternativa.REESTRUCTURACION: 4,
}

MAX_OPCIONES_PREAPROBADAS_MES = 3
MAX_DIAS_PARA_ACUERDO = 5
DIAS_MORA_MAXIMO_PARA_OFRECER = 360  # más allá de esto, el caso ya no es de gestión de opciones/acuerdos


@dataclass
class RestriccionCliente:
    """Señales de restricción legal/operativa que bloquean cualquier oferta."""
    en_proceso_judicial: bool = False
    fraude_o_alerta_seguridad: bool = False
    cliente_fallecido: bool = False
    obligacion_castigada: bool = False

    @property
    def bloquea_todo(self) -> bool:
        return any([self.en_proceso_judicial, self.fraude_o_alerta_seguridad,
                    self.cliente_fallecido, self.obligacion_castigada])


@dataclass
class EstadoObligacion:
    """Snapshot mínimo de la obligación necesario para decidir elegibilidad."""
    obligacion_id: str
    dias_mora: int
    alternativas_preaprobadas: list[TipoAlternativa] = field(default_factory=list)
    ultima_alternativa_aplicada: TipoAlternativa | None = None
    fecha_ultima_alternativa_aplicada: date | None = None
    tiene_acuerdo_vigente: bool = False
    fecha_acuerdo_vigente: date | None = None
    acuerdo_incumplido_reciente: bool = False
    restriccion: RestriccionCliente = field(default_factory=RestriccionCliente)


@dataclass
class DecisionElegibilidad:
    opciones_pago_elegibles: list[TipoAlternativa]
    acuerdo_pago_elegible: bool
    razones_bloqueo: list[str]

    @property
    def tiene_alguna_oferta(self) -> bool:
        return bool(self.opciones_pago_elegibles) or self.acuerdo_pago_elegible


def _meses_desde(fecha_evento: date | None, hoy: date) -> float | None:
    if fecha_evento is None:
        return None
    return (hoy.year - fecha_evento.year) * 12 + (hoy.month - fecha_evento.month)


def evaluar_elegibilidad(estado: EstadoObligacion, hoy: date | None = None) -> DecisionElegibilidad:
    hoy = hoy or date.today()
    razones: list[str] = []

    if estado.restriccion.bloquea_todo:
        razones.append("Restricción legal/operativa activa: no se puede ofrecer nada.")
        return DecisionElegibilidad([], False, razones)

    if estado.dias_mora > DIAS_MORA_MAXIMO_PARA_OFRECER:
        razones.append(f"Mora ({estado.dias_mora} días) supera el máximo gestionable ({DIAS_MORA_MAXIMO_PARA_OFRECER}).")
        return DecisionElegibilidad([], False, razones)

    # --- Opciones de pago ---
    opciones_elegibles: list[TipoAlternativa] = []
    if estado.ultima_alternativa_aplicada is not None:
        meses_desde_aplicacion = _meses_desde(estado.fecha_ultima_alternativa_aplicada, hoy)
        cooldown = COOLDOWN_MESES[estado.ultima_alternativa_aplicada]
        if meses_desde_aplicacion is not None and meses_desde_aplicacion < cooldown:
            razones.append(
                f"Cooldown activo: se aplicó '{estado.ultima_alternativa_aplicada.value}' hace "
                f"{meses_desde_aplicacion} meses (mínimo {cooldown})."
            )
        else:
            opciones_elegibles = list(estado.alternativas_preaprobadas)[:MAX_OPCIONES_PREAPROBADAS_MES]
    else:
        opciones_elegibles = list(estado.alternativas_preaprobadas)[:MAX_OPCIONES_PREAPROBADAS_MES]

    if len(estado.alternativas_preaprobadas) > MAX_OPCIONES_PREAPROBADAS_MES:
        razones.append(
            f"Se truncan las opciones preaprobadas a {MAX_OPCIONES_PREAPROBADAS_MES} "
            f"(venían {len(estado.alternativas_preaprobadas)})."
        )

    # --- Acuerdo de pago ---
    acuerdo_elegible = True
    if estado.tiene_acuerdo_vigente:
        acuerdo_elegible = False
        razones.append("Ya existe un acuerdo de pago vigente; no se ofrece uno nuevo hasta resolverlo.")
    elif opciones_elegibles:
        # Si el cliente ya tiene una opción de pago elegible/vigente en curso, no se
        # ofrece acuerdo de pago en el mismo ciclo (evita mezclar dos compromisos).
        acuerdo_elegible = not estado.tiene_acuerdo_vigente

    return DecisionElegibilidad(
        opciones_pago_elegibles=opciones_elegibles,
        acuerdo_pago_elegible=acuerdo_elegible,
        razones_bloqueo=razones,
    )
