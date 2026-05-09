"""
Custom exceptions for local-coder-web.
定义项目专用的异常类。
"""
from __future__ import annotations


class CodeLensError(Exception):
    """Base exception for all CodeLens errors."""
    pass


class ConfigurationError(CodeLensError):
    """Configuration related errors."""
    pass


class IndexNotReadyError(CodeLensError):
    """Raised when trying to query before indexing is complete."""
    pass


class FileAccessError(CodeLensError):
    """Raised when file access fails (read/write)."""
    pass


class SecurityError(CodeLensError):
    """Raised when a security check fails (path traversal, dangerous commands)."""
    pass


class AgentError(CodeLensError):
    """Base exception for Agent-related errors."""
    pass


class AgentTimeoutError(AgentError):
    """Raised when Agent execution exceeds time limit."""
    pass


class AgentMaxStepsError(AgentError):
    """Raised when Agent exceeds maximum steps."""
    pass


class ToolExecutionError(AgentError):
    """Raised when a tool execution fails."""
    pass


class ToolNotFoundError(AgentError):
    """Raised when requested tool is not registered."""
    pass


class ContextLimitError(CodeLensError):
    """Raised when context exceeds token limit."""
    pass


class LLMError(CodeLensError):
    """Base exception for LLM-related errors."""
    pass


class LLMConnectionError(LLMError):
    """Raised when cannot connect to LLM service."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""
    pass


class LLMResponseError(LLMError):
    """Raised when LLM returns an error response."""
    pass