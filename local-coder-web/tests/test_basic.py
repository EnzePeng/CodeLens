"""
Basic tests for local-coder-web.
验证 FastAPI 启动和基础端点。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_imports():
    """Test that all core modules can be imported."""
    import config
    import logger
    import exceptions
    import settings
    
    assert config.APP_DIR is not None
    assert logger.logger is not None
    assert settings.settings is not None


def test_config_constants():
    """Test configuration constants are properly defined."""
    import config
    
    assert config.MAX_FILE_BYTES > 0
    assert config.MAX_INDEX_FILES > 0
    assert config.MAX_CONTEXT_CHARS > 0
    assert config.BM25_K1 > 0
    assert config.BM25_B > 0
    assert len(config.CODE_EXTS) > 0
    assert len(config.IGNORE_DIRS) > 0


def test_system_prompts():
    """Test that all mode prompts are defined."""
    import config
    
    assert "ask" in config.SYSTEM_PROMPTS
    assert "plan" in config.SYSTEM_PROMPTS
    assert "craft" in config.SYSTEM_PROMPTS
    assert "agent" in config.SYSTEM_PROMPTS
    
    for mode, prompt in config.SYSTEM_PROMPTS.items():
        assert len(prompt) > 0, f"Empty prompt for mode: {mode}"


def test_settings():
    """Test settings loader."""
    import settings
    
    assert settings.settings is not None
    assert settings.settings.llama_url is not None
    assert settings.settings.log_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def test_exceptions():
    """Test custom exception classes."""
    import exceptions
    
    # Test base exception
    with pytest.raises(exceptions.CodeLensError):
        raise exceptions.CodeLensError("test")
    
    # Test specific exceptions
    with pytest.raises(exceptions.SecurityError):
        raise exceptions.SecurityError("path traversal")
    
    with pytest.raises(exceptions.AgentError):
        raise exceptions.AgentError("agent failed")


def test_logger():
    """Test logger configuration."""
    import logger
    
    # Test logger has handlers
    assert len(logger.logger.handlers) > 0
    
    # Test logging functions don't raise
    logger.debug("debug test")
    logger.info("info test")
    logger.warning("warning test")
    logger.error("error test")
    logger.critical("critical test")


def test_bm25_params():
    """Test BM25 parameters are valid."""
    import config
    
    assert 0 < config.BM25_K1 < 10
    assert 0 < config.BM25_B < 1


def test_code_exts():
    """Test CODE_EXTS contains common extensions."""
    import config
    
    assert ".py" in config.CODE_EXTS
    assert ".js" in config.CODE_EXTS
    assert ".ts" in config.CODE_EXTS
    assert ".java" in config.CODE_EXTS


def test_ignore_dirs():
    """Test IGNORE_DIRS contains common directories."""
    import config
    
    assert ".git" in config.IGNORE_DIRS
    assert "node_modules" in config.IGNORE_DIRS
    assert "__pycache__" in config.IGNORE_DIRS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])