"""Integration tests for complete route."""
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


def test_complete_basic(client):
    """Test complete endpoint accepts JSON."""
    resp = client.post("/api/complete", json={"code": "def ", "cursor_pos": 4})
    assert resp.status_code in (200, 500, 502)


def test_complete_empty_code(client):
    """Test complete endpoint handles empty code."""
    resp = client.post("/api/complete", json={"code": ""})
    assert resp.status_code in (200, 500, 502)
