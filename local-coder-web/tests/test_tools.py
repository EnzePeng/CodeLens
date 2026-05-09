"""
Tests for Agent tools.
"""
import pytest
import tempfile
from pathlib import Path

from core.tools import ToolRegistry
from core.tools.read_file import ReadFileTool
from core.tools.write_file import WriteFileTool
from core.tools.edit_file import EditFileTool
from core.tools.search_files import SearchFilesTool
from core.tools.list_directory import ListDirectoryTool
from core.tools.run_command import RunCommandTool
from core.tools.undo_edit import UndoManager
from models import state


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    
    # Create test files
    (repo / "main.py").write_text("def hello():\n    print('Hello')\n")
    (repo / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    
    # Create subdirectory
    subdir = repo / "src"
    subdir.mkdir()
    (subdir / "module.py").write_text("class Test:\n    pass\n")
    
    # Set global state
    state.root = repo
    state.files = []
    
    yield repo
    
    # Cleanup
    state.root = None
    state.files = []


def test_read_file_tool(temp_repo):
    """Test read_file tool."""
    tool = ReadFileTool()
    
    result = tool.execute(path="main.py")
    assert "main.py" in result
    assert "def hello" in result


def test_write_file_tool(temp_repo):
    """Test write_file tool."""
    tool = WriteFileTool()
    
    result = tool.execute(path="new_file.py", content="# New file\nprint('test')\n")
    assert "Successfully wrote" in result
    
    # Verify file was created
    assert (temp_repo / "new_file.py").exists()
    assert (temp_repo / "new_file.py").read_text() == "# New file\nprint('test')\n"


def test_edit_file_tool(temp_repo):
    """Test edit_file tool."""
    tool = EditFileTool()
    
    result = tool.execute(
        path="main.py",
        old_str="def hello():",
        new_str="def hello_world():"
    )
    assert "Successfully edited" in result
    
    # Verify change
    content = (temp_repo / "main.py").read_text()
    assert "def hello_world():" in content


def test_search_files_tool(temp_repo):
    """Test search_files tool."""
    tool = SearchFilesTool()
    
    result = tool.execute(pattern="def")
    assert "main.py" in result or "def" in result


def test_list_directory_tool(temp_repo):
    """Test list_directory tool."""
    tool = ListDirectoryTool()
    
    result = tool.execute(path="", recursive=False)
    assert "main.py" in result
    assert "utils.py" in result


def test_run_command_tool(temp_repo):
    """Test run_command tool."""
    tool = RunCommandTool()
    
    # Test simple command
    result = tool.execute(command="echo hello")
    assert "hello" in result.lower() or "exit code" in result.lower()


def test_undo_manager():
    """Test undo manager."""
    # Create a temp backup file for isolation
    import tempfile
    import os
    old_backup = os.environ.get("_LOCAL_CODER_BACKUP")

    # Patch the UndoManager to use a temp file
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        temp_path = tmp.name

    import core.tools.undo_edit as ue_module
    original_file = ue_module._BACKUP_FILE
    ue_module._BACKUP_FILE = Path(temp_path)
    # Create a fresh UndoManager instance
    fresh_mgr = object.__new__(UndoManager)
    fresh_mgr.max_history = 5
    fresh_mgr._history = []

    # Record some edits
    fresh_mgr.record_edit("file1.txt", "old1", "new1", "write_file")
    fresh_mgr.record_edit("file2.txt", "old2", "new2", "edit_file")

    # Get history
    history = fresh_mgr.get_history(limit=10)
    assert len(history) == 2

    # Cleanup
    ue_module._BACKUP_FILE = original_file
    try:
        os.unlink(temp_path)
    except OSError:
        pass


def test_tool_registry():
    """Test tool registry."""
    tools = ToolRegistry.list_tools()
    
    assert len(tools) > 0
    assert any(t["name"] == "read_file" for t in tools)
    assert any(t["name"] == "write_file" for t in tools)
    assert any(t["name"] == "edit_file" for t in tools)


def test_security_path_traversal(temp_repo):
    """Test security: path traversal prevention."""
    from exceptions import SecurityError
    
    tool = WriteFileTool()
    
    with pytest.raises(SecurityError):
        tool.execute(path="../../etc/passwd", content="malicious")


def test_security_dangerous_command():
    """Test security: dangerous command prevention."""
    from exceptions import SecurityError
    
    tool = RunCommandTool()
    
    with pytest.raises(SecurityError):
        tool.execute(command="rm -rf /")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])