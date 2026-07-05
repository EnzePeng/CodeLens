from __future__ import annotations

from pathlib import Path

from models import CodeFile


def _cf(root: Path, rel: str, text: str) -> CodeFile:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return CodeFile(path=path, rel=rel, size=len(text), text=text)


def test_code_graph_extracts_python_symbols_imports_and_calls(tmp_path):
    from services.code_graph import build_code_graph

    files = [
        _cf(
            tmp_path,
            "app.py",
            "from services.worker import run_job\n\n"
            "def main():\n"
            "    return run_job()\n",
        ),
        _cf(
            tmp_path,
            "services/worker.py",
            "def run_job():\n"
            "    return 42\n",
        ),
    ]

    graph = build_code_graph(files)

    app = graph.get_file("app.py")
    assert any(sym["name"] == "main" and sym["kind"] == "function" for sym in app["symbols"])
    assert any(imp["target"] == "services/worker.py" for imp in app["imports"])
    assert any(call["name"] == "run_job" for call in app["calls"])
    assert graph.imported_by("services/worker.py")[0]["path"] == "app.py"


def test_file_lens_connects_imports_imported_by_tests_and_configs(tmp_path):
    from services.code_graph import build_code_graph
    from services.project_intel import build_file_lens

    files = [
        _cf(tmp_path, "app.py", "from services.worker import run_job\n\ndef main():\n    return run_job()\n"),
        _cf(tmp_path, "services/worker.py", "def run_job():\n    return 42\n"),
        _cf(tmp_path, "tests/test_worker.py", "from services.worker import run_job\n\ndef test_run_job():\n    assert run_job() == 42\n"),
        _cf(tmp_path, "pyproject.toml", "[project]\nname='demo'\n"),
    ]
    graph = build_code_graph(files)

    lens = build_file_lens("services/worker.py", files, graph)

    assert lens["path"] == "services/worker.py"
    assert any(item["path"] == "app.py" for item in lens["imported_by"])
    assert any(item["path"] == "tests/test_worker.py" for item in lens["related_tests"])
    assert any(item["path"] == "pyproject.toml" for item in lens["related_configs"])
    assert any(e["path"] == "services/worker.py" and e["symbol"] == "run_job" for e in lens["evidence"])


def test_project_brief_contains_modules_entrypoints_risks_and_evidence(tmp_path):
    from services.code_graph import build_code_graph
    from services.project_intel import build_project_brief

    files = [
        _cf(tmp_path, "app.py", "from fastapi import FastAPI\napp = FastAPI()\n\ndef main():\n    pass\n"),
        _cf(tmp_path, "services/search.py", "def select_context():\n    pass\n"),
        _cf(tmp_path, "routes/ask.py", "def ask():\n    pass\n"),
        _cf(tmp_path, "pyproject.toml", "[project]\ndependencies=['fastapi']\n"),
    ]
    graph = build_code_graph(files)

    brief = build_project_brief(tmp_path, files, graph)

    assert "4 个源码文件" in brief["overview"]
    assert any(module["path"] == "services" for module in brief["modules"])
    assert any(entry["path"] == "app.py" for entry in brief["entrypoints"])
    assert brief["read_next"]
    assert brief["evidence"]
