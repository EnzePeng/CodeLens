"""
Files routes — /api/read-file, /api/exec, /api/browse-dirs, /api/set-folder, /api/reindex.
"""
from __future__ import annotations

import json
import os
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import (
    APP_DIR, IGNORE_DIRS, CODE_EXTS, MAX_FILE_BYTES,
    MAX_INDEX_FILES, BM25_K1, BM25_B,
)
from models import state, CodeFile, extract_symbols
from services.search import build_bm25_index, _embed_texts
from services.indexer import build_embeddings

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


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    returncode: int


# ---------------------------------------------------------------------------
# Helpers (moved from main.py)
# ---------------------------------------------------------------------------

def scan_repo(root: Path) -> list[CodeFile]:
    """Scan repository for indexable code files."""
    result: list[CodeFile] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        current_path = Path(current)
        for name in sorted(filenames):
            if len(result) >= MAX_INDEX_FILES:
                return result
            path = current_path / name
            if not should_read_file(path):
                continue
            try:
                size = path.stat().st_size
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            result.append(CodeFile(path=path, rel=rel, size=size, text=text, symbols=extract_symbols(text)))
    return result


def should_read_file(path: Path) -> bool:
    """Check if a file should be read and indexed."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return False
    except OSError:
        return False
    if path.name.startswith(".") and path.name not in {".env.example", ".gitignore"}:
        return False
    return path.suffix.lower() in CODE_EXTS


def build_tree(root: Path, files: list[CodeFile]) -> dict:
    """Build a nested tree structure for the frontend."""
    tree: dict = {"name": root.name, "type": "dir", "path": "", "children": {}}

    for file in files[:2000]:
        parts = Path(file.rel).parts
        node = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                node["children"][part] = {
                    "name": part, "type": "file", "path": file.rel,
                    "size": file.size, "ext": Path(part).suffix.lower(),
                }
            else:
                if part not in node["children"]:
                    sub_path = str(Path(*parts[: i + 1]))
                    node["children"][part] = {
                        "name": part, "type": "dir", "path": sub_path, "children": {},
                    }
                node = node["children"][part]

    def _sort_node(n: dict) -> dict:
        if n["type"] == "file":
            return {k: v for k, v in n.items() if k != "children"}
        child_list = sorted(
            n["children"].values(),
            key=lambda c: (c["type"] != "dir", c["name"].lower()),
        )
        return {
            "name": n["name"], "type": n["type"], "path": n["path"],
            "children": [_sort_node(c) for c in child_list],
        }

    return _sort_node(tree)


def _get_onnx():
    import app as _app_module
    return _app_module.get_onnx_session()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/api/set-folder")
def set_folder(req: FolderRequest) -> dict[str, Any]:
    root = Path(req.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="Folder does not exist")

    files = scan_repo(root)
    state.root = root
    state.files = files
    state.tree = build_tree(root, files)
    idf, avg_dl = build_bm25_index(state.files)
    state.idf = idf
    state.avg_dl = avg_dl

    state.embedding_ready = False
    ort_sess, ort_tok = _get_onnx()
    if ort_sess is not None and ort_tok is not None:
        if build_embeddings(files):
            state.embedding_ready = True

    return {
        "folder": str(root),
        "file_count": len(files),
        "tree": json.dumps(state.tree),
        "embedding_mode": "onnx" if state.embedding_ready else "bm25",
    }


@router.post("/api/reindex")
def reindex() -> dict[str, Any]:
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    files = scan_repo(state.root)
    state.files = files
    state.tree = build_tree(state.root, files)
    idf, avg_dl = build_bm25_index(state.files)
    state.idf = idf
    state.avg_dl = avg_dl

    state.embedding_ready = False
    ort_sess, ort_tok = _get_onnx()
    if ort_sess is not None and ort_tok is not None:
        if build_embeddings(files):
            state.embedding_ready = True

    return {
        "folder": str(state.root),
        "file_count": len(files),
        "tree": json.dumps(state.tree),
        "embedding_mode": "onnx" if state.embedding_ready else "bm25",
    }


@router.post("/api/read-file")
def read_file(req: ReadFileRequest) -> dict[str, Any]:
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
def browse_dirs(req: BrowseRequest) -> dict[str, Any]:
    base = Path(req.path).expanduser().resolve() if req.path else Path.home()
    if not base.exists() or not base.is_dir():
        base = Path.home()

    dirs: list[dict[str, str]] = []
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
def exec_command(req: ExecRequest) -> ExecResponse:
    from config import DANGEROUS_PATTERNS
    cmd_lower = req.command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            raise HTTPException(status_code=403, detail="Command not allowed for security reasons")

    cwd = req.cwd if req.cwd else str(APP_DIR)

    try:
        result = subprocess.run(
            req.command, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=60,
        )
        return ExecResponse(
            stdout=result.stdout[:50000],
            stderr=result.stderr[:10000],
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Command timed out after 60 seconds")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(exc)}")
