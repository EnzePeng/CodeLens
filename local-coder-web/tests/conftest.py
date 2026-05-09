"""
Pytest configuration and fixtures for local-coder-web tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def app_dir() -> Path:
    """Return the application directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def sample_code() -> str:
    """Return sample Python code for testing."""
    return '''
def hello():
    """Say hello."""
    print("Hello, World!")
    return True


class Calculator:
    """Simple calculator class."""
    
    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    
    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        return a - b
'''


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    
    # Create sample files
    (repo / "main.py").write_text("def main(): pass\n")
    (repo / "utils.py").write_text("def util(): pass\n")
    
    # Create subdirectory with files
    subdir = repo / "src"
    subdir.mkdir()
    (subdir / "module.py").write_text("class Module: pass\n")
    
    return repo