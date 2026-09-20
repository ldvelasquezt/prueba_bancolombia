"""
Guardrails de entrada: se ejecutan ANTES de invocar cualquier LLM, con reglas
simples y auditable (no depende del propio LLM para decidir si debe escalar,
lo cual sería circular y manipulable).

Cubre los escenarios de la prueba relacionados con seguridad y escalamiento:
  - Intentos de manipulación / prompt injection ("ignora tus instrucciones",
    "actúa como", "dame un descuento no autorizado", etc.)
  - Solicitudes sensibles (amenazas legales, menciones de fraude, salud grave,
    fallecimiento, quejas formales) que requieren gestor humano.
  - Información incompleta/contradictoria detectada en el estado del cliente.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Patrones sobre texto ya normalizado (ver `_normalizar`): minúsculas, sin tildes,
# espacios colapsados. Por eso aquí se escribe "condonacion" y no "condonación": la
# tilde ya se eliminó antes de comparar, así que escribirla en el patrón nunca
# matchearía. Se cubren variantes en español e inglés (jailbreaks suelen probar
# ambos idiomas).
PATRONES_MANIPULACION = [
    r"ignora( tus)? instrucciones",
    r"ignora (las reglas|todo lo anterior)",
    r"haz caso omiso",
    r"actua como",
    r"eres (ahora )?(un|una) ",
    r"olvida (todo|lo anterior|las reglas|tus reglas)",
    r"sin restricciones",
    r"descuento (especial|no autorizado|por fuera|del \d)",
    r"(condon|perdon|elimin|quit)\w*.*deuda",
    r"borra (mi|el) (historial|registro)",
    r"elimina (mi|el) (historial|registro)",
    r"dame acceso a",
    # Inglés: los intentos de jailbreak con frecuencia cambian de idioma para evadir
    # filtros solo-español.
    r"ignore (your |the |all )?(previous |prior )?instructions",
    r"disregard (your |the |all )?(previous |prior )?(instructions|rules)",
    r"act as (a|an) ",
    r"no restrictions",
    r"unauthorized discount",
    r"forgive (the|my|all) debt",
    r"you are now",
]

PATRONES_SENSIBLES = [
    r"demanda|abogado|tutela|denuncia|lawsuit|lawyer",
    r"fraude|robo|hackeo|suplantacion|fraud|hacked|identity theft",
    r"fallec|murio|muerte|death|deceased|died",
    r"enfermedad (grave|terminal)|cancer|hospitalizado|terminal illness|hospitalized",
    r"suicid|autolesi|self[- ]harm",
    r"queja formal|superintendencia|defensoria del consumidor|formal complaint|regulator",
]


def _normalizar(texto: str) -> str:
    """minúsculas + sin tildes/diacríticos + espacios colapsados, para que el
    parafraseo trivial (acentos, mayúsculas, espacios extra) no evada los patrones."""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto)
    return texto


@dataclass
class ResultadoGuardrail:
    intento_manipulacion: bool
    contenido_sensible: bool
    razon: str | None


def evaluar_mensaje(mensaje: str | None) -> ResultadoGuardrail:
    if not mensaje:
        return ResultadoGuardrail(False, False, None)
    texto = _normalizar(mensaje)

    for pat in PATRONES_MANIPULACION:
        if re.search(pat, texto):
            return ResultadoGuardrail(True, False, f"Patrón de manipulación detectado: '{pat}'")

    for pat in PATRONES_SENSIBLES:
        if re.search(pat, texto):
            return ResultadoGuardrail(False, True, f"Contenido sensible detectado: '{pat}'")

    return ResultadoGuardrail(False, False, None)


def datos_incompletos_o_contradictorios(raw_profile: dict | None) -> str | None:
    if raw_profile is None:
        return "No se encontró información del cliente/obligación en el sistema."
    dias_mora = raw_profile.get("dias_mora")
    if dias_mora is None:
        return "Falta el dato de días de mora; no se puede evaluar elegibilidad con seguridad."
    restriccion = raw_profile.get("restriccion") or {}
    if any(restriccion.values()):
        return "Restricción legal/operativa activa (judicial, fraude, castigo u otra): requiere revisión de un gestor humano."
    return None
