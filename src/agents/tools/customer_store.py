"""
CRM simulado: almacén en memoria de perfiles cliente-obligación.

En producción esto sería un llamado a los sistemas del banco (CRM, core
bancario, motor de cobranza). Para el prototipo, se carga desde un JSON de
datos sintéticos (ver data/synthetic/customer_profiles.json), claramente
identificados como no reales.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from src.agents.policies.eligibility import EstadoObligacion, RestriccionCliente, TipoAlternativa

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "customer_profiles.json"

_RELATIVE_DATE_RE = re.compile(r"^hace_(\d+)_dias$")


def _parse_fecha(valor: str | None) -> date | None:
    """Acepta una fecha ISO absoluta o el marcador relativo 'hace_N_dias', para que
    los escenarios sintéticos (p. ej. cooldown activo) no se rompan con el paso del
    tiempo real si se usara una fecha absoluta fija."""
    if not valor:
        return None
    m = _RELATIVE_DATE_RE.match(valor)
    if m:
        return date.today() - timedelta(days=int(m.group(1)))
    return date.fromisoformat(valor)


class CustomerStore:
    def __init__(self, path: Path = DEFAULT_PATH):
        with open(path, encoding="utf-8") as f:
            self._raw = {p["obligacion_id"]: p for p in json.load(f)}

    def get_raw(self, obligacion_id: str) -> dict | None:
        return self._raw.get(obligacion_id)

    def get_estado(self, obligacion_id: str) -> EstadoObligacion | None:
        p = self._raw.get(obligacion_id)
        if p is None:
            return None
        restriccion = RestriccionCliente(**p.get("restriccion", {}))
        fecha_alt = p.get("fecha_ultima_alternativa_aplicada")
        return EstadoObligacion(
            obligacion_id=p["obligacion_id"],
            dias_mora=p["dias_mora"],
            alternativas_preaprobadas=[TipoAlternativa(a) for a in p.get("alternativas_preaprobadas", [])],
            ultima_alternativa_aplicada=(
                TipoAlternativa(p["ultima_alternativa_aplicada"])
                if p.get("ultima_alternativa_aplicada") else None
            ),
            fecha_ultima_alternativa_aplicada=_parse_fecha(fecha_alt),
            tiene_acuerdo_vigente=p.get("tiene_acuerdo_vigente", False),
            acuerdo_incumplido_reciente=p.get("acuerdo_incumplido_reciente", False),
            restriccion=restriccion,
        )

    def list_ids(self) -> list[str]:
        return list(self._raw.keys())
