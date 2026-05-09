"""
Indexer service — unified file scanning and indexing logic.

Replaces duplicated scan_repo / build_tree / build_bm25_index / _build_embeddings
that existed in both app.py and routes/main.py.
"""
from __future__ import annotations

import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np

from config import (
    BM25_B, BM25_K1, CODE_EXTS, IGNORE_DIRS, MAX_CONTEXT_CHARS,
    MAX_FILE_BYTES, MAX_INDEX_FILES,
)
from logger import logger
from models import CodeFile
from services.search import _tokenize_doc, build_embeddings_full


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
            result.append(CodeFile(path=path, rel=rel, size=size, text=text, symbols=[]))
    return result


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


def build_bm25_index(files: list[CodeFile]) -> tuple[dict[str, float], float]:
    """Build BM25 index from files.

    Returns:
        Tuple of (idf dictionary, average document length)
    """
    N = len(files)
    if N == 0:
        return {}, 0.0

    df: dict[str, int] = defaultdict(int)
    total_len = 0
    for f in files:
        doc = f"{f.rel} {' '.join(f.symbols)} {f.text[:8000]}"
        tokens = _tokenize_doc(doc)
        f.tf = {}
        cnt = Counter(tokens)
        for term, freq in cnt.items():
            f.tf[term] = freq
            df[term] += 1
        total_len += len(tokens)

    avg_dl = total_len / N
    idf: dict[str, float] = {}
    for term, freq in df.items():
        idf[term] = math.log((N - freq + 0.5) / (freq + 0.5) + 1)

    return idf, avg_dl


def build_embeddings(
    files: list[CodeFile],
    session,
    tokenizer,
    batch_size: int = 32,
    text_window: int = 4000,
) -> bool:
    """Build ONNX embeddings for all files. Returns success status.

    Uses a wider text window (4000 chars by default) to preserve more semantic context.
    Includes file path and extracted symbol names for richer embeddings.
    """
    texts = [
        f"{f.rel}: {' '.join(f.symbols[:10])} {f.text[:text_window]}"
        for f in files
    ]
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        enc = tokenizer.encode_batch(batch_texts)
        input_ids = np.array([e.ids for e in enc], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)
        outputs = session.run(None, {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        })
        embeddings = outputs[0][:, 0, :]
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        batch_embs = embeddings / np.maximum(norms, 1e-9)
        for j, emb in enumerate(batch_embs):
            files[i + j].embedding = emb
    logger.info(f"[Embedding] Built embeddings for {len(files)} files")
    return True


def index_folder(root: Path) -> dict:
    """Full indexing pipeline: scan + BM25 + embeddings.

    Returns a dict suitable for the set-folder / reindex API response.
    """
    files = scan_repo(root)
    idf, avg_dl = build_bm25_index(files)
    tree = build_tree(root, files)

    state = {"files": files, "idf": idf, "avg_dl": avg_dl, "tree": tree}

    # Lazy ONNX import to avoid circular deps
    import app as _app_module
    ort_sess, ort_tok = _app_module.get_onnx_session()
    embedding_mode = "bm25"
    if ort_sess is not None and ort_tok is not None:
        if build_embeddings(files, ort_sess, ort_tok):
            embedding_mode = "onnx"

    return {
        **state,
        "folder": str(root),
        "file_count": len(files),
        "embedding_mode": embedding_mode,
    }
