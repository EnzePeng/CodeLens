"""
Context Manager - Smart context allocation with sliding window and compression.

Features:
- Sliding window for conversation history
- Smart context compression
- Dependency-aware file loading
- Dynamic budget allocation
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import OrderedDict, deque

from models import CodeFile
from config import MAX_CONTEXT_CHARS


@dataclass
class ContextBudget:
    """Token budget allocation for context."""
    system_prompt: int = 8000
    code_context: int = 21000
    history: int = 12600

    @classmethod
    def from_total(cls, total: int) -> "ContextBudget":
        return cls(
            system_prompt=int(total * 0.20),
            code_context=int(total * 0.50),
            history=int(total * 0.30),
        )

    @classmethod
    def for_planning(cls, total: int) -> "ContextBudget":
        return cls(
            system_prompt=int(total * 0.15),
            code_context=int(total * 0.60),
            history=int(total * 0.25),
        )

    @classmethod
    def for_asking(cls, total: int) -> "ContextBudget":
        return cls(
            system_prompt=int(total * 0.20),
            code_context=int(total * 0.45),
            history=int(total * 0.35),
        )


class ContextCache:
    """LRU cache for context selection results."""

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict[str, tuple[list[CodeFile], float]] = OrderedDict()
        self._max_size = max_size
        self._hit_count = 0
        self._miss_count = 0

    def get(self, key: str) -> Optional[list[CodeFile]]:
        if key in self._cache:
            result, _ = self._cache[key]
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


class SlidingWindowHistory:
    """Sliding window for conversation history with smart compression."""

    def __init__(self, max_messages: int = 50, max_tokens: int = 12000):
        self._window: deque[dict] = deque(maxlen=max_messages)
        self._max_tokens = max_tokens
        self._compressed_summaries: list[str] = []

    def add(self, message: dict) -> None:
        """Add message to sliding window."""
        self._window.append(message)
        self._maybe_compress()

    def _maybe_compress(self) -> None:
        """Compress old messages if over budget."""
        total_tokens = self.estimate_total_tokens()
        if total_tokens <= self._max_tokens:
            return

        # Compress oldest messages
        while len(self._window) > 10 and total_tokens > self._max_tokens:
            old_msg = self._window.popleft()
            if old_msg.get("role") != "system":
                summary = self._summarize_message(old_msg)
                if summary:
                    self._compressed_summaries.append(summary)
                total_tokens = self.estimate_total_tokens()

    def _summarize_message(self, msg: dict) -> str:
        """Create a brief summary of a message."""
        content = msg.get("content", "")
        if len(content) < 100:
            return content
        return content[:100] + "..."

    def get_context(self) -> list[dict]:
        """Get context messages with compressed history prefix."""
        context = []

        # Add compressed summaries as system context
        if self._compressed_summaries:
            summary_text = "Previous context:\n" + "\n".join(self._compressed_summaries[-3:])
            context.append({"role": "system", "content": summary_text})

        # Add current window
        context.extend(list(self._window))
        return context

    def estimate_total_tokens(self) -> int:
        """Estimate total tokens in window."""
        total = 0
        for msg in self._window:
            total += estimate_tokens(msg.get("content", ""))
        for summary in self._compressed_summaries:
            total += estimate_tokens(summary)
        return total

    def clear(self) -> None:
        self._window.clear()
        self._compressed_summaries.clear()


class SmartContextManager:
    """
    Smart context manager with:
    - Sliding window for history
    - Dependency-aware file loading
    - Dynamic budget allocation
    - Context compression
    """

    def __init__(self):
        self._cache = ContextCache()
        self._file_timestamps: dict[str, float] = {}
        self._history = SlidingWindowHistory()
        self._loaded_files: dict[str, CodeFile] = {}

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
        """Select relevant files with smart scoring."""
        cache_key = f"{question}:{len(files)}"

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        from services.search import select_context as basic_select
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

        # Add dependency-related files
        if dep_graph and selected:
            selected = self._add_dependency_files(selected, files, dep_graph)

        # Rerank by recency
        if self._file_timestamps and selected:
            selected = self._rerank_by_recency(selected)

        if use_cache:
            self._cache.set(cache_key, selected)

        return selected

    def _add_dependency_files(
        self,
        selected: list[CodeFile],
        all_files: list[CodeFile],
        dep_graph,
    ) -> list[CodeFile]:
        """Add files that are dependencies of selected files."""
        selected_paths = {f.rel for f in selected}
        additional = []

        for f in selected:
            deps = dep_graph.get(str(f.rel), [])
            for dep_path in deps:
                if dep_path not in selected_paths:
                    for af in all_files:
                        if str(af.rel) == dep_path:
                            additional.append(af)
                            selected_paths.add(dep_path)
                            break

        # Limit additional files to avoid context overflow
        return selected + additional[:5]

    def _rerank_by_recency(self, files: list[CodeFile]) -> list[CodeFile]:
        """Rerank files by recent edits."""
        scored = []
        for f in files:
            recency = self._file_timestamps.get(f.rel, 0)
            scored.append((recency, f))
        scored.sort(reverse=True)
        return [f for _, f in scored]

    def update_file_timestamp(self, path: str) -> None:
        self._file_timestamps[path] = time.time()

    def on_files_changed(self, paths: list[str]) -> None:
        now = time.time()
        for path in paths:
            self._file_timestamps[path] = now
        self._cache.clear()

    def add_to_history(self, message: dict) -> None:
        """Add message to sliding window history."""
        self._history.add(message)

    def get_history_context(self) -> list[dict]:
        """Get compressed history context."""
        return self._history.get_context()

    def clear_history(self) -> None:
        self._history.clear()

    def get_cache_stats(self) -> dict:
        return self._cache.get_stats()

    def get_budget(self, total_tokens: int, task_type: str = "ask") -> ContextBudget:
        if task_type == "planning":
            return ContextBudget.for_planning(total_tokens)
        elif task_type == "asking":
            return ContextBudget.for_asking(total_tokens)
        return ContextBudget.from_total(total_tokens)


def estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    if not text:
        return 0
    cjk = len(re.findall(r"[一-鿿㐀-䶿豈-﫿]", text))
    english = len(re.findall(r"[A-Za-z0-9_]+", text))
    other = max(0, len(text) - cjk - english * 5)
    return int(cjk * 1.5 + english * 1.3 + other * 0.5)


# Global instance
context_manager = SmartContextManager()


def get_context_manager() -> SmartContextManager:
    return context_manager
