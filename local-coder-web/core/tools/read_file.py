"""
Tool: read_file - Read file content.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from core.tools.base import Tool
from config import MAX_FILE_BYTES
from exceptions import FileAccessError, SecurityError
from models import state


class ReadFileTool(Tool):
    """Read file content within the indexed repository."""
    
    name = "read_file"
    description = "Read the content of a file. Returns file content with line numbers."
    parameters = {
        "path": {
            "type": "string",
            "description": "Relative path to the file from repository root",
        },
        "start_line": {
            "type": "integer",
            "description": "Starting line number (1-based, optional)",
        },
        "end_line": {
            "type": "integer",
            "description": "Ending line number (inclusive, optional)",
        },
    }
    
    def execute(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, **kwargs) -> str:
        """Read file content."""
        if state.root is None:
            raise FileAccessError("No repository folder set")
        
        # Security: ensure path stays within repo root
        target = (state.root / path).resolve()
        try:
            target.relative_to(state.root.resolve())
        except ValueError:
            raise SecurityError("Path is outside the repository root")
        
        if not target.exists() or not target.is_file():
            raise FileAccessError(f"File not found: {path}")
        
        try:
            size = target.stat().st_size
            if size > MAX_FILE_BYTES:
                raise FileAccessError(f"File too large: {size} bytes (max: {MAX_FILE_BYTES})")
            
            content = target.read_text(encoding="utf-8", errors="replace")
            
            # Handle line range
            lines = content.splitlines(keepends=True)
            if start_line is not None:
                start_idx = max(0, start_line - 1)
            else:
                start_idx = 0
            
            if end_line is not None:
                end_idx = min(len(lines), end_line)
            else:
                end_idx = len(lines)
            
            selected_lines = lines[start_idx:end_idx]
            numbered_content = "".join(
                f"{i+1:4d}: {line}" for i, line in enumerate(selected_lines, start=start_idx + 1)
            )
            
            return f"File: {path}\nLines: {start_idx+1}-{end_idx}\n\n{numbered_content}"
            
        except OSError as e:
            raise FileAccessError(f"Read failed: {e}")


# Register tool
read_file_tool = ReadFileTool()
from core.tools.base import register_tool
register_tool(read_file_tool)