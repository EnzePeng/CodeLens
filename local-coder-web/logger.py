"""
Logging configuration for local-coder-web.

Improvements:
- #92 Structured JSON logging
- #93 Log file rotation
- #94 Debug mode with request tracing
"""
from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str,
    level: int = LOG_LEVEL,
    log_file: Optional[Path] = None,
    structured: bool = False,
) -> logging.Logger:
    """Create and configure a logger instance.

    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)
        log_file: Optional file path for file logging
        structured: Use JSON formatting for log file
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    # File handler with rotation (#93)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Default application logger
logger = setup_logger("codelens", log_file=Path.home() / ".codelens" / "codelens.log")


# Convenience functions
def debug(msg: str) -> None:
    logger.debug(msg)

def info(msg: str) -> None:
    logger.info(msg)

def warning(msg: str) -> None:
    logger.warning(msg)

def error(msg: str, exc_info: bool = False) -> None:
    logger.error(msg, exc_info=exc_info)

def critical(msg: str) -> None:
    logger.critical(msg)
