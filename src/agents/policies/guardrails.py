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
from dataclasses import dataclass

PATRONES_MANIPULACION = [
    r"ignora( tus)? instrucciones",
    r"ignora las reglas",
    r"act[uú]a como",
    r"eres (ahora )?(un|una) ",
    r"olvida (todo|lo anterior)",
    r"sin restricciones",
    r"descuento (especial|no autorizado|por fuera)",
    r"condona(r|ción)? (toda|la) deuda",
    r"borra (mi|el) (historial|registro)",
    r"dame acceso a",
]

PATRONES_SENSIBLES = [
    r"demanda|abogado|tutela|denuncia",
    r"fraude|robo|hackeo|suplantaci[oó]n",
    r"fallec|muri[oó]|muerte",
    r"enfermedad (grave|terminal)|c[aá]ncer|hospitalizado",
    r"suicid|autolesi",
    r"queja formal|superintendencia",
]


@dataclass
class ResultadoGuardrail:
    intento_manipulacion: bool
    contenido_sensible: bool
    razon: str | None


def evaluar_mensaje(mensaje: str | None) -> ResultadoGuardrail:
    if not mensaje:
        return ResultadoGuardrail(False, False, None)
    texto = mensaje.lower()

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
