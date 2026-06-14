"""
ReportAggregator — 把多个子任务结果聚合成最终报告。

两种模式：
  - 拼接模式（默认）：按子任务顺序拼装 summary + findings，前加 TOC。省 token，可预测。
  - LLM 综合模式：当子任务数 ≤ max_llm_synthesis 时，让 LLM 写一段综合洞察。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from logger import logger


@dataclass
class AggregateConfig:
    max_llm_synthesis_subtasks: int = 6   # ≤ 该数才走 LLM 综合
    max_per_subtask_chars: int = 2500     # 每个子任务结果最多保留多少字符
    max_total_chars: int = 25000          # 最终报告总字符上限


class ReportAggregator:
    """
    报告聚合器。

    典型用法：
        agg = ReportAggregator()
        report = await agg.aggregate(query, subtask_results, mode="auto")
    """

    def __init__(self, config: AggregateConfig | None = None) -> None:
        self.config = config or AggregateConfig()

    async def aggregate(
        self,
        query: str,
        subtask_results: list,  # list[SubTaskResult]
        *,
        mode: Literal["auto", "concat", "llm"] = "auto",
    ) -> str:
        """
        聚合子任务结果。

        mode
          auto    - 子任务数 ≤ max_llm_synthesis_subtasks 时走 llm，否则 concat
          concat  - 纯拼接（推荐用于多文件分析报告）
          llm     - 强制走 LLM 综合（失败时回退到 concat）
        """
        if not subtask_results:
            return "没有子任务结果可聚合。"

        chosen = mode
        if mode == "auto":
            chosen = "llm" if len(subtask_results) <= self.config.max_llm_synthesis_subtasks else "concat"

        if chosen == "llm":
            try:
                return await self._aggregate_with_llm(query, subtask_results)
            except Exception as e:
                logger.warning(f"[Aggregator] LLM 综合失败，回退到拼接: {e}")
                return self._aggregate_concat(query, subtask_results)

        return self._aggregate_concat(query, subtask_results)

    # ---- 拼接模式 ----

    def _aggregate_concat(self, query: str, subtask_results: list) -> str:
        success = [r for r in subtask_results if r.status == "success"]
        partial = [r for r in subtask_results if r.status == "partial"]
        failed = [r for r in subtask_results if r.status == "failed"]

        lines: list[str] = []
        lines.append(f"# 任务报告")
        lines.append("")
        lines.append(f"**原始任务**: {query}")
        lines.append("")
        lines.append(f"**执行统计**: 共 {len(subtask_results)} 个子任务 — "
                     f"{len(success)} 成功 / {len(partial)} 部分 / {len(failed)} 失败")
        lines.append("")

        # TOC
        lines.append("## 目录")
        for i, r in enumerate(subtask_results, 1):
            status_mark = {"success": "✓", "partial": "△", "failed": "✗"}[r.status]
            lines.append(f"{i}. [{status_mark}] {r.description[:80]}")
        lines.append("")

        # 每个子任务详情
        lines.append("## 详细报告")
        lines.append("")
        per_cap = self.config.max_per_subtask_chars
        for i, r in enumerate(subtask_results, 1):
            block: list[str] = []
            status_label = {"success": "成功", "partial": "部分完成", "failed": "失败"}[r.status]
            block.append(f"### {i}. {r.description[:80]}")
            block.append(f"_状态: {status_label}_ · _耗时: {r.duration_s:.1f}s_")
            block.append("")

            if r.files_read:
                block.append(f"**涉及文件**: {', '.join(r.files_read)}")
                block.append("")

            if r.summary:
                block.append("#### 摘要")
                block.append(r.summary.strip()[:per_cap])
                block.append("")

            if r.findings:
                block.append("#### 发现 / 问题")
                for f in r.findings:
                    block.append(f"- {f[:300]}")
                block.append("")

            if r.error:
                block.append(f"**错误**: {r.error[:300]}")
                block.append("")

            lines.append("\n".join(block))
            lines.append("---")
            lines.append("")

        # 汇总 findings
        all_findings: list[tuple[str, str]] = []
        for r in subtask_results:
            for f in r.findings:
                all_findings.append((r.description[:40], f))
        if all_findings:
            lines.append("## 总体发现汇总")
            lines.append("")
            for src, finding in all_findings[:30]:
                lines.append(f"- **[{src}]** {finding[:200]}")
            lines.append("")

        report = "\n".join(lines)
        if len(report) > self.config.max_total_chars:
            report = report[: self.config.max_total_chars].rstrip() + "\n\n_(报告过长，已截断)_"
        return report

    # ---- LLM 综合模式 ----

    async def _aggregate_with_llm(self, query: str, subtask_results: list) -> str:
        from core.llm_client import llm_client

        digest_lines: list[str] = []
        for i, r in enumerate(subtask_results, 1):
            status_label = {"success": "成功", "partial": "部分", "failed": "失败"}[r.status]
            head = f"[{i}] {r.description[:80]} ({status_label})"
            body = []
            if r.summary:
                body.append(f"摘要: {r.summary[:300]}")
            if r.findings:
                body.append("发现: " + "; ".join(f[:120] for f in r.findings[:4]))
            if r.files_read:
                body.append("文件: " + ", ".join(r.files_read))
            if r.error:
                body.append(f"错误: {r.error[:200]}")
            digest_lines.append(f"{head}\n  " + "\n  ".join(body))

        digest = "\n\n".join(digest_lines)
        if len(digest) > 8000:
            digest = digest[:8000].rstrip() + "..."

        prompt = f"""你是一个代码分析专家。请基于以下子任务执行结果，写一份综合报告。

原始任务: {query}

子任务结果:
{digest}

要求:
- 使用中文
- 结构清晰，包含: 概述、每个模块/文件的核心功能、发现的问题与风险、总体建议
- 每个部分有具体细节，不要泛泛而谈
- 控制在 2000 字以内

输出 Markdown 格式报告:"""

        try:
            resp = await llm_client.call(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.3,
                task_type="agent",
            )
            content = (resp.content or "").strip()
            if not content:
                raise ValueError("LLM 返回空内容")
            return content
        except Exception as e:
            logger.warning(f"[Aggregator] LLM 综合失败: {e}")
            raise
