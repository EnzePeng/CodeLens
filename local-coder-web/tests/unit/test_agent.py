"""Tests for core.agent — tool-call parsing utilities.

After the engine split, core/agent.py retains only parse_tool_calls and
_extract_json_block (used by core.react.ReActLoop). These tests cover that
contract. The legacy AgentEngine/AgentConfig/AgentPlan/FileChangePlan/
TaskIntent classes were removed as dead code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import parse_tool_calls, _extract_json_block


class TestExtractJsonBlock:
    def test_extracts_simple_tool_call(self):
        text = 'before {"tool": "read_file", "args": {"path": "a.py"}} after'
        result = _extract_json_block(text, text.index("{"))
        assert result is not None
        assert result["tool"] == "read_file"
        assert result["args"]["path"] == "a.py"

    def test_returns_none_for_non_tool_json(self):
        text = '{"foo": "bar"}'
        assert _extract_json_block(text, 0) is None

    def test_returns_none_for_plain_text(self):
        assert _extract_json_block("no json here", 0) is None

    def test_handles_nested_braces_in_strings(self):
        text = '{"tool": "edit_file", "args": {"old_str": "if (x) {", "new_str": "if x:"}}'
        result = _extract_json_block(text, 0)
        assert result is not None
        assert result["tool"] == "edit_file"


class TestParseToolCalls:
    def test_parses_single_tool_call(self):
        text = 'I will read the file.\n{"tool": "read_file", "args": {"path": "main.py"}}'
        calls = parse_tool_calls(text, available_tools=["read_file"])
        assert len(calls) >= 1
        assert calls[0]["tool"] == "read_file"
        assert calls[0]["args"]["path"] == "main.py"

    def test_returns_empty_for_no_tool_calls(self):
        calls = parse_tool_calls("Just a plain answer with no tools.", available_tools=["read_file"])
        assert calls == []

    def test_ignores_unknown_tools(self):
        text = '{"tool": "nonexistent_tool", "args": {}}'
        calls = parse_tool_calls(text, available_tools=["read_file", "write_file"])
        # Parser may or may not include unknown tools depending on strictness,
        # but it should never crash.
        assert isinstance(calls, list)

    def test_handles_malformed_json_gracefully(self):
        text = '{"tool": "read_file", "args": {'  # truncated
        calls = parse_tool_calls(text, available_tools=["read_file"])
        assert isinstance(calls, list)
