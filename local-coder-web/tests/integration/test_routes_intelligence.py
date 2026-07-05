from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    from app import app

    return TestClient(app, raise_server_exceptions=False)


def test_index_start_status_project_brief_and_file_lens(client, tmp_path):
    (tmp_path / "app.py").write_text(
        "from services.worker import run_job\n\n"
        "def main():\n"
        "    return run_job()\n",
        encoding="utf-8",
    )
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "worker.py").write_text(
        "def run_job():\n    return 42\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_worker.py").write_text(
        "from services.worker import run_job\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    start = client.post("/api/index/start", json={"path": str(tmp_path)})
    assert start.status_code == 200
    job = start.json()
    assert job["stage"] == "complete"
    assert job["graph_ready"] is True
    assert job["brief_ready"] is True

    status = client.get(f"/api/index/status/{job['job_id']}")
    assert status.status_code == 200
    assert status.json()["progress"] == 1.0

    brief = client.get("/api/project/brief")
    assert brief.status_code == 200
    assert brief.json()["modules"]
    assert brief.json()["evidence"]

    lens = client.post("/api/file-lens", json={"path": "services/worker.py", "depth": 2})
    assert lens.status_code == 200
    body = lens.json()
    assert any(item["path"] == "app.py" for item in body["imported_by"])
    assert any(item["path"] == "tests/test_worker.py" for item in body["related_tests"])


def test_ask_stream_emits_context_plan_evidence_and_confidence(client, tmp_path):
    (tmp_path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    client.post("/api/set-folder", json={"path": str(tmp_path)})

    resp = client.post("/api/ask", json={"question": "main 是什么？", "mode": "ask"})

    assert resp.status_code in (200, 502)
    events = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    event_types = {event.get("type") for event in events}
    assert "context_plan" in event_types
    assert "evidence" in event_types
    assert "confidence" in event_types
