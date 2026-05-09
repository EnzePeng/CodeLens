"""
Agent API routes — handle Agent task lifecycle (start, status, action, stop, tools).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from config import (
    MAX_CONSECUTIVE_REJECTIONS,
    MAX_RECOVERY_ATTEMPTS,
)
from core.agent import get_agent, AgentConfig, AgentPhase
from core.tools import ToolRegistry
from models import AgentStartRequest, AgentActionRequest, AgentStatusResponse, state
from services.indexer import build_bm25_index
from services.memory import MemoryStore
from services.search import select_context, render_context


def _get_onnx():
    import app as _app_module
    return _app_module.get_onnx_session()


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/start")
async def start_agent(req: AgentStartRequest) -> dict:
    """Start an Agent task."""
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    agent = get_agent()
    task_id = agent.start_task(req.query)
    tools = ToolRegistry.list_tools()

    return {
        "task_id": task_id,
        "status": "running",
        "tools": tools,
    }


@router.get("/status/{task_id}")
def agent_status(task_id: str) -> AgentStatusResponse:
    """Get Agent task status."""
    agent = get_agent()
    task = agent.get_task(task_id)

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
    """Handle Agent user action (confirm/reject/cancel)."""
    agent = get_agent()
    task = agent.get_task(req.task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if req.action == "cancel":
        agent.stop_task(req.task_id, "user_cancelled")
        return {"status": "cancelled"}

    # Plan-level approve/reject
    if req.tool_call_id:
        if req.action == "confirm":
            approved = agent.approve_file(req.task_id, req.tool_call_id)
            if approved:
                # Check if all files approved -> auto-apply
                plan = agent.get_plan(req.task_id)
                if plan and plan.approved_count == plan.total_changes:
                    result = agent.apply_plan(req.task_id)
                    return {"status": "applying", "result": result}
            return {"status": "approved", "file": req.tool_call_id}
        elif req.action == "reject":
            agent.reject_file(req.task_id, req.tool_call_id)
            return {"status": "rejected", "file": req.tool_call_id}

    return {"status": task.status}


@router.post("/stop/{task_id}")
def stop_agent(task_id: str) -> dict:
    """Stop an Agent task."""
    agent = get_agent()
    if agent.stop_task(task_id, "user_stopped"):
        return {"status": "stopped"}
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/tools")
def list_tools() -> dict:
    """List all available Agent tools."""
    return {"tools": ToolRegistry.list_tools()}


@router.get("/history")
def get_edit_history() -> dict:
    """Get edit history for undo."""
    from core.tools.undo_edit import get_undo_manager
    undo_mgr = get_undo_manager()
    return {"history": undo_mgr.get_history(limit=20)}


@router.post("/undo")
def undo_edits(count: int = 1) -> dict:
    """Undo recent edits."""
    from core.tools.undo_edit import get_undo_manager
    undo_mgr = get_undo_manager()
    results = undo_mgr.undo(count)
    return {"results": results}


@router.get("/tasks")
def list_tasks() -> dict:
    """List all Agent tasks."""
    agent = get_agent()
    tasks = agent.get_all_tasks()
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "user_query": t.user_query[:100],
                "status": t.status,
                "step_count": len(t.steps),
                "created_at": t.created_at,
            }
            for t in tasks.values()
        ]
    }


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict:
    """Delete a completed task from memory."""
    agent = get_agent()
    task = agent.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Cannot delete running task")

    del agent._tasks[task_id]
    return {"status": "deleted"}


@router.post("/execute/{task_id}")
async def execute_agent_stream(task_id: str) -> StreamingResponse:
    """Execute Agent task with streaming updates (SSE).

    Flow:
      1. Analyze task (simple vs complex)
      2. For complex: generate plan -> show preview -> wait for approval -> apply
      3. For simple: ReAct loop
    """

    async def generate():
        def _sse(data: dict) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        agent = get_agent()
        task = agent.get_task(task_id)

        if not task:
            yield _sse({"type": "error", "message": "Task not found"})
            return

        # Build context
        idf, avg_dl = build_bm25_index(state.files)
        ort_sess, ort_tok = _get_onnx()
        selected = select_context(
            question=task.user_query,
            files=state.files,
            idf=idf,
            avg_dl=avg_dl,
            embedding_ready=state.embedding_ready,
            session=ort_sess,
            tokenizer=ort_tok,
        )
        context = render_context(selected)

        # Step 1: Analyze task intent
        yield _sse({"type": "phase_change", "phase": AgentPhase.PARSING, "message": "Analyzing task..."})
        intent = agent.analyze_task(task.user_query, context)
        yield _sse({
            "type": "analysis",
            "intent_type": intent.type,
            "description": intent.description,
        })

        if not intent.requires_plan:
            # Simple task: ReAct loop with self-reflection and error recovery
            memory = MemoryStore(working_size=4, episodic_max=8)
            user_msg = f"Repository: {state.root}\n\nContext:\n{context}\n\nTask: {task.user_query}"
            tools = ToolRegistry.recommend_tools(user_msg, max_tools=6)
            messages = [
                {"role": "system", "content": agent.generate_system_prompt(tools)},
                {"role": "user", "content": user_msg},
            ]

            yield _sse({"type": "status", "status": "running", "message": "Starting Agent execution (simple mode)"})

            try:
                consecutive_rejections = 0
                recovery_attempts = 0
                llm_response = ""

                while agent.should_continue(task_id):
                    # Build messages from episodic memory + working memory
                    memory_context = memory.get_context()

                    yield _sse({"type": "thinking", "message": "LLM is thinking..."})

                    try:
                        llm_response = await agent.call_llm(memory_context + messages[1:], tools)
                    except Exception as e:
                        yield _sse({"type": "error", "message": f"LLM call failed: {e}"})
                        agent.stop_task(task_id, f"LLM error: {e}")
                        break

                    yield _sse({"type": "llm_response", "content": llm_response})

                    tool_calls = agent.parse_tool_calls(llm_response)

                    if not tool_calls:
                        task.result = llm_response
                        task.status = "completed"
                        task.phase = AgentPhase.DONE
                        yield _sse({"type": "done", "result": llm_response})
                        break

                    if len(tool_calls) > 1:
                        yield _sse({
                            "type": "batch_tool_call",
                            "count": len(tool_calls),
                            "calls": [
                                {"tool": tc.get("tool"), "args": tc.get("args")}
                                for tc in tool_calls
                            ],
                        })

                    for tool_call in tool_calls:
                        tool_name = tool_call.get("tool", "")
                        tool_args = tool_call.get("args", {})

                        # Self-reflection before execution
                        yield _sse({"type": "thinking", "message": "Reflecting on next action..."})
                        reflection = await agent.reflect_before_action(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            user_query=task.user_query,
                            recent_messages=messages,
                        )
                        yield _sse({"type": "reflection", **reflection})

                        if not reflection["approved"]:
                            consecutive_rejections += 1
                            if consecutive_rejections >= MAX_CONSECUTIVE_REJECTIONS:
                                yield _sse({"type": "warning", "message": f"Multiple rejections ({consecutive_rejections}), proceeding anyway"})
                            else:
                                reconsider_prompt = (
                                    f"Your self-reflection identified issues: {reflection['reflection']}\n"
                                    f"Reconsider your approach. Output a new tool call or natural language response."
                                )
                                messages.append({"role": "user", "content": reconsider_prompt})
                                continue
                        else:
                            consecutive_rejections = 0

                        yield _sse({"type": "tool_call", "tool": tool_name, "args": tool_args})

                        step = agent.add_step(task_id, tool_name, tool_args)
                        if not step:
                            continue

                        try:
                            result = ToolRegistry.execute(tool_name, **tool_args)
                            agent.update_step(task_id, step.step_id, "success", result)
                            yield _sse({"type": "tool_result", "tool": tool_name, "result": result[:1000]})
                            recovery_attempts = 0  # Reset on success
                        except Exception as e:
                            error_msg = str(e)
                            agent.update_step(task_id, step.step_id, "failed", error=error_msg)
                            yield _sse({"type": "tool_error", "tool": tool_name, "error": error_msg})

                            # Error recovery
                            if recovery_attempts < MAX_RECOVERY_ATTEMPTS:
                                yield _sse({"type": "thinking", "message": f"Analyzing error, attempting recovery (attempt {recovery_attempts + 1}/{MAX_RECOVERY_ATTEMPTS})..."})
                                recovery = await agent.recover_from_error(
                                    tool_name=tool_name,
                                    error=error_msg,
                                    context_summary=context[:500],
                                    tool_args=tool_args,
                                )
                                can_continue = recovery.get("can_continue", False)
                                if not can_continue:
                                    task.status = "failed"
                                    task.result = f"Failed: {error_msg}. Cannot recover."
                                    yield _sse({"type": "error", "message": task.result})
                                    break
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"Previous action failed: {error_msg}\n"
                                        f"Analysis: {recovery.get('analysis', '')}\n"
                                        f"Retry approach: {json.dumps(recovery.get('retry_args', tool_args), ensure_ascii=False)}\n"
                                        f"Execute a corrected action or provide a better alternative."
                                    ),
                                })
                                recovery_attempts += 1
                            else:
                                task.status = "failed"
                                task.result = f"Max recovery attempts ({MAX_RECOVERY_ATTEMPTS}) reached for: {tool_name}"
                                yield _sse({"type": "error", "message": task.result})
                                break

                        messages.append({"role": "user", "content": f"Tool {tool_name} result:\n{result[:2000]}"})
                        memory.add(step.step_id, tool_name, result, True, llm_response)

                    # Recompute tools based on accumulated conversation context
                    last_content = messages[-1].get("content", "") if messages else ""
                    tools = ToolRegistry.recommend_tools(last_content, max_tools=6)
                    messages[0] = {"role": "system", "content": agent.generate_system_prompt(tools)}

                    if len(task.steps) >= agent.config.max_steps:
                        task.status = "failed"
                        task.result = f"Max steps ({agent.config.max_steps}) reached"
                        yield _sse({"type": "error", "message": task.result})
                        break

            except Exception as e:
                yield _sse({"type": "error", "message": str(e)})
                agent.stop_task(task_id, f"Error: {e}")

        else:
            # Complex task: Plan-then-Apply
            yield _sse({"type": "phase_change", "phase": AgentPhase.PLANNING, "message": "Generating plan..."})

            # Build system prompt for plan generation
            plan_prompt = f"""Given the codebase context below, generate a modification plan for the following request:

