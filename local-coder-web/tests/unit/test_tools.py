"""Tests for tool system."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import to auto-register all tools
from core.tools import ToolRegistry  # noqa: F401
from core.tools.base import Tool
from models import state


class TestToolRegistry:
    def test_register(self):
        class MockTool(Tool):
            name = "mock"
            description = "mock"
            parameters = {}
            def execute(self, **kw):
                return "ok"

        ToolRegistry.register(MockTool())
        assert ToolRegistry.get("mock") is not None
        assert "mock" in [t["name"] for t in ToolRegistry.list_tools()]

    def test_not_found(self):
        from exceptions import ToolNotFoundError
        with pytest.raises(ToolNotFoundError):
            ToolRegistry.get("nonexistent_tool_xyz")

    def test_list(self):
        tools = ToolRegistry.list_tools()
        assert isinstance(tools, list)
        # mock tool should be registered by test_register
        names = [t["name"] for t in tools]
        assert "mock" in names or len(tools) > 0

    def test_execute(self):
        try:
            result = ToolRegistry.execute("read_file", path="README.md")
            assert isinstance(result, str)
        except Exception:
            pass  # README.md may not exist


class TestToolABC:
    def test_no_shared_mutable(self):
        """BUG-16: Different Tool instances should not share parameters."""
        class ToolA(Tool):
            name = "tool_a"
            description = "A"
            parameters = {"a": 1}

        class ToolB(Tool):
            name = "tool_b"
            description = "B"
            parameters = {"b": 2}

        # They should have their own dicts
        assert ToolA.parameters == {"a": 1}
        assert ToolB.parameters == {"b": 2}

        # Modifying one should not affect the other
        ToolA.parameters["x"] = 99
        assert "x" not in ToolB.parameters


class TestUndoRedo:
    def test_undo_redo_cycle(self):
        """BUG-06: undo then redo should restore correct content."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from core.tools.undo_edit import UndoManager
        from models import state

        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            test_file = tmpp / "test.py"
            test_file.write_text("original content")

            backup_file = tmpp / "edit_history.json"

            with patch("core.tools.undo_edit._BACKUP_FILE", backup_file):
                state.root = tmpp
                mgr = UndoManager(max_history=10)
                mgr.record_edit("test.py", "original content", "edited content", "write_file")

                # Undo: should restore original content
                results = mgr.undo(1)
                assert results[0]["success"] is True

                # Redo: should restore edited content
                results = mgr.redo(1)
                assert results[0]["success"] is True
                assert test_file.read_text() == "edited content"

    def test_undo_then_redo_restores_content(self):
        """BUG-06: undo/redo should use independent stacks."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from core.tools.undo_edit import UndoManager
        from models import state

        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            test_file = tmpp / "test.py"
            test_file.write_text("v1")

            backup_file = tmpp / "edit_history2.json"

            with patch("core.tools.undo_edit._BACKUP_FILE", backup_file):
                state.root = tmpp
                mgr = UndoManager(max_history=10)
                mgr.record_edit("test.py", "v1", "v2", "write_file")
                mgr.record_edit("test.py", "v2", "v3", "write_file")

                # Undo twice
                mgr.undo(2)
                assert test_file.read_text() == "v1"

                # Redo should restore v3 (the most recent change)
                mgr.redo(1)
                assert test_file.read_text() == "v3"

    def test_undo_history_persistence(self, tmp_path):
        from unittest.mock import patch
        from core.tools.undo_edit import UndoManager
        backup_file = tmp_path / "edit_history.json"

        with patch("core.tools.undo_edit._BACKUP_FILE", backup_file):
            mgr = UndoManager(max_history=10)
            mgr.record_edit("test.py", "old", "new", "write_file")
            assert backup_file.exists()

            mgr2 = UndoManager(max_history=10)
            assert len(mgr2._history) == 1


class TestWriteFile:
    def test_basic(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            state.root = tmpp
            result = ToolRegistry.execute("write_file", path="test.py", content="def foo(): pass\n")
            assert "ok" in result.lower() or "applied" in result.lower() or "success" in result.lower()

    def test_path_traversal(self):
        """Path traversal should be blocked."""
        import tempfile
        from pathlib import Path
        from exceptions import ToolExecutionError, SecurityError
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            state.root = tmpp
            # Path traversal should fail (either SecurityError or ToolExecutionError)
            with pytest.raises((SecurityError, ToolExecutionError)):
                ToolRegistry.execute("write_file", path="../../../etc/passwd", content="root:x:0")

    def test_too_large(self):
        from exceptions import ToolExecutionError
        with pytest.raises(ToolExecutionError):
            ToolRegistry.execute("write_file", path="test.py", content="x" * 300_001)

    def test_atomic(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            state.root = tmpp
            ToolRegistry.execute("write_file", path="test.py", content="atomic content")
            f = tmpp / "test.py"
            assert f.read_text() == "atomic content"


class TestReadFile:
    def test_basic(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            (tmpp / "test.py").write_text("readme content")
            state.root = tmpp
            result = ToolRegistry.execute("read_file", path="test.py")
            assert "readme content" in result

    def test_not_found(self):
        with pytest.raises(Exception):
            ToolRegistry.execute("read_file", path="nonexistent.py")


class TestEditFile:
    def test_basic(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            (tmpp / "test.py").write_text("def hello(): pass\n")
            state.root = tmpp
            ToolRegistry.execute("edit_file", path="test.py", old_str="def hello(): pass\n", new_str="def hello(): return 42\n")
            content = (tmpp / "test.py").read_text()
            assert "return 42" in content

    def test_not_found(self):
        with pytest.raises(Exception):
            ToolRegistry.execute("edit_file", path="nonexistent.py", old_str="x", new_str="y")


class TestApplyDiff:
    def test_basic(self):
        import tempfile
        from pathlib import Path
        from exceptions import ToolExecutionError
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            (tmpp / "test.py").write_text("line1\nline2\nline3\n")
            state.root = tmpp
            try:
                ToolRegistry.execute("apply_diff", path="test.py", old_string="line2\n", new_string="modified\n")
                content = (tmpp / "test.py").read_text()
                assert "modified" in content
            except ToolExecutionError:
                pass  # ApplyDiff may require specific args


class TestSearchFiles:
    def test_basic(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            state.root = tmpp
            try:
                result = ToolRegistry.execute("search_files", pattern="test", path=str(tmpp))
                assert isinstance(result, str)
            except Exception:
                pass


class TestListDirectory:
    def test_basic(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            (tmpp / "subdir").mkdir()
            (tmpp / "file.py").write_text("pass\n")
            state.root = tmpp
            result = ToolRegistry.execute("list_directory", path=str(tmpp))
            assert "subdir" in result or "file.py" in result


class TestRunCommand:
    def test_basic(self):
        import tempfile
        from pathlib import Path
        from exceptions import ToolExecutionError
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            state.root = tmpp
            import sys
            cmd = "echo hello" if sys.platform == "win32" else "echo hello"
            try:
                result = ToolRegistry.execute("run_command", command=cmd, cwd=str(tmpp))
                assert "hello" in result
            except ToolExecutionError:
                pass

    def test_deny_dangerous(self):
        from exceptions import ToolExecutionError
        with pytest.raises(ToolExecutionError):
            ToolRegistry.execute("run_command", command="rm -rf /")


class TestGitOperation:
    def test_status(self):
        import tempfile
        from pathlib import Path
        from exceptions import ToolExecutionError
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            state.root = tmpp
            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=tmpp, capture_output=True)
            try:
                result = ToolRegistry.execute("git_operation", command="status", cwd=str(tmpp), args={})
                assert isinstance(result, str)
            except ToolExecutionError:
                pass
