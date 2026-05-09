"""Tool System - unified registry and auto-registration."""
from core.tools.base import Tool, ToolDefinition, ToolRegistry, register_tool

# Import all tools to trigger their module-level registration
from core.tools import read_file   # noqa: F401
from core.tools import write_file  # noqa: F401
from core.tools import edit_file   # noqa: F401
from core.tools import apply_diff  # noqa: F401
from core.tools import search_files  # noqa: F401
from core.tools import list_directory  # noqa: F401
from core.tools import run_command  # noqa: F401
from core.tools import git_operation  # noqa: F401
from core.tools import undo_edit  # noqa: F401
from core.tools import diff_preview  # noqa: F401
from core.tools import file_operations  # noqa: F401
from core.tools import code_analysis  # noqa: F401
from core.tools import test  # noqa: F401
from core.tools import project  # noqa: F401

__all__ = ["Tool", "ToolDefinition", "ToolRegistry", "register_tool"]
