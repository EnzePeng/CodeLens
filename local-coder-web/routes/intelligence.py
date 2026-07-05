"""Project understanding API routes."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from models import FileLensRequest, FolderRequest, state
from services.indexer import index_folder
from services.project_intel import build_file_lens

router = APIRouter()


@router.post("/api/index/start")
def start_index(req: FolderRequest) -> dict:
    root = Path(req.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="Folder does not exist")

    job_id = str(uuid.uuid4())[:8]
    job = {
        "job_id": job_id,
        "stage": "indexing",
        "progress": 0.2,
        "file_count": 0,
        "graph_ready": False,
        "brief_ready": False,
        "errors": [],
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    state.index_jobs[job_id] = job
    try:
        result = index_folder(root)
        state.root = root
        state.files = result["files"]
        state.tree = result["tree"]
        state.idf = result["idf"]
        state.avg_dl = result["avg_dl"]
        state.dep_graph = result.get("dep_graph")
        state.code_graph = result.get("code_graph")
        state.project_brief = result.get("project_brief")
        state.embedding_ready = result["embedding_mode"] == "onnx"
        job.update({
            "stage": "complete",
            "progress": 1.0,
            "file_count": result["file_count"],
            "graph_ready": state.code_graph is not None,
            "brief_ready": state.project_brief is not None,
            "updated_at": time.time(),
        })
    except Exception as exc:
        job.update({
            "stage": "failed",
            "progress": 1.0,
            "errors": [str(exc)],
            "updated_at": time.time(),
        })
    return _public_job(job)


@router.get("/api/index/status/{job_id}")
def index_status(job_id: str) -> dict:
    job = state.index_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Index job not found")
    return _public_job(job)


@router.get("/api/project/brief")
def project_brief() -> dict:
    if state.project_brief is None:
        raise HTTPException(status_code=404, detail="Project brief not ready")
    return state.project_brief


@router.post("/api/file-lens")
def file_lens(req: FileLensRequest) -> dict:
    if state.root is None or state.code_graph is None:
        raise HTTPException(status_code=400, detail="Please index a folder first")
    file_paths = {f.rel for f in state.files}
    if req.path not in file_paths:
        raise HTTPException(status_code=404, detail="File not found in current index")
    return build_file_lens(req.path, state.files, state.code_graph, depth=req.depth)


def _public_job(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "stage": job["stage"],
        "progress": job["progress"],
        "file_count": job["file_count"],
        "graph_ready": job["graph_ready"],
        "brief_ready": job["brief_ready"],
        "errors": job["errors"],
    }
