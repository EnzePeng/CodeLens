"""
Tool: write_file - Write content to file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tools.base import Tool
from config import MAX_FILE_BYTES
from exceptions import FileAccessError, SecurityError
from models import state


class WriteFileTool(Tool):
    """Write content to a file within the indexed repository."""
    
    name = "write_file"
    description = "Create or overwrite a file with given content."
    parameters = {
        "path": {
            "type": "string",
            "description": "Relative path to the file from repository root",
        },
        "content": {
            "type": "string",
            "description": "File content to write",
        },
    }
    
    def execute(self, path: str, content: str, **kwargs) -> str:
        """Write content to file, recording edit history for undo."""
        if state.root is None:
            raise FileAccessError("No repository folder set")

        target = (state.root / path).resolve()
        try:
            target.relative_to(state.root.resolve())
        except ValueError:
            raise SecurityError("Path is outside the repository root")

        content_bytes = len(content.encode("utf-8"))
        if content_bytes > MAX_FILE_BYTES:
            raise FileAccessError(f"Content too large: {content_bytes} bytes (max: {MAX_FILE_BYTES})")

        # Record old content for undo
        old_content = ""
        try:
            if target.exists():
                old_content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as e:
            raise FileAccessError(f"Write failed: {e}")

        # Record edit for undo
        from core.tools.undo_edit import get_undo_manager
        undo_mgr = get_undo_manager()
        undo_mgr.record_edit(path, old_content, content, "write_file")

        return f"Successfully wrote {content_bytes} bytes to {path}"


# Register tool
write_file_tool = WriteFileTool()
from core.tools.base import register_tool
register_tool(write_file_tool)