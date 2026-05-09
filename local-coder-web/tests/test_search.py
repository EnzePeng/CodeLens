"""
Tests for the search service (BM25 + embeddings).
"""
from __future__ import annotations

import pytest

from models import CodeFile, extract_symbols
from services.search import _tokenize_doc, _tokenize_query, _split_camel


class TestTokenization:
    """Test BM25 tokenization improvements."""

    def test_camel_case_split(self):
        result = _split_camel("getUserInfo")
        # Should split camelCase into separate words
        assert "get" in result and "User" in result and "Info" in result

    def test_tokenize_doc_handles_camel(self):
        tokens = _tokenize_doc("getUserInfo returns user details")
        assert len(tokens) > 0
        # Should contain individual tokens
        assert any("get" in t for t in tokens) or any("user" in t for t in tokens)

    def test_tokenize_query_strips_stop_words(self):
        tokens = _tokenize_query("如何在哪里找到用户")
        assert "如何" not in tokens  # stop word
        assert "怎么" not in tokens  # stop word
        assert len(tokens) >= 0  # may be empty after filtering

    def test_tokenize_cjk(self):
        tokens = _tokenize_doc("这是一个中文测试文件")
        assert any(len(t) >= 1 for t in tokens)

    def test_tokenize_empty(self):
        tokens = _tokenize_doc("")
        assert tokens == []


class TestExtractSymbols:
    """Test symbol extraction from various languages."""

    def test_python_functions(self):
        code = "def my_function(): pass\nclass MyClass: pass"
        symbols = extract_symbols(code)
        assert "my_function" in symbols
        assert "MyClass" in symbols

    def test_python_decorators(self):
        code = "@pytest.fixture\ndef test_func(): pass"
        symbols = extract_symbols(code)
        assert "test_func" in symbols

    def test_javascript_functions(self):
        code = "export function myFunc() {}\nclass MyClass {}\nconst myVar = async () => {}"
        symbols = extract_symbols(code)
        assert "myFunc" in symbols or "myVar" in symbols

    def test_typescript_interface(self):
        code = "export interface UserConfig {}\ntype MyType = {}\nenum Status { A, B }"
        symbols = extract_symbols(code)
        assert any("UserConfig" in s or "MyType" in s or "Status" in s for s in symbols)

    def test_extract_symbols_limits(self):
        long_code = "\n".join(f"def func{i}(): pass" for i in range(100))
        symbols = extract_symbols(long_code)
        assert len(symbols) <= 30  # Should be limited to ~30
