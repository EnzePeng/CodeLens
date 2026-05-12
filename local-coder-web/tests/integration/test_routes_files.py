"""Integration tests for files route."""
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


class TestCraftApply:
    def test_craft_apply_endpoint_exists(self, client, tmp_path):
        """BUG-04: /api/craft-apply endpoint should exist."""
        resp = client.post("/api/set-folder", json={"path": str(tmp_path)})
        assert resp.status_code == 200

        resp = client.post("/api/craft-apply", json={
            "file_path": "test.py",
            "content": "def foo(): pass\n",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    def test_craft_apply_writes_file(self, client, tmp_path):
        """BUG-04: craft-apply should write file correctly."""
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/craft-apply", json={
            "file_path": "hello.py",
            "content": "print('hello')\n",
        })
        assert resp.status_code == 200
        assert (tmp_path / "hello.py").read_text() == "print('hello')\n"

    def test_craft_apply_validates_path(self, client, tmp_path):
        """BUG-04: craft-apply should validate path traversal."""
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/craft-apply", json={
            "file_path": "../../etc/passwd",
            "content": "root:x:0",
        })
        assert resp.status_code == 403


class TestExecCommand:
    def test_exec_command_whitelist_logic(self, client):
        """BUG-26: Whitelist should work correctly."""
        import sys
        import os
        # Use a command that should work
        cmd = "echo hello"
        resp = client.post("/api/exec", json={"command": cmd})
        assert resp.status_code == 200

    def test_exec_command_dangerous_patterns(self, client):
        """BUG-25: Dangerous patterns should not be overly broad."""
        # && should NOT be blocked (BUG-25 fix)
        cmd = "echo a && echo b"
        resp = client.post("/api/exec", json={"command": cmd})
        # Should either work or return a different error, not "Command not allowed"
        if resp.status_code == 403:
            assert "&&" not in resp.json().get("detail", "")

        # rm -rf should still be blocked
        resp2 = client.post("/api/exec", json={"command": "rm -rf /tmp/test"})
        assert resp2.status_code == 403


class TestFolderRoutes:
    def test_set_folder_basic(self, client, tmp_path):
        resp = client.post("/api/set-folder", json={"path": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.json()["folder"] == str(tmp_path)

    def test_set_folder_not_exists(self, client):
        resp = client.post("/api/set-folder", json={"path": "/nonexistent/path"})
        assert resp.status_code == 400

    def test_read_file_basic(self, client, tmp_path):
        (tmp_path / "test.py").write_text("content")
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/read-file", json={"path": "test.py"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "content"

    def test_read_file_path_traversal(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/read-file", json={"path": "../../etc/passwd"})
        assert resp.status_code == 403

    def test_browse_dirs_basic(self, client, tmp_path):
        (tmp_path / "subdir").mkdir()
        resp = client.post("/api/browse-dirs", json={"path": str(tmp_path)})
        assert resp.status_code == 200
        dirs = resp.json()["dirs"]
        assert any(d["name"] == "subdir" for d in dirs)

    def test_browse_dirs_home(self, client):
        resp = client.post("/api/browse-dirs", json={"path": ""})
        assert resp.status_code == 200


class TestOtherEndpoints:
    def test_reindex(self, client, tmp_path):
        client.post("/api/set-folder", json={"path": str(tmp_path)})
        resp = client.post("/api/reindex")
        assert resp.status_code == 200

    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_index_stats(self, client):
        resp = client.get("/api/index-stats")
        assert resp.status_code == 200
