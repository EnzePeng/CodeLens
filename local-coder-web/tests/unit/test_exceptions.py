"""Tests for exception classes."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import exceptions as exc_module


class TestExceptionHierarchy:
    def test_base_exception(self):
        assert issubclass(exc_module.CodeLensError, Exception)

    def test_inheritance_chain(self):
        assert issubclass(exc_module.FileAccessError, exc_module.CodeLensError)
        assert issubclass(exc_module.SecurityError, exc_module.CodeLensError)
        assert issubclass(exc_module.ToolNotFoundError, exc_module.CodeLensError)
        assert issubclass(exc_module.ToolExecutionError, exc_module.CodeLensError)

    def test_exception_messages(self):
        e = exc_module.FileAccessError("Cannot read file")
        assert "Cannot read file" in str(e)

        e = exc_module.SecurityError("Path traversal detected")
        assert "Path traversal" in str(e)

        e = exc_module.ToolNotFoundError("missing_tool")
        assert "missing_tool" in str(e)

        e = exc_module.ToolExecutionError("Execution failed")
        assert "Execution failed" in str(e)
