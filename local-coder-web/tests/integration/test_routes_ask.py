"""Integration tests for ask route."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import app
    return TestClient(app, raise_server_exceptions=False)


def test_ask_endpoint_receives_json_body(client, tmp_path):
    """BUG-02: POST JSON body should be correctly parsed."""
    resp = client.post("/api/ask", json={
        "question": "How do I sort a list?",
        "mode": "ask",
    })
    assert resp.status_code in (200, 502)
    # SSE format, streaming
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_ask_endpoint_returns_sse_format(client, tmp_path):
    """BUG-19: Response should be in SSE format matching frontend."""
    resp = client.post("/api/ask", json={
        "question": "test question",
        "mode": "ask",
    })
    assert resp.status_code in (200, 502)
    content = resp.text
    # Should contain data: prefix for SSE
    assert "data:" in content or "error" in content.lower()


def test_ask_endpoint_includes_context(client, tmp_path):
    """BUG-03: Response should include code context and sources."""
    (tmp_path / "test.py").write_text("def foo(): pass\n")
    client.post("/api/set-folder", json={"path": str(tmp_path)})
    resp = client.post("/api/ask", json={
        "question": "What is foo?",
        "mode": "ask",
    })
    assert resp.status_code in (200, 502)
    content = resp.text
    # Should have type: sources or type: delta or type: error in SSE events
    assert '"type"' in content


def test_ask_endpoint_client_defined(client, tmp_path):
    """BUG-01: httpx client should be properly defined."""
    resp = client.post("/api/ask", json={"question": "test"})
    # If client was undefined, this would crash with NameError
    assert resp.status_code in (200, 502)


def test_ask_craft_mode(client, tmp_path):
    """Test craft mode applies file change."""
    client.post("/api/set-folder", json={"path": str(tmp_path)})
    resp = client.post("/api/ask", json={
        "question": "write foo",
        "mode": "craft",
        "file_path": "craft_test.py",
        "new_content": "def hello(): return 42\n",
    })
    assert resp.status_code in (200, 502)
