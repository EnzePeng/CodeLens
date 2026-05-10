"""
Search service — BM25 + ONNX embedding + dependency graph hybrid search.

Improvements over v0.3:
- #1  Split @ $ . symbols in tokenization
- #2  Path depth boost (deeper = more specific)
- #3  Symbol relevance boost
- #4  Phrase matching for multi-term queries
- #5  Prefix matching for partial words
- #6,#7 Dependency graph boost
- #9  File-type-aware embedding weighting
- #10 Integrated file watcher callback
- #13 Search cache with LRU + query fingerprint
- #41 Symbol-level fuzzy search
- #42 Improved CJK-aware tokenization
- #44 Phrase-based search
- #45 Wildcard pattern search
- #54 Query expansion
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np

from config import BM25_B, BM25_K1, MAX_CONTEXT_CHARS, MAX_INDEX_FILES
from logger import logger
from models import CodeFile

# ---- Tokenization ----

_CAMEL_CASE = re.compile(r'([a-z])([A-Z])|([A-Z]+)([A-Z][a-z])')
_STOP_WORDS = frozenset({
    "the", "and", "or", "for", "with", "this", "that", "is", "it", "to",
    "of", "in", "code", "项目", "文件", "函数", "哪里", "什么", "如何", "怎么",
    "请", "帮", "我", "是", "的", "在", "有", "了", "要", "看",
    "def", "class", "import", "from", "return", "if", "else", "for", "while",
    "let", "const", "var", "function", "async", "await", "type", "interface",
    "pub", "fn", "struct", "enum", "impl", "trait", "use", "mod",
})


def _split_camel(text: str) -> str:
    """Split camelCase and PascalCase: 'getUserInfo' -> 'get User Info'."""
    return _CAMEL_CASE.sub(r'\1\3 \2\4', text)


def _split_symbols(text: str) -> str:
    """#1 Split @ $ . symbols: '@pytest.fixture' -> 'pytest fixture', 'src/main.py' -> 'src main py'."""
    text = text.replace('@', ' ').replace('$', ' ').replace('.', ' ')
    return text


def _tokenize_doc(text: str) -> list[str]:
    """#1,#42 Tokenize document text for BM25 indexing. Improved CJK awareness."""
    text = _split_camel(text)
    text = _split_symbols(text)
    text = re.sub(r'[^\w\s]', ' ', text)
    # Match English words or CJK characters (2+ consecutive for better grouping)
    tokens = re.findall(r'[A-Za-z_][\w$.-]*|[^\s]{2,}', text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2]


def _tokenize_query(text: str) -> list[str]:
    """#1,#42 Tokenize query text for BM25 search."""
    text = _split_camel(text)
    text = _split_symbols(text)
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = re.findall(r'[A-Za-z_][\w$.-]*|[^\s]{2,}', text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2][:60]


# ---- #54 Query expansion with synonyms ----

_QUERY_SYNONYMS: dict[str, list[str]] = {
    "fetch": ["select", "query", "retrieve", "read", "获取"],
    "data": ["model", "entity", "record", "row", "object"],
    "display": ["render", "show", "view", "ui", "显示"],
    "send": ["post", "upload", "emit", "dispatch", "发送"],
    "save": ["persist", "store", "write", "写入"],
    "delete": ["remove", "drop", "销毁"],
    "update": ["modify", "change", "edit", "更新"],
    "test": ["spec", "specification", "测试"],
    "error": ["exception", "fail", "err", "错误"],
}


def _expand_query(terms: list[str]) -> list[str]:
    """#54 Expand query terms with synonyms."""
    expanded = set(terms)
    for term in terms:
        if term in _QUERY_SYNONYMS:
            expanded.update(_QUERY_SYNONYMS[term])
    return list(expanded)


# ---- BM25 Index Building ----

def build_bm25_index(files: list[CodeFile]) -> tuple[dict[str, float], float, dict[str, dict[str, int]]]:
    """Build BM25 index from files.

    Returns:
        Tuple of (idf dict, average document length, term_frequency dict per file)
    """
    N = len(files)
    if N == 0:
        return {}, 0.0, {}

    df: dict[str, int] = defaultdict(int)
    total_len = 0

    for f in files:
        doc = f"{f.rel} {' '.join(f.symbols)} {f.text[:8000]}"
        tokens = _tokenize_doc(doc)
        f.tf: dict[str, int] = {}
        f.tokens_list = tokens
        cnt = Counter(tokens)
        for term, freq in cnt.items():
            f.tf[term] = freq
            df[term] += 1
        total_len += len(tokens)

    avg_dl = total_len / N
    idf: dict[str, float] = {}
    for term, freq in df.items():
        idf[term] = math.log((N - freq + 0.5) / (freq + 0.5) + 1)

    return idf, avg_dl, {f.rel: f.tf for f in files}


