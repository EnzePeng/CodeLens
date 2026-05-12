"""
Tool: undo_edit — Undo/redo recent edits with JSON persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from exceptions import FileAccessError, SecurityError
from models import state


_BACKUP_FILE = Path.home() / ".local-coder-web" / "edit_history.json"


class UndoManager:
    """Manage edit history with JSON persistence."""

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._history: list[dict] = []
        self._redo_stack: list[dict] = []
        self._load_history()

    def _load_history(self) -> None:
        if _BACKUP_FILE.exists():
            try:
                data = json.loads(_BACKUP_FILE.read_text(encoding="utf-8"))
                self._history = data.get("history", [])
                self._redo_stack = data.get("redo_stack", [])
            except Exception:
                self._history = []
                self._redo_stack = []

    def _save_history(self) -> None:
        _BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BACKUP_FILE.write_text(
            json.dumps({"history": self._history, "redo_stack": self._redo_stack}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_edit(self, path: str, old_content: str, new_content: str, tool: str) -> None:
        record = {
            "path": path,
            "timestamp": __import__("time").time(),
            "old_content": old_content,
            "new_content": new_content,
            "tool": tool,
        }
        self._history.append(record)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
        self._save_history()

    def undo(self, count: int = 1) -> list[dict]:
        results = []
        for _ in range(min(count, len(self._history))):
            if not self._history:
                break
            record = self._history.pop()
            self._redo_stack.append(record)
            if state.root is None:
                results.append({"success": False, "error": "No repository set", "path": record["path"]})
                continue
            target = (state.root / record["path"]).resolve()
            try:
                target.relative_to(state.root.resolve())
            except ValueError:
                results.append({"success": False, "error": "Path outside repo", "path": record["path"]})
                self._redo_stack.pop()  # remove the one we just added
                continue
            if not target.exists():
                results.append({"success": False, "error": "File not found", "path": record["path"]})
                self._redo_stack.pop()  # remove the one we just added
                continue
            try:
                current = target.read_text(encoding="utf-8", errors="replace")
                # Store current content so redo can restore it
                record_with_current = {**record, "_current_content": current}
                backup_path = Path.home() / ".local-coder-web" / "backups" / f"{record['path'].replace('/', '_')}_{int(record['timestamp'])}.bak"
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_text(current, encoding="utf-8")
                target.write_text(record["old_content"], encoding="utf-8")
                results.append({"success": True, "path": record["path"], "action": "undo"})
            except Exception as e:
                results.append({"success": False, "error": str(e), "path": record["path"]})
                self._redo_stack.pop()  # remove the one we just added
        self._save_history()
        return results

    def redo(self, count: int = 1) -> list[dict]:
        """Redo the last N undone edits (restore to new_content after undo)."""
        results = []
        for _ in range(min(count, len(self._redo_stack))):
            if not self._redo_stack:
                break
            record = self._redo_stack.pop(0)
            if state.root is None:
                results.append({"success": False, "error": "No repository set", "path": record["path"]})
                continue
            target = (state.root / record["path"]).resolve()
            try:
                target.relative_to(state.root.resolve())
            except ValueError:
                results.append({"success": False, "error": "Path outside repo", "path": record["path"]})
                continue
            try:
                # Restore the new_content from the original edit
                target.write_text(record["new_content"], encoding="utf-8")
                results.append({"success": True, "path": record["path"], "action": "redo"})
            except Exception as e:
                results.append({"success": False, "error": str(e), "path": record["path"]})
        self._save_history()
        return results

    def get_history(self, limit: int = 10) -> list[dict]:
        return [
            {
                "path": r["path"],
                "timestamp": r["timestamp"],
                "tool": r["tool"],
                "preview": r["new_content"][:100] + ("..." if len(r["new_content"]) > 100 else ""),
            }
            for r in self._history[-limit:][::-1]
        ]


# Global undo manager
undo_manager = UndoManager()


def get_undo_manager() -> UndoManager:
    return undo_manager


class UndoEditTool(Tool):
    """Undo/redo recent file edits."""

    name = "undo_edit"
    description = "Undo the last N file edits, or redo with action='redo'."
    parameters = {
        "count": {"type": "integer", "description": "Number of edits to undo/redo (default: 1)"},
        "action": {"type": "string", "description": "'undo' or 'redo' (default: 'undo')"},
    }

    def execute(self, count: int = 1, action: str = "undo", **kwargs) -> str:
        if action == "redo":
            results = undo_manager.redo(count)
        else:
            results = undo_manager.undo(count)
        if not results:
            return "No edits to undo/redo"
        success = sum(1 for r in results if r.get("success"))
        failed = len(results) - success
        msg = f"{action.capitalize()}d {success} edits"
        if failed:
            msg += f", {failed} failed"
        return msg


# Register tool
undo_edit_tool = UndoEditTool()
from core.tools.base import register_tool
register_tool(undo_edit_tool)
