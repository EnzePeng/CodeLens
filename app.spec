# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for CodeLens web app.
Bundles the FastAPI application into a single directory.
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Project paths
# Use the current working directory as the project root
SPEC_DIR = os.getcwd()
WEB_DIR = os.path.join(SPEC_DIR, "local-coder-web")

a = Analysis(
    [os.path.join(WEB_DIR, "app.py")],
    pathex=[WEB_DIR, SPEC_DIR],
    binaries=[],
    datas=[
        (os.path.join(WEB_DIR, "static"), "static"),
    ],
    hiddenimports=[
        # Core app
        "app",
        "config",
        "logger",
        "exceptions",
        "models",
        "models.state",

        # FastAPI + Uvicorn
        "fastapi",
        "fastapi.middleware",
        "fastapi.middleware.cors",
        "fastapi.middleware.gzip",
        "fastapi.responses",
        "fastapi.staticfiles",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "starlette",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.middleware.base",
        "starlette.types",
        "starlette.responses",

        # HTTP client
        "httpx",

        # Data / Config
        "pydantic",
        "numpy",

        # File watching
        "watchdog",
        "watchdog.observers",
        "watchdog.events",

        # Routes
        "routes",
        "routes.main",
        "routes.ask",
        "routes.files",
        "routes.complete",
        "routes.comment",
        "routes.agent",

        # Core modules
        "core",
        "core.agent",
        "core.engine",
        "core.react",
        "core.router",
        "core.decomposer",
        "core.aggregator",
        "core.memory",
        "core.context",
        "core.llm_client",
        "core.model_manager",
        "core.tool_call_parser",
        "core.self_improve",
        "core.metrics",
        "core.optimizer",
        "core.fast_completion",

        # Core tools
        "core.tools",
        "core.tools.base",
        "core.tools.read_file",
        "core.tools.write_file",
        "core.tools.edit_file",
        "core.tools.apply_diff",
        "core.tools.diff_preview",
        "core.tools.diff_utils",
        "core.tools.search_files",
        "core.tools.list_directory",
        "core.tools.run_command",
        "core.tools.git_operation",
        "core.tools.undo_edit",
        "core.tools.file_operations",
        "core.tools.code_analysis",
        "core.tools.test",
        "core.tools.project",
        "core.tools.glob_tool",
        "core.tools.grep_tool",
        "core.tools.lsp_tool",

        # Services
        "services",
        "services.search",
        "services.indexer",
        "services.cache",
        "services.file_watcher",
        "services.chat_history",
        "services.context_manager",
        "services.memory",
        "services.ast_indexer",

        # Optional ONNX
        "onnxruntime",
        "tokenizers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "PIL",
        "cv2",
        "pytest",
        "unittest",
        "doctest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="app",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="app",
)
