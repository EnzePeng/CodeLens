"""Tests for memory service."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.memory import MemoryStore


class TestMemory:
    def test_add_basic(self):
        store = MemoryStore(working_size=3, episodic_max=5)
        store.add(0, "read_file", "result1", True, "thought1")
        assert len(store.working) > 0

    def test_compress_to_episodic(self):
        store = MemoryStore(working_size=1, episodic_max=5)
        store.add(0, "read_file", "result1", True, "thought1")
        store.add(1, "read_file", "result2", True, "thought2")
        # Working should have at most 1 item
        assert len(store.working) <= 1

    def test_get_context_format(self):
        store = MemoryStore(working_size=3, episodic_max=5)
        store.add(0, "read_file", "result1", True, "thought1")
        store.add(1, "write_file", "result2", True, "thought2")
        ctx = store.get_context()
        assert isinstance(ctx, list)

    def test_episodic_max(self):
        store = MemoryStore(working_size=2, episodic_max=2)
        for i in range(10):
            store.add(i, "tool", f"result{i}", True, f"thought{i}")
        assert len(store.episodic) <= 2

    def test_clear(self):
        store = MemoryStore(working_size=3, episodic_max=5)
        store.add(0, "read_file", "result1", True, "thought1")
        store.clear()
        assert len(store.working) == 0
        assert len(store.episodic) == 0
