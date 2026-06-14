"""
Tool: project — read_config, list_packages, read_lockfile.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.tools.base import Tool
from exceptions import FileAccessError, SecurityError
from models import state


class ProjectTool(Tool):
    """Project info: read config, list packages, read lockfiles."""

    name = "project"
    description = "Read project config, list packages, read lock files."
    parameters = {
        "operation": {
            "type": "string",
            "description": "Operation: read_config, list_packages, read_lockfile",
        },
        "path": {
            "type": "string",
            "description": "Config file path or package name (relative to repo root)",
        },
    }

    def execute(self, operation: str = "", path: str = "", **kwargs) -> str:
        if not operation:
            raise FileAccessError("Missing required argument: operation")
        if state.root is None:
            raise FileAccessError("No repository folder set")

        if operation == "read_config":
            target_path = Path(path) if path else None
            default_configs = [
                "pyproject.toml", "setup.cfg", "setup.py",
                "package.json", "Cargo.toml", "go.mod",
                "requirements.txt", "Pipfile", ".env.example",
            ]
            if target_path:
                candidates = [target_path]
            else:
                candidates = [Path(p) for p in default_configs]

            for c in candidates:
                fp = (state.root / c).resolve()
                try:
                    fp.relative_to(state.root.resolve())
                except ValueError:
                    continue
                if fp.exists():
                    try:
                        content = fp.read_text(encoding="utf-8", errors="replace")
                        return f"=== {c} ===\n{content[:5000]}"
                    except OSError as e:
                        return f"Error reading {c}: {e}"

            return "No config file found"

        elif operation == "list_packages":
            # Look for requirements.txt
            req_file = state.root / "requirements.txt"
            if req_file.exists():
                return f"=== requirements.txt ===\n{req_file.read_text(encoding='utf-8', errors='replace')[:5000]}"

            # Look for package.json
            pkg_file = state.root / "package.json"
            if pkg_file.exists():
                try:
                    pkg = json.loads(pkg_file.read_text(encoding="utf-8")[:50000])
                    deps = {}
                    deps.update(pkg.get("dependencies", {}))
                    deps.update(pkg.get("devDependencies", {}))
                    return f"=== package.json ({len(deps)} dependencies) ===\n" + "\n".join(
                        f"  {k}: {v}" for k, v in sorted(deps.items())
                    )[:5000]
                except Exception as e:
                    return f"Error parsing package.json: {e}"

            # Look for Cargo.toml
            cargo_file = state.root / "Cargo.toml"
            if cargo_file.exists():
                return f"=== Cargo.toml ===\n{cargo_file.read_text(encoding='utf-8', errors='replace')[:5000]}"

            return "No package info found"

        elif operation == "read_lockfile":
            default_lockfiles = [
                "requirements.txt", "poetry.lock", "Pipfile.lock",
                "package-lock.json", "yarn.lock",
                "Cargo.lock", "go.sum",
            ]
            for lf in default_lockfiles:
                fp = (state.root / lf).resolve()
                try:
                    fp.relative_to(state.root.resolve())
                except ValueError:
                    continue
                if fp.exists():
                    try:
                        return f"=== {lf} ===\n{fp.read_text(encoding='utf-8', errors='replace')[:5000]}"
                    except OSError as e:
                        return f"Error reading {lf}: {e}"

            return "No lockfile found"

        raise ValueError(f"Unknown operation: {operation}")


# Register tool
project_tool = ProjectTool()
from core.tools.base import register_tool
register_tool(project_tool)
