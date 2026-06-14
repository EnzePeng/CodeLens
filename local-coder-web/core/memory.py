"""
HierarchicalMemory — 三层结构化记忆，供 Agent 引擎使用。

三层：
  working   — 当前（子）任务的近期消息，容量有限
  episodic  — 已完成子任务的结构化摘要，用于跨任务上下文延续
  semantic  — 从 episodic 提炼出的核心发现，用于最终报告拼装

与 services/memory.py（通用 MemoryStore）的关系：
  本模块是 agent 专用版，提供更丰富的结构；services/memory.py 保留不动。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SubTaskResult:
    """一个子任务的执行结果（结构化）。"""
    subtask_id: str
    description: str
    status: Literal["success", "partial", "failed"]
    summary: str = ""
    findings: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    error: str | None = None
    duration_s: float = 0.0
    finished_at: float = field(default_factory=time.time)


@dataclass
class _WorkingEntry:
    role: str
    content: str
    kind: str = "message"   # message | tool_result | system_hint
    timestamp: float = field(default_factory=time.time)


class HierarchicalMemory:
    """
    三层记忆。

    参数
    ----
    working_size
        working 层最多保留多少条消息。超出时最早的走 summarization（由调用方驱动），
        本类本身只做裁剪。
    max_findings_per_subtask
        每个子任务最多保留多少条 findings。
    """

    def __init__(
        self,
        working_size: int = 8,
        max_findings_per_subtask: int = 8,
    ) -> None:
        self.working_size = working_size
        self.max_findings_per_subtask = max_findings_per_subtask

        self._working: list[_WorkingEntry] = []
        self._episodic: dict[str, SubTaskResult] = {}
        self._episodic_order: list[str] = []  # 按完成时间排序
        self._semantic: list[str] = []        # 核心发现（扁平）

        # 当前活跃子任务 ID（可选）
        self._active_subtask: str | None = None

        # 跨子任务统计，用于 work_summary
        self._files_read_all: list[str] = []
        self._files_written_all: list[str] = []
        self._searches_all: list[str] = []
        self._commands_all: list[str] = []

    # ---- working 层 ----

    def add_working(
        self,
        role: str,
        content: str,
        kind: str = "message",
    ) -> None:
        self._working.append(_WorkingEntry(role=role, content=content, kind=kind))
        overflow = len(self._working) - self.working_size
        if overflow > 0:
            # 旧的 working 条目被丢弃。调用方应在丢弃前通过
            # summarize_working_older() 把信息压缩到 episodic/semantic。
            self._working = self._working[overflow:]

    def get_working(self) -> list[dict[str, str]]:
        """按原始格式返回，便于拼到 messages 里。"""
        return [{"role": e.role, "content": e.content} for e in self._working]

    def clear_working(self) -> None:
        self._working.clear()

    # ---- 活跃子任务 ----

    def set_active_subtask(self, subtask_id: str) -> None:
        self._active_subtask = subtask_id
        self.clear_working()

    @property
    def active_subtask(self) -> str | None:
        return self._active_subtask

    # ---- episodic 层 ----

    def complete_subtask(
        self,
        subtask_id: str,
        description: str,
        *,
        status: Literal["success", "partial", "failed"] = "success",
        summary: str = "",
        findings: list[str] | None = None,
        files_read: list[str] | None = None,
        files_written: list[str] | None = None,
        tools_used: list[str] | None = None,
        error: str | None = None,
        duration_s: float = 0.0,
    ) -> SubTaskResult:
        """记录一个子任务完成。同时把它的统计数据累加到全局统计。"""
        findings = (findings or [])[: self.max_findings_per_subtask]
        result = SubTaskResult(
            subtask_id=subtask_id,
            description=description,
            status=status,
            summary=summary,
            findings=findings,
            files_read=list(files_read or []),
            files_written=list(files_written or []),
            tools_used=list(tools_used or []),
            error=error,
            duration_s=duration_s,
        )
        self._episodic[subtask_id] = result
        if subtask_id not in self._episodic_order:
            self._episodic_order.append(subtask_id)

        # 累计全局统计
        for p in result.files_read:
            if p not in self._files_read_all:
                self._files_read_all.append(p)
        for p in result.files_written:
            if p not in self._files_written_all:
                self._files_written_all.append(p)

        if self._active_subtask == subtask_id:
            self._active_subtask = None
            self.clear_working()
        return result

    def get_subtask_result(self, subtask_id: str) -> SubTaskResult | None:
        return self._episodic.get(subtask_id)

    def iter_subtask_results(self) -> list[SubTaskResult]:
        return [self._episodic[sid] for sid in self._episodic_order if sid in self._episodic]

    # ---- semantic 层 ----

    def add_finding(self, finding: str) -> None:
        """直接往 semantic 层追加一条核心发现。"""
        if finding and finding not in self._semantic:
            self._semantic.append(finding)

    def promote_subtask(self, subtask_id: str) -> None:
        """把子任务的 findings 合并到 semantic 层。"""
        res = self._episodic.get(subtask_id)
        if not res:
            return
        for f in res.findings:
            self.add_finding(f)

    # ---- 全局统计（用于 record_work_detail 风格摘要）----

    def record_tool_use(self, tool_name: str, args: dict[str, Any]) -> None:
        """记录工具使用到全局统计（用于 work_summary）。"""
        if tool_name == "read_file":
            p = args.get("path", "")
            if p and p not in self._files_read_all:
                self._files_read_all.append(p)
        elif tool_name in ("write_file", "edit_file", "apply_diff"):
            p = args.get("path", "")
            if p and p not in self._files_written_all:
                self._files_written_all.append(p)
        elif tool_name == "search_files" or tool_name == "grep":
            pat = args.get("pattern", "")
            if pat:
                self._searches_all.append(pat)
        elif tool_name == "run_command":
            cmd = args.get("command", "")
            if cmd:
                self._commands_all.append(cmd[:80])

    # ---- 渲染（输出给 prompt）----

    def render_work_summary(self, max_chars: int = 1500) -> str:
        """生成'已完成的工作'的结构化摘要，作为固定槽位插入上下文。"""
        parts: list[str] = []

        if self._episodic:
            done_count = sum(1 for r in self._episodic.values() if r.status == "success")
            failed_count = sum(1 for r in self._episodic.values() if r.status == "failed")
            partial_count = sum(1 for r in self._episodic.values() if r.status == "partial")
            parts.append(f"已完成子任务: {done_count} 成功 / {partial_count} 部分 / {failed_count} 失败 (共 {len(self._episodic)})")
            # 每个子任务一句话摘要
            for sid in self._episodic_order[-6:]:
                r = self._episodic.get(sid)
                if not r:
                    continue
                status_mark = {"success": "✓", "partial": "△", "failed": "✗"}[r.status]
                head = r.description[:60].replace("\n", " ")
                parts.append(f"  [{status_mark}] {head}")

        if self._files_read_all:
            uniq = list(dict.fromkeys(self._files_read_all))
            if len(uniq) <= 5:
                parts.append(f"已读取文件: {', '.join(uniq)}")
            else:
                parts.append(f"已读取 {len(uniq)} 个文件: {', '.join(uniq[:4])} 等")

        if self._files_written_all:
            uniq = list(dict.fromkeys(self._files_written_all))
            parts.append(f"已修改文件: {', '.join(uniq)}")

        if self._searches_all:
            uniq = list(dict.fromkeys(self._searches_all))[-5:]
            parts.append(f"已搜索: {', '.join(uniq)}")

        if self._commands_all:
            parts.append(f"已执行 {len(self._commands_all)} 个命令")

        if self._semantic:
            parts.append("核心发现:")
            for f in self._semantic[-6:]:
                parts.append(f"  - {f[:120]}")

        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        return text

    def render_episodic_digest(self, max_chars: int = 2000) -> str:
        """把所有子任务结果渲染成一段紧凑的 digest（用于最终报告拼装或上下文）。"""
        if not self._episodic:
            return ""
        chunks: list[str] = []
        for sid in self._episodic_order:
            r = self._episodic.get(sid)
            if not r:
                continue
            head = f"[{r.status.upper()}] {r.description[:80]}"
            body_lines = [head]
            if r.summary:
                body_lines.append(f"  摘要: {r.summary[:200]}")
            if r.findings:
                body_lines.append("  发现:")
                for f in r.findings[:4]:
                    body_lines.append(f"    - {f[:120]}")
            if r.error:
                body_lines.append(f"  错误: {r.error[:120]}")
            chunks.append("\n".join(body_lines))
        text = "\n\n".join(chunks)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        return text
