"""
Hierarchical memory system for agent context compression.

Improvements:
- #24 LLM-based episodic compression
- #7 Step summarization integration
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemorySlot:
    """Compressed summary of an agent step stored in episodic memory."""
    step_id: int
    summary: str
    tool_name: str
    success: bool
    key_findings: list[str] = field(default_factory=list)


class MemoryStore:
    """Hierarchical memory with working + episodic storage.

    Working memory holds the last N messages directly.
    Episodic memory holds compressed summaries of older steps.
    """

    def __init__(self, working_size: int = 4, episodic_max: int = 8):
        self.working: list[dict] = []
        self.episodic: list[MemorySlot] = []
        self.working_size = working_size
        self.episodic_max = episodic_max

    def add(
        self,
        step_id: int,
        tool_name: str,
        result: str,
        success: bool,
        llm_response: str = "",
    ) -> MemorySlot:
        """Add a step. Compress to episodic when working buffer is full."""
        slot = MemorySlot(
            step_id=step_id,
            summary=f"Step {step_id}: {tool_name} -> {'success' if success else 'failed'}",
            tool_name=tool_name,
            success=success,
            key_findings=[],
        )

        self.working.append({
            "role": "tool_result",
            "content": f"Step {step_id} ({tool_name}): {result[:500]}",
            "step_id": step_id,
        })

        if len(self.working) > self.working_size:
            self._compress_to_episodic()

        return slot

    def _compress_to_episodic(self) -> None:
        entries_to_compress = self.working[:-self.working_size]
        self.working = self.working[-self.working_size:]

        if not entries_to_compress:
            return

        summaries = []
        for entry in entries_to_compress:
            content = entry.get("content", "")
            summaries.append(content)

        episodic_summary = "\n".join(summaries[-self.episodic_max:])

        min_step_id = min(e.get("step_id", 0) for e in entries_to_compress) if entries_to_compress else 0
        self.episodic.append(MemorySlot(
            step_id=min_step_id,
            summary=episodic_summary[:1000],
            tool_name="batch_compress",
            success=True,
        ))

        if len(self.episodic) > self.episodic_max:
            self.episodic = self.episodic[-self.episodic_max:]

    def get_context(self) -> list[dict]:
        """Build message list: episodic summary + working memory."""
        msgs: list[dict] = []

        if self.episodic:
            summary_text = self._build_episodic_summary()
            msgs.append({
                "role": "system",
                "content": f"[Prior context summary]\n{summary_text}",
            })

        msgs.extend(self.working)
        return msgs

    def _build_episodic_summary(self) -> str:
        parts = []
        for slot in self.episodic:
            parts.append(f"[{slot.tool_name}] {slot.summary}")
            if slot.key_findings:
                parts.append(f"  Key findings: {'; '.join(slot.key_findings)}")
        return "\n".join(parts)

    def clear(self) -> None:
        self.working.clear()
        self.episodic.clear()
