"""
Tool: search_files - Search for pattern in files.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from core.tools.base import Tool
from exceptions import FileAccessError, SecurityError
from models import state


class SearchFilesTool(Tool):
    """Search for a pattern in files within the repository."""
    
    name = "search_files"
    description = "Search for a regex pattern in files. Returns matching lines with context."
    parameters = {
        "pattern": {
            "type": "string",
            "description": "Regular expression pattern to search for",
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (relative path, optional)",
        },
        "file_glob": {
            "type": "string",
            "description": "File glob pattern (e.g., '*.py', 'src/*.js')",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return (default: 50)",
        },
    }
    
    def execute(
        self,
        pattern: str,
        path: str = "",
        file_glob: Optional[str] = None,
        max_results: int = 50,
        **kwargs
    ) -> str:
        """Search for pattern in files."""
        if state.root is None:
            raise FileAccessError("No repository folder set")
        
        # Resolve search directory
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
        
        # Compile regex
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise FileAccessError(f"Invalid regex pattern: {e}")
        
        # Search files
        results: list[str] = []
        files_checked = 0
        
        for file in state.files:
            if len(results) >= max_results:
                break
            
            # Skip files outside search directory
            try:
                file.path.relative_to(search_dir)
            except ValueError:
                continue
            
            # Filter by glob if specified
            if file_glob:
                import fnmatch
                if not fnmatch.fnmatch(file.path.name, file_glob):
                    continue
            
            # Search in file content
            files_checked += 1
            lines = file.text.splitlines()
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    results.append(f"{file.rel}:{i}: {line[:150]}")
                    if len(results) >= max_results:
                        break
        
        if not results:
            return f"No matches found for pattern: {pattern}\nSearched {files_checked} files."
        
        return f"Found {len(results)} matches (max: {max_results}):\n\n" + "\n".join(results[:max_results])


# Register tool
search_files_tool = SearchFilesTool()
from core.tools.base import register_tool
register_tool(search_files_tool)