"""
Tests for the indexer service.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from services.indexer import scan_repo, build_tree, should_read_file
from models import CodeFile


class TestScanRepo:
    """Test repository scanning."""

    def test_scan_creates_cofiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create a test file
            test_file = root / "test.py"
            test_file.write_text("def hello(): pass\n", encoding="utf-8")

            files = scan_repo(root)
            assert len(files) >= 1
            assert any(f.rel == "test.py" for f in files)

    def test_scan_respects_max_index_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create many files
            for i in range(100):
                (root / f"file{i}.py").write_text(f"def f{i}(): pass\n", encoding="utf-8")

            files = scan_repo(root)
            assert len(files) <= 100

    def test_scan_ignores_excluded_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            venv_dir = root / ".venv"
            venv_dir.mkdir()
            (venv_dir / "ignored.py").write_text("# ignored\n", encoding="utf-8")
            (root / "included.py").write_text("# included\n", encoding="utf-8")

            files = scan_repo(root)
            assert len(files) >= 1
            assert not any(".venv" in f.rel for f in files)

    def test_scan_excludes_large_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            big_file = root / "big.py"
            big_file.write_text("x = 1\n" * 50000, encoding="utf-8")  # ~100KB

            files = scan_repo(root)
            assert not any(f.rel == "big.py" for f in files)


class TestBuildTree:
    """Test tree building."""

    def test_build_tree_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "main.py").write_text("# main\n", encoding="utf-8")
            subdir = root / "src"
            subdir.mkdir()
            (subdir / "utils.py").write_text("# utils\n", encoding="utf-8")

            files = scan_repo(root)
            tree = build_tree(root, files)

            assert tree["name"] == root.name
            assert tree["type"] == "dir"
            assert "children" in tree


class TestShouldReadFile:
    """Test file read eligibility."""

    def test_accepts_code_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "test.py").write_text("pass\n", encoding="utf-8")
            assert should_read_file(root / "test.py") is True

    def test_rejects_non_code_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "test.jpg").write_text("binary\n", encoding="utf-8")
            assert should_read_file(root / "test.jpg") is False

    def test_rejects_hidden_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".hidden").write_text("data\n", encoding="utf-8")
            assert should_read_file(root / ".hidden") is False

    def test_hidden_files_filtered(self):
        """Hidden files (except .env.example and .gitignore) should be excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # .hidden file with code extension passes the name check but fails extension
            (root / ".hidden.py").write_text("pass\n", encoding="utf-8")
            # .hidden.py: name starts with . AND not in allowed set → False
            assert should_read_file(root / ".hidden.py") is False
