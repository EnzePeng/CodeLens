"""
Tool System - Base classes and registry for Agent tools.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from logger import logger
from exceptions import ToolNotFoundError, ToolExecutionError


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
    parameters: dict[str, Any] = field(default_factory=dict)

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
