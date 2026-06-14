"""
Tool: search_files - Search for pattern in files with highlighting.

Improvements:
- #67 Search with ANSI highlight matches
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Optional

from core.tools.base import Tool
from exceptions import FileAccessError, SecurityError
from models import state


class SearchFilesTool(Tool):
    """Search for a pattern in files with ANSI highlighting."""

    name = "search_files"
    description = "Search for a regex pattern in files. Returns matching lines with highlighted matches."
    parameters = {
        "pattern": {"type": "string", "description": "Regular expression pattern to search for"},
        "path": {"type": "string", "description": "Directory to search in (relative path)"},
        "file_glob": {"type": "string", "description": "File glob pattern (e.g., '*.py')"},
        "max_results": {"type": "integer", "description": "Maximum number of results (default: 50)"},
    }

    def execute(
        self,
        pattern: str = "",
        path: str = "",
        file_glob: Optional[str] = None,
        max_results: int = 50,
        **kwargs
    ) -> str:
        if not pattern:
            raise FileAccessError("Missing required argument: pattern")
        if state.root is None:
            raise FileAccessError("No repository folder set")

        if path:
            search_dir = (state.root / path).resolve()
            try:
                search_dir.relative_to(state.root.resolve())
            except ValueError:
                raise SecurityError("Search path is outside the repository root")
        else:
            search_dir = state.root

        if not search_dir.exists():
            raise FileAccessError(f"Search directory not found: {path}")

        # Auto-convert glob patterns to regex (e.g. "*.py" -> ".*\.py")
        if '*' in pattern or '?' in pattern:
            pattern = fnmatch.translate(pattern)

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise FileAccessError(f"Invalid regex pattern: {e}")

        results: list[str] = []
        files_checked = 0

        for file in state.files:
            if len(results) >= max_results:
                break
            try:
                file.path.relative_to(search_dir)
            except ValueError:
                continue

            if file_glob and not fnmatch.fnmatch(file.path.name, file_glob):
                continue

            files_checked += 1
            lines = file.text.splitlines()
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    # #67 Highlight matches with ANSI codes
                    highlighted = regex.sub(lambda m: f"\x1b[41m{m.group()}\x1b[0m", line)
                    results.append(f"{file.rel}:{i}: {highlighted[:150]}")
                    if len(results) >= max_results:
                        break

        if not results:
            return f"No matches found for pattern: {pattern}\nSearched {files_checked} files."
        return f"Found {len(results)} matches (max: {max_results}):\n\n" + "\n".join(results[:max_results])


search_files_tool = SearchFilesTool()
from core.tools.base import register_tool
register_tool(search_files_tool)
