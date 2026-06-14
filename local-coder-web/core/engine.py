"""
AgentEngine — 任务调度主引擎。

把 TaskRouter、TaskDecomposer、ReActLoop、ReportAggregator 粘合起来，
对外暴露统一的"创建任务 → 流式执行 → 获取状态/结果"接口。

职责
----
- 任务生命周期管理（pending / running / paused / stopped / completed / failed）
- 按路由结果选择执行策略（simple / multi_step / map_reduce）
- 把 ReActEvent 转换为 AgentEvent（与现有前端 SSE 协议兼容）
- 维护 AgentState（与 models.AgentState 保持字段兼容）
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from logger import logger
from models import AgentState, AgentStep


# ---- 阶段/事件 ----

class AgentPhase:
    ROUTING = "routing"
    DECOMPOSING = "decomposing"
    EXECUTING = "executing"
    AGGREGATING = "aggregating"
    DONE = "done"


@dataclass
class AgentEvent:
    """引擎对外输出的统一事件（替代旧的 AgentEvent）。"""
    type: str
    data: Any = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"type": self.type, "data": self.data, "timestamp": self.timestamp}


# ---- 配置 ----

@dataclass
class EngineConfig:
    # map_reduce 并行子任务上限。
    # 本地单 GPU + 单 llama-server 进程实际串行处理请求，
    # 并行只会让请求排队、集体超时。默认 1（串行）最稳定；
    # 多 GPU / 远程多副本部署时可调高。
    max_parallel_subtasks: int = 1
    subtask_context_max_tokens: int = 16000
    root_context_max_tokens: int = 24000


# ---- 内部任务句柄 ----

@dataclass
class _TaskHandle:
    state: AgentState
    memory: Any          # HierarchicalMemory
    context: Any         # ContextWindow
    stop_flag: bool = False
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    max_steps: Optional[int] = None  # optional per-task iteration cap (D6)

    def __post_init__(self):
        self.pause_event.set()  # 初始为非暂停（set = 不阻塞）


# ---- 引擎主体 ----

class AgentEngine:
    """
    Agent 主引擎。

    用法:
        engine = AgentEngine()
        task_id = engine.start_task(query)
        async for event in engine.run_task(task_id):
            # 转 SSE 或直接处理
    """

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        self.config = config or EngineConfig()
        self._handles: dict[str, _TaskHandle] = {}

    # ---- 生命周期 ----

    def start_task(self, query: str, max_steps: Optional[int] = None) -> str:
        from core.memory import HierarchicalMemory
        from core.context import ContextWindow

        task_id = str(uuid.uuid4())[:8]
        agent_state = AgentState(
            task_id=task_id,
            user_query=query,
            status="running",
            created_at=time.time(),
            updated_at=time.time(),
            phase=AgentPhase.ROUTING,
        )
        memory = HierarchicalMemory(working_size=8, max_findings_per_subtask=8)
        context = ContextWindow(
            max_tokens=self.config.root_context_max_tokens,
            recent_n=8,
        )
        # Optional per-task iteration cap. When set, ReAct loops created for
        # this task use min(ReActConfig.max_iterations, max_steps).
        handle = _TaskHandle(state=agent_state, memory=memory, context=context)
        if max_steps is not None and max_steps > 0:
            handle.max_steps = max_steps
        self._handles[task_id] = handle
        logger.info(f"[Engine] Started task {task_id}: {query[:60]}...")
        return task_id

    def get_state(self, task_id: str) -> Optional[AgentState]:
        h = self._handles.get(task_id)
        return h.state if h else None

    def get_all_tasks(self) -> dict[str, AgentState]:
        return {tid: h.state for tid, h in self._handles.items()}

    def stop_task(self, task_id: str, reason: str = "user_stopped") -> bool:
        h = self._handles.get(task_id)
        if not h:
            return False
        h.stop_flag = True
        h.state.status = "stopped"
        h.state.result = reason
        h.state.phase = AgentPhase.DONE
        h.state.updated_at = time.time()
        return True

    def pause_task(self, task_id: str) -> bool:
        h = self._handles.get(task_id)
        if not h or h.state.status != "running":
            return False
        h.state.status = "paused"
        h.pause_event.clear()
        return True

    def resume_task(self, task_id: str) -> bool:
        h = self._handles.get(task_id)
        if not h or h.state.status != "paused":
            return False
        h.state.status = "running"
        h.pause_event.set()
        return True

    # ---- 执行 ----

    async def run_task(self, task_id: str, project_root: Optional[Path] = None) -> AsyncGenerator[AgentEvent, None]:
        """
        执行任务，产出 AgentEvent 流。

        project_root 由调用方（routes/agent.py）从 state.root 取到后传入。
        """
        handle = self._handles.get(task_id)
        if not handle:
            yield AgentEvent(type="error", data={"message": "Task not found"})
            return

        state = handle.state
        memory = handle.memory
        context = handle.context

        try:
            # Step 1: 路由
            yield AgentEvent(type="phase_change", data={"phase": AgentPhase.ROUTING})
            from core.router import TaskRouter
            router = TaskRouter(use_llm=False)
            route = await router.route(state.user_query)
            yield AgentEvent(type="analysis", data={
                "intent_type": route.kind,
                "description": route.reasoning,
                "confidence": 1.0 if route.kind == "map_reduce" else 0.8,
                "subtask_count_hint": route.subtask_count_hint,
            })

            # Step 2: 分解（如果是 map_reduce 或 multi_step）
            subtasks: list = []
            if route.kind in ("map_reduce", "multi_step"):
                yield AgentEvent(type="phase_change", data={"phase": AgentPhase.DECOMPOSING})
                from core.decomposer import TaskDecomposer
                decomposer = TaskDecomposer(use_llm_fallback=(route.kind == "multi_step"))
                subtasks = await decomposer.decompose(state.user_query, route, project_root)
                yield AgentEvent(type="plan_generated", data={
                    "count": len(subtasks),
                    "kind": route.kind,
                    "subtasks": [s.to_dict() for s in subtasks],
                })

            # Step 3: 执行
            yield AgentEvent(type="phase_change", data={"phase": AgentPhase.EXECUTING})

            if route.kind == "simple":
                async for event in self._run_simple(handle, project_root):
                    yield event
            elif route.kind == "map_reduce":
                async for event in self._run_map_reduce(handle, subtasks, project_root):
                    yield event
            else:  # multi_step
                async for event in self._run_multi_step(handle, subtasks, project_root):
                    yield event

        except Exception as e:
            logger.exception(f"[Engine] Task {task_id} failed: {e}")
            state.status = "failed"
            state.result = f"Internal error: {e}"
            state.phase = AgentPhase.DONE
            state.updated_at = time.time()
            yield AgentEvent(type="error", data={"message": str(e)})

    # ---- 简单任务 ----

    async def _run_simple(
        self,
        handle: _TaskHandle,
        project_root: Optional[Path],
    ) -> AsyncGenerator[AgentEvent, None]:
        from core.react import ReActLoop, ReActConfig, select_tools_for_task

        state = handle.state
        tools = select_tools_for_task(state.user_query, kind="simple")
        loop = ReActLoop(
            config=ReActConfig().capped(handle.max_steps),
            memory=handle.memory,
            context=handle.context,
            stop_checker=lambda: handle.stop_flag,
        )

        async for ev in loop.run(
            state.user_query,
            tools,
            initial_context="",
        ):
            if ev.type == "done":
                state.status = "completed"
                state.result = ev.data.get("result", "")
                state.phase = AgentPhase.DONE
                state.updated_at = time.time()
            elif ev.type == "error":
                state.status = "failed"
                state.result = ev.data.get("message", "error")
                state.phase = AgentPhase.DONE
                state.updated_at = time.time()
            yield self._translate_react_event(ev)

    # ---- map_reduce（并行子任务） ----

    async def _run_map_reduce(
        self,
        handle: _TaskHandle,
        subtasks: list,
        project_root: Optional[Path],
    ) -> AsyncGenerator[AgentEvent, None]:
        from core.aggregator import ReportAggregator
        from core.react import ReActLoop, ReActConfig, select_tools_for_task

        state = handle.state
        memory = handle.memory

        if not subtasks:
            state.status = "failed"
            state.result = "No subtasks generated"
            state.phase = AgentPhase.DONE
            state.updated_at = time.time()
            yield AgentEvent(type="error", data={"message": "No subtasks generated"})
            return

        # 区分可并行子任务与依赖性子任务（如汇总）
        parallelizable = [s for s in subtasks if s.parallelizable and not s.depends_on]
        sequential = [s for s in subtasks if not s.parallelizable or s.depends_on]

        total_parallel = len(parallelizable)
        yield AgentEvent(type="info", data={
            "message": f"准备执行 {total_parallel} 个子任务（{'串行' if self.config.max_parallel_subtasks <= 1 else '并行度 ' + str(self.config.max_parallel_subtasks)}）+ {len(sequential)} 个汇总任务",
        })

        # 用 Queue 实现流式转发：每个子任务实时把事件推入队列，
        # 主循环从队列读取并 yield，用户即可看到实时进度。
        sem = asyncio.Semaphore(self.config.max_parallel_subtasks)
        queue: asyncio.Queue = asyncio.Queue()
        _SENTINEL = object()  # 子任务结束标记

        async def _run_one_streaming(subtask):
            """运行单个子任务，所有事件实时入队。"""
            async with sem:
                # 先发 subtask_start（经队列转发）
                await queue.put(AgentEvent(type="subtask_start", data={
                    "id": subtask.id,
                    "description": subtask.description,
                    "kind": subtask.kind,
                }))
                try:
                    async for ev in self._run_subtask(handle, subtask, project_root):
                        await queue.put(ev)
                except Exception as e:
                    logger.exception(f"[Engine] Subtask {subtask.id} failed: {e}")
                    await queue.put(AgentEvent(type="error", data={
                        "message": f"子任务 {subtask.id} 执行失败: {e}",
                        "subtask_id": subtask.id,
                    }))
                await queue.put(_SENTINEL)

        # 按批执行，每批的事件实时流式转发
        completed = 0
        for batch_start in range(0, total_parallel, self.config.max_parallel_subtasks):
            if handle.stop_flag:
                break
            batch = parallelizable[batch_start:batch_start + self.config.max_parallel_subtasks]
            batch_num = batch_start // self.config.max_parallel_subtasks + 1
            yield AgentEvent(type="info", data={
                "message": f"执行第 {batch_num} 批 ({len(batch)} 个，已完成 {completed}/{total_parallel})",
            })

            # 启动本批所有子任务协程
            workers = [asyncio.ensure_future(_run_one_streaming(st)) for st in batch]
            pending_in_batch = len(batch)

            # 从队列实时转发事件，直到本批所有子任务结束
            while pending_in_batch > 0:
                item = await queue.get()
                if item is _SENTINEL:
                    pending_in_batch -= 1
                    completed += 1
                else:
                    yield item

            # 确保所有 worker 协程正常结束
            await asyncio.gather(*workers, return_exceptions=True)

        # 串行执行依赖性子任务（如汇总）
        for subtask in sequential:
            if handle.stop_flag:
                break
            yield AgentEvent(type="subtask_start", data={
                "id": subtask.id,
                "description": subtask.description,
                "kind": subtask.kind,
            })
            async for ev in self._run_subtask(handle, subtask, project_root):
                yield ev

        # 聚合报告
        yield AgentEvent(type="phase_change", data={"phase": AgentPhase.AGGREGATING})
        results = memory.iter_subtask_results()
        aggregator = ReportAggregator()
        try:
            report = await aggregator.aggregate(state.user_query, results, mode="concat")
            state.status = "completed"
            state.result = report
            state.phase = AgentPhase.DONE
            state.updated_at = time.time()
            yield AgentEvent(type="done", data={"result": report})
        except Exception as e:
            state.status = "failed"
            state.result = f"Aggregate failed: {e}"
            state.phase = AgentPhase.DONE
            state.updated_at = time.time()
            yield AgentEvent(type="error", data={"message": str(e)})

    # ---- multi_step（串行） ----

    async def _run_multi_step(
        self,
        handle: _TaskHandle,
        subtasks: list,
        project_root: Optional[Path],
    ) -> AsyncGenerator[AgentEvent, None]:
        state = handle.state
        memory = handle.memory

        for i, subtask in enumerate(subtasks, 1):
            if handle.stop_flag:
                break
            yield AgentEvent(type="subtask_start", data={
                "id": subtask.id,
                "description": subtask.description,
                "kind": subtask.kind,
                "index": i,
                "total": len(subtasks),
            })
            async for ev in self._run_subtask(handle, subtask, project_root):
                yield ev

        # 汇总结果
        yield AgentEvent(type="phase_change", data={"phase": AgentPhase.AGGREGATING})
        digest = memory.render_episodic_digest(max_chars=6000)
        final_result = f"# 多步骤任务完成\n\n**原始任务**: {state.user_query}\n\n## 执行详情\n\n{digest}"
        state.status = "completed"
        state.result = final_result
        state.phase = AgentPhase.DONE
        state.updated_at = time.time()
        yield AgentEvent(type="done", data={"result": final_result})

    # ---- 子任务执行 ----

    async def _run_subtask(
        self,
        handle: _TaskHandle,
        subtask,
        project_root: Optional[Path],
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        执行单个子任务。

        每个子任务有独立的 ContextWindow（共享 HierarchicalMemory 以便跨子任务延续信息）。
        """
        from core.context import ContextWindow
        from core.react import ReActLoop, ReActConfig, select_tools_for_task

        state = handle.state
        start_time = time.time()

        # 子任务独立上下文
        sub_ctx = ContextWindow(
            max_tokens=self.config.subtask_context_max_tokens,
            recent_n=6,
        )

        tools = select_tools_for_task(subtask.description, kind=subtask.kind)

        loop = ReActLoop(
            config=ReActConfig().capped(handle.max_steps),
            memory=handle.memory,
            context=sub_ctx,
            stop_checker=lambda: handle.stop_flag,
        )

        handle.memory.set_active_subtask(subtask.id)

        files_read_local: list[str] = []
        files_written_local: list[str] = []
        tools_used_local: list[str] = []
        findings_local: list[str] = []
        summary_local = ""
        status_local = "success"
        error_local: Optional[str] = None

        last_llm_response = ""
        async for ev in loop.run(
            user_query=subtask.description,
            tools=tools,
            subtask=subtask,
            initial_context="",
        ):
            # 跟踪工具结果
            if ev.type == "tool_result":
                tool_name = ev.data.get("tool", "")
                tools_used_local.append(tool_name)
            elif ev.type == "tool_call":
                args = ev.data.get("args", {}) or {}
                tool_name = ev.data.get("tool", "")
                if tool_name == "read_file" and args.get("path"):
                    files_read_local.append(args["path"])
                elif tool_name in ("write_file", "edit_file", "apply_diff") and args.get("path"):
                    files_written_local.append(args["path"])
            elif ev.type == "llm_response":
                content = ev.data.get("content", "")
                if content and len(content) > 50:
                    last_llm_response = content
            elif ev.type == "done":
                summary_local = ev.data.get("result", "") or last_llm_response
                # G2: 如果是迭代上限触发的兜底结束，标记为 partial 而非 success
                if ev.data.get("hit_limit"):
                    status_local = "partial"
            elif ev.type == "error":
                error_local = ev.data.get("message", "unknown error")
                status_local = "failed"

            # 转发 ReAct 循环的事件（加 subtask_id 标注）
            # 注：ReActLoop 只产生 thinking_chunk / llm_response / tool_* /
            # iteration_start / warning / info / done / error / stopped。
            # subtask_start / subtask_done 由 engine 层（本方法末尾）统一发送。
            if ev.type == "error":
                yield ev
            elif ev.type == "thinking_chunk":
                yield AgentEvent(type="thinking_chunk", data={
                    "subtask_id": subtask.id,
                    "content": ev.data.get("content", ""),
                })
            elif ev.type in ("tool_call", "tool_result", "tool_error", "iteration_start", "warning", "info", "llm_response"):
                yield AgentEvent(type=ev.type, data={**ev.data, "subtask_id": subtask.id})

            if handle.stop_flag:
                status_local = "partial"
                break

        # 兜底：若 summary 还没拿到，用最后一次 LLM 响应
        if not summary_local and last_llm_response:
            summary_local = last_llm_response

        # 清理 summary：去掉 <think> 块和工具调用 JSON 块，避免污染 episodic digest
        if summary_local:
            import re as _re
            # 去 <think>...</think>
            summary_local = _re.sub(r"<think>[\s\S]*?</think>\s*", "", summary_local)
            summary_local = _re.sub(r"<think>[\s\S]*$", "", summary_local)
            # 去 {"tool": "...", "args": {...}} 单行 JSON
            summary_local = _re.sub(
                r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{[\s\S]*?\}\s*\}',
                "", summary_local,
            )
            # 去 markdown 代码块里包着的工具调用
            summary_local = _re.sub(
                r'```(?:json)?\s*\n\s*\{\s*"tool"[\s\S]*?```',
                "", summary_local,
            )
            # 合并多余空行
            summary_local = _re.sub(r"\n\s*\n\s*\n+", "\n\n", summary_local).strip()

        # 从 summary 抽取 findings：bullet 行 + "问题/风险" 段落
        if summary_local:
            for line in summary_local.split("\n"):
                s = line.strip()
                if s.startswith(("- ", "* ", "• ")) and 10 < len(s) < 250:
                    findings_local.append(s.lstrip("-*• ").strip()[:200])
            import re as _re
            problem_block = _re.search(
                r"(?:问题|潜在问题|风险|Issues|Risks|Problems)[：:]\s*\n([\s\S]{0,800}?)(?:\n\n|\n#|\Z)",
                summary_local, _re.IGNORECASE,
            )
            if problem_block:
                for line in problem_block.group(1).split("\n"):
                    s = line.strip()
                    if s and len(s) > 5 and len(findings_local) < 8:
                        findings_local.append(s.lstrip("-*• ").strip()[:200])
            # 去重并截断
            findings_local = list(dict.fromkeys(findings_local))[:8]

        # 把结果写入 hierarchical memory
        duration = time.time() - start_time
        handle.memory.complete_subtask(
            subtask_id=subtask.id,
            description=subtask.description,
            status=status_local,
            summary=summary_local[:500],
            findings=findings_local[:6],
            files_read=files_read_local,
            files_written=files_written_local,
            tools_used=tools_used_local,
            error=error_local,
            duration_s=duration,
        )
        handle.memory.promote_subtask(subtask.id)

        # G3: 统一在子任务结束时发 subtask_done 事件。
        # 这样 _run_multi_step（串行）和 _run_map_reduce（并行）都能收到，
        # 前端 Todo 列表据此更新子任务完成态。
        yield AgentEvent(type="subtask_done", data={
            "id": subtask.id,
            "status": status_local,
            "summary": summary_local[:300] if summary_local else "",
            "findings_count": len(findings_local),
        })

    # ---- 工具：ReActEvent → AgentEvent ----

    def _translate_react_event(self, ev) -> AgentEvent:
        # 大部分 ReActEvent 直接同名转发
        return AgentEvent(type=ev.type, data=ev.data, timestamp=ev.timestamp)


# ---- 全局实例 ----

_engine: Optional[AgentEngine] = None


def get_engine() -> AgentEngine:
    global _engine
    if _engine is None:
        _engine = AgentEngine()
    return _engine
