"""F015 server tests — control surface, memory delete, and the /ws invoker
wiring. The Pipecat pipeline itself is exercised by test_pipeline.py; here we
test what the FastAPI app owns."""

import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.graph.state import new_session_state
from app.server.main import app


@pytest.fixture()
def client():
    # No context manager: skip lifespan (init_db) so TestClient's own event
    # loop never touches the pytest-loop-bound engine cache.
    return TestClient(app)


def test_control_surface_serves_crisis_resources(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert settings.crisis_helpline_number in html
    assert "Tele-MANAS" in html
    assert "voice" in html.lower()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_delete_history_endpoint(client, monkeypatch):
    import app.server.main as main

    calls = []

    async def fake_delete(pid, database_url=None):
        calls.append(pid)

    monkeypatch.setattr(main, "delete_participant", fake_delete)
    resp = client.post("/participant/p-abc/delete")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "participant_id": "p-abc"}
    assert calls == ["p-abc"]


@pytest.mark.asyncio
async def test_make_graph_invoker_runs_turn_graph(monkeypatch):
    """The invoker compiles + runs the turn graph (fake graph injected)."""
    import app.server.main as main
    from app.graph.state import make_thread_id

    class _FakeGraph:
        async def ainvoke(self, state, config=None):
            return {"response": "ok", "phase": "deepening"}

    monkeypatch.setattr(main, "build_turn_graph", lambda checkpointer=None: _FakeGraph())

    pid = "invoker-test"
    invoker = main.make_graph_invoker(pid, 1)
    state = new_session_state(patient_utterance="hello")
    result = await invoker(make_thread_id(pid, 1), state)
    assert result["response"] == "ok"
