"""
Indexer service — unified file scanning, BM25, embeddings, and dependency graph.

Improvements over v0.3:
- #6,#7 Dependency graph from import/require/include
- #9 File-type-aware embedding weighting
- #11 Index caching with file hash
- #12 Incremental index updates
- #34 Function-level chunking for context
- #39 Parallel file scanning
- #47 Persisted embedding cache
- #51 Selective indexing profiles
"""
from __future__ import annotations

import re
import hashlib
import json
import math
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np

from config import (
    BM25_B, BM25_K1, CODE_EXTS, IGNORE_DIRS, MAX_CONTEXT_CHARS,
    MAX_FILE_BYTES, MAX_INDEX_FILES,
)
from logger import logger
from models import CodeFile
from services.search import (
    DependencyGraph, _search_cache, build_bm25_index, set_onnx_session,
)


# ---- File hashing for incremental updates (#11) ----

def _file_hash(path: Path) -> str:
    """Lightweight hash: mtime + size (fast, no content read)."""
    try:
        st = path.stat()
        return f"{st.st_mtime}:{st.st_size}"
    except OSError:
        return ""



# ---- Index cache persistence (#47) ----

def _get_cache_path(root: Path) -> Path:
    cache_dir = Path.home() / ".codelens" / "index_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    root_hash = hashlib.md5(str(root.resolve()).encode()).hexdigest()[:12]
    return cache_dir / f"{root_hash}.json"


def _load_index_cache(root: Path) -> Optional[dict]:
    """#11 Load cached index metadata."""
    cache_file = _get_cache_path(root)
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        if data.get("root") != str(root.resolve()):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _save_index_cache(root: Path, cache_data: dict) -> None:
    """Save index cache metadata."""
    cache_file = _get_cache_path(root)
    try:
        cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, default=str))
    except OSError as e:
        logger.warning(f"[IndexCache] Failed to save cache: {e}")


# ---- #39 Parallel file scanning ----

def should_read_file(path: Path) -> bool:
    """Check if a file should be indexed based on extension and name."""
    if path.suffix.lower() not in CODE_EXTS:
        return False
    if path.name.startswith(".") and path.name not in {".env.example", ".gitignore"}:
        return False
    return True


def _read_single_file(path: Path, root: Path) -> Optional[CodeFile]:
    """Read a single file. Used with ThreadPoolExecutor."""
    try:
        if not should_read_file(path):
            return None
        st = path.stat()
        if st.st_size > MAX_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        symbols = _extract_symbols_fast(text)
        return CodeFile(path=path, rel=rel, size=st.st_size, text=text, symbols=symbols)
    except OSError:
        return None


def scan_repo(root: Path, max_workers: int = 4) -> list[CodeFile]:
    """#39 Scan repository with parallel file reads."""
    candidates: list[Path] = []

    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        current_path = Path(current)
        for name in sorted(filenames):
            if len(candidates) >= MAX_INDEX_FILES:
                break
            candidates.append(current_path / name)

    # Parallel read
    result: list[CodeFile] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_read_single_file, p, root): p for p in candidates}
        for future in as_completed(futures):
            cf = future.result()
            if cf is not None:
                result.append(cf)
            if len(result) >= MAX_INDEX_FILES:
                break

    return result


# ---- Fast symbol extraction (#41) ----

_SYMBOL_PATTERNS = [
    re.compile(r'^\s*def\s+(\w+)'),
    re.compile(r'^\s*class\s+(\w+)'),
    re.compile(r'^\s*@(\w+)'),
    re.compile(r'\b(function|const|let|var)\s+(\w+)'),
    re.compile(r'\b(\w+)\s*\([^)]*\)\s*{'),
    re.compile(r'\b(interface|type|enum)\s+(\w+)'),
    re.compile(r'\b(func\s+)(\w+)'),
]


def _extract_symbols_fast(text: str, max_symbols: int = 30) -> list[str]:
    """Fast regex-based symbol extraction."""
    symbols = []
    for line in text.split('\n')[:200]:
        for pat in _SYMBOL_PATTERNS:
            m = pat.search(line)
            if m:
                sym = m.group(m.lastindex) if m.lastindex else m.group(0).strip()
                if sym not in symbols and len(sym) > 1:
                    symbols.append(sym)
                    if len(symbols) >= max_symbols:
                        return symbols
    return symbols


# ---- Build tree ----

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
                    sub_path = str(Path(*parts[:i + 1]))
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


# ---- ONNX Embeddings (#9) ----

