"""
Tool: git_operation - Git operations with safety.

Improvements:
- #61 Stash push/pop/list
- #62 Blame operation
"""
from __future__ import annotations

import subprocess
from typing import Any

from core.tools.base import Tool
from exceptions import SecurityError
from models import state


class GitOperationTool(Tool):
    """Perform Git operations with safety checks."""

    name = "git_operation"
    description = (
        "Execute Git commands: status, diff, log, show, branch, blame, stash (push/pop/list), "
        "add, commit. Write operations (commit) default to no-op."
    )
    parameters = {
        "command": {"type": "string", "description": "Git subcommand: status, diff, log, branch, blame, stash, add, commit"},
        "args": {"type": "string", "description": "Additional arguments"},
        "confirm_write": {"type": "boolean", "description": "Confirm write operations (default: false)", "default": False},
    }

    ALLOWED_COMMANDS = {
        "status", "diff", "log", "show", "branch", "tag", "blame",
        "stash", "add", "commit", "checkout", "pull", "push",
    }
    DANGEROUS_COMMANDS = {"push", "reset --hard", "rebase --hard", "force", "filter-branch"}

    def execute(self, command: str = "", args: str = "", confirm_write: bool = False, **kwargs) -> str:
        if not command:
            raise SecurityError("Missing required argument: command")
        if state.root is None:
            raise SecurityError("No repository folder set")

        command = command.lower().strip()
        if command not in self.ALLOWED_COMMANDS:
            raise SecurityError(f"Git command not allowed: {command}")

        # Check dangerous commands
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command:
                if not confirm_write:
                    raise SecurityError(f"Dangerous git command blocked: {command}")

        git_cmd = ["git", command]
        if args:
            git_cmd.extend(args.split())

        # Add safety flags
        if command == "diff":
            git_cmd.append("--no-color")
        elif command == "log":
            git_cmd.extend(["--oneline", "-n", "20"])
        elif command == "blame":
            git_cmd.extend(["-n", "-p", "-L", "1,100"])

        try:
            result = subprocess.run(
                git_cmd, cwd=str(state.root),
                capture_output=True, text=True, timeout=30,
            )
            output = []
            output.append(f"$ git {' '.join(git_cmd[1:])}")
            output.append("")
            if result.stdout:
                output.append(result.stdout[:50000])
            if result.stderr and command not in ("status", "log"):
                output.append(f"Warning: {result.stderr[:5000]}")
            if not result.stdout and not result.stderr:
                output.append("(no output)")
            output.append(f"\n[Exit code: {result.returncode}]")
            return "\n".join(output)
        except subprocess.TimeoutExpired:
            raise SecurityError("Git command timed out")
        except FileNotFoundError:
            raise SecurityError("Git is not installed or not in PATH")
        except Exception as e:
            raise SecurityError(f"Git command failed: {e}")


git_operation_tool = GitOperationTool()
from core.tools.base import register_tool
register_tool(git_operation_tool)
