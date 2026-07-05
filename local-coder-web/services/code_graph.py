"""Lightweight code graph for project understanding.

The v1 graph is deliberately local and deterministic: Python uses ``ast`` for
symbols/imports/calls, while other languages use conservative regex fallbacks.
It returns plain dictionaries so routes can serialize results directly.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models import CodeFile


_CONFIG_NAMES = {
    "pyproject.toml", "package.json", "tsconfig.json", "vite.config.ts",
    "vite.config.js", "requirements.txt", "uv.lock", "Cargo.toml",
    "go.mod", "docker-compose.yml", "Dockerfile",
}


@dataclass
class CodeGraph:
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    symbol_index: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def get_file(self, rel: str) -> dict[str, Any]:
        return self.files.get(rel, _empty_file(rel))

    def imported_by(self, rel: str) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for source, info in self.files.items():
            for imp in info.get("imports", []):
                if imp.get("target") == rel:
                    refs.append({
                        "path": source,
                        "symbol": imp.get("name", ""),
                        "line": imp.get("line", 1),
                        "reason": "imports this file",
                    })
        return refs

    def callees_for_file(self, rel: str) -> list[dict[str, Any]]:
        info = self.get_file(rel)
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for call in info.get("calls", []):
            for target in self.symbol_index.get(call.get("name", ""), []):
                if target.get("path") == rel:
                    continue
                key = (target.get("path", ""), target.get("name", ""))
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "path": target.get("path", ""),
                    "symbol": target.get("name", ""),
                    "line": target.get("start_line", 1),
                    "reason": f"called as {call.get('name')}",
                })
        return out

    def callers_for_file(self, rel: str) -> list[dict[str, Any]]:
        names = {sym.get("name") for sym in self.get_file(rel).get("symbols", [])}
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for source, info in self.files.items():
            if source == rel:
                continue
            for call in info.get("calls", []):
                if call.get("name") in names:
                    key = (source, call.get("name", ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "path": source,
                        "symbol": call.get("name", ""),
                        "line": call.get("line", 1),
                        "reason": "calls a symbol from this file",
                    })
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"files": self.files, "symbol_index": self.symbol_index}


def build_code_graph(files: list[CodeFile]) -> CodeGraph:
    rels = {f.rel for f in files}
    graph = CodeGraph()
    for file in files:
        info = _analyze_file(file, rels)
        graph.files[file.rel] = info
        for symbol in info["symbols"]:
            graph.symbol_index.setdefault(symbol["name"], []).append(symbol)
    return graph


def is_config_file(rel: str) -> bool:
    name = Path(rel).name
    return name in _CONFIG_NAMES or name.endswith((".ini", ".env", ".yaml", ".yml"))


def _empty_file(rel: str) -> dict[str, Any]:
    return {"path": rel, "symbols": [], "imports": [], "calls": []}


def _analyze_file(file: CodeFile, rels: set[str]) -> dict[str, Any]:
    suffix = Path(file.rel).suffix.lower()
    if suffix == ".py":
        return _analyze_python(file, rels)
    return _analyze_text_code(file, rels)


def _analyze_python(file: CodeFile, rels: set[str]) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    try:
        tree = ast.parse(file.text)
    except SyntaxError:
        return _analyze_text_code(file, rels)

    parent_stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            symbols.append(_symbol(file.rel, node.name, "class", node))
            parent_stack.append(node.name)
            self.generic_visit(node)
            parent_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            kind = "method" if parent_stack else "function"
            item = _symbol(file.rel, node.name, kind, node)
            item["parent"] = parent_stack[-1] if parent_stack else ""
            symbols.append(item)
            parent_stack.append(node.name)
            self.generic_visit(node)
            parent_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_Import(self, node: ast.Import) -> Any:
            for alias in node.names:
                target = _resolve_python_import(alias.name, rels)
                imports.append({
                    "name": alias.name,
                    "target": target,
                    "line": node.lineno,
                })

        def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
            module = "." * node.level + (node.module or "")
            target = _resolve_python_import(module.lstrip("."), rels)
            for alias in node.names:
                imports.append({
                    "name": alias.name,
                    "module": module,
                    "target": target,
                    "line": node.lineno,
                })

        def visit_Call(self, node: ast.Call) -> Any:
            name = _call_name(node.func)
            if name:
                calls.append({"name": name, "line": getattr(node, "lineno", 1)})
            self.generic_visit(node)

    Visitor().visit(tree)
    return {"path": file.rel, "symbols": symbols, "imports": imports, "calls": calls}


def _analyze_text_code(file: CodeFile, rels: set[str]) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    for idx, line in enumerate(file.text.splitlines(), 1):
        stripped = line.strip()
        sym_match = re.search(
            r"\b(?:function|class|interface|type|def|func)\s+([A-Za-z_][\w$]*)",
            stripped,
        )
        if sym_match:
            symbols.append({
                "path": file.rel,
                "name": sym_match.group(1),
                "kind": "symbol",
                "start_line": idx,
                "end_line": idx,
                "signature": stripped[:200],
            })
        imp_match = re.search(r"(?:from|import|require\()\s+[\"']?([A-Za-z0-9_./@-]+)", stripped)
        if imp_match:
            raw = imp_match.group(1)
            imports.append({"name": raw, "target": _resolve_path_like_import(raw, file.rel, rels), "line": idx})
        for call_name in re.findall(r"\b([A-Za-z_][\w$]*)\s*\(", stripped):
            if call_name not in {"if", "for", "while", "switch", "return", "function"}:
                calls.append({"name": call_name, "line": idx})
    return {"path": file.rel, "symbols": symbols, "imports": imports, "calls": calls}


def _symbol(rel: str, name: str, kind: str, node: ast.AST) -> dict[str, Any]:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return {
        "path": rel,
        "name": name,
        "kind": kind,
        "start_line": start,
        "end_line": end,
        "signature": name,
    }


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _resolve_python_import(module: str, rels: set[str]) -> str:
    if not module:
        return ""
    candidate = module.replace(".", "/") + ".py"
    if candidate in rels:
        return candidate
    package_init = module.replace(".", "/") + "/__init__.py"
    if package_init in rels:
        return package_init
    parts = module.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = "/".join(parts) + ".py"
        if candidate in rels:
            return candidate
    return ""


def _resolve_path_like_import(raw: str, source_rel: str, rels: set[str]) -> str:
    normalized = raw.strip("./").replace("\\", "/")
    candidates = [
        normalized,
        f"{normalized}.py",
        f"{normalized}.ts",
        f"{normalized}.js",
        f"{normalized}/index.ts",
        f"{normalized}/index.js",
    ]
    source_dir = str(Path(source_rel).parent).replace("\\", "/")
    if source_dir == ".":
        source_dir = ""
    for candidate in list(candidates):
        if source_dir:
            candidates.append(f"{source_dir}/{candidate}")
    for candidate in candidates:
        if candidate in rels:
            return candidate
    return ""
