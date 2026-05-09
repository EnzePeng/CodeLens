"""
Tests for the chat history service.
"""
from __future__ import annotations

import pytest

from services.chat_history import ChatHistory, ConversationStore


class TestChatHistory:
    """Test ChatHistory class."""

    def test_add_message(self):
        history = ChatHistory()
        history.add_message("user", "hello", "ask")
        history.add_message("assistant", "hi there", "ask")
        assert len(history.messages) == 2

    def test_system_message_not_trimmed(self):
        history = ChatHistory(max_messages=2, max_chars=50)
        history.add_message("system", "You are helpful", "ask")
        history.add_message("user", "very long message that exceeds the character limit significantly more than expected", "ask")
        history.add_message("assistant", "response", "ask")
        # System message should remain
        roles = [m.role for m in history.messages]
        assert "system" in roles

    def test_char_limit_trimming(self):
        history = ChatHistory(max_chars=50, max_messages=100)
        history.add_message("user", "first very long message that takes up a lot of space", "ask")
        history.add_message("assistant", "second message", "ask")
        # After adding second message, the first should be trimmed if over limit
        total_chars = history.estimate_cost()
        assert total_chars <= history.max_chars + len("second message")  # Allow some slack for the last addition

    def test_max_messages_trimming(self):
        history = ChatHistory(max_messages=3, max_chars=100000)
        history.add_message("user", "msg1", "ask")
        history.add_message("assistant", "msg2", "ask")
        history.add_message("user", "msg3", "ask")
        history.add_message("assistant", "msg4", "ask")
        # Should have at most 3 messages + 1 system
        assert len(history.messages) <= 4  # 3 user/assistant + 1 system

    def test_get_conversation(self):
        history = ChatHistory()
        history.add_message("system", "be helpful", "ask")
        history.add_message("user", "hello", "ask")
        history.add_message("assistant", "hi", "ask")
        conv = history.get_conversation()
        roles = [m["role"] for m in conv]
        assert "system" not in roles
        assert "user" in roles
        assert "assistant" in roles

    def test_clear(self):
        history = ChatHistory()
        history.add_message("system", "be helpful", "ask")
        history.add_message("user", "hello", "ask")
        history.clear()
        roles = [m.role for m in history.messages]
        assert roles == ["system"]

    def test_empty_message_ignored(self):
        history = ChatHistory()
        history.add_message("user", "", "ask")
        assert len(history.messages) == 0


class TestConversationStore:
    """Test ConversationStore class."""

    def test_create_new_conversation(self):
        store = ConversationStore()
        history = store.get_or_create("session1")
        assert isinstance(history, ChatHistory)

    def test_separate_conversations(self):
        store = ConversationStore()
        store.add("session1", "user", "hello from s1", "ask")
        store.add("session2", "user", "hello from s2", "ask")
        s1_messages = store.get("session1")
        s2_messages = store.get("session2")
        assert len(s1_messages) == 1
        assert s1_messages[0]["content"] == "hello from s1"
        assert s2_messages[0]["content"] == "hello from s2"

    def test_returns_empty_for_unknown_session(self):
        store = ConversationStore()
        assert store.get("unknown_session") == []
