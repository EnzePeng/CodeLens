"""Tests for context manager service."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.context_manager import ContextBudget, ContextCache, ContextManager


class TestContextBudget:
    def test_default(self):
        b = ContextBudget()
        assert b.system_prompt == 8000
        assert b.code_context == 21000
        assert b.history == 12600

    def test_from_total(self):
        b = ContextBudget.from_total(42000)
        assert b.system_prompt == int(42000 * 0.20)
        assert b.code_context == int(42000 * 0.50)
        assert b.history == int(42000 * 0.30)

    def test_for_planning(self):
        b = ContextBudget.for_planning(10000)
        assert b.code_context == int(10000 * 0.60)
        assert b.history == int(10000 * 0.25)

    def test_for_asking(self):
        b = ContextBudget.for_asking(10000)
        assert b.history == int(10000 * 0.35)


class TestContextCache:
    def test_lru(self):
        cache = ContextCache(max_size=2)
        cache.set("a", ["f1"])
        cache.set("b", ["f2"])
        # Access "a" to make it recently used
        cache.get("a")
        # Add "c" - should evict "b" (LRU)
        cache.set("c", ["f3"])
        assert cache.get("a") is not None
        assert cache.get("b") is None

    def test_hit_miss(self):
        cache = ContextCache(max_size=10)
        cache.set("key", ["f"])
        assert cache._hit_count == 0
        assert cache.get("key") is not None
        assert cache._hit_count == 1
        assert cache._miss_count == 0
        assert cache.get("other") is None
        assert cache._miss_count == 1

    def test_clear(self):
        cache = ContextCache(max_size=10)
        cache.set("k", ["f"])
        cache.get("k")
        cache.clear()
        assert cache.get("k") is None


class TestContextManager:
    def test_select_files_with_cache(self):
        mgr = ContextManager()
        from models import CodeFile
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.py"
            p.write_text("def foo(): pass\n")
            cf = CodeFile(path=p, rel="test.py", size=p.stat().st_size, text=p.read_text())
            result = mgr.select_files(
                question="foo",
                files=[cf],
                idf={},
                avg_dl=0.0,
                embedding_ready=False,
                session=None,
                tokenizer=None,
                use_cache=True,
            )
            assert isinstance(result, list)

    def test_select_files_rerank_by_recency(self):
        mgr = ContextManager()
        from models import CodeFile
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            f1 = tmpp / "old.py"
            f1.write_text("pass\n")
            f2 = tmpp / "new.py"
            f2.write_text("pass\n")
            cf1 = CodeFile(path=f1, rel="old.py", size=f1.stat().st_size, text="pass\n")
            cf2 = CodeFile(path=f2, rel="new.py", size=f2.stat().st_size, text="pass\n")

            mgr.update_file_timestamp("new.py")

            # Reranking should put new.py first
            reranked = mgr._rerank_by_recency([cf1, cf2])
            assert reranked[0].rel == "new.py"

    def test_estimate_tokens_accuracy(self):
        """BUG-24: Token estimation should use reasonable multipliers."""
        mgr = ContextManager()
        # Pure English text
        tokens = mgr.estimate_tokens("hello world test")
        assert tokens > 0
        # Longer text should have more tokens
        tokens_long = mgr.estimate_tokens("hello world test " * 100)
        assert tokens_long > tokens

    def test_on_files_changed_clears_cache(self):
        mgr = ContextManager()
        mgr._cache.set("key", ["f"])
        mgr.on_files_changed(["main.py"])
        assert mgr._cache.get("key") is None
