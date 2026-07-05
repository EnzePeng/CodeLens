"""Project understanding helpers for overview and File Lens."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from models import CodeFile
from services.code_graph import CodeGraph, is_config_file


def build_project_brief(root: Path, files: list[CodeFile], graph: CodeGraph) -> dict[str, Any]:
    modules = _modules(files, graph)
    entrypoints = _entrypoints(files, graph)
    evidence = _brief_evidence(files, graph)
    return {
        "overview": f"已索引 {len(files)} 个源码文件，识别 {len(modules)} 个主要模块和 {len(entrypoints)} 个入口候选。",
        "modules": modules,
        "entrypoints": entrypoints,
        "flows": _flows(graph),
        "risks": _risks(files, graph),
        "read_next": _read_next(entrypoints, modules),
        "evidence": evidence,
    }


def build_file_lens(path: str, files: list[CodeFile], graph: CodeGraph, depth: int = 2) -> dict[str, Any]:
    file_map = {f.rel: f for f in files}
    info = graph.get_file(path)
    target_file = file_map.get(path)
    tests = _related_tests(path, files)
    configs = _related_configs(path, files)
    evidence = [
        _evidence(path, sym.get("start_line", 1), sym.get("end_line", 1), sym.get("name", ""), "symbol in focus file")
        for sym in info.get("symbols", [])[:8]
    ]
    if not evidence and target_file:
        evidence.append(_evidence(path, 1, 1, "", "focus file"))
    return {
        "path": path,
        "summary": _file_summary(path, target_file, info),
        "imports": [imp for imp in info.get("imports", []) if imp.get("target")][:depth * 8],
        "imported_by": graph.imported_by(path)[:depth * 8],
        "callers": graph.callers_for_file(path)[:depth * 8],
        "callees": graph.callees_for_file(path)[:depth * 8],
        "related_tests": tests[:depth * 8],
        "related_configs": configs[:8],
        "evidence": evidence,
    }


def _modules(files: list[CodeFile], graph: CodeGraph) -> list[dict[str, Any]]:
    buckets: dict[str, list[CodeFile]] = defaultdict(list)
    for file in files:
        top = file.rel.split("/", 1)[0] if "/" in file.rel else "."
        if top.startswith("."):
            top = "."
        buckets[top].append(file)
    modules: list[dict[str, Any]] = []
    for name, grouped in sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0])):
        symbols = []
        for file in grouped:
            symbols.extend(graph.get_file(file.rel).get("symbols", [])[:3])
        modules.append({
            "path": name,
            "file_count": len(grouped),
            "role": _module_role(name),
            "symbols": [s.get("name", "") for s in symbols[:10]],
            "evidence": [_evidence(grouped[0].rel, 1, 1, "", f"module sample for {name}")],
        })
    return modules[:12]


def _entrypoints(files: list[CodeFile], graph: CodeGraph) -> list[dict[str, Any]]:
    hints = ("app.py", "main.py", "server.py", "index.js", "index.ts", "package.json", "pyproject.toml")
    entries: list[dict[str, Any]] = []
    for file in files:
        name = Path(file.rel).name
        if name in hints or "FastAPI(" in file.text or "if __name__" in file.text:
            entries.append({
                "path": file.rel,
                "reason": "entrypoint candidate",
                "symbols": [s.get("name", "") for s in graph.get_file(file.rel).get("symbols", [])[:5]],
                "evidence": [_evidence(file.rel, 1, 1, "", "entrypoint candidate")],
            })
    return entries[:10]


def _flows(graph: CodeGraph) -> list[dict[str, Any]]:
    flows = []
    for rel, info in graph.files.items():
        targets = [imp.get("target") for imp in info.get("imports", []) if imp.get("target")]
        if targets:
            flows.append({"from": rel, "to": targets[:6], "kind": "imports"})
    return flows[:12]


def _risks(files: list[CodeFile], graph: CodeGraph) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    large = [f for f in files if len(f.text.splitlines()) > 500]
    if large:
        f = large[0]
        risks.append({
            "title": "Large file may be hard to reason about",
            "path": f.rel,
            "severity": "medium",
            "evidence": [_evidence(f.rel, 1, 1, "", "large file")],
        })
    unlinked = [rel for rel, info in graph.files.items() if not info.get("imports") and not graph.imported_by(rel)]
    if unlinked:
        risks.append({
            "title": "Some files are isolated from the import graph",
            "path": unlinked[0],
            "severity": "low",
            "evidence": [_evidence(unlinked[0], 1, 1, "", "isolated file")],
        })
    return risks[:8]


def _read_next(entrypoints: list[dict[str, Any]], modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{"path": e["path"], "reason": "start from an entrypoint"} for e in entrypoints[:3]]
    out.extend({"path": m["path"], "reason": "major module"} for m in modules[:4])
    return out[:6]


def _brief_evidence(files: list[CodeFile], graph: CodeGraph) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for file in files[:8]:
        symbols = graph.get_file(file.rel).get("symbols", [])
        if symbols:
            sym = symbols[0]
            evidence.append(_evidence(file.rel, sym.get("start_line", 1), sym.get("end_line", 1), sym.get("name", ""), "project symbol"))
        else:
            evidence.append(_evidence(file.rel, 1, 1, "", "project file"))
    return evidence


def _related_tests(path: str, files: list[CodeFile]) -> list[dict[str, Any]]:
    stem = Path(path).stem.lower()
    module_bits = set(Path(path).with_suffix("").parts)
    tests: list[dict[str, Any]] = []
    for file in files:
        lower = file.rel.lower()
        if "test" not in lower:
            continue
        if stem in lower or any(bit and bit in file.text for bit in module_bits):
            tests.append({"path": file.rel, "reason": "test references focus module", "line": 1})
    return tests


def _related_configs(path: str, files: list[CodeFile]) -> list[dict[str, Any]]:
    return [{"path": f.rel, "reason": "project configuration", "line": 1} for f in files if is_config_file(f.rel)]


def _file_summary(path: str, file: CodeFile | None, info: dict[str, Any]) -> str:
    if file is None:
        return "文件未在当前索引中找到。"
    symbols = [s.get("name", "") for s in info.get("symbols", [])[:5]]
    if symbols:
        return f"{path} 定义了 {', '.join(symbols)} 等符号。"
    return f"{path} 包含 {len(file.text.splitlines())} 行内容。"


def _module_role(name: str) -> str:
    mapping = {
        "core": "agent and orchestration core",
        "services": "backend services and indexing",
        "routes": "FastAPI HTTP API routes",
        "static": "browser workbench UI",
        "tests": "test suite",
        ".": "project root files",
    }
    return mapping.get(name, "source module")


def _evidence(path: str, start: int, end: int, symbol: str, reason: str) -> dict[str, Any]:
    return {
        "path": path,
        "start_line": max(1, int(start or 1)),
        "end_line": max(1, int(end or start or 1)),
        "symbol": symbol,
        "reason": reason,
    }
