"""
Settings loader for local-coder-web.
从环境变量和 .env 文件加载配置。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Try to load .env file if exists
def _load_env_file() -> None:
    """Load .env file if present."""
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

_load_env_file()


class Settings:
    """Application settings loaded from environment variables."""
    
    # LLM settings
    llama_url: str = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080/v1/chat/completions")
    
    # Logging
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")
    
    # Optional features
    use_onnx: bool = os.environ.get("USE_ONNX", "").lower() in ("true", "1", "yes")
    
    # Server
    host: str = os.environ.get("HOST", "127.0.0.1")
    port: int = int(os.environ.get("PORT", "8765"))
    
    # Agent settings
    agent_max_steps: int = int(os.environ.get("AGENT_MAX_STEPS", "15"))
    agent_timeout: int = int(os.environ.get("AGENT_TIMEOUT", "60"))
    
    # Context settings
    max_context_chars: int = int(os.environ.get("MAX_CONTEXT_CHARS", "42000"))
    max_file_bytes: int = int(os.environ.get("MAX_FILE_BYTES", "220000"))
    max_index_files: int = int(os.environ.get("MAX_INDEX_FILES", "5000"))
    
    # Security
    allow_git_push: bool = os.environ.get("ALLOW_GIT_PUSH", "false").lower() in ("true", "1", "yes")
    allow_dangerous_commands: bool = os.environ.get("ALLOW_DANGEROUS_COMMANDS", "false").lower() in ("true", "1", "yes")
    
    @classmethod
    def get(cls, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get setting by key."""
        return os.environ.get(key, default)
    
    @classmethod
    def set(cls, key: str, value: str) -> None:
        """Set setting (runtime only, not persisted)."""
        os.environ[key] = value


# Global settings instance
settings = Settings()