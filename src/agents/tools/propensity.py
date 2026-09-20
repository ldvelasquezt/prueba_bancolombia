"""
Tool de propensión: en producción, este tool llamaría al endpoint de inferencia
del modelo entrenado en la Parte 1 (src/ml/inference/predict.py), pasándole las
mismas features (lag1_*, prob_*, prevmes_*, etc.) construidas para la obligación.

Para este prototipo, como los perfiles de clientes son sintéticos y no traen el
historial completo de 6 meses que el modelo real necesita, el score de
propensión viene precalculado en el perfil (campo `prob_propension_opcion_pago`)
como stand-in explícito del resultado que devolvería el modelo de la Parte 1.
Esto se documenta para que quede claro que la integración real es un llamado a
un servicio de scoring, no una réplica del pipeline de features aquí.
"""
from __future__ import annotations

from src.agents.tools.customer_store import CustomerStore


def get_propension(store: CustomerStore, obligacion_id: str) -> float | None:
    raw = store.get_raw(obligacion_id)
    if raw is None:
        return None
    return raw.get("prob_propension_opcion_pago")
