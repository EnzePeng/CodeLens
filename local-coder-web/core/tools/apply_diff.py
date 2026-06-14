"""
Tool: apply_diff - Apply unified diff to file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from core.tools.diff_utils import apply_unified_diff, parse_unified_diff
from config import MAX_FILE_BYTES
from exceptions import FileAccessError, SecurityError
from models import state


class ApplyDiffTool(Tool):
    """Apply a unified diff to a file."""
    
    name = "apply_diff"
    description = "Apply a unified diff patch to a file."
    parameters = {
        "path": {
            "type": "string",
            "description": "Relative path to the file to patch",
        },
        "diff": {
            "type": "string",
            "description": "Unified diff content (---/+++ lines + hunks)",
        },
    }
    
    def execute(self, path: str = "", diff: str = "", **kwargs) -> str:
        """Apply diff to file."""
        if not path or not diff:
            raise FileAccessError(f"Missing required arguments: {'path' if not path else 'diff'}")
        if state.root is None:
            raise FileAccessError("No repository folder set")
        
        # Security check
        target = (state.root / path).resolve()
        try:
            target.relative_to(state.root.resolve())
        except ValueError:
            raise SecurityError("Path is outside the repository root")
        
        if not target.exists():
            raise FileAccessError(f"File not found: {path}")
        
        # Read original content
        try:
            original = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise FileAccessError(f"Read failed: {e}")
        
        # Apply diff
        try:
            new_content = apply_unified_diff(original, diff)
        except Exception as e:
            raise FileAccessError(f"Failed to apply diff: {e}")
        
        # Check size
        new_bytes = len(new_content.encode("utf-8"))
        if new_bytes > MAX_FILE_BYTES:
            raise FileAccessError(f"Result too large: {new_bytes} bytes (max: {MAX_FILE_BYTES})")
        
        # Write back with atomic write
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to temp file then rename
            temp_path = target.with_suffix(target.suffix + ".tmp")
            temp_path.write_text(new_content, encoding="utf-8")
            os.replace(str(temp_path), str(target))
        except OSError as e:
            # Clean up temp file on failure
            try:
                target.with_suffix(target.suffix + ".tmp").unlink(missing_ok=True)
            except OSError:
                pass
            raise FileAccessError(f"Write failed: {e}")

        # Record edit for undo
        from core.tools.undo_edit import get_undo_manager
        undo_mgr = get_undo_manager()
        undo_mgr.record_edit(path, original, new_content, "apply_diff")
        
        # Parse diff for stats
        patches = parse_unified_diff(diff)
        hunk_count = sum(len(p.get("hunks", [])) for p in patches)
        
        return f"Successfully applied diff to {path}\nPatches: {len(patches)}, Hunks: {hunk_count}"


# Register tool
apply_diff_tool = ApplyDiffTool()
from core.tools.base import register_tool
register_tool(apply_diff_tool)