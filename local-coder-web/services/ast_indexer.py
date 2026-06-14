"""
AST Indexer - Code structure understanding via AST parsing

Features:
- Multi-language support (Python, JS/TS, Go, etc.)
- Symbol extraction with type information
- Import/require relationship extraction
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class SymbolInfo:
    """Information about a code symbol."""
    name: str
    type: str  # function, class, variable, type, etc.
    file: str
    line: int
    end_line: int = 0
    args: list[str] = field(default_factory=list)
    docstring: str = ""
    parent: str = ""


@dataclass
class ImportInfo:
    """Import statement information."""
    source_file: str
    module: str
    names: list[str] = field(default_factory=list)
    alias: str = ""
    is_relative: bool = False


class ASTIndexer:
    """
    Multi-language code indexer using regex-based parsing.
    Supports Python, JavaScript/TypeScript, Go, Rust, Java.
    """

    def __init__(self):
        self.symbols: dict[str, list[SymbolInfo]] = {}
        self.imports: dict[str, list[ImportInfo]] = {}
        self.call_graph: dict[str, set[str]] = {}

    def index_file(self, file_path: str, content: str) -> None:
        """Index a single file."""
        path = Path(file_path)
        ext = path.suffix.lower()

        symbols = []
        imports = []

        if ext == ".py":
            symbols = self._parse_python(content, file_path)
            imports = self._parse_python_imports(content, file_path)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            symbols = self._parse_javascript(content, file_path)
            imports = self._parse_js_imports(content, file_path)
        elif ext == ".go":
            symbols = self._parse_go(content, file_path)
            imports = self._parse_go_imports(content, file_path)
        elif ext == ".rs":
            symbols = self._parse_rust(content, file_path)
        elif ext in (".java", ".kt"):
            symbols = self._parse_java(content, file_path)

        self.symbols[file_path] = symbols
        self.imports[file_path] = imports

    def _parse_python(self, content: str, file_path: str) -> list[SymbolInfo]:
        """Parse Python file for symbols."""
        symbols = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Function definition
            match = re.match(r"def\s+(\w+)\s*\((.*?)\)", stripped)
            if match:
                name = match.group(1)
                args = [a.strip().split(":")[0].strip() for a in match.group(2).split(",") if a.strip()]
                symbols.append(SymbolInfo(
                    name=name, type="function", file=file_path,
                    line=i, args=args,
                ))

            # Class definition
            match = re.match(r"class\s+(\w+)(?:\((.*?)\))?:", stripped)
            if match:
                name = match.group(1)
                symbols.append(SymbolInfo(
                    name=name, type="class", file=file_path, line=i,
                ))

            # Variable assignments (module level)
            if i <= 50:  # Only top-level
                match = re.match(r"(\w+)\s*=\s*", stripped)
                if match and not stripped.startswith("_"):
                    symbols.append(SymbolInfo(
                        name=match.group(1), type="variable", file=file_path, line=i,
                    ))

        return symbols

    def _parse_python_imports(self, content: str, file_path: str) -> list[ImportInfo]:
        """Parse Python imports."""
        imports = []
        for match in re.finditer(r"from\s+([\w.]+)\s+import\s+(.+)", content):
            module = match.group(1)
            names = [n.strip().split(" as ")[0] for n in match.group(2).split(",")]
            imports.append(ImportInfo(
                source_file=file_path, module=module, names=names,
                is_relative=module.startswith("."),
            ))

        for match in re.finditer(r"import\s+([\w.]+)", content):
            module = match.group(1)
            if "from" not in content[match.start() - 5:match.start()]:
                imports.append(ImportInfo(
                    source_file=file_path, module=module,
                ))

        return imports

    def _parse_javascript(self, content: str, file_path: str) -> list[SymbolInfo]:
        """Parse JavaScript/TypeScript file."""
        symbols = []

        for match in re.finditer(
            r"(?:function|const|let|var|async\s+function)\s+(\w+)", content
        ):
            symbols.append(SymbolInfo(
                name=match.group(1), type="function", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        for match in re.finditer(r"(?:class)\s+(\w+)", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="class", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        for match in re.finditer(r"(?:interface|type)\s+(\w+)", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="type", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        return symbols

    def _parse_js_imports(self, content: str, file_path: str) -> list[ImportInfo]:
        """Parse JavaScript/TypeScript imports."""
        imports = []

        for match in re.finditer(r'import\s+.*?from\s+["\'](.+?)["\']', content):
            imports.append(ImportInfo(source_file=file_path, module=match.group(1)))

        for match in re.finditer(r'require\s*\(\s*["\'](.+?)["\']\s*\)', content):
            imports.append(ImportInfo(source_file=file_path, module=match.group(1)))

        return imports

    def _parse_go(self, content: str, file_path: str) -> list[SymbolInfo]:
        """Parse Go file."""
        symbols = []

        for match in re.finditer(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="function", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        for match in re.finditer(r"type\s+(\w+)\s+struct", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="struct", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        return symbols

    def _parse_go_imports(self, content: str, file_path: str) -> list[ImportInfo]:
        """Parse Go imports."""
        imports = []
        for match in re.finditer(r'"([^"]+)"', content[content.find("import"):content.find(")") + 1] if "import" in content else ""):
            imports.append(ImportInfo(source_file=file_path, module=match.group(1)))
        return imports

    def _parse_rust(self, content: str, file_path: str) -> list[SymbolInfo]:
        """Parse Rust file."""
        symbols = []

        for match in re.finditer(r"fn\s+(\w+)", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="function", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        for match in re.finditer(r"(?:struct|enum|trait)\s+(\w+)", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="type", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        return symbols

    def _parse_java(self, content: str, file_path: str) -> list[SymbolInfo]:
        """Parse Java/Kotlin file."""
        symbols = []

        for match in re.finditer(r"(?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)+(\w+)\s*\(", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="function", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        for match in re.finditer(r"(?:class|interface|enum)\s+(\w+)", content):
            symbols.append(SymbolInfo(
                name=match.group(1), type="type", file=file_path, line=content[:match.start()].count("\n") + 1,
            ))

        return symbols

    def get_symbol(self, name: str) -> Optional[SymbolInfo]:
        """Find a symbol by name across all indexed files."""
        for file_path, symbols in self.symbols.items():
            for sym in symbols:
                if sym.name == name:
                    return sym
        return None

    def get_references(self, name: str) -> list[SymbolInfo]:
        """Find all references to a symbol."""
        refs = []
        for file_path, symbols in self.symbols.items():
            for sym in symbols:
                if sym.name == name:
                    refs.append(sym)
        return refs

    def get_file_symbols(self, file_path: str) -> list[SymbolInfo]:
        """Get all symbols in a file."""
        return self.symbols.get(file_path, [])

    def clear(self) -> None:
        self.symbols.clear()
        self.imports.clear()
        self.call_graph.clear()


# Global instance
ast_indexer = ASTIndexer()
