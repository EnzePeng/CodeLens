"""
Tool: run_command — Execute shell commands with whitelist security.
"""
from __future__ import annotations

import subprocess
from typing import Any

from core.tools.base import Tool
from config import DANGEROUS_PATTERNS
from exceptions import SecurityError

# Whitelist of allowed commands (basename check)
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
}

# Maximum output size
MAX_OUTPUT_BYTES = 50_000


class RunCommandTool(Tool):
    """Execute a shell command and return the output."""

    name = "run_command"
    description = "Execute a shell command in the workspace directory."
    parameters = {
        "command": {"type": "string", "description": "Shell command to execute"},
        "cwd": {"type": "string", "description": "Working directory (relative to repo root, optional)"},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)"},
    }

    def execute(self, command: str, cwd: str = "", timeout: int = 60, **kwargs) -> str:
        # Security check 1: dangerous patterns
        cmd_lower = command.lower()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                raise SecurityError(f"Command not allowed: contains dangerous pattern '{pattern}'")

        # Security check 2: whitelist
        cmd_basename = command.split()[0].lower().split("\\")[-1].split("/")[-1] if command.strip() else ""
        if ALLOWED_COMMANDS and cmd_basename not in ALLOWED_COMMANDS and not any(
            cmd_basename in a or a in cmd_basename for a in ALLOWED_COMMANDS
        ):
            raise SecurityError(f"Command '{cmd_basename}' not in allowed commands whitelist")

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
            output_parts = [
                f"Command: {command}",
                f"Working directory: {work_dir}",
                f"Exit code: {result.returncode}",
                "",
            ]
            if result.stdout:
                stdout = result.stdout[:MAX_OUTPUT_BYTES]
                output_parts.extend(["=== STDOUT ===", stdout])
            if result.stderr:
                stderr = result.stderr[:MAX_OUTPUT_BYTES]
                output_parts.extend(["=== STDERR ===", stderr])
            if not result.stdout and not result.stderr:
                output_parts.append("(no output)")
            return "\n".join(output_parts)
        except subprocess.TimeoutExpired:
            raise SecurityError(f"Command timed out after {timeout} seconds")
        except Exception as e:
            raise SecurityError(f"Command execution failed: {e}")


# Register tool
run_command_tool = RunCommandTool()
from core.tools.base import register_tool
register_tool(run_command_tool)
