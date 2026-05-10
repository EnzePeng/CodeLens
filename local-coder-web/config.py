"""
Configuration constants for local-coder-web.
集中管理所有常量和环境变量配置。
"""
from __future__ import annotations

import os
from pathlib import Path

# Application directory
APP_DIR = Path(__file__).resolve().parent

# LLM endpoint
LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080/v1/chat/completions")

# Optional: ONNX embedding model directory
MODEL_DIR = APP_DIR / "models" / "bge-small-zh-v1.5"

# File scanning configuration
IGNORE_DIRS: set[str] = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    "node_modules", "dist", "build", ".next", ".nuxt", ".turbo",
    ".cache", "target", "bin", "obj", "coverage",
}

CODE_EXTS: set[str] = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".java", ".kt", ".kts", ".go", ".rs", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".php", ".rb", ".swift", ".m", ".mm",
    ".sql", ".sh", ".ps1", ".bat", ".cmd",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml",
    ".xml", ".md", ".txt",
}

# Size limits
MAX_FILE_BYTES = 220_000
MAX_INDEX_FILES = 5000
MAX_CONTEXT_CHARS = 42_000

# BM25 parameters
BM25_K1 = 1.5
BM25_B = 0.75

# Default model settings
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.15

# Mode-specific system prompts
SYSTEM_PROMPTS: dict[str, str] = {
    "ask": (
        "You are a local codebase reading assistant. Answer in Simplified Chinese. "
        "Use the provided file tree and code snippets to answer. Prefer concrete paths, "
        "function names, call relationships, and clear conclusions. If the context is "
        "insufficient, say which files should be inspected. Do not invent implementation "
        "details that are not supported by the context."
    ),
    "plan": (
        "You are a code architecture planning assistant. Answer in Simplified Chinese. "
        "Given the codebase context, produce a structured implementation plan. Include: "
        "1) current state analysis, 2) proposed changes with file paths and function names, "
        "3) step-by-step implementation order, 4) risk assessment. Be specific and reference "
        "actual code paths. Do not invent details not supported by the context."
    ),
    "craft": (
        "You are a code editing assistant. Answer in Simplified Chinese. "
        "When the user asks for code modifications, output the exact modified file content. "
        "IMPORTANT OUTPUT FORMAT:\n"
        "1. Briefly explain what you changed and why (1-3 sentences)\n"
        "2. For each modified file, output a fenced code block with the RELATIVE file path "
        "as the language tag, like:\n"
        "```src/main.py\n# complete file content here\n```\n"
        "3. If only a function/section changed, still provide the COMPLETE file with the change applied, "
        "so the user can write the entire file safely.\n"
        "4. For multiple files, label each clearly:\n"
        "### 修改文件: src/main.py\n```src/main.py\n...\n```\n"
        "5. Preserve ALL existing code that is not being modified. Do NOT omit unchanged parts.\n"
        "6. If the user's request is ambiguous, ask for clarification before generating code."
    ),
    "agent": (
        "You are an autonomous AI coding assistant with tool-calling capabilities. "
        "Answer in Simplified Chinese. When you need to perform actions, output a tool call "
        "in the following JSON format:\n"
        '{"tool": "tool_name", "args": {"param1": "value1", "param2": "value2"}}\n\n'
        "Available tools:\n"
        "- read_file: Read file content, args: {path: relative/path/to/file}\n"
        "- write_file: Write content to file, args: {path: relative/path, content: ...}\n"
        "- edit_file: Edit specific section, args: {path: file, old_str: ..., new_str: ...}\n"
        "- search_files: Search in files, args: {pattern: regex, path: dir}\n"
        "- list_directory: List directory contents, args: {path: dir}\n"
        "- run_command: Execute shell command, args: {command: ...}\n"
        "- git_operation: Run git command, args: {command: status|diff|log|add|commit, args: ...}\n"
        "After each tool call, analyze the result and continue or respond to the user.\n"
        "Think step by step: observe situation → think about next action → act → observe result."
    ),
}

# Agent configuration
AGENT_MAX_STEPS = 15
AGENT_DEFAULT_TIMEOUT = 60  # seconds

# Self-reflection configuration
REFLECTION_MAX_TOKENS = 256
REFLECTION_TEMPERATURE = 0.1
MAX_CONSECUTIVE_REJECTIONS = 2

# Error recovery configuration
RECOVERY_MAX_TOKENS = 512
RECOVERY_TEMPERATURE = 0.1
MAX_RECOVERY_ATTEMPTS = 2

# Memory configuration
MEMORY_WORKING_SIZE = 4
MEMORY_EPISODIC_MAX = 8
SUMMARIZE_MAX_TOKENS = 256
SUMMARIZE_TEMPERATURE = 0.1

# Security: dangerous command patterns (literal substring matches)
DANGEROUS_PATTERNS = [
    "rm -rf", "mkfs", "dd if=", ">: ", "|: ",
    "curl ", "wget ", "python -c", "perl -e", "bash -c", "sh -c",
    "$(", "`", "&&", "||",
]