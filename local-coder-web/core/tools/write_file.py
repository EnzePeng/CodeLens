"""
Tool: write_file - Write content to file with atomic write (#127).

Improvements:
- #64 Atomic write with backup
- #127 Atomic file writes
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from config import MAX_FILE_BYTES
from exceptions import FileAccessError, SecurityError
from models import state


class WriteFileTool(Tool):
    """Write content to file with atomic write and backup."""

    name = "write_file"
    description = "Create or overwrite a file with given content. Uses atomic write for safety."
    parameters = {
        "path": {"type": "string", "description": "Relative path to the file"},
        "content": {"type": "string", "description": "File content to write"},
    }

    def execute(self, path: str = "", content: str = "", **kwargs) -> str:
        if not path or not content:
            raise FileAccessError(f"Missing required arguments: {'path' if not path else 'content'}")
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

        old_content = ""
        try:
            if target.exists():
                old_content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # #64,#127 Atomic write: write to temp file then rename
            temp_path = target.with_suffix(target.suffix + ".tmp")
            temp_path.write_text(content, encoding="utf-8")
            os.replace(str(temp_path), str(target))
        except OSError as e:
            # Clean up temp file on failure
            try:
                target.with_suffix(target.suffix + ".tmp").unlink(missing_ok=True)
            except OSError:
                pass
            raise FileAccessError(f"Write failed: {e}")

        # Record edit for undo
        from core.tools.undo_edit import get_undo_manager
        undo_mgr = get_undo_manager()
        undo_mgr.record_edit(path, old_content, content, "write_file")

        return f"Successfully wrote {content_bytes} bytes to {path}"


write_file_tool = WriteFileTool()
from core.tools.base import register_tool
register_tool(write_file_tool)