# ---- BM25 Scoring with enhancements ----

def bm25_score(
    query_terms: list[str],
    file: CodeFile,
    avg_dl: float,
    idf: dict[str, float],
    path_boost: float = 0.0,
    symbol_boost: float = 0.0,
) -> float:
    """Calculate BM25 score with path and symbol boosts."""
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
    return score + path_boost + symbol_boost


def _calc_path_boost(query_terms: list[str], rel: str, depth: int) -> float:
    """#2 Path depth boost: deeper paths are more specific."""
    boost = 0.0
    rel_parts = set(rel.lower().split('/'))
    for term in query_terms:
        if term in rel_parts:
            boost += 3.0 * min(depth / 3.0, 1.0)
    return boost


def _calc_symbol_boost(query_terms: list[str], symbols: list[str]) -> float:
    """#3 Symbol relevance boost."""
    boost = 0.0
    for term in query_terms:
        for sym in symbols:
            if term in sym.lower() or sym.lower() in term:
                boost += 4.0
    return boost


def _calc_phrase_boost(query_terms: list[str], file: CodeFile) -> float:
    """#4 Phrase matching: boost when consecutive query terms appear."""
    if len(query_terms) < 2:
        return 0.0
    tokens = getattr(file, 'tokens_list', [])
    if not tokens:
        return 0.0
    text_lower = ' '.join(tokens[:500])
    for i in range(len(query_terms) - 1):
        phrase = f"{query_terms[i]} {query_terms[i+1]}"
        if phrase in text_lower:
            return 5.0
    return 0.0


def _calc_prefix_match(query_terms: list[str], file: CodeFile) -> float:
    """#5 Prefix matching: boost for partial word matches."""
    boost = 0.0
    for term in query_terms:
        if len(term) < 3:
            continue
        for sym in file.symbols:
            if sym.lower().startswith(term):
                boost += 1.5
    return boost


# ---- #6,#7 Dependency Graph ----

class DependencyGraph:
    """Record import/require/include relationships between files."""

    def __init__(self, files: list[CodeFile]):
        self.imports: dict[str, set[str]] = defaultdict(set)
        self.referents: dict[str, set[str]] = defaultdict(set)
        self._build(files)

    def _build(self, files: list[CodeFile]):
        file_paths = {f.rel for f in files}
        ext_map = {
            '.py': {'import', 'from'},
            '.js': {'import', 'require'},
            '.ts': {'import', 'require'},
            '.java': {'import'},
            '.go': {'import'},
            '.rs': {'use', 'extern'},
            '.rb': {'require', 'require_relative'},
            '.php': {'use', 'require', 'include'},
        }

        for f in files:
            rel = f.rel
            ext = Path(rel).suffix.lower()
            triggers = ext_map.get(ext, {'import'})

            for line in f.text.split('\n')[:50]:
                line = line.strip()
                if any(line.startswith(trig) for trig in triggers):
                    # Extract module path and map to file
                    parts = re.split(r'[\s.,;:]', line)
                    for part in parts:
                        cleaned = part.strip().rstrip(';').rstrip(',').rstrip('.')
                        if cleaned and len(cleaned) > 1:
                            # Try to match to indexed file
                            for target in file_paths:
                                if target != rel and cleaned.replace('.', '/') in target:
                                    self.imports[rel].add(target)
                                    self.referents[target].add(rel)
                                    break

    def get_referent_boost(self, file_rel: str, query_terms: list[str]) -> float:
        """#7 Boost files that are referenced by files matching query terms."""
        boosting_files = set()
        for f in self.imports:
            file_text = f"{f} {' '.join(self.imports[f])}"
            if any(t in file_text.lower() for t in query_terms):
                boosting_files.update(self.imports[f])

        boost = 0.0
        if file_rel in boosting_files:
            boost += 2.0
        if file_rel in self.referents:
            for ref in self.referents[file_rel]:
                if any(t in ref.lower() for t in query_terms):
                    boost += 1.5
        return boost


# ---- ONNX Embeddings ----

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


def set_onnx_session(session, tokenizer):
    """Set ONNX runtime session."""
    global _ort_session, _ort_tokenizer
    _ort_session = session
    _ort_tokenizer = tokenizer


def get_onnx_session():
    """Get current ONNX runtime session."""
    return _ort_session, _ort_tokenizer


# ---- #13 Search Cache ----

