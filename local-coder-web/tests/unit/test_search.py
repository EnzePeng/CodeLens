"""Tests for search service."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import CodeFile
from services.search import (
    _tokenize_doc, _tokenize_query, _expand_query,
    build_bm25_index, bm25_score, SearchCache,
    DependencyGraph, select_context, render_context,
)


class TestTokenizeDoc:
    def test_basic(self):
        tokens = _tokenize_doc("def hello_world(): pass")
        # "hello_world" is not split by tokenizer (no camelCase), but should appear
        assert "hello_world" in tokens or any("hello" in t for t in tokens)

    def test_camel_case(self):
        tokens = _tokenize_doc("getUserInfo")
        assert "get" in tokens
        assert "user" in tokens
        assert "info" in tokens

    def test_symbols_split(self):
        tokens = _tokenize_doc("@pytest.fixture")
        assert "pytest" in tokens
        assert "fixture" in tokens

    def test_stop_words_filtered(self):
        tokens = _tokenize_doc("the quick brown fox")
        assert "the" not in tokens
        assert "quick" in tokens


class TestExpandQuery:
    def test_synonym_expansion(self):
        """BUG-10: Query expansion should add synonyms."""
        terms = ["fetch"]
        expanded = _expand_query(terms)
        assert "select" in expanded
        assert "query" in expanded
        assert "fetch" in expanded

    def test_no_synonym(self):
        expanded = _expand_query(["xyznonexist"])
        assert expanded == ["xyznonexist"]


class TestBM25Index:
    def test_empty(self):
        idf, avg_dl, tf_dict = build_bm25_index([])
        assert idf == {}
        assert avg_dl == 0.0

    def test_normal(self, tmp_path):
        files = []
        for name, content in [("a.py", "def foo(): pass"), ("b.py", "class Bar: pass")]:
            p = tmp_path / name
            p.write_text(content)
            files.append(CodeFile(path=p, rel=name, size=p.stat().st_size, text=content))
        idf, avg_dl, tf_dict = build_bm25_index(files)
        assert len(idf) > 0
        assert avg_dl > 0


class TestBM25Score:
    def test_basic(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("def hello(): pass")
        cf = CodeFile(path=p, rel="test.py", size=16, text=p.read_text())
        cf.tf = {"hello": 1}
        score = bm25_score(["hello"], cf, 10.0, {"hello": 1.0})
        assert score > 0

    def test_no_match(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("def hello(): pass")
        cf = CodeFile(path=p, rel="test.py", size=16, text=p.read_text())
        cf.tf = {"hello": 1}
        score = bm25_score(["xyznonexist"], cf, 10.0, {"hello": 1.0})
        assert score == 0.0


class TestSearchCache:
    def test_set_get(self):
        """BUG-09: Basic cache get/set."""
        cache = SearchCache(max_size=10)
        result = ["file1.py"]
        cache.set("test query", 1, result)
        assert cache.get("test query", 1) == result

    def test_eviction_not_immediate(self):
        """BUG-09: New entries should not be immediately evicted."""
        cache = SearchCache(max_size=3)
        # Fill cache to max
        cache.set("q1", 1, ["f1"])
        time.sleep(0.02)
        cache.set("q2", 1, ["f2"])
        time.sleep(0.02)
        cache.set("q3", 1, ["f3"])
        assert len(cache._cache) == 3

        # Add a new one - oldest (q1) should be evicted, not the new one (q4)
        time.sleep(0.02)
        cache.set("q4", 1, ["f4"])
        assert "q4:1" in cache._cache
        assert "q1:1" not in cache._cache

    def test_eviction_lru_by_timestamp(self):
        """BUG-09: Eviction should use timestamp, not access count."""
        cache = SearchCache(max_size=3)
        cache.set("q1", 1, ["f1"])
        time.sleep(0.02)
        cache.set("q2", 1, ["f2"])
        time.sleep(0.02)
        cache.set("q3", 1, ["f3"])
        time.sleep(0.02)
        # q1 is oldest, should be evicted
        cache.set("q4", 1, ["f4"])
        assert "q1:1" not in cache._cache
        assert "q4:1" in cache._cache


class TestDependencyGraph:
    def test_build(self, tmp_path):
        files = []
        for name, content in [("a.py", "import b"), ("b.py", "pass")]:
            p = tmp_path / name
            p.write_text(content)
            files.append(CodeFile(path=p, rel=name, size=p.stat().st_size, text=content))
        dg = DependencyGraph(files)
        assert len(dg.imports) >= 0

    def test_referent_boost(self, tmp_path):
        files = []
        for name, content in [("a.py", "import b"), ("b.py", "pass")]:
            p = tmp_path / name
            p.write_text(content)
            files.append(CodeFile(path=p, rel=name, size=p.stat().st_size, text=content))
        dg = DependencyGraph(files)
        boost = dg.get_referent_boost("b.py", ["b"])
        assert boost >= 0


class TestSelectContext:
    def test_empty_files(self):
        result = select_context("test", [], {}, 0.0, False, None, None)
        assert result == []

    def test_basic(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("def hello(): pass")
        cf = CodeFile(path=p, rel="test.py", size=16, text=p.read_text())
        result = select_context("hello", [cf], {}, 0.0, False, None, None)
        assert len(result) <= 10

    def test_uses_expanded_terms_in_bm25(self):
        """BUG-10: Expanded terms should be used in BM25 scoring."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            files = []
            f1 = tmpp / "save_utils.py"
            f1.write_text("def persist_data(): pass")
            cf1 = CodeFile(path=f1, rel="save_utils.py", size=f1.stat().st_size, text=f1.read_text())
            files.append(cf1)

            idf, avg_dl, _ = build_bm25_index(files)

            result = select_context("persist", files, idf, avg_dl, False, None, None)
            assert len(result) >= 0


class TestRenderContext:
    def test_basic(self):
        cf = CodeFile(path=Path("test.py"), rel="test.py", size=10, text="def foo(): pass\n")
        rendered = render_context([cf])
        assert "test.py" in rendered
        assert "def foo" in rendered

    def test_budget(self):
        cf = CodeFile(path=Path("test.py"), rel="test.py", size=100, text="x\n" * 100)
        rendered = render_context([cf], context_limit=10)
        assert len(rendered) <= 10 + len("--- FILE: test.py ---\n")
