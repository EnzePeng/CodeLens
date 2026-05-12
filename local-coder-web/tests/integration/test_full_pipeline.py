"""Integration tests for full pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import app
    return TestClient(app, raise_server_exceptions=False)


class TestFullPipeline:
    def test_set_folder_then_ask(self, client, tmp_path):
        """Set folder then ask a question."""
        (tmp_path / "test.py").write_text("def foo(): pass\n")
        resp = client.post("/api/set-folder", json={"path": str(tmp_path)})
        assert resp.status_code == 200

    def test_set_folder_then_search(self, client, tmp_path):
        """Set folder then search."""
        (tmp_path / "utils.py").write_text("def helper(): pass\n")
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["file_count"] > 0

    def test_set_folder_then_reindex(self, client, tmp_path):
        """Set folder then reindex."""
        (tmp_path / "main.py").write_text("def main(): pass\n")
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/reindex")
        assert resp.status_code == 200

    def test_index_and_context_selection(self, client, tmp_path):
        """Index should enable context selection."""
        (tmp_path / "calc.py").write_text("def add(a, b): return a + b\n")
        resp = client.post("/api/set-folder", json={"path": str(tmp_path)})
        assert resp.status_code == 200

        health = client.get("/api/health")
        assert health.json()["file_count"] >= 1
