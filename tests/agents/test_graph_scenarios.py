"""
Pruebas de integración end-to-end sobre el grafo completo de agentes, una por
cada escenario pedido en el enunciado de la prueba. Usan el MockLLM (no
requieren ANTHROPIC_API_KEY) para que sean reproducibles en cualquier entorno.
"""
import pytest

from src.agents.graph.collections_graph import build_graph
from src.agents.tools.customer_store import CustomerStore

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def app():
    return build_graph(CustomerStore())


def run(app, obligacion_id, mensaje=None):
    store = CustomerStore()
    raw = store.get_raw(obligacion_id)
    mensaje = mensaje if mensaje is not None else (raw or {}).get("mensaje_cliente")
    return app.invoke({"obligacion_id": obligacion_id, "mensaje_cliente": mensaje, "trace": []})


def test_mora_temprana_alta_propension_ofrece_acuerdo(app):
    result = run(app, "OB-001")
    assert result["accion"].tipo == "acuerdo_pago"
    assert result["requiere_escalamiento"] is False


def test_multiples_opciones_elige_una_y_explica(app):
    result = run(app, "OB-002")
    assert result["accion"].tipo == "opcion_pago"
    assert result["accion"].alternativa is not None
    assert result["accion"].justificacion  # debe venir con explicación


def test_no_elegible_por_cooldown_no_ofrece_opcion_de_pago_nueva(app):
    result = run(app, "OB-003")
    # El cooldown bloquea una NUEVA opción de pago; el sistema puede seguir
    # ofreciendo un acuerdo de pago (mecanismo distinto, no sujeto a ese cooldown),
    # pero nunca debe ofrecer otra opción de pago formal mientras el cooldown esté activo.
    assert result["accion"].tipo != "opcion_pago"
    assert result["decision_elegibilidad"].opciones_pago_elegibles == []


def test_incumplimiento_previo_no_bloquea_pero_se_registra(app):
    result = run(app, "OB-004")
    # Puede seguir siendo elegible para una opción de pago formal, pero no debería
    # priorizarse un nuevo acuerdo de pago tras un incumplimiento reciente.
    assert result["accion"].tipo != "acuerdo_pago"


def test_contacto_reactivo_dificultad_de_pago(app):
    result = run(app, "OB-005")
    assert result["requiere_escalamiento"] is False
    assert result["accion"].tipo in ("opcion_pago", "acuerdo_pago")


def test_informacion_incompleta_escala(app):
    result = run(app, "OB-006")
    assert result["requiere_escalamiento"] is True


def test_intento_de_manipulacion_escala_y_no_ofrece_descuento(app):
    result = run(app, "OB-007")
    assert result["requiere_escalamiento"] is True
    assert "descuento" not in result["respuesta_agente"].lower()


def test_solicitud_sensible_escala_a_humano(app):
    result = run(app, "OB-008")
    assert result["requiere_escalamiento"] is True


def test_restriccion_legal_no_ofrece_nada(app):
    result = run(app, "OB-009")
    assert result["requiere_escalamiento"] is True  # datos con restricción -> se prefiere revisión humana


def test_obligacion_inexistente_no_crashea_y_escala(app):
    result = run(app, "OB-999", mensaje="Hola, tengo una pregunta")
    assert result["requiere_escalamiento"] is True
    assert result["respuesta_agente"]  # siempre debe responder algo, nunca crashear


def test_trace_registra_todos_los_pasos(app):
    result = run(app, "OB-001")
    nodos = [t["nodo"] for t in result["trace"]]
    assert "fetch_state" in nodos
    assert "guardrails" in nodos
    assert len(nodos) >= 3  # trazabilidad mínima end-to-end


def test_fallo_del_llm_degrada_a_escalamiento_no_crashea(monkeypatch):
    """Si el LLM real falla (timeout, rate-limit, API caída), el grafo no debe
    propagar la excepción: debe degradar a escalamiento con una respuesta genérica."""
    import src.agents.graph.collections_graph as graph_module

    class LLMQueFalla:
        def invoke(self, messages):
            raise RuntimeError("timeout simulado")

    monkeypatch.setattr(graph_module, "get_llm", lambda: LLMQueFalla())
    app_con_fallo = graph_module.build_graph(CustomerStore())

    result = run(app_con_fallo, "OB-001")  # caso que normalmente llega a `respond`
    assert result["requiere_escalamiento"] is True
    assert result["respuesta_agente"]  # sigue devolviendo algo, nunca crashea
    nodos = [t["nodo"] for t in result["trace"]]
    assert nodos[-2:] == ["respond", "escalate_human"]


def test_solicitud_sensible_se_etiqueta_como_sensible(app):
    # OB-008 amenaza con demanda y a la vez pide condonación: debe llegar al gestor
    # como contenido sensible, no como manipulación.
    result = run(app, "OB-008")
    assert "sensible" in result["razon_escalamiento"].lower()
