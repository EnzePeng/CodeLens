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


# Max chars to return to LLM (keep context manageable)
MAX_RETURN_CHARS = 6000


class ReadFileTool(Tool):
    """Read file content within the indexed repository."""
    
    name = "read_file"
    description = "读取文件内容并返回带行号的代码。需要分析文件时必须调用此工具。"
    parameters = {
        "path": {
            "type": "string",
            "description": "文件的相对路径，如 core/agent.py 或 config.py",
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
    
    def execute(self, path: str = "", start_line: Optional[int] = None, end_line: Optional[int] = None, **kwargs) -> str:
        """Read file content."""
        if not path:
            raise FileAccessError("Missing required argument: path")
        if state.root is None:
            raise FileAccessError("No repository folder set")
        
        # Security: ensure path stays within repo root
        # Handle both absolute and relative paths from LLM
        p = Path(path)
        if p.is_absolute():
            try:
                target = p.resolve()
                target.relative_to(state.root.resolve())
            except ValueError:
                # Try stripping repo root prefix
                try:
                    rel = p.resolve().relative_to(state.root.resolve())
                    target = state.root / rel
                except ValueError:
                    raise SecurityError("Path is outside the repository root")
        else:
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
            full_content = "".join(selected_lines)
            
            # Smart truncation for large files
            if len(full_content) > MAX_RETURN_CHARS:
                half = MAX_RETURN_CHARS // 2
                head = "".join(selected_lines[:50])  # First 50 lines
                tail = "".join(selected_lines[-30:])  # Last 30 lines
                numbered_content = f"{head}\n\n... [{len(lines)} lines total, truncated] ...\n\n{tail}"
            else:
                numbered_content = "".join(
                    f"{i+1:4d}: {line}" for i, line in enumerate(selected_lines, start=start_idx + 1)
                )
            
            return f"File: {path}\nLines: {start_idx+1}-{end_idx}\nSize: {size} bytes\n\n{numbered_content}"
            
        except OSError as e:
            raise FileAccessError(f"Read failed: {e}")


# Register tool
read_file_tool = ReadFileTool()
from core.tools.base import register_tool
register_tool(read_file_tool)