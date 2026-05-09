"""
Tool: file_operations — copy, move, delete, create_directory.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from exceptions import FileAccessError, SecurityError
from models import state


class FileOperationsTool(Tool):
    """File operations: copy, move, delete, create_directory."""

    name = "file_operations"
    description = "Copy, move, delete files or create directories."
    parameters = {
        "operation": {
            "type": "string",
            "description": "Operation: copy, move, delete, create_directory",
        },
        "source": {
            "type": "string",
            "description": "Source path (relative to repo root)",
        },
        "destination": {
            "type": "string",
            "description": "Destination path (relative to repo root, for copy/move)",
        },
    }

    def execute(self, operation: str, source: str = "", destination: str = "", **kwargs) -> str:
        if state.root is None:
            raise FileAccessError("No repository folder set")

        src = (state.root / source).resolve()
        try:
            src.relative_to(state.root.resolve())
        except ValueError:
            raise SecurityError("Source path is outside the repository root")

        if operation == "delete":
            if src.is_dir():
                shutil.rmtree(src)
            else:
                src.unlink()
            return f"Deleted: {source}"

        elif operation == "copy":
            dst = (state.root / destination).resolve()
            try:
                dst.relative_to(state.root.resolve())
            except ValueError:
                raise SecurityError("Destination path is outside the repository root")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return f"Copied: {source} -> {destination}"

        elif operation == "move":
            dst = (state.root / destination).resolve()
            try:
                dst.relative_to(state.root.resolve())
            except ValueError:
                raise SecurityError("Destination path is outside the repository root")
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            return f"Moved: {source} -> {destination}"

        elif operation == "create_directory":
            dst = (state.root / source).resolve()
            dst.mkdir(parents=True, exist_ok=True)
            return f"Created directory: {source}"

        raise ValueError(f"Unknown operation: {operation}")


# Register tool
file_operations_tool = FileOperationsTool()
from core.tools.base import register_tool
register_tool(file_operations_tool)
