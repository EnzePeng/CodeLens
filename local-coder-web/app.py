"""
local-coder-web - Local offline AI coding assistant with Agent capabilities.
Main application entry point.
"""
from __future__ import annotations

import os

from config import APP_DIR
from logger import logger
from models import state
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Optional: ONNX embedding model (load early)
# ---------------------------------------------------------------------------
MODEL_DIR = APP_DIR / "models" / "bge-small-zh-v1.5"
_ort_session = None
_ort_tokenizer = None


def _try_load_onnx_model() -> bool:
    """Load ONNX embedding model if available."""
    global _ort_session, _ort_tokenizer
    onnx_path = MODEL_DIR / "model.onnx"
    tokenizer_path = MODEL_DIR / "tokenizer.json"
    if not onnx_path.exists() or not tokenizer_path.exists():
        return False
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        _ort_session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        _ort_tokenizer = Tokenizer.from_file(str(tokenizer_path))
        _ort_tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=512)
        _ort_tokenizer.enable_truncation(max_length=512)
        logger.info(f"[Embedding] ONNX model loaded from {onnx_path}")
        return True
    except Exception as exc:
        logger.warning(f"[Embedding] ONNX load failed ({exc}), using BM25 fallback")
        return False


_onnx_available = _try_load_onnx_model()


def get_onnx_session():
    """Get ONNX session. Called by routes to access the loaded session."""
    return _ort_session, _ort_tokenizer


# Set ONNX session in search service
if _ort_session and _ort_tokenizer:
    from services.search import set_onnx_session
    set_onnx_session(_ort_session, _ort_tokenizer)


app = FastAPI(title="Local Coder Web")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


# Import routes AFTER app is created (avoids circular imports)
from routes import router  # noqa: E402
app.include_router(router)


# ---------------------------------------------------------------------------
# Startup hook: reload saved folder state
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """On startup, try to restore the saved folder if it exists."""
    try:
        folder = state.root
        if folder and folder.exists():
            logger.info(f"[Startup] Restoring folder: {folder}")
            # Don't auto-reindex on startup to avoid blocking
    except Exception as exc:
        logger.warning(f"[Startup] Could not restore folder: {exc}")


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    uvicorn.run("app:app", host=host, port=port, reload=False)
