"""
Data models for local-coder-web.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel


@dataclass
class CodeFile:
    """Represents a code file in the repository."""

    path: Path
    rel: str
    size: int
    text: str
    symbols: list[str] = field(default_factory=list)
    tf: dict[str, float] = field(default_factory=dict)
    tokens_list: list[str] = field(default_factory=list)
    embedding: np.ndarray | None = None


def extract_symbols(text: str) -> list[str]:
    """Extract function/class/def names and import relationships from source code."""

    symbols: list[str] = []
    patterns = [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w$]*)",
        r"^\s*(?:export\s+)?class\s+([A-Za-z_][\w$]*)",
        r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(",
        r"^\s*class\s+([A-Za-z_]\w*)",
        r"^\s*func\s+([A-Za-z_]\w*)",
        r"^\s*@(?:dataclass|property|staticmethod|classmethod|cached_property)\b",
        r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s+)?\(",
        r"^\s*(?:export\s+)?(?:interface|type|enum)\s+([A-Za-z_][\w$]*)",
        r"^\s*(?:pub\s+)?(impl|trait)\s+([A-Za-z_]\w*)",
    ]
    for line in text.splitlines()[:1600]:
        for pattern in patterns:
            match = re.search(pattern, line, re.MULTILINE)
            if match:
                name = match.group(1)
                if name and name not in symbols:
                    symbols.append(name)
                break
        if len(symbols) >= 30:
            break
    return symbols


@dataclass
class AppState:
    """Application global state."""

    root: Path | None = None
    files: list[CodeFile] = field(default_factory=list)
    tree: dict = field(default_factory=dict)
    idf: dict[str, float] = field(default_factory=dict)
    avg_dl: float = 0.0
    embedding_ready: bool = False
    dep_graph: Any = None
    code_graph: Any = None
    project_brief: dict[str, Any] | None = None
    index_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)


state = AppState()


class EvidenceRef(BaseModel):
    path: str
    start_line: int = 1
    end_line: int = 1
    symbol: str = ""
    reason: str = ""


class IndexJobState(BaseModel):
    job_id: str
    stage: str = "pending"
    progress: float = 0.0
    file_count: int = 0
    graph_ready: bool = False
    brief_ready: bool = False
    errors: list[str] = field(default_factory=list)


class ProjectBrief(BaseModel):
    overview: str
    modules: list[dict[str, Any]]
    entrypoints: list[dict[str, Any]]
    flows: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    read_next: list[dict[str, Any]]
    evidence: list[EvidenceRef]


class FileLens(BaseModel):
    path: str
    summary: str
    imports: list[dict[str, Any]]
    imported_by: list[dict[str, Any]]
    callers: list[dict[str, Any]]
    callees: list[dict[str, Any]]
    related_tests: list[dict[str, Any]]
    related_configs: list[dict[str, Any]]
    evidence: list[EvidenceRef]


class FileLensRequest(BaseModel):
    path: str
    depth: int = 2


class FolderRequest(BaseModel):
    path: str


class AskRequest(BaseModel):
    question: str
    mode: str = "ask"
    file_path: str | None = None
    new_content: str | None = None
    history: list[dict] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    context_limit: int | None = None


class CraftApplyRequest(BaseModel):
    file_path: str
    content: str


class ReadFileRequest(BaseModel):
    path: str


class BrowseRequest(BaseModel):
    path: str = ""


class ExecRequest(BaseModel):
    command: str
    cwd: str = ""


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    returncode: int


class CompleteRequest(BaseModel):
    code: str
    cursor_pos: int = 0
    file_path: str = ""


class CompleteResponse(BaseModel):
    completions: list[dict]
    is_incomplete: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.3.1"
    folder: str = ""
    file_count: int = 0
    embedding_mode: str = "bm25"
    search_cache: dict = field(default_factory=dict)


class IndexStatsResponse(BaseModel):
    file_count: int = 0
    embedding_mode: str = "bm25"
    index_time: float = 0.0
    search_cache: dict = field(default_factory=dict)
    mode: str = "full"


class ChatHistoryMessage(BaseModel):
    role: str
    content: str
    mode: str = "ask"
    timestamp: float = 0.0


class AgentStep(BaseModel):
    step_id: int
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: str | None = None
    status: str = "pending"
    timestamp: float = 0.0
    duration: float = 0.0
    error: str | None = None


class AgentState(BaseModel):
    task_id: str
    user_query: str
    status: str = "pending"
    steps: list[AgentStep] = field(default_factory=list)
    current_step: int = 0
    phase: str = "parsing"
    context: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


class AgentStartRequest(BaseModel):
    query: str
    max_steps: int = 15


class AgentActionRequest(BaseModel):
    task_id: str
    action: str
    tool_call_id: str | None = None


class AgentStatusResponse(BaseModel):
    task_id: str
    status: str
    steps: list[AgentStep]
    current_step: int
    result: str | None = None
