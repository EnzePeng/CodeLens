"""Tests for config module."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    LLAMA_URL, IGNORE_DIRS, CODE_EXTS,
    MAX_FILE_BYTES, MAX_INDEX_FILES, MAX_CONTEXT_CHARS,
    DANGEROUS_PATTERNS, SYSTEM_PROMPTS,
)


class TestConfig:
    def test_llama_url_default(self):
        assert "127.0.0.1" in LLAMA_URL or "localhost" in LLAMA_URL

    def test_ignore_dirs_contains_git(self):
        assert ".git" in IGNORE_DIRS

    def test_code_exts_common(self):
        assert ".py" in CODE_EXTS
        assert ".js" in CODE_EXTS
        assert ".ts" in CODE_EXTS

    def test_dangerous_patterns_not_too_broad(self):
        """BUG-25: && and || should NOT be in dangerous patterns."""
        assert "&&" not in DANGEROUS_PATTERNS
        assert "||" not in DANGEROUS_PATTERNS
        # But destructive patterns should still be there
        assert "rm -rf" in DANGEROUS_PATTERNS

    def test_system_prompts_all_modes(self):
        assert "ask" in SYSTEM_PROMPTS
        assert "plan" in SYSTEM_PROMPTS
        assert "craft" in SYSTEM_PROMPTS
        assert "agent" in SYSTEM_PROMPTS

    def test_max_values_reasonable(self):
        assert MAX_FILE_BYTES > 0
        assert MAX_INDEX_FILES > 0
        assert MAX_CONTEXT_CHARS > 0
