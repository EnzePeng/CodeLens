"""
Tool: edit_file - Edit specific sections of a file.

Improvements:
- #65 Multi-location replacement support
"""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from config import MAX_FILE_BYTES
from exceptions import FileAccessError, SecurityError
from models import state


class EditFileTool(Tool):
    """Edit a file with exact matching + fuzzy fallback + multi-location."""

    name = "edit_file"
    description = (
        "Edit a file by replacing text. Supports exact matching with fuzzy fallback. "
        "For multiple replacements, call multiple times."
    )
    parameters = {
        "path": {"type": "string", "description": "Relative path to the file"},
        "old_str": {"type": "string", "description": "Text to replace (must match including whitespace)"},
        "new_str": {"type": "string", "description": "Replacement text"},
        "all_occurrences": {"type": "boolean", "description": "Replace all occurrences (default: false)"},
    }

    def execute(self, path: str, old_str: str, new_str: str, all_occurrences: bool = False, **kwargs) -> str:
        if state.root is None:
            raise FileAccessError("No repository folder set")

        target = (state.root / path).resolve()
        try:
            target.relative_to(state.root.resolve())
        except ValueError:
            raise SecurityError("Path is outside the repository root")

        if not target.exists() or not target.is_file():
            raise FileAccessError(f"File not found: {path}")

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise FileAccessError(f"Read failed: {e}")

        if old_str in content:
            count = 0 if all_occurrences else 1
            new_content = content.replace(old_str, new_str, count)
            if not all_occurrences and new_content == content:
                new_content = self._fuzzy_edit(content, old_str, new_str)
        else:
            new_content = self._fuzzy_edit(content, old_str, new_str)

        if new_content == content:
            # Provide diff hint (#65)
            similarity = self._similarity(content, old_str)
            raise FileAccessError(
                f"old_str not found in '{path}' (similarity: {similarity:.0%}). "
                f"Ensure exact match including whitespace. Searched for:\n{old_str[:500]}"
            )

        try:
            target.write_text(new_content, encoding="utf-8")
        except OSError as e:
            raise FileAccessError(f"Write failed: {e}")

        old_lines = len(old_str.splitlines())
        new_lines = len(new_str.splitlines())
        return f"Successfully edited {path} ({old_lines} lines -> {new_lines} lines, {new_lines - old_lines:+d})"

    def _fuzzy_edit(self, content: str, old_str: str, new_str: str) -> str:
        content_lines = content.splitlines(keepends=True)
        old_lines_list = old_str.splitlines(keepends=True)
        if not old_lines_list:
            return content

        best_match = None
        best_ratio = 0.0

        for i in range(len(content_lines) - len(old_lines_list) + 1):
            chunk = content_lines[i:i + len(old_lines_list)]
            if chunk == old_lines_list:
                return content.replace(old_str, new_str, 1)
            match_ratio = sum(
                1.0 for a, b in zip(chunk, old_lines_list) if a.strip() == b.strip()
            ) / len(old_lines_list)
            if match_ratio > best_ratio:
                best_ratio = match_ratio
                best_match = i
                if match_ratio == 1.0:
                    break

        if best_match is not None and best_ratio >= 0.8:
            new_lines_list = new_str.splitlines(keepends=True)
            content_lines[best_match:best_match + len(old_lines_list)] = new_lines_list
            return "".join(content_lines)

        return content

    def _similarity(self, a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a[:2000], b[:2000]).ratio()


edit_file_tool = EditFileTool()
from core.tools.base import register_tool
register_tool(edit_file_tool)
