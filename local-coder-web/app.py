"""
local-coder-web — Main application entry point.

Improvements:
- #61 Connection pooling via shared httpx.AsyncClient in http_service.py
- #65 HTTP caching headers via middleware
- #77 CORS headers
- #83 Health check moved to routes
- #85 Graceful shutdown with signal handling
"""
from __future__ import annotations

import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from config import APP_DIR
from logger import logger
from models import state

# ---- Optional ONNX model loading ----

MODEL_DIR = APP_DIR / "models" / "bge-small-zh-v1.5"
_ort_session = None
_ort_tokenizer = None


def _try_load_onnx_model() -> bool:
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

        # Set ONNX session in search service
        from services.search import set_onnx_session
        set_onnx_session(_ort_session, _ort_tokenizer)
        return True
    except Exception as exc:
        logger.warning(f"[Embedding] ONNX load failed ({exc}), using BM25 fallback")
        return False


_onnx_available = _try_load_onnx_model()


def get_onnx_session():
    """Get ONNX session."""
    return _ort_session, _ort_tokenizer


# ---- File Watcher (#10) ----

_file_watcher_ref = None


def start_file_watcher_if_available(root: Path):
    """#10 Start file watcher for auto-reindex on file changes."""
    try:
        from services.file_watcher import start_file_watcher

        def on_change(changes):
            logger.info(f"[FileWatcher] {len(changes)} file changes detected, triggering reindex...")
            # Debounce: reindex is triggered by the route, not automatically
            # to avoid excessive reindexing
            pass

        global _file_watcher_ref
        _file_watcher_ref = start_file_watcher(root, on_change)
        logger.info(f"[FileWatcher] Started for: {root}")
    except Exception as e:
        logger.warning(f"[FileWatcher] Failed to start: {e}")


def stop_file_watcher():
    """Stop file watcher on shutdown."""
    global _file_watcher_ref
    if _file_watcher_ref:
        try:
            from services.file_watcher import stop_file_watcher as stop_w
            stop_w()
            logger.info("[FileWatcher] Stopped")
        except Exception as e:
            logger.warning(f"[FileWatcher] Stop failed: {e}")


# ---- HTTP Service (#61 connection pooling) ----

_http_client = None


def get_http_client():
    """#61 Shared httpx.AsyncClient with connection pooling."""
    global _http_client
    if _http_client is None:
        _http_client = __import__('httpx').AsyncClient(timeout=300)
    return _http_client


async def close_http_client():
    """Close shared httpx client."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


# ---- Lifespan (replaces startup/shutdown events) ----

@asynccontextmanager
async def lifespan(app):
    """Graceful startup and shutdown."""
    # Startup
    try:
        folder = state.root
        if folder and folder.exists():
            logger.info(f"[Startup] Restoring folder: {folder}")
    except Exception as exc:
        logger.warning(f"[Startup] Could not restore folder: {exc}")

    yield

    # Shutdown
    logger.info("[Shutdown] Closing resources...")
    stop_file_watcher()
    await close_http_client()
    logger.info("[Shutdown] Done")


# ---- FastAPI App ----

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="CodeLens", version="0.3.1", lifespan=lifespan)

# #77 CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/") and path.endswith(('.js', '.css', '.html')):
            response.headers["cache-control"] = "no-cache, no-store, must-revalidate"
            response.headers["pragma"] = "no-cache"
            response.headers["expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

# Import routes AFTER app is created
from routes import router as main_router  # noqa: E402
app.include_router(main_router)


# ---- Signal handling for graceful shutdown (#85) ----

def _handle_signal(signum, frame):
    logger.info(f"[Shutdown] Received signal {signum}, shutting down gracefully...")
    sys.exit(0)


if sys.platform == "win32":
    signal.signal(signal.SIGBREAK, _handle_signal)
else:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    uvicorn.run("app:app", host=host, port=port, reload=False)