def build_embeddings(
    files: list[CodeFile],
    session,
    tokenizer,
    batch_size: int = 32,
    text_window: int = 4000,
) -> bool:
    """#9 Build ONNX embeddings with file-type-aware weighting."""
    texts = []
    for f in files:
        ext = Path(f.rel).suffix.lower()
        # Different emphasis based on file type
        if ext in ('.py',):
            preamble = f"python {f.rel}: {' '.join(f.symbols[:10])}"
        elif ext in ('.ts', '.tsx', '.js', '.jsx'):
            preamble = f"typescript {f.rel}: {' '.join(f.symbols[:10])}"
        elif ext in ('.go',):
            preamble = f"go {f.rel}: {' '.join(f.symbols[:10])}"
        elif ext in ('.rs',):
            preamble = f"rust {f.rel}: {' '.join(f.symbols[:10])}"
        else:
            preamble = f"{f.rel}: {' '.join(f.symbols[:10])}"
        texts.append(f"{preamble} {f.text[:text_window]}")

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


# ---- #12 Incremental Update ----

def _incremental_update(
    root: Path,
    files: list[CodeFile],
    old_cache: Optional[dict],
) -> tuple[list[CodeFile], bool]:
    """#12 Incrementally update index: only re-read changed files."""
    needs_full_reindex = False

    if old_cache is None:
        return files, True

    old_file_hashes = old_cache.get("file_hashes", {})

    # Detect structural changes - BUG-11: filter IGNORE_DIRS like scan_repo does
    old_dirs = set(old_cache.get("dirs", []))
    current_dirs: set[str] = set()
    for current, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        current_dirs.add(current)

    if old_dirs != current_dirs:
        needs_full_reindex = True

    # BUG-12: Detect new and deleted files
    current_file_set = {f.rel for f in files}
    old_file_set = set(old_file_hashes.keys())

    new_files_rel = current_file_set - old_file_set
    deleted_files_rel = old_file_set - current_file_set

    if new_files_rel or deleted_files_rel:
        needs_full_reindex = True

    # Re-read changed files (existing files only)
    for f in files:
        new_hash = _file_hash(f.path)
        old_hash = old_file_hashes.get(f.rel, "")
        if new_hash != old_hash:
            try:
                text = f.path.read_text(encoding="utf-8", errors="replace")
                f.text = text
                f.symbols = _extract_symbols_fast(text)
                logger.info(f"[Index] Re-indexed changed file: {f.rel}")
            except OSError:
                pass

    return files, needs_full_reindex


# ---- Full Indexing Pipeline ----

def index_folder(root: Path) -> dict:
    """Full indexing pipeline: scan + BM25 + embeddings + dependency graph."""
    logger.info(f"[Index] Starting index for: {root}")
    start_time = time.time()

    old_cache = _load_index_cache(root)
    needs_full_reindex = old_cache is None

    # #39 Parallel scan
    files = scan_repo(root)
    if old_cache is not None:
        files, needs_full_reindex = _incremental_update(root, files, old_cache)

    mode = "full" if needs_full_reindex else "incremental"
    logger.info(f"[Index] {mode} index ({len(files)} files)")

    # BM25
    idf, avg_dl, tf_dict = build_bm25_index(files)

    # #6,#7 Dependency graph
    dep_graph = DependencyGraph(files)

    # Tree
    tree = build_tree(root, files)

    # Embeddings
    import app as _app_module
    ort_sess, ort_tok = _app_module.get_onnx_session()
    embedding_mode = "bm25"
    if ort_sess is not None and ort_tok is not None:
        if build_embeddings(files, ort_sess, ort_tok):
            embedding_mode = "onnx"

    elapsed = time.time() - start_time

    # Build directory set for cache
    current_dirs: set[str] = set()
    for current, _, _ in os.walk(root):
        current_dirs.add(current)

    # Save cache
    cache_data = {
        "root": str(root.resolve()),
        "file_count": len(files),
        "file_hashes": {f.rel: _file_hash(f.path) for f in files},
        "dirs": list(current_dirs),
        "indexed_at": time.time(),
    }
    _save_index_cache(root, cache_data)

    # Clear search cache on reindex
    _search_cache.clear()

    return {
        "files": files,
        "idf": idf,
        "avg_dl": avg_dl,
        "tf_dict": tf_dict,
        "tree": tree,
        "folder": str(root),
        "file_count": len(files),
        "embedding_mode": embedding_mode,
        "dep_graph": dep_graph,
        "index_time": round(elapsed, 2),
        "mode": mode,
    }
