# Sistema agéntico de cobranza

Prototipo de agentes coordinados para gestionar clientes en mora. Atiende las dos puntas:
la campaña saliente y el cliente que escribe por su cuenta. Lo que no quería es que le
ofreciera un acuerdo o una opción de pago a alguien que no es elegible, así que esa
decisión no pasa por el LLM.

La arquitectura está en
[docs/arquitectura/sistema_agentico.md](../../docs/arquitectura/sistema_agentico.md).

## Para probarlo

```bash
# Demo de punta a punta sobre los 9 escenarios sintéticos. No necesita API key
python -m src.agents.run_demo

# Las pruebas
pytest tests/agents -v
```

## Si quiere correrlo contra Claude

Cuando existe `ANTHROPIC_API_KEY`, `src/agents/llm_client.py` llama al modelo real para el
nodo `respond`, que redacta la respuesta al cliente. Sin la key usa un `MockLLM`
determinístico, para que el grafo se pueda correr y probar en cualquier máquina.

```bash
$env:ANTHROPIC_API_KEY = "sk-..."
python -m src.agents.run_demo
```

## Los datos sintéticos

`data/synthetic/customer_profiles.json` tiene 9 perfiles cliente-obligación inventados, sin
información personal real. Cubren los escenarios del enunciado: mora temprana con alta
propensión, varias opciones elegibles al tiempo, cooldown activo, incumplimiento previo,
contacto reactivo, datos incompletos, intento de manipulación, solicitud sensible y
restricción legal vigente.
