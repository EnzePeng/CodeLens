"""
Tool System - Base classes and registry for Agent tools.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from logger import logger
from exceptions import ToolNotFoundError, ToolExecutionError


# ---- Tool recommendation configuration ----

ALWAYS_AVAILABLE = {"read_file", "list_directory", "search_files"}

_RELEVANT_TOOL_KEYWORDS: dict[str, list[str]] = {
    "file_read": ["read", "open", "view", "check", "查看", "读取", "打开", "浏览"],
    "file_write": ["write", "create", "edit", "modify", "新增", "修改", "创建", "写入", "更新", "change", "add"],
    "search": ["search", "find", "grep", "查找", "搜索", "定位", "match", "pattern", "glob"],
    "execution": ["run", "execute", "test", "build", "运行", "执行", "测试", "编译", "命令"],
    "git": ["git", "commit", "push", "branch", "rebase", "merge", "stash", "tag"],
    "undo": ["undo", "revert", "恢复", "撤销", "回滚"],
    "code_analysis": ["analyze", "complexity", "reference", "统计", "分析", "count", "lines", "symbol", "definition"],
    "project": ["config", "package", "dependency", "依赖", "配置", "project", "lockfile"],
    "lsp": ["definition", "references", "hover", "symbol", "跳转", "定义", "引用"],
}


@dataclass
class ToolDefinition:
    """Tool definition for registry and LLM prompt generation."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    execute: Optional[Callable] = None


class Tool(ABC):
    """Base class for all Agent tools."""
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Ensure each subclass gets its own parameters dict
        if "parameters" not in cls.__dict__:
            cls.parameters = {}

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool with given arguments. Returns result as string."""
        pass

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            execute=self.execute,
        )


class ToolRegistry:
    """Registry for all available Agent tools."""
    _tools: dict[str, Tool] = {}
    _definitions: dict[str, ToolDefinition] = {}

    @classmethod
    def register(cls, tool: Tool) -> None:
        cls._tools[tool.name] = tool
        cls._definitions[tool.name] = tool.get_definition()
        logger.info(f"[Tools] Registered: {tool.name}")

    @classmethod
    def get(cls, name: str) -> Tool:
        if name not in cls._tools:
            raise ToolNotFoundError(f"Tool not found: {name}")
        return cls._tools[name]

    @classmethod
    def get_definition(cls, name: str) -> ToolDefinition:
        if name not in cls._definitions:
            raise ToolNotFoundError(f"Tool definition not found: {name}")
        return cls._definitions[name]

    @classmethod
    def list_tools(cls) -> list[dict[str, Any]]:
        return [
            {"name": d.name, "description": d.description, "parameters": d.parameters}
            for d in cls._definitions.values()
        ]

    @classmethod
    def recommend_tools(cls, query_or_message: str, max_tools: int = 6) -> list[dict[str, Any]]:
        """Select a subset of tools relevant to the current query/message.

        Uses keyword matching to score tools by relevance, always includes
        ALWAYS_AVAILABLE tools, and returns at most max_tools.
        """
        text = query_or_message.lower()

        # Start with always-available tools
        selected: set[str] = set(ALWAYS_AVAILABLE)

        # Score tools by keyword matching
        scores: list[tuple[float, str]] = []
        for tool_name in cls._definitions:
            if tool_name in selected:
                continue
            score = 0.0
            for category, keywords in _RELEVANT_TOOL_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    score += 1.0
            # Also check tool description
            desc_lower = cls._definitions[tool_name].description.lower()
            if any(kw in desc_lower for kw in text.split()[:20]):
                score += 0.5
            if score > 0:
                scores.append((score, tool_name))

        # Add top-scoring tools
        scores.sort(reverse=True)
        for _, name in scores[:max_tools - len(selected)]:
            selected.add(name)

        return [
            {
                "name": d.name,
                "description": d.description,
                "parameters": d.parameters,
            }
            for name, d in sorted(
                [(n, cls._definitions[n]) for n in selected],
                key=lambda x: x[1].name,
            )
        ]

    @classmethod
    def execute(cls, name: str, **kwargs) -> str:
        tool = cls.get(name)
        try:
            result = tool.execute(**kwargs)
            logger.info(f"[Tools] Executed: {name}")
            return result
        except Exception as e:
            logger.error(f"[Tools] Execution failed: {name} - {e}")
            raise ToolExecutionError(f"Tool {name} failed: {e}")


def register_tool(tool: Tool) -> None:
    """Convenience function to register a tool."""
    ToolRegistry.register(tool)
