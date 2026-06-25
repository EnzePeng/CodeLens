"""
Configuration constants for local-coder-web.
集中管理所有常量和环境变量配置。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from dataclasses import dataclass

# Application directory
# When frozen by PyInstaller, __file__ points inside the temp extraction dir.
# APP_DIR is used for bundled resources (static files, ONNX models).
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).resolve().parent

# BASE_DIR is the directory containing the exe (or the project root in dev mode).
# Used for runtime files: config.ini, models/, llama-server/
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# LLM endpoint
LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080/v1/chat/completions")


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    file: str
    endpoint: str
    context_size: int
    purpose: str  # main, fast, embedding
    description: str


# 模型配置 - 使用 Qwen3.5-9B（Q4_K_M 量化）
MODELS = {
    "main": ModelConfig(
        name="Qwen3.5-9B",
        file="Qwen3.5-9B.Q4_K_M.gguf",
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        context_size=32768,
        purpose="main",
        description="主推理模型 - Agent/Ask/Plan/Craft 全模式共用"
    ),
    "fast": ModelConfig(
        name="Qwen3.5-9B",
        file="Qwen3.5-9B.Q4_K_M.gguf",
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        context_size=32768,
        purpose="fast",
        description="快速模型 - 与主模型相同（单模型部署）"
    ),
    "fallback": ModelConfig(
        name="Qwen3.5-9B",
        file="Qwen3.5-9B.Q4_K_M.gguf",
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        context_size=32768,
        purpose="main",
        description="备选主模型"
    )
}

# 当前使用的模型（可通过环境变量覆盖）
CURRENT_MAIN_MODEL = os.environ.get("CODELENS_MAIN_MODEL", "main")
CURRENT_FAST_MODEL = os.environ.get("CODELENS_FAST_MODEL", "fast")


def get_model(purpose: str = "main") -> ModelConfig:
    """获取指定用途的模型配置"""
    if purpose == "fast":
        return MODELS[CURRENT_FAST_MODEL]
    return MODELS[CURRENT_MAIN_MODEL]


# 快速模型端点（用于代码补全和快速反思）
# 如果快速模型未运行，回退到主模型
FAST_MODEL_URL = os.environ.get("FAST_MODEL_URL", "http://127.0.0.1:8081/v1/chat/completions")

# 主模型端点（用于代码补全的备选方案）
MAIN_MODEL_URL = os.environ.get("MAIN_MODEL_URL", "http://127.0.0.1:8080/v1/chat/completions")

# Optional: ONNX embedding model directory
MODEL_DIR = BASE_DIR / "models" / "bge-small-zh-v1.5"

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
MAX_CONTEXT_CHARS = 3_000  # 最小上下文以获得最快速度

# BM25 parameters
BM25_K1 = 1.5
BM25_B = 0.75

# Default model settings
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.15

# Mode-specific system prompts
SYSTEM_PROMPTS: dict[str, str] = {
    "ask": (
        "你是一个专业的代码阅读助手。使用简体中文回答。\n\n"
        "你的核心能力：\n"
        "1. **代码解读**：解释代码的功能、逻辑流程、设计模式\n"
        "2. **架构分析**：分析模块间的依赖关系、调用链路\n"
        "3. **问题定位**：帮助理解代码中的问题或bug\n"
        "4. **知识传授**：解释代码中使用的编程概念和技术\n\n"
        "回答规范：\n"
        "- 引用具体的文件路径和函数名（如 `src/utils.py:calculate()`）\n"
        "- 使用代码块展示关键代码片段\n"
        "- 解释调用关系和数据流\n"
        "- 如果上下文不足，明确指出需要查看哪些文件\n"
        "- 不要编造代码中不存在的实现细节\n\n"
        "输出格式：\n"
        "- 使用 Markdown 格式化回答\n"
        "- 代码块使用正确的语言标记\n"
        "- 重要概念使用**加粗**强调\n"
        "- 适当使用列表和表格组织信息"
    ),
    "plan": (
        "你是一个代码架构规划助手。使用简体中文回答。\n\n"
        "给定代码库上下文，生成结构化的实现计划：\n"
        "1) **现状分析**：当前代码结构和问题\n"
        "2) **修改方案**：具体的文件路径和函数名\n"
        "3) **实施步骤**：按依赖关系排序的执行顺序\n"
        "4) **风险评估**：可能的影响和注意事项\n\n"
        "要求：\n"
        "- 引用实际的代码路径\n"
        "- 不要编造上下文不支持的细节"
    ),
    "craft": (
        "你是一个代码编辑助手。使用简体中文回答。\n\n"
        "当用户要求代码修改时，输出完整的修改后文件内容。\n\n"
        "输出格式：\n"
        "1. 简要说明修改内容和原因（1-3句话）\n"
        "2. 对于每个修改的文件，使用相对路径作为语言标签的代码块：\n"
        "```src/main.py\n# 完整文件内容\n```\n"
        "3. 即使只修改了部分，也要提供**完整**的文件内容\n"
        "4. 多个文件时，分别标注：\n"
        "### 修改文件: src/main.py\n```src/main.py\n...\n```\n"
        "5. 保留所有未修改的代码\n"
        "6. 如果请求不明确，先询问用户"
    ),
    "agent": (
        "你是一个自主AI编程助手。使用简体中文回答。\n\n"
        "工具调用格式：\n"
        '{"tool": "tool_name", "args": {"param1": "value1"}}\n\n'
        "可用工具：\n"
        "- read_file: 读取文件，args: {path: 文件路径}\n"
        "- write_file: 写入文件，args: {path: 文件路径, content: 内容}\n"
        "- edit_file: 编辑文件，args: {path: 文件路径, old_str: 旧内容, new_str: 新内容}\n"
        "- search_files: 搜索文件，args: {pattern: 正则表达式}\n"
        "- list_directory: 列出目录，args: {path: 目录路径}\n"
        "- run_command: 执行命令，args: {command: 命令}\n"
        "- git_operation: Git操作，args: {command: 操作类型}\n\n"
        "执行流程：观察 → 思考 → 执行 → 验证"
    ),
}

# Agent configuration
# ReAct 循环的迭代上限是「软兜底」——正常情况下任务靠模型不再调用工具
# 自然结束，max_iterations 仅防止本地小模型无限循环。
# 实际生效值由前端传入的 max_steps 决定（默认 15，见 models.AgentStartRequest），
# 经 ReActConfig.capped() 应用到每个 ReAct 循环。
# AGENT_MAX_STEPS 这里仅作文档参考，实际不被代码读取。
AGENT_MAX_STEPS = 15

# Security: dangerous command patterns (literal substring matches)
DANGEROUS_PATTERNS = [
    "rm -rf", "mkfs", "dd if=", ">: ", "|: ",
    "curl ", "wget ", "perl -e", "bash -c", "sh -c",
    "$(", "`",
]