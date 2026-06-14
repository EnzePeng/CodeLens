"""
Complete route — /api/complete (code completion).

Uses fast model (Qwen3-1.7B) for low-latency code completion.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel as PydanticBaseModel

from core.fast_completion import fast_completion

router = APIRouter()

# 语言映射
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".sql": "sql",
    ".sh": "bash",
    ".ps1": "powershell",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".md": "markdown",
}


def detect_language(file_path: str) -> str:
    """从文件路径检测编程语言"""
    if not file_path:
        return ""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext, "")


class CompleteRequest(PydanticBaseModel):
    code: str
    cursor_pos: int = 0
    file_path: str = ""


class CompleteResponse(PydanticBaseModel):
    completions: list[dict]
    is_incomplete: bool = False
    latency_ms: float = 0


@router.post("/api/complete")
async def code_complete(req: CompleteRequest) -> CompleteResponse:
    if not req.code or not req.code.strip():
        return CompleteResponse(completions=[])

    before_cursor = req.code[:req.cursor_pos]
    after_cursor = req.code[req.cursor_pos:]

    # 检测语言
    language = detect_language(req.file_path)
    
    # 优化：减少前缀长度以提高速度
    max_prefix = 2000  # 从3000减少到2000
    if len(before_cursor) > max_prefix:
        before_cursor = before_cursor[-max_prefix:]

    result = await fast_completion.complete(
        prefix=before_cursor,
        suffix=after_cursor,
        max_tokens=64,  # 从128减少到64以提高速度
        temperature=0.2,
        language=language,
    )

    if not result.text:
        return CompleteResponse(completions=[], latency_ms=result.latency_ms)

    completions = [{"text": result.text, "description": "AI completion"}]
    return CompleteResponse(
        completions=completions,
        latency_ms=result.latency_ms,
    )
