"""Tests for agent core."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import (
    AgentLoop, AgentConfig, AgentPhase, AgentPlan, FileChangePlan,
    TaskIntent, _extract_json_block, parse_tool_calls,
)
from core.tools.base import ToolRegistry


class TestAgentLoop:
    def test_start_task(self):
        loop = AgentLoop()
        tid = loop.start_task("Fix bug")
        assert len(tid) > 0
        task = loop.get_task(tid)
        assert task is not None
        assert task.user_query == "Fix bug"

    def test_stop_task(self):
        loop = AgentLoop()
        tid = loop.start_task("Fix bug")
        loop.stop_task(tid, "user_stopped")
        task = loop.get_task(tid)
        assert task.status == "stopped"

    def test_should_continue(self):
        loop = AgentLoop()
        loop.config = AgentConfig(max_steps=2)
        tid = loop.start_task("Fix bug")
        assert loop.should_continue(tid) is True

    def test_should_continue_max_steps(self):
        loop = AgentLoop()
        loop.config = AgentConfig(max_steps=1)
        tid = loop.start_task("Fix bug")
        loop.add_step(tid, "test", {})
        assert loop.should_continue(tid) is False

    def test_set_get_plan(self):
        loop = AgentLoop()
        tid = loop.start_task("Fix bug")
        plan = AgentPlan(description="Test plan", estimated_steps=1)
        loop.set_plan(tid, plan)
        assert loop.get_plan(tid) is plan

    def test_approve_file(self):
        loop = AgentLoop()
        tid = loop.start_task("Fix bug")
        fcp = FileChangePlan(path="main.py", diff="", old_content="", new_content="pass\n")
        plan = AgentPlan(description="Test", estimated_steps=1, files=[fcp])
        loop.set_plan(tid, plan)
        assert loop.approve_file(tid, "main.py") is True
        assert fcp.user_approved is True

    def test_reject_file(self):
        loop = AgentLoop()
        tid = loop.start_task("Fix bug")
        fcp = FileChangePlan(path="main.py", diff="", old_content="", new_content="pass\n")
        plan = AgentPlan(description="Test", estimated_steps=1, files=[fcp])
        loop.set_plan(tid, plan)
        assert loop.reject_file(tid, "main.py") is True
        assert fcp.status == "rejected"


class TestAnalyzeTask:
    def test_simple(self):
        loop = AgentLoop()
        intent = loop.analyze_task("What does this function do?", "context")
        assert intent.type == "simple"

    def test_complex(self):
        loop = AgentLoop()
        intent = loop.analyze_task("Refactor the authentication module to use JWT", "context")
        assert intent.requires_plan is True


class TestGeneratePlan:
    def test_from_json(self):
        plan_text = '''```plan
{
  "description": "Add logging",
  "files": [
    {"path": "main.py", "diff": "diff", "old_content": "", "new_content": "import logging", "dependencies": []}
  ]
}
```'''
        loop = AgentLoop()
        plan = loop.generate_plan("Add logging", "", [plan_text])
        assert plan is not None
        assert len(plan.files) == 1

    def test_from_code_blocks(self):
        plan_text = '''```main.py
import logging
print("hello")
```'''
        loop = AgentLoop()
        plan = loop.generate_plan("Add logging", "", [plan_text])
        assert plan is not None
        assert len(plan.files) == 1


class TestApplyPlan:
    def test_dependency_skip(self):
        """BUG-13: When dependency is not met, the entire file should be skipped."""
        loop = AgentLoop()
        tid = loop.start_task("Fix bug")
        # b depends on c, but c is not in the plan at all
        fcp_c = FileChangePlan(path="c.py", diff="", old_content="", new_content="import x\n", dependencies=["nonexistent.py"])
        plan = AgentPlan(description="Test", estimated_steps=1, files=[fcp_c])
        loop.set_plan(tid, plan)
        # Approve c but its dependency is nonexistent, so it should be skipped
        loop.approve_file(tid, "c.py")
        from unittest.mock import patch, MagicMock
        import core.tools
        with patch.object(core.tools.ToolRegistry, 'execute') as mock_exec:
            mock_exec.return_value = "ok"
            result = loop.apply_plan(tid)
            assert "SKIPPED" in result

    def test_dependency_order(self):
        """BUG-13: Files should be applied in dependency order."""
        loop = AgentLoop()
        fcp_a = FileChangePlan(path="a.py", diff="", old_content="", new_content="pass\n", dependencies=[])
        fcp_b = FileChangePlan(path="b.py", diff="", old_content="", new_content="import a\n", dependencies=["a.py"])
        plan = AgentPlan(description="Test", estimated_steps=2, files=[fcp_a, fcp_b])

        ordered = loop._topo_sort_files(plan.files)
        assert ordered[0].path == "a.py"

    def test_topo_sort_circular(self):
        loop = AgentLoop()
        fcp_a = FileChangePlan(path="a.py", diff="", old_content="", new_content="", dependencies=["b.py"])
        fcp_b = FileChangePlan(path="b.py", diff="", old_content="", new_content="", dependencies=["a.py"])
        # Circular dependency - should handle gracefully
        result = loop._topo_sort_files([fcp_a, fcp_b])
        assert len(result) == 2


class TestJSONBlockExtraction:
    def test_basic(self):
        text = 'some text {"tool": "read_file", "args": {"path": "main.py"}} more text'
        result = _extract_json_block(text, len("some text "))
        assert result is not None
        assert result["tool"] == "read_file"

    def test_nested(self):
        """Nested JSON with tool/args should be extracted correctly."""
        text = '{"tool": "write_file", "args": {"path": "main.py", "nested": {"deep": "value"}}}'
        result = _extract_json_block(text, 0)
        assert result is not None
        assert result["tool"] == "write_file"
        assert result["args"]["nested"]["deep"] == "value"

    def test_nested_vs_recover_regex(self):
        """BUG-14: Nested JSON should be handled by _extract_json_block (not regex)."""
        nested_json = json.dumps({
            "tool": "edit_file",
            "args": {
                "path": "main.py",
                "nested_analysis": {
                    "key": "nested: {value}"
                }
            }
        })
        result = _extract_json_block(nested_json, 0)
        assert result is not None
        assert result["tool"] == "edit_file"
        assert result["args"]["nested_analysis"]["key"] == "nested: {value}"


class TestParseToolCalls:
    def test_json_format(self):
        text = '{"tool": "read_file", "args": {"path": "main.py"}}'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["tool"] == "read_file"

    def test_xml_tags(self):
        text = '<tool>{"tool": "write_file", "args": {"path": "test.py"}}</tool>'
        calls = parse_tool_calls(text)
        assert len(calls) == 1

    def test_code_blocks(self):
        text = '```src/main.py\nimport os\nprint("hello")\n```'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["tool"] == "write_file"

    def test_no_calls(self):
        calls = parse_tool_calls("Just plain text")
        assert calls == []


class TestToolRegistry:
    def test_register(self):
        from core.tools.base import Tool
        class TestTool(Tool):
            name = "test_tool_xyz"
            description = "A test tool"
            parameters = {}
            def execute(self, **kw):
                return "ok"
        ToolRegistry.register(TestTool())
        assert ToolRegistry.get("test_tool_xyz") is not None

    def test_not_found(self):
        from exceptions import ToolNotFoundError
        import pytest
        with pytest.raises(ToolNotFoundError):
            ToolRegistry.get("nonexistent_tool_xyz")
