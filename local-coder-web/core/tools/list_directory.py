"""
Tool: list_directory - List directory contents.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from config import IGNORE_DIRS, CODE_EXTS
from exceptions import FileAccessError, SecurityError
from models import state


class ListDirectoryTool(Tool):
    """List directory contents with optional recursion."""
    
    name = "list_directory"
    description = "列出目录中的文件和子目录。"
    parameters = {
        "path": {
            "type": "string",
            "description": "Directory path (relative to repo root, or empty for root)",
        },
        "recursive": {
            "type": "boolean",
            "description": "Whether to list recursively (default: false)",
        },
        "max_depth": {
            "type": "integer",
            "description": "Maximum depth for recursive listing (default: 2)",
        },
        "include_files": {
            "type": "boolean",
            "description": "Whether to include files (default: true)",
        },
    }
    
    def execute(
        self,
        path: str = "",
        recursive: bool = False,
        max_depth: int = 2,
        include_files: bool = True,
        **kwargs
    ) -> str:
        """List directory contents."""
        if state.root is None:
            raise FileAccessError("No repository folder set")
        
        # Resolve directory
        if path:
            # Handle both absolute and relative paths from LLM
            p = Path(path)
            if p.is_absolute():
                try:
                    target_dir = p.resolve()
                    target_dir.relative_to(state.root.resolve())
                except ValueError:
                    # Try stripping repo root prefix
                    try:
                        rel = p.resolve().relative_to(state.root.resolve())
                        target_dir = state.root / rel
                    except ValueError:
                        raise SecurityError("Path is outside the repository root")
            else:
                target_dir = (state.root / path).resolve()
                try:
                    target_dir.relative_to(state.root.resolve())
                except ValueError:
                    raise SecurityError("Path is outside the repository root")
        else:
            target_dir = state.root
        
        if not target_dir.exists():
            raise FileAccessError(f"Directory not found: {path}")
        
        if not target_dir.is_dir():
            raise FileAccessError(f"Not a directory: {path}")
        
        # Build tree structure
        def list_dir(dir_path: Path, depth: int = 0, prefix: str = "") -> list[str]:
            if depth > max_depth:
                return []
            
            lines = []
            try:
                entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError as e:
                return [f"Error reading {dir_path}: {e}"]
            
            for i, entry in enumerate(entries):
                if entry.name in IGNORE_DIRS or entry.name.startswith("."):
                    continue
                
                is_last = i == len(entries) - 1
                current_prefix = "└── " if is_last else "├── "
                connector = "    " if is_last else "│   "
                
                if entry.is_dir():
                    lines.append(f"{prefix}{current_prefix}{entry.name}/")
                    if recursive and depth < max_depth:
                        lines.extend(list_dir(entry, depth + 1, prefix + connector))
                elif include_files:
                    ext = entry.suffix.lower()
                    icon = "[py]" if ext == ".py" else "[code]" if ext in CODE_EXTS else "[file]"
                    try:
                        size = entry.stat().st_size
                        size_str = f" ({size:,} bytes)" if size < 100000 else ""
                    except OSError:
                        size_str = ""
                    lines.append(f"{prefix}{current_prefix}{icon} {entry.name}{size_str}")
            
            return lines
        
        result = [f"Directory: {path or '.'}", ""]
        result.extend(list_dir(target_dir))
        
        # Count summary
        try:
            file_count = sum(1 for _ in target_dir.rglob("*") if _.is_file() and not _.name.startswith("."))
            dir_count = sum(1 for _ in target_dir.rglob("*") if _.is_dir() and not _.name.startswith("."))
            result.append("")
            result.append(f"Total: {file_count} files, {dir_count} directories")
        except OSError:
            pass
        
        return "\n".join(result)


# Register tool
list_directory_tool = ListDirectoryTool()
from core.tools.base import register_tool
register_tool(list_directory_tool)