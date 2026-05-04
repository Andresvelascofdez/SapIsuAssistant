"""UI control visibility tests for high-friction actions."""
from src.shared.client_manager import ClientManager


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps

    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
    ClientManager(tmp_path).register_client("TST", "Test Client")

    from src.web.app import app
    from starlette.testclient import TestClient

    c = TestClient(app)
    c.post("/api/session/client", json={"code": "TST"})
    return c


def test_chat_page_has_visible_delete_chat_controls(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/chat")

    assert resp.status_code == 200
    assert "Delete Chat" in resp.text
    assert "deleteActiveSession()" in resp.text
    assert "Delete chat" in resp.text


def test_incidents_page_has_explicit_search_controls(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/incidents")

    assert resp.status_code == 200
    assert "Buscar" in resp.text
    assert "Limpiar" in resp.text
