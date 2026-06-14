"""
GlobTool - File pattern matching tool (like Claude Code's Glob)
"""
from __future__ import annotations

import os
from pathlib import Path


from core.tools.base import Tool, register_tool
from models import state


class GlobTool(Tool):
    """Find files matching a glob pattern."""
    name = "glob"
    description = "Find files matching a glob pattern (e.g., **/*.py, src/**/*.ts)"
    parameters = {
        "pattern": {"type": "string", "description": "Glob pattern to match"},
        "path": {"type": "string", "description": "Directory to search in (default: repo root)"},
    }

    def execute(self, pattern: str = "", path: str = "", **kwargs) -> str:
        if not pattern:
            return "Error: pattern is required"

        root = state.root
        if not root:
            return "Error: No repository folder set"

        search_dir = root / path if path else root
        if not search_dir.exists():
            return f"Error: Directory not found: {path}"

        matches = []
        max_results = 200

        for dirpath, dirnames, filenames in os.walk(search_dir):
            # Skip hidden and ignored directories
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith('.') and d not in {
                    'node_modules', '__pycache__', '.git', '.venv', 'venv',
                    'dist', 'build', '.next', '.nuxt', '.turbo', '.cache',
                    'target', 'bin', 'obj', 'coverage',
                }
            ]

            for filename in filenames:
                if len(matches) >= max_results:
                    break

                full_path = Path(dirpath) / filename
                rel_path = full_path.relative_to(root)

                # Match against pattern
                if rel_path.match(pattern) or Path(filename).match(pattern):
                    matches.append(str(rel_path))

            if len(matches) >= max_results:
                break

        if not matches:
            return f"No files matched pattern: {pattern}"

        matches.sort()
        return "\n".join(matches)


register_tool(GlobTool())
