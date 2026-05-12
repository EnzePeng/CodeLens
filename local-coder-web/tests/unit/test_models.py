"""Tests for data models."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import (
    CodeFile, AppState, AgentState, HealthResponse,
    AskRequest, CraftApplyRequest, extract_symbols,
)


class TestCodeFileCreation:
    def test_codefile_creation(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo(): pass\n")
        cf = CodeFile(path=f, rel="test.py", size=f.stat().st_size, text=f.read_text())
        assert cf.path == f
        assert cf.rel == "test.py"
        assert cf.symbols == []
        assert cf.tf == {}

    def test_codefile_defaults(self):
        cf = CodeFile(path=Path("/dev/null"), rel="x", size=0, text="")
        assert cf.symbols == []
        assert cf.tf == {}
        assert cf.tokens_list == []
        assert cf.embedding is None


class TestExtractSymbols:
    def test_extract_symbols_python(self):
        text = "def hello(): pass\nclass Foo: pass\n"
        syms = extract_symbols(text)
        assert "hello" in syms
        assert "Foo" in syms

    def test_extract_symbols_no_duplicates(self):
        """BUG-27: duplicate patterns should not create duplicate symbols."""
        text = "def foo(): pass\ndef bar(): pass\n"
        syms = extract_symbols(text)
        assert syms.count("foo") == 1
        assert syms.count("bar") == 1

    def test_extract_symbols_max_30(self):
        text = "\n".join(f"def func{i}(): pass" for i in range(50))
        syms = extract_symbols(text)
        assert len(syms) <= 30

    def test_extract_symbols_async_def(self):
        text = "async def async_foo(): pass\n"
        syms = extract_symbols(text)
        assert "async_foo" in syms


class TestAskRequest:
    def test_ask_request_model(self):
        """BUG-02: AskRequest should parse JSON body correctly."""
        req = AskRequest(question="How do I sort a list?")
        assert req.question == "How do I sort a list?"
        assert req.mode == "ask"

    def test_ask_request_all_fields(self):
        req = AskRequest(
            question="Fix bug",
            mode="craft",
            file_path="main.py",
            new_content="def foo(): return 42\n",
            max_tokens=1024,
            temperature=0.5,
            context_limit=5000,
        )
        assert req.mode == "craft"
        assert req.file_path == "main.py"
        assert req.max_tokens == 1024


class TestCraftApplyRequest:
    def test_craft_apply_request_model(self):
        """BUG-04: CraftApplyRequest should validate fields."""
        req = CraftApplyRequest(file_path="main.py", content="def foo(): pass\n")
        assert req.file_path == "main.py"
        assert req.content == "def foo(): pass\n"


class TestAgentState:
    def test_agent_state_mutable_defaults(self):
        """BUG-17: AgentState instances should not share mutable defaults."""
        s1 = AgentState(task_id="t1", user_query="q")
        s2 = AgentState(task_id="t2", user_query="q")
        s1.steps.append("step1")
        s1.context["key"] = "value"
        assert len(s2.steps) == 0
        assert "key" not in s2.context


class TestHealthResponse:
    def test_health_response_defaults(self):
        h = HealthResponse()
        assert h.status == "ok"
        assert h.embedding_mode == "bm25"
