"""
ContextWindow — 槽位式上下文窗口管理。

设计原则
--------
- 上下文被划分为固定槽位：
    [system, user_query, work_summary, recent_N_messages]
- system 和 user_query 永不截断
- work_summary 由 HierarchicalMemory.render_work_summary() 生成
- recent_N_messages 超出时，旧消息走 summarize（调用方负责），本类仅做容量控制

本类不依赖 LLM 做压缩；压缩/摘要在调用方（engine/react）中完成。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from logger import logger


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（按字符数 / 3）。适合中英混合文本。"""
    return max(1, len(text) // 3)


@dataclass
class _Slot:
    role: str
    content: str
    kind: str = "message"    # system | user_query | work_summary | message | summary
    pinned: bool = False     # 被钉住的消息不会被裁剪
    token_estimate: int = 0

    def __post_init__(self):
        self.token_estimate = estimate_tokens(self.content)


class ContextWindow:
    """
    固定槽位式上下文窗口。

    参数
    ----
    max_tokens
        上下文总 token 上限（应预留模型输出空间）。
    recent_n
        最近保留多少条 working 消息；超出时旧的走压缩路径。
    system_reserve_tokens
        预留给 system + user_query + work_summary 的 token 数；
        剩余预算才分给 recent 消息。
    """

    def __init__(
        self,
        max_tokens: int = 24000,
        recent_n: int = 8,
        system_reserve_tokens: int = 4000,
    ) -> None:
        self.max_tokens = max_tokens
        self.recent_n = recent_n
        self.system_reserve_tokens = system_reserve_tokens

        # 四个固定槽位
        self._system: _Slot | None = None
        self._user_query: _Slot | None = None
        self._work_summary: _Slot | None = None
        self._messages: list[_Slot] = []    # 最近 N 条 working 消息
        self._summaries: list[_Slot] = []   # 历史消息被压缩后的摘要

    # ---- 槽位设置 ----

    def set_system(self, content: str) -> None:
        self._system = _Slot(role="system", content=content, kind="system", pinned=True)

    def set_user_query(self, content: str) -> None:
        self._user_query = _Slot(role="user", content=content, kind="user_query", pinned=True)

    def set_work_summary(self, content: str) -> None:
        if not content:
            self._work_summary = None
            return
        full = f"已完成的工作摘要:\n{content}"
        self._work_summary = _Slot(role="user", content=full, kind="work_summary", pinned=True)

    # ---- working 消息管理 ----

    def append_message(self, role: str, content: str, kind: str = "message") -> None:
        self._messages.append(_Slot(role=role, content=content, kind=kind))

    def append_summary(self, content: str) -> None:
        """把一组旧消息的摘要作为一条 summary 消息追加。"""
        if not content:
            return
        self._summaries.append(
            _Slot(role="user", content=content, kind="summary")
        )

    def recent_messages(self) -> list[dict[str, str]]:
        """返回最近 recent_n 条 working 消息（OpenAI messages 格式）。"""
        tail = self._messages[-self.recent_n :]
        return [{"role": s.role, "content": s.content} for s in tail]

    def pop_oldest_messages(self, n: int) -> list[dict[str, str]]:
        """弹出最旧的 N 条 working 消息，供调用方拿去压缩。"""
        if n <= 0 or not self._messages:
            return []
        n = min(n, len(self._messages))
        popped = self._messages[:n]
        self._messages = self._messages[n:]
        return [{"role": s.role, "content": s.content} for s in popped]

    @property
    def message_count(self) -> int:
        return len(self._messages)

    # ---- 预算计算 ----

    def _pinned_tokens(self) -> int:
        total = 0
        if self._system:
            total += self._system.token_estimate
        if self._user_query:
            total += self._user_query.token_estimate
        if self._work_summary:
            total += self._work_summary.token_estimate
        for s in self._summaries:
            total += s.token_estimate
        return total

    def remaining_budget(self) -> int:
        return max(0, self.max_tokens - self._pinned_tokens())

    # ---- 渲染 ----

    def render(self) -> list[dict[str, str]]:
        """
        输出最终 messages，顺序：
          system → user_query → [summaries...] → work_summary → [recent messages]
        """
        out: list[dict[str, str]] = []
        if self._system:
            out.append({"role": self._system.role, "content": self._system.content})
        if self._user_query:
            out.append({"role": self._user_query.role, "content": self._user_query.content})
        for s in self._summaries:
            out.append({"role": s.role, "content": s.content})
        if self._work_summary:
            out.append({"role": self._work_summary.role, "content": self._work_summary.content})
        for s in self._messages[-self.recent_n :]:
            out.append({"role": s.role, "content": s.content})
        return out

    # ---- 溢出处理 ----

    def needs_compression(self) -> bool:
        total = self._pinned_tokens()
        for s in self._messages[-self.recent_n :]:
            total += s.token_estimate
        return total > self.max_tokens

    def excess_message_count(self) -> int:
        """超过 recent_n 的消息数量 — 这些消息应该被压缩。"""
        return max(0, len(self._messages) - self.recent_n)

    def total_tokens_estimate(self) -> int:
        total = self._pinned_tokens()
        for s in self._messages:
            total += s.token_estimate
        return total

    # ---- 工具 ----

    def stats(self) -> dict:
        return {
            "max_tokens": self.max_tokens,
            "pinned_tokens": self._pinned_tokens(),
            "message_count": len(self._messages),
            "summary_count": len(self._summaries),
            "total_tokens_estimate": self.total_tokens_estimate(),
            "has_system": self._system is not None,
            "has_user_query": self._user_query is not None,
            "has_work_summary": self._work_summary is not None,
        }


def build_summary_message(messages: list[dict[str, str]], header: str = "之前的上下文摘要:") -> str:
    """
    把一组旧消息（OpenAI messages 格式）压成一条 summary 消息的文本。

    不做 LLM 调用；只做结构化抽取：
      - 识别 tool result 消息，保留工具名和前 300 字符结果
      - 保留 user/assistant 消息的前 200 字符
      - 末尾加上"请勿重复执行"的提示
    """
    import re
    if not messages:
        return ""

    parts: list[str] = [header]
    for m in messages:
        content = m.get("content", "")
        role = m.get("role", "user")
        if not content:
            continue

        # 工具结果消息：形如 "Tool read_file result:\n..."
        tool_match = re.search(r"Tool\s+(\w+)\s+result:", content)
        if tool_match:
            tool_name = tool_match.group(1)
            # 跳过首行标题
            body = content.split("\n", 1)[-1] if "\n" in content else content
            preview = body[:300].replace("\n", " ").strip()
            parts.append(f"  - [{tool_name}] {preview}")
            continue

        # 普通消息
        preview = content[:200].replace("\n", " ").strip()
        parts.append(f"  - {role}: {preview}")

    parts.append("")
    parts.append("重要: 以上信息已压缩。如需详细内容，请重新读取相关文件。请勿重复执行上述已完成的操作。")
    return "\n".join(parts)
