"""
Context Manager - Smart context allocation and management.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from collections import OrderedDict

from models import CodeFile
from config import MAX_CONTEXT_CHARS


@dataclass
class ContextBudget:
    """Token budget allocation for context."""
    system_prompt: int = 8000      # 20%
    code_context: int = 21000      # 50%
    history: int = 12600           # 30%
    
    @classmethod
    def from_total(cls, total: int) -> "ContextBudget":
        """Create budget from total token count."""
        return cls(
            system_prompt=int(total * 0.20),
            code_context=int(total * 0.50),
            history=int(total * 0.30),
        )


@dataclass
class FileImportance:
    """File importance score for context selection."""
    file: CodeFile
    bm25_score: float = 0.0
    recency_score: float = 0.0    # Based on last edit time
    reference_score: float = 0.0  # Based on import references
    total_score: float = 0.0
    
    # Weights for scoring
    BM25_WEIGHT = 0.5
    RECENCY_WEIGHT = 0.3
    REFERENCE_WEIGHT = 0.2
    
    def calculate_total(self) -> float:
        """Calculate weighted total score."""
        self.total_score = (
            self.bm25_score * self.BM25_WEIGHT +
            self.recency_score * self.RECENCY_WEIGHT +
            self.reference_score * self.REFERENCE_WEIGHT
        )
        return self.total_score


class ContextCache:
    """Cache for context selection results."""
    
    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict[str, tuple[list[CodeFile], float]] = OrderedDict()
        self._max_size = max_size
        self._hit_count = 0
        self._miss_count = 0
    
    def get(self, key: str) -> Optional[list[CodeFile]]:
        """Get cached result."""
        if key in self._cache:
            result, timestamp = self._cache[key]
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hit_count += 1
            return result
        self._miss_count += 1
        return None
    
    def set(self, key: str, value: list[CodeFile]) -> None:
        """Set cached result."""
        # Remove oldest if at capacity
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        
        self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear cache."""
        self._cache.clear()
        self._hit_count = 0
        self._miss_count = 0
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0
        return {
            "size": len(self._cache),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": round(hit_rate, 3),
        }


class ContextManager:
    """Manages smart context selection and allocation."""
    
    def __init__(self):
        self._cache = ContextCache()
        self._last_index_time: float = 0
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
        """Select relevant files with smart scoring."""
        
        # Check cache
        cache_key = f"{question}:{len(files)}"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        
        # Import here to avoid circular imports
        from services.search import select_context as basic_select
        
        # Use basic selection
        selected = basic_select(
            question=question,
            files=files,
            idf=idf,
            avg_dl=avg_dl,
            embedding_ready=embedding_ready,
            session=session,
            tokenizer=tokenizer,
            context_limit=context_limit,
        )
        
        # Apply smart scoring if we have timestamps
        if self._file_timestamps:
            selected = self._rerank_by_recency(selected, question)
        
        # Cache result
        if use_cache:
            self._cache.set(cache_key, selected)
        
        return selected
    
    def _rerank_by_recency(self, files: list[CodeFile], question: str) -> list[CodeFile]:
        """Rerank files by recent edits."""
        # This would use file modification times
        # For now, return as-is
        return files
    
    def update_file_timestamp(self, path: str) -> None:
        """Update file modification timestamp."""
        self._file_timestamps[path] = time.time()
    
    def on_files_changed(self, paths: list[str]) -> None:
        """Handle file changes - invalidate cache for affected files."""
        # Clear cache entries that might be affected
        self._cache.clear()
        
        # Update timestamps
        now = time.time()
        for path in paths:
            self._file_timestamps[path] = now
    
    def get_cache_stats(self) -> dict:
        """Get context cache statistics."""
        return self._cache.get_stats()
    
    def get_budget(self, total_tokens: int) -> ContextBudget:
        """Get context budget allocation."""
        return ContextBudget.from_total(total_tokens)
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        if not text:
            return 0
        
        # Rough estimation: ~0.75 chars per token for Chinese, ~1.25 for English
        import re
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        non_cjk = len(text) - cjk
        english = len(re.findall(r"[A-Za-z0-9_]+", text))
        other = non_cjk - english
        
        return int(cjk * 0.75 + english * 1.25 + other * 0.2)


# Global context manager
context_manager = ContextManager()


def get_context_manager() -> ContextManager:
    """Get global context manager."""
    return context_manager