Request: {task.user_query}

Context:
{context}

Output a structured plan in the following JSON format inside a ```plan code block:
{{
  "description": "Brief description of the plan",
  "files": [
    {{
      "path": "relative/path/to/file",
      "diff": "unified diff showing changes",
      "old_content": "original file content (first 500 chars)",
      "new_content": "complete new file content",
      "dependencies": ["path/to/dependency1", ...],
      "verification": "how to verify this change is correct"
    }}
  ]
}}

Rules:
- List dependencies: files that must be applied BEFORE this file
- Provide clear verification criteria for each file
- Be specific about file paths and include the complete new file content for each file."""

            try:
                plan_response = await agent.call_llm(
                    [{"role": "user", "content": plan_prompt}],
                    tools,
                )
            except Exception as e:
                yield _sse({"type": "error", "message": f"Plan generation failed: {e}"})
                agent.stop_task(task_id, f"Plan generation failed: {e}")
                return

            yield _sse({"type": "plan_generated", "content": plan_response})

            # Generate plan object
            plan = agent.generate_plan(task.user_query, context, [plan_response])
            if plan:
                agent.set_plan(task_id, plan)
                yield _sse({
                    "type": "plan_data",
                    "description": plan.description,
                    "estimated_steps": plan.estimated_steps,
                    "files": [
                        {
                            "path": fcp.path,
                            "diff": fcp.diff,
                            "status": fcp.status,
                        }
                        for fcp in plan.files
                    ],
                })
            else:
                yield _sse({"type": "warning", "message": "Could not parse plan, falling back to simple mode"})

            yield _sse({"type": "phase_change", "phase": AgentPhase.PREVIEW, "message": "Waiting for user approval..."})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
