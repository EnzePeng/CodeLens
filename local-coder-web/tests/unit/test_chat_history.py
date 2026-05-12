"""Tests for chat history service."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.chat_history import ChatHistory, ConversationStore


class TestChatHistory:
    def test_add_message_basic(self):
        ch = ChatHistory()
        ch.add_message("user", "Hello")
        ch.add_message("assistant", "Hi there")
        assert len(ch.messages) == 2  # No system message added automatically

    def test_add_message_system_first(self):
        ch = ChatHistory()
        ch.add_message("user", "Hello")
        ch.add_message("assistant", "Hi")
        ch.add_message("system", "Updated system prompt")
        # System message should be at index 0
        assert ch.messages[0].role == "system"

    def test_add_message_empty_skipped(self):
        ch = ChatHistory()
        ch.add_message("user", "")
        ch.add_message("user", "Hello")
        assert len(ch.messages) == 1  # empty message skipped

    def test_trim_removes_oldest_not_newest(self):
        """BUG-18: Trim should remove oldest messages, not newest."""
        ch = ChatHistory(max_messages=3, max_chars=1000)
        ch.add_message("system", "You are a helper.")
        ch.add_message("user", "msg1")
        ch.add_message("assistant", "resp1")
        ch.add_message("user", "msg2")
        ch.add_message("assistant", "resp2")
        ch.add_message("user", "msg3")
        ch.add_message("assistant", "resp3")
        ch.add_message("user", "msg4")

        # The oldest non-system message should be removed first
        non_system_msgs = [m for m in ch.messages if m.role != "system"]
        # "msg1" (the oldest) should have been trimmed, not "msg4" (newest)
        assert "msg4" in " ".join(m.content for m in non_system_msgs)

    def test_trim_by_char_count(self):
        ch = ChatHistory(max_messages=100, max_chars=50)
        ch.add_message("system", "You are a helper.")
        ch.add_message("user", "This is a very long message that should cause trimming")
        # Should trim down to max_chars
        assert ch._total_chars <= 50 + 20  # +20 for system message

    def test_trim_by_message_count(self):
        ch = ChatHistory(max_messages=2, max_chars=100000)
        ch.add_message("system", "You are a helper.")
        for i in range(10):
            ch.add_message("user", f"msg{i}")
            ch.add_message("assistant", f"resp{i}")
        non_system = [m for m in ch.messages if m.role != "system"]
        assert len(non_system) <= 2

    def test_trim_never_removes_system(self):
        ch = ChatHistory(max_messages=1, max_chars=10)
        ch.add_message("system", "System prompt")
        ch.add_message("user", "x")
        ch.add_message("user", "y")
        # System message should always remain
        system_msgs = [m for m in ch.messages if m.role == "system"]
        assert len(system_msgs) == 1

    def test_get_context_excludes_system(self):
        ch = ChatHistory()
        ch.add_message("system", "System")
        ch.add_message("user", "Hello")
        ch.add_message("assistant", "Hi")
        ctx = ch.get_context()
        roles = [m["role"] for m in ctx]
        assert "system" not in roles

    def test_get_conversation_last_n(self):
        ch = ChatHistory()
        for i in range(10):
            ch.add_message("user", f"msg{i}")
            ch.add_message("assistant", f"resp{i}")
        conv = ch.get_conversation(last_n=4)
        assert len(conv) == 4

    def test_clear_keeps_system(self):
        ch = ChatHistory()
        ch.add_message("system", "System")
        ch.add_message("user", "Hello")
        ch.clear()
        assert len(ch.messages) == 1
        assert ch.messages[0].role == "system"


class TestConversationStore:
    def test_get_or_create(self):
        store = ConversationStore()
        h1 = store.get_or_create("s1")
        h2 = store.get_or_create("s1")
        assert h1 is h2

    def test_create_new(self):
        store = ConversationStore()
        h1 = store.get_or_create("s1")
        h2 = store.get_or_create("s2")
        assert h1 is not h2

    def test_get_empty(self):
        store = ConversationStore()
        assert store.get("nonexistent") == []
