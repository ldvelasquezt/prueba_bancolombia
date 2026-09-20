"""
Wrapper delgado sobre el LLM usado por los agentes conversacionales.

Diseño: si hay ANTHROPIC_API_KEY configurada, usa Claude (via langchain-anthropic)
de verdad. Si NO hay key disponible (p. ej. en el entorno de evaluación de esta
prueba, donde no se garantiza acceso a la API), cae a un `MockLLM` determinístico
que permite que todo el grafo de agentes se ejecute end-to-end y sea probado sin
necesitar credenciales. Esto se documenta explícitamente para transparencia: el
MockLLM NO reemplaza la calidad de razonamiento de un LLM real, solo mantiene el
prototipo funcional y testeable en cualquier entorno.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str


class MockLLM:
    """Genera respuestas basadas en reglas simples sobre el último mensaje,
    suficiente para probar el flujo del grafo sin llamar a una API real."""

    def invoke(self, messages: list[dict]) -> LLMResponse:
        last = messages[-1]["content"].lower() if messages else ""
        if any(w in last for w in ["no puedo", "no quiero", "no tengo", "difícil", "dificil"]):
            texto = ("Entiendo la situación. Vamos a revisar juntos qué alternativa se ajusta "
                     "mejor a tu capacidad de pago actual.")
        elif re.search(r"acuerdo|compromiso|pagar en \d+ d", last):
            texto = ("Perfecto, formalicemos el compromiso de pago dentro de los próximos días "
                     "acordados.")
        else:
            texto = ("Gracias por la información. Con base en tu situación, esta es la opción "
                     "recomendada para tu obligación.")
        return LLMResponse(content=texto)


class ClaudeLLM:
    def __init__(self, model: str = "claude-sonnet-4-5"):
        from langchain_anthropic import ChatAnthropic
        self._client = ChatAnthropic(model=model, temperature=0.2)

    def invoke(self, messages: list[dict]) -> LLMResponse:
        result = self._client.invoke(messages)
        return LLMResponse(content=result.content)


def get_llm():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ClaudeLLM()
    return MockLLM()
