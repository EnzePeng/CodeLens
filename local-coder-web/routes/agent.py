"""
Agent API routes — HTTP/SSE 适配层。

本文件只做：
- HTTP 端点定义（start / execute / action / status / stop / tools / ...）
- 把 core.engine.AgentEvent 转成前端期望的 SSE 数据格式
- 转发控制命令（pause / resume / cancel）到 engine

所有 ReAct 循环、上下文管理、任务分解逻辑都在 core.engine 与 core.react 里。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.engine import get_engine, AgentPhase
from core.tools import ToolRegistry
from logger import logger
from models import AgentStartRequest, AgentActionRequest, AgentStatusResponse, state


router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---- 生命周期端点 ----

@router.post("/start")
async def start_agent(req: AgentStartRequest) -> dict:
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    engine = get_engine()
    task_id = engine.start_task(req.query, max_steps=req.max_steps)
    tools = ToolRegistry.list_tools()

    return {
        "task_id": task_id,
        "status": "running",
        "tools": tools,
    }


@router.get("/status/{task_id}")
def agent_status(task_id: str) -> AgentStatusResponse:
    engine = get_engine()
    task = engine.get_state(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return AgentStatusResponse(
        task_id=task.task_id,
        status=task.status,
        steps=task.steps,
        current_step=task.current_step,
        result=task.result,
    )


@router.post("/action")
async def agent_action(req: AgentActionRequest) -> dict:
    engine = get_engine()
    task = engine.get_state(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if req.action == "cancel":
        engine.stop_task(req.task_id, "user_cancelled")
        return {"status": "cancelled"}
    if req.action == "pause":
        if engine.pause_task(req.task_id):
            return {"status": "paused"}
        raise HTTPException(status_code=400, detail="Cannot pause task")
    if req.action == "resume":
        if engine.resume_task(req.task_id):
            return {"status": "running"}
        raise HTTPException(status_code=400, detail="Cannot resume task")

    return {"status": task.status}


@router.post("/stop/{task_id}")
def stop_agent(task_id: str) -> dict:
    engine = get_engine()
    if engine.stop_task(task_id, "user_stopped"):
        return {"status": "stopped"}
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/tools")
def list_tools() -> dict:
    return {"tools": ToolRegistry.list_tools()}


@router.get("/history")
def get_edit_history() -> dict:
    from core.tools.undo_edit import get_undo_manager
    return {"history": get_undo_manager().get_history(limit=20)}


@router.post("/undo")
def undo_edits(count: int = 1) -> dict:
    from core.tools.undo_edit import get_undo_manager
    return {"results": get_undo_manager().undo(count)}


@router.get("/tasks")
def list_tasks() -> dict:
    engine = get_engine()
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "user_query": t.user_query[:100],
                "status": t.status,
                "phase": t.phase,
                "step_count": len(t.steps),
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "result_preview": (t.result or "")[:200],
            }
            for t in engine.get_all_tasks().values()
        ]
    }


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict:
    engine = get_engine()
    task = engine.get_state(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("completed", "failed", "stopped"):
        raise HTTPException(status_code=400, detail="Cannot delete running task")
    del engine._handles[task_id]
    return {"status": "deleted"}


@router.post("/self-improve")
async def trigger_self_improvement() -> dict:
    from core.self_improve import self_improvement_engine
    return self_improvement_engine.run_iteration()


@router.get("/improvement-report")
async def get_improvement_report() -> dict:
    from core.self_improve import self_improvement_engine
    return self_improvement_engine.get_improvement_report()


@router.get("/metrics/summary")
async def get_metrics_summary() -> dict:
    from core.metrics import enhanced_metrics
    return {
        "counters": dict(enhanced_metrics._counters),
        "gauges": dict(enhanced_metrics._gauges),
        "iterations": enhanced_metrics.get_iteration_trend(),
    }


# ---- 核心：流式执行端点 ----

@router.post("/execute/{task_id}")
async def execute_agent_stream(task_id: str) -> StreamingResponse:
    """把 engine 的 AgentEvent 流翻译为前端期望的 SSE 数据流。"""

    async def generate():
        def sse(data: dict) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        engine = get_engine()
        task = engine.get_state(task_id)
        if not task:
            yield sse({"type": "error", "message": "Task not found"})
            return

        yield sse({
            "type": "status",
            "status": "running",
            "message": "Starting execution",
        })

        try:
            async for ev in engine.run_task(task_id, project_root=state.root):
                payload = _translate_event(ev)
                if payload is None:
                    continue
                # 兼容：engine 的 data 字段有时是 dict，有时是标量；SSE 协议用扁平结构
                if isinstance(payload.get("data"), dict):
                    flat = {"type": payload["type"], **payload["data"]}
                else:
                    flat = payload
                yield sse(flat)

        except Exception as e:
            logger.exception(f"[Agent] stream error: {e}")
            yield sse({"type": "error", "message": f"Stream error: {e}"})
            engine.stop_task(task_id, f"Stream error: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _translate_event(ev) -> dict | None:
    """把 AgentEvent 翻译成前端兼容的 payload dict。"""
    t = ev.type
    data = ev.data or {}

    # 直接转发的类型（data 通常是 dict）
    if t in {
        "phase_change", "analysis", "tool_call", "tool_result", "tool_error",
        "thinking_chunk", "llm_response", "warning", "info", "error",
        "plan_generated", "plan_data",
        "subtask_start", "subtask_done",
    }:
        return {"type": t, "data": data}

    # tool_call_batch：前端期望 {"count", "tools"}
    if t == "tool_call_batch":
        return {"type": "tool_call_batch", "data": {
            "count": data.get("count", 0),
            "tools": data.get("tools", []),
        }}

    # done：前端期望 {"result"}
    if t == "done":
        return {"type": "done", "data": {"result": data.get("result", "")}}

    # iteration_start：转发给前端用于在思考内容中插入迭代分隔（D3）
    if t == "iteration_start":
        return {"type": "iteration_start", "data": data}

    # stopped：静默跳过
    if t == "stopped":
        return None

    # 默认：转发
    return {"type": t, "data": data}
