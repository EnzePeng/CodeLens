"""
Agent Core — Plan-then-Apply architecture.

Workflow:
  1. Parsing   — Analyze user intent (simple Q&A vs complex task)
  2. Planning   — Generate modification plan
  3. Preview    — Show diff preview to user
  4. Applying   — Execute confirmed modifications
  5. Done       — Complete
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from config import AGENT_MAX_STEPS, AGENT_DEFAULT_TIMEOUT, LLAMA_URL, SYSTEM_PROMPTS
from logger import logger
from models import AgentStep, AgentState, state


# ---------------------------------------------------------------------------
# Phase constants
# ---------------------------------------------------------------------------

class AgentPhase:
    PARSING = "parsing"
    PLANNING = "planning"
    PREVIEW = "preview"
    APPLYING = "applying"
    DONE = "done"


# ---------------------------------------------------------------------------
# Plan data models
# ---------------------------------------------------------------------------

@dataclass
class FileChangePlan:
    """Modification plan for a single file."""
    path: str
    diff: str
    old_content: str
    new_content: str
    old_content_hash: str = ""
    user_approved: bool = False
    status: str = "pending"  # pending / approved / rejected / applied / error


@dataclass
class AgentPlan:
    """Modification plan: list of file changes and overall description."""
    description: str
    estimated_steps: int
    files: list[FileChangePlan] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.files)

    @property
    def approved_count(self) -> int:
        return sum(1 for f in self.files if f.user_approved)

    @property
    def approved_files(self) -> list[FileChangePlan]:
        return [f for f in self.files if f.user_approved]


@dataclass
class TaskIntent:
    """Classification of user task intent."""
    type: str  # "simple" | "complex"
    description: str
    requires_plan: bool = False


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

@dataclass
class AgentConfig:
    max_steps: int = AGENT_MAX_STEPS
    timeout: int = AGENT_DEFAULT_TIMEOUT
    temperature: float = 0.15
    max_tokens: int = 2048


# ---------------------------------------------------------------------------
# Core Agent engine
# ---------------------------------------------------------------------------

class AgentLoop:
    """Agent execution engine with Plan-then-Apply pattern.

    For complex tasks:
      1. Analyze task (simple vs complex)
      2. Generate a modification plan (diffs, not full files)
      3. Show diff preview to user for approval
      4. Apply confirmed changes sequentially
    For simple tasks:
      1. Direct LLM response (tool-based ReAct loop)
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self._tasks: dict[str, AgentState] = {}
        self._plans: dict[str, AgentPlan] = {}

    # ---- Task management ----

    def start_task(self, query: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        agent_state = AgentState(
            task_id=task_id,
            user_query=query,
            status="running",
            created_at=time.time(),
            updated_at=time.time(),
            phase=AgentPhase.PARSING,
        )
        self._tasks[task_id] = agent_state
        logger.info(f"[Agent] Started task {task_id}: {query[:50]}...")
        return task_id

    def get_task(self, task_id: str) -> Optional[AgentState]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> dict[str, AgentState]:
        return self._tasks

    def pause_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status == "running":
            task.status = "paused"
            task.updated_at = time.time()
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status == "paused":
            task.status = "running"
            task.updated_at = time.time()
            return True
        return False

    def stop_task(self, task_id: str, reason: str = "user_stopped") -> bool:
        task = self._tasks.get(task_id)
        if task:
            task.status = "failed" if reason else "completed"
            task.result = reason
            task.updated_at = time.time()
            task.phase = AgentPhase.DONE
            logger.info(f"[Agent] Task {task_id} stopped: {reason}")
            return True
        return False

    # ---- Step management ----

    def add_step(self, task_id: str, tool_name: str, tool_input: dict[str, Any]) -> Optional[AgentStep]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        step = AgentStep(
            step_id=len(task.steps),
            tool_name=tool_name,
            tool_input=tool_input,
            status="running",
            timestamp=time.time(),
        )
        task.steps.append(step)
        task.current_step = len(task.steps) - 1
        task.updated_at = time.time()
        return step

    def update_step(self, task_id: str, step_id: int, status: str,
                    output: Optional[str] = None, error: Optional[str] = None) -> bool:
        task = self._tasks.get(task_id)
        if not task or step_id >= len(task.steps):
            return False
        step = task.steps[step_id]
        step.status = status
        step.duration = time.time() - step.timestamp
        if output:
            step.tool_output = output
        if error:
            step.error = error
        task.updated_at = time.time()
        return True

    def should_continue(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status != "running":
            return False
        if len(task.steps) >= self.config.max_steps:
            task.status = "failed"
            task.result = f"Max steps ({self.config.max_steps}) reached"
            return False
        return True

    # ---- Plan management ----

    def set_plan(self, task_id: str, plan: AgentPlan) -> None:
        self._plans[task_id] = plan
        task = self._tasks.get(task_id)
        if task:
            task.phase = AgentPhase.PREVIEW

    def get_plan(self, task_id: str) -> Optional[AgentPlan]:
        return self._plans.get(task_id)

    def approve_file(self, task_id: str, file_path: str) -> bool:
        """Approve a specific file change."""
        plan = self._plans.get(task_id)
        if not plan:
            return False
        for fcp in plan.files:
            if fcp.path == file_path and fcp.status == "pending":
                fcp.user_approved = True
                fcp.status = "approved"
                return True
        return False

    def reject_file(self, task_id: str, file_path: str) -> bool:
        """Reject a specific file change."""
        plan = self._plans.get(task_id)
        if not plan:
            return False
        for fcp in plan.files:
            if fcp.path == file_path and fcp.status == "pending":
                fcp.status = "rejected"
                return True
        return False

    # ---- Tool call parsing ----

    def parse_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Parse tool calls from LLM output.

        Supports multiple formats:
        1. JSON object: {"tool": "...", "args": {...}}
        2. Tagged block: <tool>...</tool>
        3. Code block with file path as language tag (for plan/apply)
        4. Natural language: "read file path/to/file"
        """
        tool_calls = []

        # Pattern 1: JSON object with "tool" and "args" keys (handles nested braces)
        for i, ch in enumerate(text):
            if ch != '{':
                continue
            segment = text[i:i+200]
            if '"tool"' not in segment or '"args"' not in segment:
                continue
            depth = 0
            in_str = False
            esc = False
            for j, c in enumerate(segment):
                if esc:
                    esc = False
                    continue
                if c == '\\':
                    esc = True
                    continue
                if c == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            candidate = text[i:i+j+1]
                            try:
                                obj = json.loads(candidate)
                                if "tool" in obj and "args" in obj:
                                    tool_calls.append(obj)
                            except json.JSONDecodeError:
                                continue
                            break

        # Pattern 2: Tagged block <tool>{...}</tool>
        block_pattern = r'<tool>\s*(.*?)\s*</tool>'
        for match in re.finditer(block_pattern, text, re.DOTALL):
            try:
                obj = json.loads(match.group(1))
                if "tool" in obj and "args" in obj:
                    tool_calls.append(obj)
            except json.JSONDecodeError:
                continue

        # Pattern 3: Code block with file path as language tag (for write_file)
        code_block_pattern = r'```(\S+)\n([\s\S]*?)```'
        for match in re.finditer(code_block_pattern, text):
            lang = match.group(1)
            code = match.group(2).strip()
            if '.' in lang and '/' not in lang:
                tool_calls.append({"tool": "write_file", "args": {"path": lang, "content": code}})

        return tool_calls if tool_calls else []

    # ---- LLM interaction ----

    def generate_system_prompt(self, tools: list[dict[str, Any]]) -> str:
        """Generate system prompt with available tools."""
        base_prompt = SYSTEM_PROMPTS.get("agent", SYSTEM_PROMPTS["ask"])

        tools_desc = "\n".join([
            f"- **{t['name']}**: {t.get('description', '')}"
            + (f" | Args: {json.dumps(t.get('parameters', {}), ensure_ascii=False)}"
               if t.get('parameters') else "")
            for t in tools
        ])

        return f"""{base_prompt}

You are an autonomous coding agent. Available tools:

{tools_desc}

When you need to use a tool, output exactly one JSON object per tool call:
{{"tool": "tool_name", "args": {{"param1": "value1"}}}}

Rules:
- Use ONE tool call per response (do not batch multiple tool calls)
- After each tool call, analyze the result before deciding the next action
- If multiple changes are needed, do them one at a time
- When task is complete, respond with a natural language summary (no tool call)
- Think step by step: observe -> think -> act -> observe

For code file modifications, prefer using write_file (complete file) or edit_file (section replacement).
For viewing changes, read_file with line ranges is preferred.

Think step by step."""

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> str:
        """Call LLM with messages and tools."""
        system_prompt = self.generate_system_prompt(tools)
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        payload = {
            "model": "local",
            "messages": full_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(LLAMA_URL, json=payload)
                response.raise_for_status()
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content
        except httpx.ConnectError:
            raise ConnectionError("Cannot connect to LLM service")
        except httpx.TimeoutException:
            raise TimeoutError("LLM request timed out")
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

    # ---- Plan-then-Apply methods ----

    def analyze_task(self, query: str, context: str) -> TaskIntent:
        """Analyze user intent: simple Q&A vs complex task requiring plan."""
        # Heuristic-based classification
        complex_keywords = [
            "modify", "refactor", "rewrite", "implement", "add feature",
            "create", "build", "migrate", "delete", "rename", "move",
            "fix", "update", "add test", "remove", "change", "edit",
            "重构", "重写", "实现", "添加", "删除", "修改", "创建",
        ]
        query_lower = query.lower()

        # Check for simple questions
        question_words = ["what", "where", "how", "why", "who", "explain", "describe",
                          "mean", "什么意思", "怎么工作", "哪里", "哪个", "是什么"]
        if any(w in query_lower for w in question_words) and not any(kw in query_lower for kw in complex_keywords):
            return TaskIntent(type="simple", description="Direct question, no code changes needed")

        # Check for complex indicators
        if any(kw in query_lower for kw in complex_keywords) or len(query) > 50:
            return TaskIntent(
                type="complex",
                description=f"Complex task requiring plan: {query[:100]}",
                requires_plan=True,
            )

        return TaskIntent(type="simple", description="Simple task")

    def generate_plan(self, query: str, context: str, tools_output: list[str]) -> Optional[AgentPlan]:
        """Generate a modification plan from LLM context.

        The LLM should output structured plan data with file diffs.
        Falls back to a simple plan based on tools_output.
        """
        # Try to parse plan from LLM output (tools_output[-1] is the plan response)
        plan_text = tools_output[-1] if tools_output else ""

        # Try to extract plan blocks from LLM output
        plan_pattern = r'```(?:plan|Plan)\s*\n([\s\S]*?)```'
        match = re.search(plan_pattern, plan_text)
        if match:
            try:
                plan_data = json.loads(match.group(1))
                files = []
                for file_data in plan_data.get("files", []):
                    fcp = FileChangePlan(
                        path=file_data.get("path", ""),
                        diff=file_data.get("diff", ""),
                        old_content=file_data.get("old_content", ""),
                        new_content=file_data.get("new_content", ""),
                    )
                    files.append(fcp)
                return AgentPlan(
                    description=plan_data.get("description", query),
                    estimated_steps=len(files),
                    files=files,
                )
            except json.JSONDecodeError:
                pass

        # Fallback: treat as simple write plan
        # Each ```filepath...``` block is treated as a file change
        file_changes: list[FileChangePlan] = []
        write_pattern = r'```(\S+\.+\S+)\n([\s\S]*?)```'
        for match in re.finditer(write_pattern, plan_text):
            path = match.group(1)
            content = match.group(2).strip()
            fcp = FileChangePlan(
                path=path,
                diff="(auto-generated diff)",
                old_content="",
                new_content=content,
            )
            file_changes.append(fcp)

        if file_changes:
            return AgentPlan(
                description=query,
                estimated_steps=len(file_changes),
                files=file_changes,
            )

        return None

    def apply_plan(self, task_id: str) -> str:
        """Apply all approved file changes in the plan.

        Returns a summary of applied changes.
        """
        plan = self._plans.get(task_id)
        task = self._tasks.get(task_id)
        if not plan or not task:
            return "No plan found"

        if task:
            task.phase = AgentPhase.APPLYING

        results = []
        from core.tools import ToolRegistry

        for fcp in plan.approved_files:
            step = self.add_step(task_id, "apply_file", {"path": fcp.path})
            if not step:
                continue

            try:
                # Use write_file tool to apply changes
                ToolRegistry.execute("write_file", path=fcp.path, content=fcp.new_content)
                fcp.status = "applied"
                self.update_step(task_id, step.step_id, "success", output=f"Applied to {fcp.path}")
                results.append(f"Applied: {fcp.path}")
            except Exception as e:
                fcp.status = "error"
                self.update_step(task_id, step.step_id, "failed", error=str(e))
                results.append(f"Error: {fcp.path} - {e}")

        # Mark remaining pending files as rejected
        for fcp in plan.files:
            if fcp.status == "pending":
                fcp.status = "rejected"

        if task:
            task.status = "completed"
            task.result = "; ".join(results)
            task.phase = AgentPhase.DONE

        return "Plan applied: " + "; ".join(results)

    def execute_agent_stream(self, task_id: str):
        """Execute agent task with streaming updates.

        For complex tasks: generate plan -> user approves -> apply
        For simple tasks: ReAct loop
        """
        # Implemented in routes/agent.py as async generator for SSE
        pass


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

agent_loop = AgentLoop()


def get_agent() -> AgentLoop:
    """Get global Agent instance."""
    return agent_loop
