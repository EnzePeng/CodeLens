"""
Tool: edit_file - Edit specific sections of a file.
Supports exact replacement with fuzzy fallback.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from core.tools.base import Tool
from config import MAX_FILE_BYTES
from exceptions import FileAccessError, SecurityError
from models import state


class EditFileTool(Tool):
    """Edit a file by replacing text with exact matching + fuzzy fallback."""

    name = "edit_file"
    description = (
        "Edit a file by replacing exact text. Uses exact string matching with "
        "fuzzy fallback (matching stripped lines). If old_str not found, "
        "provides error message with expected text."
    )
    parameters = {
        "path": {"type": "string", "description": "Relative path to the file from repository root"},
        "old_str": {"type": "string", "description": "Exact text to replace (must match including whitespace)"},
        "new_str": {"type": "string", "description": "New text to replace old_str with"},
        "all_occurrences": {"type": "boolean", "description": "Replace all occurrences (default: false)", "default": False},
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

        # Exact match
        if old_str in content:
            count = 0 if all_occurrences else 1
            new_content = content.replace(old_str, new_str, count)
            if not all_occurrences and new_content == content:
                new_content = self._fuzzy_edit(content, old_str, new_str)
        else:
            new_content = self._fuzzy_edit(content, old_str, new_str)

        if new_content == content:
            raise FileAccessError(
                f"old_str not found in file '{path}'. "
                f"Make sure to include exact whitespace and newlines.\n"
                f"Searched for:\n{old_str[:300]}..."
            )

        new_bytes = len(new_content.encode("utf-8"))
        if new_bytes > MAX_FILE_BYTES:
            raise FileAccessError(f"Result too large: {new_bytes} bytes (max: {MAX_FILE_BYTES})")

        try:
            target.write_text(new_content, encoding="utf-8")
        except OSError as e:
            raise FileAccessError(f"Write failed: {e}")

        old_lines = len(old_str.splitlines())
        new_lines = len(new_str.splitlines())
        diff_lines = new_lines - old_lines

        return f"Successfully edited {path} ({old_lines} lines -> {new_lines} lines, {diff_lines:+d})"

    def _fuzzy_edit(self, content: str, old_str: str, new_str: str) -> str:
        """Try fuzzy matching when exact match fails (matching stripped lines)."""
        content_lines = content.splitlines(keepends=True)
        old_lines = old_str.splitlines(keepends=True)

        if not old_lines:
            return content

        best_match = None
        best_ratio = 0.0

        for i in range(len(content_lines) - len(old_lines) + 1):
            chunk = content_lines[i:i + len(old_lines)]
            if chunk == old_lines:
                return content.replace(old_str, new_str, 1)
            match_ratio = sum(
                1.0 for a, b in zip(chunk, old_lines) if a.strip() == b.strip()
            ) / len(old_lines)
            if match_ratio > best_ratio:
                best_ratio = match_ratio
                best_match = i
                if match_ratio == 1.0:
                    break

        if best_match is not None and best_ratio >= 0.8:
            new_lines = new_str.splitlines(keepends=True)
            content_lines[best_match:best_match + len(old_lines)] = new_lines
            return "".join(content_lines)

        return content


edit_file_tool = EditFileTool()
from core.tools.base import register_tool
register_tool(edit_file_tool)
