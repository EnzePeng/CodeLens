"""
Tool: run_command - Execute shell commands safely.

Improvements:
- #73 Whitelist-based command execution
- #16 Per-command timeout
"""
from __future__ import annotations

import re
import subprocess
from typing import Any

from core.tools.base import Tool
from config import DANGEROUS_PATTERNS
from exceptions import SecurityError

ALLOWED_COMMANDS: set[str] = {
    "python", "python3", "pip", "pip3",
    "node", "npm", "npx",
    "git",
    "dir", "type", "echo", "copy", "xcopy",
    "ls", "cat", "touch", "mkdir", "cp", "mv", "rm",
    "pytest", "nosetests", "go", "go build", "go test",
    "rustc", "cargo",
    "swift", "swift build",
    "dotnet", "dotnet build", "dotnet test",
    "powershell", "pwsh", "where", "get-content", "cls",
}

# Regex for safe commands (allow more characters for flexibility)
_SAFE_CMD_RE = re.compile(r'^[\w./\\ -]+$')

MAX_OUTPUT_BYTES = 50_000


class RunCommandTool(Tool):
    """Execute a shell command with whitelist and safety checks."""

    name = "run_command"
    description = "Execute a shell command in the workspace directory."
    parameters = {
        "command": {"type": "string", "description": "Shell command to execute"},
        "cwd": {"type": "string", "description": "Working directory (relative to repo root)"},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)"},
    }

    def execute(self, command: str = "", cwd: str = "", timeout: int = 60, **kwargs) -> str:
        if not command:
            raise ToolExecutionError("Missing required argument: command")
        cmd_lower = command.lower()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                raise SecurityError(f"Command not allowed: contains dangerous pattern")

        # Exact match against whitelist (split by space to get first token)
        cmd_basename = command.split()[0].lower().split("\\")[-1].split("/")[-1] if command.strip() else ""
        if cmd_basename and cmd_basename not in ALLOWED_COMMANDS and not any(
            cmd_basename == a or cmd_basename.startswith(a + " ") or a.startswith(cmd_basename + " ")
            for a in ALLOWED_COMMANDS
        ):
            raise SecurityError(f"Command '{cmd_basename}' not in allowed commands whitelist")

        # Reject commands with shell metacharacters that could enable injection
        if not _SAFE_CMD_RE.match(command.strip()):
            raise SecurityError("Command contains disallowed characters")

        from models import state
        if state.root:
            work_dir = str(state.root / cwd) if cwd else str(state.root)
        else:
            work_dir = cwd or "."

        try:
            result = subprocess.run(
                command, shell=True, cwd=work_dir,
                capture_output=True, text=True, timeout=timeout,
            )
            parts = [f"Command: {command}", f"Exit code: {result.returncode}", ""]
            if result.stdout:
                parts.append(f"=== STDOUT ===\n{result.stdout[:MAX_OUTPUT_BYTES]}")
            if result.stderr:
                parts.append(f"=== STDERR ===\n{result.stderr[:MAX_OUTPUT_BYTES]}")
            if not result.stdout and not result.stderr:
                parts.append("(no output)")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            raise SecurityError(f"Command timed out after {timeout} seconds")
        except Exception as e:
            raise SecurityError(f"Command execution failed: {e}")


run_command_tool = RunCommandTool()
from core.tools.base import register_tool
register_tool(run_command_tool)
