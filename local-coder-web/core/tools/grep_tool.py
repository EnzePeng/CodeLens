"""
GrepTool - Content search tool (like Claude Code's Grep)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from core.tools.base import Tool, register_tool
from models import state


class GrepTool(Tool):
    """Search file contents using regex pattern."""
    name = "grep"
    description = "Search file contents using regex pattern (like ripgrep)"
    parameters = {
        "pattern": {"type": "string", "description": "Regex pattern to search for"},
        "include": {"type": "string", "description": "File pattern to include (e.g., *.py)"},
        "path": {"type": "string", "description": "Directory to search in (default: repo root)"},
        "max_results": {"type": "integer", "description": "Max results (default: 50)"},
    }

    def execute(self, pattern: str = "", include: str = "", path: str = "", max_results: int = 50, **kwargs) -> str:
        if not pattern:
            return "Error: pattern is required"

        root = state.root
        if not root:
            return "Error: No repository folder set"

        search_dir = root / path if path else root
        if not search_dir.exists():
            return f"Error: Directory not found: {path}"

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results = []
        files_searched = 0

        ignore_dirs = {
            '.git', '.hg', '.svn', '.venv', 'venv', 'env', '__pycache__',
            'node_modules', 'dist', 'build', '.next', '.nuxt', '.turbo',
            '.cache', 'target', 'bin', 'obj', 'coverage',
        }

        for dirpath, dirnames, filenames in os.walk(search_dir):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith('.')]

            for filename in filenames:
                if len(results) >= max_results:
                    break

                # Filter by include pattern
                if include and not fnmatch(filename, include):
                    continue

                full_path = Path(dirpath) / filename

                # Skip binary files and large files
                try:
                    if full_path.stat().st_size > 500_000:
                        continue
                except OSError:
                    continue

                try:
                    content = full_path.read_text(encoding='utf-8', errors='ignore')
                except (OSError, UnicodeDecodeError):
                    continue

                files_searched += 1
                lines = content.split('\n')

                for line_num, line in enumerate(lines, 1):
                    if len(results) >= max_results:
                        break

                    if regex.search(line):
                        rel_path = full_path.relative_to(root)
                        results.append({
                            "file": str(rel_path),
                            "line": line_num,
                            "content": line.strip()[:200],
                        })

            if len(results) >= max_results:
                break

        if not results:
            return f"No matches found for pattern: {pattern} (searched {files_searched} files)"

        # Format output
        output_lines = [f"Found {len(results)} matches in {files_searched} files:\n"]
        for r in results:
            output_lines.append(f"{r['file']}:{r['line']}: {r['content']}")

        return "\n".join(output_lines)


def fnmatch(name: str, pattern: str) -> bool:
    """Simple fnmatch implementation."""
    from fnmatch import fnmatch as _fnmatch
    return _fnmatch(name, pattern)


register_tool(GrepTool())
