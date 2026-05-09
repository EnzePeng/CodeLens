"""
Tool: diff_preview — Generate diff preview for code changes.
"""
from __future__ import annotations

from typing import Any

from core.tools.base import Tool
from core.tools.diff_utils import generate_unified_diff, get_diff_stats


class DiffPreviewTool(Tool):
    """Generate a unified diff preview between old and new content."""

    name = "diff_preview"
    description = "Generate a unified diff preview between old and new content."
    parameters = {
        "old_content": {
            "type": "string",
            "description": "Original file content",
        },
        "new_content": {
            "type": "string",
            "description": "New file content",
        },
        "file_path": {
            "type": "string",
            "description": "File path (for context in the diff)",
        },
    }

    def execute(self, old_content: str = "", new_content: str = "", file_path: str = "", **kwargs) -> str:
        diff = generate_unified_diff(old_content, new_content,
                                     old_path=f"a/{file_path}" if file_path else "a",
                                     new_path=f"b/{file_path}" if file_path else "b")
        stats = get_diff_stats(old_content, new_content)
        summary = f"Diff for {file_path}:\n{diff}"
        if stats["total_old"] > 0 or stats["total_new"] > 0:
            summary += f"\n\nStats: +{stats['added']} -{stats['removed']} ~{stats['unchanged']} (similarity: {stats['similarity']})"
        return summary


# Register tool
diff_preview_tool = DiffPreviewTool()
from core.tools.base import register_tool
register_tool(diff_preview_tool)
