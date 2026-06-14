"""
Tool: code_analysis — count_lines, find_references.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from exceptions import FileAccessError, SecurityError
from models import state


class CodeAnalysisTool(Tool):
    """Code analysis: count lines, find references."""

    name = "code_analysis"
    description = "Analyze code: count lines of code, find references to a symbol."
    parameters = {
        "operation": {
            "type": "string",
            "description": "Operation: count_lines, find_references",
        },
        "path": {
            "type": "string",
            "description": "File path to analyze or search in (relative to repo root)",
        },
        "symbol": {
            "type": "string",
            "description": "Symbol name to search for (for find_references)",
        },
    }

    def execute(self, operation: str = "", path: str = "", symbol: str = "", **kwargs) -> str:
        if not operation:
            raise FileAccessError("Missing required argument: operation")
        if state.root is None:
            raise FileAccessError("No repository folder set")

        if operation == "count_lines":
            target = (state.root / path).resolve() if path else state.root
            try:
                target.relative_to(state.root.resolve())
            except ValueError:
                raise SecurityError("Path is outside the repository root")

            total_lines = 0
            code_lines = 0
            comment_lines = 0
            blank_lines = 0

            def count_file(fp: Path) -> tuple[int, int, int, int]:
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return 0, 0, 0, 0
                lines = text.splitlines()
                total = len(lines)
                comments = 0
                blanks = 0
                code = 0
                in_block_comment = False
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        blanks += 1
                        continue
                    if in_block_comment:
                        comments += 1
                        if "*/" in stripped:
                            in_block_comment = False
                        continue
                    if stripped.startswith(("#", "//", "--", "%")):
                        comments += 1
                        code += 1  # count comment lines as code for metrics
                        continue
                    if stripped.startswith(("/*", '"""', "'''")):
                        in_block_comment = True
                        comments += 1
                        code += 1
                        continue
                    code += 1
                return total, code, comments, blanks

            if target.is_file():
                t, c, cm, b = count_file(target)
                total_lines += t
                code_lines += c
                comment_lines += cm
                blank_lines += b
            else:
                for fp in target.rglob("*"):
                    if fp.is_file() and fp.suffix.lower() in {
                        ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
                        ".rb", ".php", ".swift", ".kt", ".cs", ".sql", ".sh",
                    }:
                        t, c, cm, b = count_file(fp)
                        total_lines += t
                        code_lines += c
                        comment_lines += cm
                        blank_lines += b

            return (
                f"Code analysis for {path or str(state.root)}:\n"
                f"  Total lines: {total_lines}\n"
                f"  Code lines:  {code_lines}\n"
                f"  Comments:    {comment_lines}\n"
                f"  Blank lines: {blank_lines}"
            )

        elif operation == "find_references":
            if not symbol:
                return "Error: symbol parameter required for find_references"

            results = []
            for f in state.files:
                if symbol in f.text:
                    # Find line numbers
                    for i, line in enumerate(f.text.splitlines(), 1):
                        if symbol in line:
                            results.append(f"{f.rel}:{i}: {line.strip()[:120]}")
                            if len(results) >= 50:
                                break
                    if len(results) >= 50:
                        break

            if not results:
                return f"No references to '{symbol}' found"
            return f"Found {len(results)} references to '{symbol}':\n" + "\n".join(results)

        raise ValueError(f"Unknown operation: {operation}")


# Register tool
code_analysis_tool = CodeAnalysisTool()
from core.tools.base import register_tool
register_tool(code_analysis_tool)
