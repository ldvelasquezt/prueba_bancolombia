# Sistema agéntico de cobranza

Prototipo funcional de agentes coordinados para gestionar proactiva y
reactivamente clientes en mora, ofreciendo únicamente acuerdos u opciones de
pago para los que el cliente sea elegible.

Ver [docs/arquitectura/sistema_agentico.md](../../docs/arquitectura/sistema_agentico.md)
para la arquitectura completa.

## Quickstart

```bash
# Demo end-to-end sobre 9 escenarios sintéticos (no requiere API key)
python -m src.agents.run_demo

# Tests (unitarios + integración)
pytest tests/agents -v
```

## Con un LLM real

Si se exporta `ANTHROPIC_API_KEY`, `src/agents/llm_client.py` usa Claude de
verdad para el nodo `respond` (redacción de la respuesta al cliente). Sin la
key, usa un `MockLLM` determinístico para que el grafo completo sea
reproducible y testeable en cualquier entorno.

```bash
$env:ANTHROPIC_API_KEY = "sk-..."
python -m src.agents.run_demo
```

## Datos sintéticos

`data/synthetic/customer_profiles.json` contiene 9 perfiles cliente-obligación
sintéticos (identificados como tales, sin información personal real), uno por
cada escenario relevante del enunciado de la prueba: mora temprana con alta
propensión, múltiples opciones elegibles, cooldown activo, incumplimiento
previo, contacto reactivo, datos incompletos, intento de manipulación,
solicitud sensible y restricción legal activa.
