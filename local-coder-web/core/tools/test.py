"""
Tool: test — run_tests, run_test_file, run_test_function.
"""
from __future__ import annotations

import subprocess
from typing import Any

from core.tools.base import Tool
from config import DANGEROUS_PATTERNS
from exceptions import SecurityError


class TestTool(Tool):
    """Run tests: pytest, unittest, etc."""

    name = "test"
    description = "Run tests: pytest, or run a specific test file/function."
    parameters = {
        "operation": {
            "type": "string",
            "description": "Operation: run_tests, run_test_file, run_test_function",
        },
        "pattern": {
            "type": "string",
            "description": "Test pattern (e.g. '-k pattern' for pytest)",
        },
        "test_file": {
            "type": "string",
            "description": "Test file path (relative to repo root)",
        },
        "test_function": {
            "type": "string",
            "description": "Specific test function to run",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 120)",
        },
    }

    def execute(
        self,
        operation: str = "run_tests",
        pattern: str = "",
        test_file: str = "",
        test_function: str = "",
        timeout: int = 120,
        **kwargs,
    ) -> str:
        from models import state

        if state.root is None:
            raise SecurityError("No repository folder set")

        if operation == "run_tests":
            cmd = f"python -m pytest {pattern}"
        elif operation == "run_test_file":
            if not test_file:
                return "Error: test_file required for run_test_file"
            cmd = f"python -m pytest {test_file}"
        elif operation == "run_test_function":
            if not test_function:
                return "Error: test_function required for run_test_function"
            cmd = f"python -m pytest {test_file or '.'} -k {test_function}"
        else:
            return f"Unknown operation: {operation}"

        # Security check
        cmd_lower = cmd.lower()
        for dangerous_pattern in DANGEROUS_PATTERNS:
            if dangerous_pattern in cmd_lower:
                raise SecurityError(f"Command not allowed: {dangerous_pattern}")

        work_dir = str(state.root)
        try:
            result = subprocess.run(
                cmd, shell=True, cwd=work_dir,
                capture_output=True, text=True, timeout=timeout,
            )
            output = [f"Command: {cmd}", f"Working directory: {work_dir}", f"Exit code: {result.returncode}", ""]
            if result.stdout:
                output.extend(["=== STDOUT ===", result.stdout[:20000]])
            if result.stderr:
                output.extend(["=== STDERR ===", result.stderr[:20000]])
            if not result.stdout and not result.stderr:
                output.append("(no output)")
            return "\n".join(output)
        except subprocess.TimeoutExpired:
            return f"Tests timed out after {timeout} seconds"
        except Exception as e:
            return f"Test execution failed: {e}"


# Register tool
test_tool = TestTool()
from core.tools.base import register_tool
register_tool(test_tool)
