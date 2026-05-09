"""
Search service - BM25 + ONNX embedding based code search.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np

from config import BM25_B, BM25_K1, MAX_CONTEXT_CHARS, MAX_FILE_BYTES, MAX_INDEX_FILES
from models import CodeFile


def _split_camel(text: str) -> str:
    """Split camelCase and PascalCase identifiers for better tokenization."""
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)
    return text


def _tokenize_doc(text: str) -> list[str]:
    """Tokenize document text for BM25 indexing.

    Handles camelCase, PascalCase, and CJK text.
    """
    text = _split_camel(text)
    text = re.sub(r'[^\w]', ' ', text)
    tokens = re.findall(r'[A-Za-z_][\w$.-]*|[一-鿿]{1,}', text.lower())
    stop = {
        "the", "and", "or", "for", "with", "this", "that",
        "代码", "项目", "文件", "函数", "哪里", "什么", "如何", "怎么",
        "请", "帮", "我", "是", "的", "在", "有", "了", "要", "看",
    }
    return [t for t in tokens if t not in stop and len(t) >= 2]


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


def bm25_score(query_terms: list[str], file: CodeFile, avg_dl: float, idf: dict[str, float]) -> float:
    """Calculate BM25 score for a file given query terms."""
    dl = sum(file.tf.values())
    score = 0.0
    for term in query_terms:
        if term not in file.tf:
            continue
        tf = file.tf[term]
        idf_val = idf.get(term, 0.0)
        numerator = tf * (BM25_K1 + 1)
        denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / max(avg_dl, 1))
        score += idf_val * numerator / denominator
    return score


def _tokenize_query(text: str) -> list[str]:
    """Tokenize query text for BM25 search.

    Handles camelCase, PascalCase, and CJK text.
    """
    text = _split_camel(text)
    text = re.sub(r'[^\w]', ' ', text)
    tokens = re.findall(r'[A-Za-z_][\w$.-]*|[一-鿿]{1,}', text.lower())
    stop = {
        "the", "and", "or", "for", "with", "this", "that",
        "代码", "项目", "文件", "函数", "哪里", "什么", "如何", "怎么",
        "请", "帮", "我", "是", "的", "在", "有", "了", "要", "��",
    }
    return [t for t in tokens if t not in stop and len(t) >= 2][:60]


# Global ONNX session (lazy loaded, set by app.py at startup)
_ort_session = None
_ort_tokenizer = None


def _embed_texts(texts: list[str], session, tokenizer) -> np.ndarray:
    """Generate embeddings using ONNX model."""
    enc = tokenizer.encode_batch(texts)
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
    return embeddings / np.maximum(norms, 1e-9)


def build_embeddings(files: list[CodeFile], session, tokenizer, batch_size: int = 32) -> None:
    """Build embeddings for all files. (Kept for backward compat; uses 4000-char window internally.)"""
    build_embeddings_full(files, session, tokenizer, batch_size, text_window=4000)


def build_embeddings_full(
    files: list[CodeFile],
    session,
    tokenizer,
    batch_size: int = 32,
    text_window: int = 4000,
) -> None:
    """Build ONNX embeddings for all files with configurable text window.

    Uses 4000-char window by default to preserve more semantic context,
    including file path and extracted symbol names for richer embeddings.
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
    print(f"[Embedding] Built embeddings for {len(files)} files")


# Global ONNX session accessor (set by app.py at startup)
def set_onnx_session(session, tokenizer):
    """Set ONNX runtime session."""
    global _ort_session, _ort_tokenizer
    _ort_session = session
    _ort_tokenizer = tokenizer


def get_onnx_session():
    """Get current ONNX runtime session."""
    return _ort_session, _ort_tokenizer


def select_context(
    question: str,
    files: list[CodeFile],
    idf: dict[str, float],
    avg_dl: float,
    embedding_ready: bool,
    session,
    tokenizer,
    context_limit: Optional[int] = None,
) -> list[CodeFile]:
    """Select relevant code files for the question."""
    if not files:
        return []

    query_terms = _tokenize_query(question)
    if not query_terms:
        return files[:10]

    # BM25 scoring
    bm25_scored: list[tuple[float, CodeFile]] = []
    for f in files:
        score = bm25_score(query_terms, f, avg_dl, idf)
        for term in query_terms:
            if term in f.rel.lower():
                score += 3.0
            if any(term in sym.lower() for sym in f.symbols):
                score += 2.0
        if score > 0:
            bm25_scored.append((score, f))

    if not bm25_scored:
        return files[:10]

    bm25_scored.sort(key=lambda x: x[0], reverse=True)
    candidates = [f for _, f in bm25_scored[:30]]

    # ONNX re-ranking
    if embedding_ready and session and tokenizer and candidates:
        try:
            q_emb = _embed_texts([question], session, tokenizer)[0]
            scored_by_emb: list[tuple[float, CodeFile]] = []
            for f in candidates:
                sim = float(np.dot(q_emb, f.embedding)) if f.embedding is not None else 0.0
                scored_by_emb.append((sim, f))
            scored_by_emb.sort(key=lambda x: x[0], reverse=True)
            candidates = [f for _, f in scored_by_emb]
        except Exception as exc:
            print(f"[Embedding] re-rank failed: {exc}")

    # Select files within context limit
    max_chars = context_limit if context_limit is not None else MAX_CONTEXT_CHARS

    selected: list[CodeFile] = []
    total = 0
    for f in candidates:
        selected.append(f)
        total += min(len(f.text), 7000)
        if len(selected) >= 14 or total >= max_chars:
            break
    return selected


def render_context(files: list[CodeFile], context_limit: Optional[int] = None) -> str:
    """Render selected files into context string."""
    max_chars = context_limit if context_limit is not None else MAX_CONTEXT_CHARS
    chunks: list[str] = []
    used = 0
    for file in files:
        budget = min(9000, max_chars - used)
        if budget <= 0:
            break
        text = file.text[:budget]
        chunks.append(f"--- FILE: {file.rel} ---\n{text}")
        used += len(text)
    return "\n\n".join(chunks)
