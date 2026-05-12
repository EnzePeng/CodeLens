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
