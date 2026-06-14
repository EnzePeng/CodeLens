"""Integration tests for agent route."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import app
    return TestClient(app, raise_server_exceptions=False)


class TestAgentRoutes:
    def test_agent_start(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/agent/start", json={"query": "Fix bug"})
        assert resp.status_code == 200
        assert "task_id" in resp.json()

    def test_agent_status(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        start_resp = client.post("/api/agent/start", json={"query": "test"})
        task_id = start_resp.json()["task_id"]
        resp = client.get(f"/api/agent/status/{task_id}")
        assert resp.status_code == 200

    def test_agent_stop(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        start_resp = client.post("/api/agent/start", json={"query": "test"})
        task_id = start_resp.json()["task_id"]
        resp = client.post(f"/api/agent/stop/{task_id}")
        assert resp.status_code == 200

    def test_agent_list_tools(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.get("/api/agent/tools")
        assert resp.status_code == 200
        assert "tools" in resp.json()

    def test_agent_tasks_list(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        client.post("/api/agent/start", json={"query": "test1"})
        client.post("/api/agent/start", json={"query": "test2"})
        resp = client.get("/api/agent/tasks")
        assert resp.status_code == 200
        assert len(resp.json()["tasks"]) >= 2

    def test_agent_pause_resume(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        start_resp = client.post("/api/agent/start", json={"query": "test pause"})
        task_id = start_resp.json()["task_id"]
        pause = client.post(
            "/api/agent/action",
            json={"task_id": task_id, "action": "pause"},
        )
        assert pause.status_code == 200
        assert pause.json().get("status") == "paused"
        resume = client.post(
            "/api/agent/action",
            json={"task_id": task_id, "action": "resume"},
        )
        assert resume.status_code == 200
        assert resume.json().get("status") == "running"

    def test_translate_event_passes_subtask_events(self):
        """A1: subtask_start/subtask_done must NOT be downgraded to 'info'."""
        from routes.agent import _translate_event

        class _Ev:
            def __init__(self, type, data):
                self.type = type
                self.data = data

        # subtask_start should be forwarded with its own type
        ev = _Ev("subtask_start", {"id": "s1", "description": "read file", "kind": "read"})
        payload = _translate_event(ev)
        assert payload is not None
        assert payload["type"] == "subtask_start"
        assert payload["data"]["id"] == "s1"

        # subtask_done should be forwarded with its own type
        ev = _Ev("subtask_done", {"id": "s1", "status": "success", "summary": "ok"})
        payload = _translate_event(ev)
        assert payload is not None
        assert payload["type"] == "subtask_done"
        assert payload["data"]["status"] == "success"

    def test_translate_event_passes_iteration_start(self):
        """D3: iteration_start should be forwarded (not silently dropped)."""
        from routes.agent import _translate_event

        class _Ev:
            def __init__(self, type, data):
                self.type = type
                self.data = data

        ev = _Ev("iteration_start", {"iteration": 2})
        payload = _translate_event(ev)
        assert payload is not None
        assert payload["type"] == "iteration_start"

    def test_translate_event_drops_internal_events(self):
        """Internal-only events (stopped) should still be dropped."""
        from routes.agent import _translate_event

        class _Ev:
            def __init__(self, type, data):
                self.type = type
                self.data = data

        assert _translate_event(_Ev("stopped", {"reason": "x"})) is None

    def test_list_tasks_returns_extended_fields(self, client, tmp_path):
        """E4: list_tasks should include phase, updated_at, result_preview."""
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        client.post("/api/agent/start", json={"query": "task with fields"})
        resp = client.get("/api/agent/tasks")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert len(tasks) >= 1
        t = tasks[0]
        for field in ("phase", "updated_at", "result_preview", "step_count"):
            assert field in t, f"missing field {field}"

    def test_action_no_longer_supports_confirm_reject(self, client, tmp_path):
        """C3: confirm/reject (legacy diff approval) should fall through to default."""
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        start_resp = client.post("/api/agent/start", json={"query": "test"})
        task_id = start_resp.json()["task_id"]
        # confirm with a tool_call_id — legacy path removed, should return current status
        resp = client.post(
            "/api/agent/action",
            json={"task_id": task_id, "action": "confirm", "tool_call_id": "some/file.py"},
        )
        assert resp.status_code == 200
        # Should return the task's current status, not "approved"
        assert resp.json().get("status") != "approved"

    def test_start_task_accepts_max_steps(self, client, tmp_path):
        """D6: start_task should accept and store max_steps."""
        from core.engine import get_engine

        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/agent/start", json={"query": "capped task", "max_steps": 5})
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]
        engine = get_engine()
        handle = engine._handles.get(task_id)
        assert handle is not None
        assert handle.max_steps == 5

    def test_react_config_capped_by_max_steps(self):
        """G1: ReActConfig.capped() should apply max_steps as the iteration limit."""
        from core.react import ReActConfig

        # Default is 15; capping at 5 should yield 5
        cfg = ReActConfig().capped(5)
        assert cfg.max_iterations == 5

        # No cap → stays at default 15
        cfg = ReActConfig().capped(None)
        assert cfg.max_iterations == 15

        # Cap larger than default → stays at default (min)
        cfg = ReActConfig().capped(100)
        assert cfg.max_iterations == 15

        # Zero/negative cap → ignored (stays at default)
        cfg = ReActConfig().capped(0)
        assert cfg.max_iterations == 15

    def test_react_config_no_legacy_factory_methods(self):
        """G1: for_simple/for_subtask/for_root factory methods should be removed."""
        from core.react import ReActConfig

        assert not hasattr(ReActConfig, "for_simple")
        assert not hasattr(ReActConfig, "for_subtask")
        assert not hasattr(ReActConfig, "for_root")

    def test_engine_config_no_default_max_iterations(self):
        """G4: EngineConfig.default_max_iterations should be removed (was unused)."""
        from core.engine import EngineConfig

        assert not hasattr(EngineConfig(), "default_max_iterations")