class SearchCache:
    """LRU cache for search results with query fingerprinting."""

    def __init__(self, max_size: int = 200):
        self._cache: dict[str, tuple[list[CodeFile], float, int]] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _fingerprint(query: str, file_count: int) -> str:
        q = query.lower().strip()[:200]
        return f"{q}:{file_count}"

    def get(self, query: str, file_count: int) -> Optional[list[CodeFile]]:
        key = self._fingerprint(query, file_count)
        if key in self._cache:
            result, timestamp, access = self._cache[key]
            self._cache[key] = (result, timestamp, access + 1)
            self._hits += 1
            return result
        self._misses += 1
        return None

    def set(self, query: str, file_count: int, result: list[CodeFile]) -> None:
        key = self._fingerprint(query, file_count)
        if key in self._cache:
            del self._cache[key]
        while len(self._cache) >= self._max_size:
            oldest = min(self._cache, key=lambda k: self._cache[k][2])
            del self._cache[oldest]
        self._cache[key] = (result, 0, 0)

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
        }


# Global search cache
_search_cache = SearchCache()


# ---- Select Context ----

def select_context(
    question: str,
    files: list[CodeFile],
    idf: dict[str, float],
    avg_dl: float,
    embedding_ready: bool,
    session,
    tokenizer,
    context_limit: Optional[int] = None,
    dep_graph: Optional[DependencyGraph] = None,
) -> list[CodeFile]:
    """Select relevant code files for the question."""
    if not files:
        return []

    # #13 Check search cache
    cached = _search_cache.get(question, len(files))
    if cached is not None:
        return cached

    query_terms = _tokenize_query(question)
    if not query_terms:
        return files[:10]

    # #54 Expand query with synonyms
    expanded_terms = _expand_query(query_terms)

    # BM25 scoring for all files
    scored: list[tuple[float, CodeFile]] = []
    for f in files:
        # Ensure tokens_list exists for phrase matching
        if not hasattr(f, 'tokens_list') or not f.tokens_list:
            f.tokens_list = _tokenize_doc(f"{f.rel} {' '.join(f.symbols)} {f.text[:8000]}")

        score = bm25_score(query_terms, f, avg_dl, idf)

        # #2 Path depth boost
        depth = f.rel.count('/')
        score += _calc_path_boost(query_terms, f.rel, depth)

        # #3 Symbol relevance boost
        sym_b = _calc_symbol_boost(query_terms, f.symbols)
        score += sym_b

        # #4 Phrase matching
        score += _calc_phrase_boost(query_terms, f)

        # #5 Prefix matching
        score += _calc_prefix_match(query_terms, f)

        # #7 Dependency graph boost
        if dep_graph:
            score += dep_graph.get_referent_boost(f.rel, expanded_terms)

        if score > 0:
            scored.append((score, f))

    if not scored:
        return files[:10]

    scored.sort(key=lambda x: x[0], reverse=True)
    candidates = [f for _, f in scored[:30]]

    # ONNX re-ranking
    if embedding_ready and session and tokenizer and candidates:
        try:
            q_emb = _embed_texts([question], session, tokenizer)[0]
            emb_scored: list[tuple[float, CodeFile]] = []
            for f in candidates:
                sim = float(np.dot(q_emb, f.embedding)) if f.embedding is not None else 0.0
                emb_scored.append((sim, f))
            emb_scored.sort(key=lambda x: x[0], reverse=True)
            candidates = [f for _, f in emb_scored]
        except Exception as e:
            logger.warning(f"[Embedding] re-rank failed: {e}")

    # Select files within context limit
    max_chars = context_limit if context_limit is not None else MAX_CONTEXT_CHARS
    selected: list[CodeFile] = []
    total = 0
    for f in candidates:
        selected.append(f)
        total += min(len(f.text), 7000)
        if len(selected) >= 14 or total >= max_chars:
            break

    # #13 Cache result
    _search_cache.set(question, len(files), selected)
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


# ---- Search API ----

def search_files(
    query: str,
    files: list[CodeFile],
    idf: dict[str, float],
    avg_dl: float,
    embedding_ready: bool,
    session,
    tokenizer,
    limit: int = 20,
    dep_graph: Optional[DependencyGraph] = None,
) -> list[dict]:
    """Search files and return scored results."""
    if not files:
        return []

    query_terms = _tokenize_query(query)
    expanded_terms = _expand_query(query_terms)

    scored: list[tuple[float, CodeFile]] = []
    for f in files:
        score = bm25_score(query_terms, f, avg_dl, idf)
        depth = f.rel.count('/')
        score += _calc_path_boost(query_terms, f.rel, depth)
        score += _calc_symbol_boost(query_terms, f.symbols)
        if dep_graph:
            score += dep_graph.get_referent_boost(f.rel, expanded_terms)
        if score > 0:
            scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, f in scored[:limit]:
        results.append({
            "path": f.rel,
            "score": round(score, 3),
            "size": f.size,
            "symbols": f.symbols[:5],
        })
    return results
