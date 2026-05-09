"""
Logging configuration for local-coder-web.
统一日志格式和级别管理。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

# Default log level
LOG_LEVEL = logging.INFO

# Log format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str,
    level: int = LOG_LEVEL,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """Create and configure a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)
        log_file: Optional file path for file logging
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


# Default application logger
logger = setup_logger("local-coder-web")


# Convenience functions
def debug(msg: str) -> None:
    """Log debug message."""
    logger.debug(msg)


def info(msg: str) -> None:
    """Log info message."""
    logger.info(msg)


def warning(msg: str) -> None:
    """Log warning message."""
    logger.warning(msg)


def error(msg: str, exc_info: bool = False) -> None:
    """Log error message."""
    logger.error(msg, exc_info=exc_info)


def critical(msg: str) -> None:
    """Log critical message."""
    logger.critical(msg)