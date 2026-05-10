"""
Main API routes — serve UI, status, settings.

Improvements:
- #77 CORS headers (in app.py)
- #83 Health check moved to files.py
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from config import APP_DIR, SYSTEM_PROMPTS, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from models import state

router = APIRouter()


@router.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@router.get("/api/status")
def status() -> dict[str, Any]:
    import app as _app_module
    ort_sess, _ = _app_module.get_onnx_session()
    return {
        "folder": str(state.root) if state.root else "",
        "file_count": len(state.files),
        "tree": state.tree,
        "embedding_mode": "onnx" if (ort_sess is not None and state.embedding_ready) else "bm25",
        "search_cache": __import__('services.search', fromlist=['_search_cache'])._search_cache.stats(),
    }


@router.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return {
        "system_prompts": SYSTEM_PROMPTS,
        "defaults": {
            "max_tokens": DEFAULT_MAX_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
        },
    }
