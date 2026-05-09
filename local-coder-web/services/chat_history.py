"""
Chat History service — cross-session context management.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChatMessage:
    role: str        # "system", "user", "assistant"
    content: str
    mode: str = "ask"  # "ask", "plan", "craft", "agent"
    timestamp: float = 0.0


class ChatHistory:
    """Conversation history manager with size-based trimming."""

    def __init__(self, max_messages: int = 50, max_chars: int = 100_000):
        self.messages: list[ChatMessage] = []
        self.max_messages = max_messages
        self.max_chars = max_chars
        self._total_chars = 0

    def add_message(self, role: str, content: str, mode: str = "ask") -> None:
        if not content:
            return
        msg = ChatMessage(role=role, content=content, mode=mode, timestamp=__import__("time").time())
        # System messages are never trimmed
        if role == "system":
            self.messages.insert(0, msg)
        else:
            self.messages.append(msg)
        self._total_chars += len(content)
        self._trim()

    def _trim(self) -> None:
        """Trim oldest non-system messages if over limits."""
        # Trim by char count
        while self._total_chars > self.max_chars and len(self.messages) > 1:
            # Find last non-system message
            for i in range(len(self.messages) - 1, -1, -1):
                if self.messages[i].role != "system":
                    self._total_chars -= len(self.messages[i].content)
                    del self.messages[i]
                    break

        # Trim by message count
        while len(self.messages) > self.max_messages + 1:  # +1 for system
            for i in range(len(self.messages) - 1, -1, -1):
                if self.messages[i].role != "system":
                    del self.messages[i]
                    break

    def get_context(self) -> list[dict]:
        """Return messages as API-compatible format."""
        return [
            {"role": m.role, "content": m.content, "mode": m.mode}
            for m in self.messages if m.role != "system"
        ]

    def get_conversation(self, last_n: int = 20) -> list[dict]:
        """Return last N user/assistant messages."""
        return [
            {"role": m.role, "content": m.content}
            for m in self.messages[-last_n:] if m.role in ("user", "assistant")
        ]

    def estimate_cost(self) -> int:
        """Estimate current history char count."""
        return self._total_chars

    def clear(self) -> None:
        """Remove all messages except system."""
        system_msgs = [m for m in self.messages if m.role == "system"]
        self.messages = system_msgs
        self._total_chars = sum(len(m.content) for m in system_msgs)


# Global chat history per conversation
class ConversationStore:
    """Store multiple conversations keyed by session ID."""

    def __init__(self):
        self._stores: dict[str, ChatHistory] = {}

    def get_or_create(self, session_id: str) -> ChatHistory:
        if session_id not in self._stores:
            self._stores[session_id] = ChatHistory()
        return self._stores[session_id]

    def add(self, session_id: str, role: str, content: str, mode: str = "ask") -> None:
        history = self.get_or_create(session_id)
        history.add_message(role, content, mode)

    def get(self, session_id: str, last_n: int = 20) -> list[dict]:
        history = self._stores.get(session_id)
        if history:
            return history.get_conversation(last_n)
        return []


# Singleton
conversation_store = ConversationStore()
