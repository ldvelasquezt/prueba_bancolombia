"""
Corre los escenarios sintéticos a través del grafo completo e imprime, para
cada uno, la traza de decisión y la respuesta generada. Sirve como demo
funcional end-to-end y como evidencia de trazabilidad.

Uso:
    python -m src.agents.run_demo
"""
from src.agents.graph.collections_graph import build_graph
from src.agents.tools.customer_store import CustomerStore


def main():
    store = CustomerStore()
    app = build_graph(store)

    for obligacion_id in store.list_ids():
        raw = store.get_raw(obligacion_id)
        result = app.invoke({
            "obligacion_id": obligacion_id,
            "mensaje_cliente": raw.get("mensaje_cliente"),
            "trace": [],
        })

        print("=" * 90)
        print(f"[{obligacion_id}] {raw.get('escenario')}")
        print(f"Mensaje cliente: {raw.get('mensaje_cliente')}")
        print(f"Escalamiento: {result.get('requiere_escalamiento')}"
              + (f" ({result.get('razon_escalamiento')})" if result.get("requiere_escalamiento") else ""))
        if result.get("accion"):
            print(f"Acción: {result['accion'].tipo} | {result['accion'].justificacion}")
        print(f"Respuesta: {result.get('respuesta_agente')}")
        print("Traza:")
        for ev in result.get("trace", []):
            print(f"  - {ev['nodo']}: {ev['detalle']}")


if __name__ == "__main__":
    main()
