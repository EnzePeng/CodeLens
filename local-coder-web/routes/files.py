"""
Files routes — /api/read-file, /api/exec, /api/browse-dirs, /api/set-folder, /api/reindex.

Improvements over v0.3:
- #11,#12,#39 Uses new indexer with parallel scan + incremental update
- #6,#7 dep_graph stored in state
- #83 Health check endpoint
- #84 Index stats endpoint
- #10 File watcher triggers reindex
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import APP_DIR, IGNORE_DIRS, CODE_EXTS, MAX_FILE_BYTES, MAX_INDEX_FILES
from models import state, HealthResponse, IndexStatsResponse
from services.indexer import index_folder, build_tree, scan_repo
from services.search import _search_cache

router = APIRouter()


class FolderRequest(BaseModel):
    path: str


class ReadFileRequest(BaseModel):
    path: str


class BrowseRequest(BaseModel):
    path: str = ""


class ExecRequest(BaseModel):
    command: str
    cwd: str = ""


# ---- Helpers ----

def _get_onnx():
    import app as _app_module
    return _app_module.get_onnx_session()


# ---- Routes ----

@router.get("/api/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """#83 Health check endpoint."""
    import app as _app_module
    ort_sess, _ = _app_module.get_onnx_session()
    return HealthResponse(
        folder=str(state.root) if state.root else "",
        file_count=len(state.files),
        embedding_mode="onnx" if (ort_sess is not None and state.embedding_ready) else "bm25",
        search_cache=_search_cache.stats(),
    )


@router.get("/api/index-stats", response_model=IndexStatsResponse)
def index_stats() -> IndexStatsResponse:
    """#84 Index statistics endpoint."""
    import app as _app_module
    ort_sess, _ = _app_module.get_onnx_session()
    return IndexStatsResponse(
        file_count=len(state.files),
        embedding_mode="onnx" if (ort_sess is not None and state.embedding_ready) else "bm25",
        search_cache=_search_cache.stats(),
    )


@router.post("/api/set-folder")
def set_folder(req: FolderRequest) -> dict:
    """#11,#12,#39 Set workspace folder using new indexer."""
    root = Path(req.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="Folder does not exist")

    result = index_folder(root)
    state.root = root
    state.files = result["files"]
    state.tree = result["tree"]
    state.idf = result["idf"]
    state.avg_dl = result["avg_dl"]
    state.dep_graph = result.get("dep_graph")
    state.embedding_ready = result["embedding_mode"] == "onnx"

    return {
        "folder": str(root),
        "file_count": result["file_count"],
        "tree": json.dumps(result["tree"]),
        "embedding_mode": result["embedding_mode"],
        "index_time": result.get("index_time", 0),
        "mode": result.get("mode", "full"),
    }


@router.post("/api/reindex")
def reindex() -> dict:
    """#11,#12,#39 Reindex current folder."""
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    result = index_folder(state.root)
    state.files = result["files"]
    state.tree = result["tree"]
    state.idf = result["idf"]
    state.avg_dl = result["avg_dl"]
    state.dep_graph = result.get("dep_graph")
    state.embedding_ready = result["embedding_mode"] == "onnx"

    return {
        "folder": str(state.root),
        "file_count": result["file_count"],
        "tree": json.dumps(result["tree"]),
        "embedding_mode": result["embedding_mode"],
        "index_time": result.get("index_time", 0),
    }


@router.post("/api/read-file")
def read_file(req: ReadFileRequest) -> dict:
    """Read a file with path traversal protection (#122)."""
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    target = (state.root / req.path).resolve()
    try:
        target.relative_to(state.root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path is outside the repository root")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Read failed: {exc}") from exc

    return {
        "path": req.path,
        "name": target.name,
        "ext": target.suffix.lower(),
        "size": target.stat().st_size,
        "content": content,
    }


@router.post("/api/browse-dirs")
def browse_dirs(req: BrowseRequest) -> dict:
    base = Path(req.path).expanduser().resolve() if req.path else Path.home()
    if not base.exists() or not base.is_dir():
        base = Path.home()

    dirs: list[dict] = []
    try:
        for entry in sorted(base.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.is_dir() and not entry.name.startswith(".") and entry.name not in IGNORE_DIRS:
                try:
                    dirs.append({"name": entry.name, "path": str(entry)})
                except OSError:
                    continue
    except OSError:
        pass

    return {
        "current": str(base),
        "parent": str(base.parent) if str(base) != str(base.parent) else "",
        "dirs": dirs,
    }


@router.post("/api/exec")
def exec_command(req: ExecRequest) -> dict:
    """#73 Command execution with whitelist and safety checks."""
    from config import DANGEROUS_PATTERNS

    # Dangerous pattern check
    cmd_lower = req.command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            raise HTTPException(status_code=403, detail="Command not allowed for security reasons")

    # Whitelist: exact match or prefix match for multi-word commands
    cmd_basename = req.command.split()[0].lower().split("\\")[-1].split("/")[-1] if req.command.strip() else ""
    allowed = {
        "python", "python3", "pip", "pip3",
        "node", "npm", "npx", "git",
        "dir", "type", "echo", "copy", "xcopy",
        "ls", "cat", "touch", "mkdir", "cp", "mv", "rm",
        "pytest", "nosetests", "go", "rustc", "cargo",
        "dotnet", "powershell", "pwsh",
    }
    if cmd_basename and cmd_basename not in allowed and not any(
        cmd_basename == a or cmd_basename.startswith(a + " ") or a.startswith(cmd_basename + " ")
        for a in allowed
    ):
        raise HTTPException(status_code=403, detail=f"Command '{cmd_basename}' not allowed")

    # Reject shell metacharacters
    import re
    if not re.match(r'^[\w./ -]+$', req.command.strip()):
        raise HTTPException(status_code=403, detail="Command contains disallowed characters")

    cwd = req.cwd if req.cwd else str(APP_DIR)

    try:
        result = subprocess.run(
            req.command, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=60,
        )
        return {
            "stdout": result.stdout[:50000],
            "stderr": result.stderr[:10000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Command timed out after 60 seconds")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(exc)}")
