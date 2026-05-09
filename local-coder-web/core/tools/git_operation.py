"""
Tool: git_operation - Git operations.
"""
from __future__ import annotations

import subprocess
from typing import Any, Optional

from core.tools.base import Tool
from exceptions import SecurityError
from models import state


class GitOperationTool(Tool):
    """Perform Git operations on the repository."""
    
    name = "git_operation"
    description = "Execute Git commands: status, diff, log, add, commit."
    parameters = {
        "command": {
            "type": "string",
            "description": "Git command: status, diff, log, add, commit, branch, checkout",
        },
        "args": {
            "type": "string",
            "description": "Additional arguments for the git command",
        },
    }
    
    # Allowed git commands (safe subset)
    ALLOWED_COMMANDS = {"status", "diff", "log", "add", "commit", "branch", "checkout", "pull", "push"}
    # Dangerous commands that require explicit user confirmation
    DANGEROUS_COMMANDS = {"push", "commit"}
    
    def execute(self, command: str, args: str = "", **kwargs) -> str:
        """Execute Git operation."""
        if state.root is None:
            raise SecurityError("No repository folder set")
        
        # Validate command
        command = command.lower().strip()
        if command not in self.ALLOWED_COMMANDS:
            raise SecurityError(f"Git command not allowed: {command}")
        
        # Build git command
        git_cmd = ["git", command]
        if args:
            git_cmd.extend(args.split())
        
        # Add safety flags
        if command == "diff":
            git_cmd.append("--no-color")
        elif command == "log":
            git_cmd.extend(["--oneline", "-n", "20"])
        
        try:
            result = subprocess.run(
                git_cmd,
                cwd=str(state.root),
                capture_output=True,
                text=True,
                timeout=30,
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


# Register tool
git_operation_tool = GitOperationTool()
from core.tools.base import register_tool
register_tool(git_operation_tool)