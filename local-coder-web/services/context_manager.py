"""
Context Manager - Smart context allocation and management.

Improvements:
- #14 Actually used in ask.py
- #16 Dynamic budget allocation based on task type
- #24 Dynamic allocation per task type
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from collections import OrderedDict

from models import CodeFile
from config import MAX_CONTEXT_CHARS
from services.search import select_context as basic_select


@dataclass
class ContextBudget:
    """Token budget allocation for context."""
    system_prompt: int = 8000      # 20%
    code_context: int = 21000      # 50%
    history: int = 12600           # 30%

    @classmethod
    def from_total(cls, total: int) -> "ContextBudget":
        return cls(
            system_prompt=int(total * 0.20),
            code_context=int(total * 0.50),
            history=int(total * 0.30),
        )

    @classmethod
    def for_planning(cls, total: int) -> "ContextBudget":
        """#24 More code context for planning tasks."""
        return cls(
            system_prompt=int(total * 0.15),
            code_context=int(total * 0.60),
            history=int(total * 0.25),
        )

    @classmethod
    def for_asking(cls, total: int) -> "ContextBudget":
        """#24 More history context for asking tasks."""
        return cls(
            system_prompt=int(total * 0.20),
            code_context=int(total * 0.45),
            history=int(total * 0.35),
        )


class ContextCache:
    """Cache for context selection results."""

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict[str, tuple[list[CodeFile], float]] = OrderedDict()
        self._max_size = max_size
        self._hit_count = 0
        self._miss_count = 0

    def get(self, key: str) -> Optional[list[CodeFile]]:
        if key in self._cache:
            result, timestamp = self._cache[key]
            self._cache.move_to_end(key)
            self._hit_count += 1
            return result
        self._miss_count += 1
        return None

    def set(self, key: str, value: list[CodeFile]) -> None:
        if key in self._cache:
            del self._cache[key]
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (value, time.time())

    def clear(self) -> None:
        self._cache.clear()
        self._hit_count = 0
        self._miss_count = 0

    def get_stats(self) -> dict:
        total = self._hit_count + self._miss_count
        return {
            "size": len(self._cache),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": round(self._hit_count / total, 3) if total > 0 else 0,
        }


class ContextManager:
    """Manages smart context selection and allocation."""

    def __init__(self):
        self._cache = ContextCache()
        self._file_timestamps: dict[str, float] = {}

    def select_files(
        self,
        question: str,
        files: list[CodeFile],
        idf: dict[str, float],
        avg_dl: float,
        embedding_ready: bool,
        session,
        tokenizer,
        context_limit: Optional[int] = None,
        use_cache: bool = True,
    ) -> list[CodeFile]:
        """#14,#24 Select relevant files with smart scoring and caching."""
        cache_key = f"{question}:{len(files)}"

        # Check cache
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Use basic selection with dependency graph
        from models import state
        dep_graph = getattr(state, 'dep_graph', None)

        selected = basic_select(
            question=question,
            files=files,
            idf=idf,
            avg_dl=avg_dl,
            embedding_ready=embedding_ready,
            session=session,
            tokenizer=tokenizer,
            context_limit=context_limit,
            dep_graph=dep_graph,
        )

        # Apply recency reranking
        if self._file_timestamps and selected:
            selected = self._rerank_by_recency(selected)

        # Cache result
        if use_cache:
            self._cache.set(cache_key, selected)

        return selected

    def _rerank_by_recency(self, files: list[CodeFile]) -> list[CodeFile]:
        """#28 Rerank files by recent edits."""
        scored = []
        for f in files:
            recency = self._file_timestamps.get(f.rel, 0)
            scored.append((recency, f))
        scored.sort(reverse=True)
        return [f for _, f in scored]

    def update_file_timestamp(self, path: str) -> None:
        """#28 Update file modification timestamp."""
        self._file_timestamps[path] = time.time()

    def on_files_changed(self, paths: list[str]) -> None:
        """Handle file changes - update timestamps and clear cache."""
        now = time.time()
        for path in paths:
            self._file_timestamps[path] = now
        self._cache.clear()

    def get_cache_stats(self) -> dict:
        return self._cache.get_stats()

    def get_budget(self, total_tokens: int, task_type: str = "ask") -> ContextBudget:
        """#24 Get context budget based on task type."""
        if task_type == "planning":
            return ContextBudget.for_planning(total_tokens)
        elif task_type == "asking":
            return ContextBudget.for_asking(total_tokens)
        return ContextBudget.from_total(total_tokens)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        if not text:
            return 0
        import re
        # CJK characters: roughly 1.5 tokens per char
        cjk = len(re.findall(r"[一-鿿㐀-䶿豈-﫿]", text))
        # English words: roughly 1.3 tokens per word
        english = len(re.findall(r"[A-Za-z0-9_]+", text))
        non_cjk_english = english + len(re.findall(r"[A-Za-z0-9_]+", text[cjk:]))
        other = max(0, len(text) - cjk - english)
        return int(cjk * 1.5 + english * 1.3 + other * 0.5)


# Global context manager
context_manager = ContextManager()


def get_context_manager() -> ContextManager:
    return context_manager
