"""
Main API routes — serve UI, status, settings.
Ask/craft/file/agent endpoints live in their own route modules.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from config import APP_DIR, SYSTEM_PROMPTS, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from models import state

router = APIRouter()

# Lazy ONNX session accessor
def _get_onnx():
    import app as _app_module
    return _app_module.get_onnx_session()


@router.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@router.get("/api/status")
def status() -> dict[str, Any]:
    ort_sess, _ = _get_onnx()
    return {
        "folder": str(state.root) if state.root else "",
        "file_count": len(state.files),
        "tree": state.tree,  # Already a dict, no need for json.dumps
        "embedding_mode": "onnx" if (ort_sess is not None and state.embedding_ready) else "bm25",
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
