"""
LSPTool - Language Server Protocol integration for code intelligence
"""
from __future__ import annotations

import json
from pathlib import Path

from core.tools.base import Tool, register_tool
from models import state


class LSPTool(Tool):
    """Language Server Protocol operations for code intelligence."""
    name = "lsp"
    description = "Code intelligence: find definition, references, hover info (basic implementation)"
    parameters = {
        "operation": {"type": "string", "enum": ["definition", "references", "symbols"], "description": "Operation type"},
        "file": {"type": "string", "description": "File path"},
        "symbol": {"type": "string", "description": "Symbol name to search for"},
    }

    def execute(self, operation: str = "symbols", file: str = "", symbol: str = "", **kwargs) -> str:
        root = state.root
        if not root:
            return "Error: No repository folder set"

        if operation == "symbols":
            return self._list_symbols(root, file)
        elif operation == "definition":
            return self._find_definition(root, symbol)
        elif operation == "references":
            return self._find_references(root, symbol)
        else:
            return f"Error: Unknown operation: {operation}"

    def _list_symbols(self, root: Path, file: str) -> str:
        """List symbols in a file or all indexed files."""
        if file:
            # List symbols in specific file
            file_path = root / file
            if not file_path.exists():
                return f"Error: File not found: {file}"

            symbols = self._extract_symbols_from_file(file_path)
            if not symbols:
                return f"No symbols found in {file}"

            lines = [f"Symbols in {file}:"]
            for sym in symbols:
                lines.append(f"  {sym['type']:10} {sym['name']:30} line {sym['line']}")
            return "\n".join(lines)
        else:
            # List symbols from indexed files
            from models import state
            all_symbols = []
            for code_file in state.files:
                for sym in code_file.symbols[:10]:
                    all_symbols.append({
                        "file": str(code_file.rel),
                        "name": sym,
                        "type": "symbol",
                    })

            if not all_symbols:
                return "No symbols indexed. Load a repository first."

            lines = [f"Found {len(all_symbols)} symbols:"]
            for s in all_symbols[:50]:
                lines.append(f"  {s['file']}: {s['name']}")
            return "\n".join(lines)

    def _find_definition(self, root: Path, symbol: str) -> str:
        """Find where a symbol is defined."""
        if not symbol:
            return "Error: symbol is required"

        results = []
        ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build'}

        import os
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith('.')]

            for filename in filenames:
                full_path = Path(dirpath) / filename
                try:
                    content = full_path.read_text(encoding='utf-8', errors='ignore')
                except (OSError, UnicodeDecodeError):
                    continue

                lines = content.split('\n')
                for line_num, line in enumerate(lines, 1):
                    # Check for function/class/variable definition
                    if self._is_definition(line, symbol):
                        rel_path = full_path.relative_to(root)
                        results.append({
                            "file": str(rel_path),
                            "line": line_num,
                            "content": line.strip()[:150],
                        })

        if not results:
            return f"No definition found for: {symbol}"

        lines = [f"Definitions for '{symbol}':"]
        for r in results:
            lines.append(f"  {r['file']}:{r['line']}: {r['content']}")
        return "\n".join(lines)

    def _find_references(self, root: Path, symbol: str) -> str:
        """Find all references to a symbol."""
        if not symbol:
            return "Error: symbol is required"

        results = []
        ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build'}

        import os
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith('.')]

            for filename in filenames:
                full_path = Path(dirpath) / filename
                try:
                    content = full_path.read_text(encoding='utf-8', errors='ignore')
                except (OSError, UnicodeDecodeError):
                    continue

                lines = content.split('\n')
                for line_num, line in enumerate(lines, 1):
                    if symbol in line and not self._is_comment(line):
                        rel_path = full_path.relative_to(root)
                        results.append({
                            "file": str(rel_path),
                            "line": line_num,
                            "content": line.strip()[:150],
                        })

        if not results:
            return f"No references found for: {symbol}"

        lines = [f"References to '{symbol}' ({len(results)} found):"]
        for r in results[:30]:
            lines.append(f"  {r['file']}:{r['line']}: {r['content']}")
        if len(results) > 30:
            lines.append(f"  ... and {len(results) - 30} more")
        return "\n".join(lines)

    def _is_definition(self, line: str, symbol: str) -> bool:
        """Check if a line defines the given symbol."""
        stripped = line.strip()
        patterns = [
            f"def {symbol}(",
            f"class {symbol}(",
            f"class {symbol}:",
            f"function {symbol}(",
            f"const {symbol} ",
            f"let {symbol} ",
            f"var {symbol} ",
            f"interface {symbol} ",
            f"type {symbol} ",
            f"enum {symbol} ",
            f"func {symbol}(",
            f"impl {symbol}",
            f"trait {symbol}",
        ]
        return any(p in stripped for p in patterns)

    def _is_comment(self, line: str) -> bool:
        """Check if line is a comment."""
        stripped = line.strip()
        return stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*')

    def _extract_symbols_from_file(self, file_path: Path) -> list[dict]:
        """Extract symbols from a file using regex."""
        import re

        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except (OSError, UnicodeDecodeError):
            return []

        symbols = []
        lines = content.split('\n')

        patterns = [
            (r'^\s*def\s+(\w+)', 'function'),
            (r'^\s*class\s+(\w+)', 'class'),
            (r'^\s*@(\w+)', 'decorator'),
            (r'\bfunction\s+(\w+)', 'function'),
            (r'\b(const|let|var)\s+(\w+)', 'variable'),
            (r'\b(interface|type|enum)\s+(\w+)', 'type'),
            (r'\bfunc\s+(\w+)', 'function'),
        ]

        for line_num, line in enumerate(lines, 1):
            for pattern, sym_type in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1) if match.lastindex == 1 else match.group(2)
                    symbols.append({
                        "name": name,
                        "type": sym_type,
                        "line": line_num,
                    })
                    break

        return symbols


register_tool(LSPTool())
