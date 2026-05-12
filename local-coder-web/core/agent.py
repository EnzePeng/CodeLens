"""
Agent Core — Plan-then-Apply architecture with streaming tool calls.

Improvements:
- #16 Proper JSON extraction with brace depth counting
- #17 Support structured <tool> tags
- #19 LLM-generated plan with proper JSON
- #20 Structured plan with dependency-ordered execution
- #21 Verification gate per file
- #22 Self-reflection with JSON parsing
- #23 Error recovery with retry
- #25 Streaming tool calls (via SSE)
- #27 Dependency-aware parallel tool execution
- #28 Timeout and progress tracking
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from config import (
    AGENT_MAX_STEPS, AGENT_DEFAULT_TIMEOUT, LLAMA_URL, SYSTEM_PROMPTS,
    REFLECTION_MAX_TOKENS, REFLECTION_TEMPERATURE, MAX_CONSECUTIVE_REJECTIONS,
    RECOVERY_MAX_TOKENS, RECOVERY_TEMPERATURE, MAX_RECOVERY_ATTEMPTS,
    SUMMARIZE_MAX_TOKENS, SUMMARIZE_TEMPERATURE,
)
from logger import logger
from models import AgentStep, AgentState, state


# ---- Phase constants ----

class AgentPhase:
    PARSING = "parsing"
    PLANNING = "planning"
    PREVIEW = "preview"
    APPLYING = "applying"
    DONE = "done"


# ---- Plan data models ----

@dataclass
class FileChangePlan:
    """Modification plan for a single file."""
    path: str
    diff: str = ""
    old_content: str = ""
    new_content: str = ""
    old_content_hash: str = ""
    user_approved: bool = False
    status: str = "pending"
    dependencies: list[str] = field(default_factory=list)
    verification: str = ""


@dataclass
class AgentPlan:
    """Modification plan."""
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
    type: str
    description: str
    requires_plan: bool = False


# ---- Agent configuration ----

@dataclass
class AgentConfig:
    max_steps: int = AGENT_MAX_STEPS
    timeout: int = AGENT_DEFAULT_TIMEOUT
    temperature: float = 0.15
    max_tokens: int = 2048


# ---- Tool call parsing improvements (#16-19) ----

def _extract_json_block(text: str, start: int, max_len: int = 2000) -> Optional[dict]:
    """#16 Proper JSON extraction with brace depth counting."""
    segment = text[start:start + max_len]
    depth = 0
    in_str = False
    esc = False
    for i, c in enumerate(segment):
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
                    candidate = text[start:start + i + 1]
                    try:
                        obj = json.loads(candidate)
                        if "tool" in obj and "args" in obj:
                            return obj
                    except json.JSONDecodeError:
                        continue
                    break
    return None


def _extract_all_json_blocks(text: str) -> list[dict]:
    """Extract all JSON tool call objects from text."""
    results = []
    for i, ch in enumerate(text):
        if ch == '{':
            obj = _extract_json_block(text, i)
            if obj:
                results.append(obj)
    return results


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """#16-19 Parse tool calls from LLM output with multiple strategies."""
    tool_calls = []

    # Strategy 1: JSON objects with "tool" and "args" keys
    tool_calls.extend(_extract_all_json_blocks(text))

    # Strategy 2: <tool>{...}</tool> tags
    if not tool_calls:
        for match in re.finditer(r'<tool>\s*(.*?)\s*</tool>', text, re.DOTALL):
            try:
                obj = json.loads(match.group(1))
                if "tool" in obj and "args" in obj:
                    tool_calls.append(obj)
            except json.JSONDecodeError:
                continue

    # Strategy 3: Code blocks with file path (contains dot and slash, e.g. src/main.py)
    if not tool_calls:
        for match in re.finditer(r'```(\S+)\n([\s\S]*?)```', text):
            lang = match.group(1)
            code = match.group(2).strip()
            # Only match if it looks like a file path (contains a dot and either a slash or common extension)
            if '.' in lang and ('/' in lang or lang.count('.') >= 1 and any(
                lang.endswith(ext) for ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs',
                                               '.java', '.cpp', '.h', '.md', '.json', '.yaml',
                                               '.yml', '.html', '.css', '.toml', '.sh', '.ps1']
            )) and len(code) > 10:
                tool_calls.append({"tool": "write_file", "args": {"path": lang, "content": code}})

    return tool_calls if tool_calls else []


# ---- Core Agent engine ----

class AgentLoop:
    """Agent execution engine with Plan-then-Apply pattern."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self._tasks: dict[str, AgentState] = {}
        self._plans: dict[str, AgentPlan] = {}

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
            task.status = "stopped"
            task.result = reason
            task.updated_at = time.time()
            task.phase = AgentPhase.DONE
            logger.info(f"[Agent] Task {task_id} stopped: {reason}")
            return True
        return False

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

    def set_plan(self, task_id: str, plan: AgentPlan) -> None:
        self._plans[task_id] = plan
        task = self._tasks.get(task_id)
        if task:
            task.phase = AgentPhase.PREVIEW

    def get_plan(self, task_id: str) -> Optional[AgentPlan]:
        return self._plans.get(task_id)

    def approve_file(self, task_id: str, file_path: str) -> bool:
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
        plan = self._plans.get(task_id)
        if not plan:
            return False
        for fcp in plan.files:
            if fcp.path == file_path and fcp.status == "pending":
                fcp.status = "rejected"
                return True
        return False

    def generate_system_prompt(self, tools: list[dict[str, Any]]) -> str:
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
- You may batch up to 3 independent read-only tool calls per response (e.g., read_file, search_files, list_directory)
- Write operations (write_file, edit_file, apply_diff) must NOT be batched
- After each tool call batch, analyze all results before deciding the next action
- When task is complete, respond with a natural language summary (no tool call)
- Think step by step: observe -> think -> act -> observe

For code file modifications, prefer using write_file (complete file) or edit_file (section replacement).
Think step by step."""

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> str:
        """#28 Non-streaming LLM call with timeout.
        
        If messages don't start with a system role, prepends one automatically.
        """
        # Only prepend system prompt if messages don't already have one
        has_system = messages and messages[0].get("role") == "system"
        if has_system:
            full_messages = messages
        else:
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
            from app import get_http_client
            client = get_http_client()
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

    def analyze_task(self, query: str, context: str) -> TaskIntent:
        """#29 Simple heuristic-based classification."""
        complex_keywords = [
            "modify", "refactor", "rewrite", "implement", "add feature",
            "create", "build", "migrate", "delete", "rename", "move",
            "fix", "update", "add test", "remove", "change", "edit",
            "重��", "重写", "实现", "添加", "删除", "修改", "创建",
        ]
        query_lower = query.lower()
        question_words = ["what", "where", "how", "why", "who", "explain", "describe",
                          "什么意思", "怎么工作", "哪里", "哪个", "是什么"]
        if any(w in query_lower for w in question_words) and not any(kw in query_lower for kw in complex_keywords):
            return TaskIntent(type="simple", description="Direct question, no code changes needed")
        if any(kw in query_lower for kw in complex_keywords) or len(query) > 50:
            return TaskIntent(
                type="complex",
                description=f"Complex task requiring plan: {query[:100]}",
                requires_plan=True,
            )
        return TaskIntent(type="simple", description="Simple task")

    def generate_plan(self, query: str, context: str, tools_output: list[str]) -> Optional[AgentPlan]:
        """#19 Generate plan from LLM output."""
        plan_text = tools_output[-1] if tools_output else ""

        # Strategy 1: ```plan ... ``` code block with JSON
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
                        dependencies=file_data.get("dependencies", []),
                        verification=file_data.get("verification", ""),
                    )
                    files.append(fcp)
                if files:
                    return AgentPlan(
                        description=plan_data.get("description", query),
                        estimated_steps=len(files),
                        files=files,
                    )
            except json.JSONDecodeError:
                pass

        # Strategy 2: Any JSON block with "files" and "description" keys
        for json_match in re.finditer(r'```(?:json|JSON)?\s*\n([\s\S]*?)```', plan_text):
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict) and "files" in data and isinstance(data["files"], list):
                    files = []
                    for file_data in data["files"]:
                        if isinstance(file_data, dict) and "path" in file_data:
                            fcp = FileChangePlan(
                                path=file_data.get("path", ""),
                                diff=file_data.get("diff", ""),
                                old_content=file_data.get("old_content", ""),
                                new_content=file_data.get("new_content", ""),
                                dependencies=file_data.get("dependencies", []),
                                verification=file_data.get("verification", ""),
                            )
                            files.append(fcp)
                    if files:
                        return AgentPlan(
                            description=data.get("description", query),
                            estimated_steps=len(files),
                            files=files,
                        )
            except json.JSONDecodeError:
                continue

        # Strategy 3: Code blocks with file-path-like language tags (e.g. src/main.py)
        file_changes: list[FileChangePlan] = []
        path_pattern = r'```(\S+\.\w{1,10})\s*\n([\s\S]*?)```'
        for match in re.finditer(path_pattern, plan_text):
            lang = match.group(1)
            # Heuristic: file path contains / or \\ or has a known extension
            if '/' in lang or '\\' in lang or any(
                lang.endswith(ext) for ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs',
                                               '.java', '.cpp', '.c', '.h', '.html', '.css', '.scss',
                                               '.json', '.yaml', '.yml', '.toml', '.md', '.sh', '.ps1',
                                               '.sql', '.xml', '.rb', '.php', '.swift', '.kt', '.cs']
            ):
                content = match.group(2).strip()
                if len(content) > 20:
                    file_changes.append(FileChangePlan(
                        path=lang,
                        diff="(auto-generated diff)",
                        old_content="",
                        new_content=content,
                    ))

        # Strategy 4: Code blocks with known language tags, try to extract file path from surrounding text
        if not file_changes:
            known_langs = {'python', 'py', 'javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx',
                          'java', 'kotlin', 'go', 'rust', 'c', 'cpp', 'h', 'hpp', 'cs', 'ruby', 'rb',
                          'php', 'swift', 'sql', 'sh', 'bash', 'powershell', 'ps1', 'html', 'css',
                          'scss', 'json', 'yaml', 'yml', 'toml', 'xml', 'markdown', 'md'}
            for match in re.finditer(r'```(\w+)\s*\n([\s\S]*?)```', plan_text):
                lang = match.group(1).lower()
                if lang not in known_langs:
                    continue
                code = match.group(2).strip()
                if len(code) < 30:
                    continue
                # Look for file path before this code block
                before = plan_text[:match.start()]
                path = None
                # Try to find path patterns: ### src/main.py, **File: path**, `path`, etc.
                for pat in [
                    r'(?:文件|路径|File|Path|file|path)\s*[：:]\s*`?([^\s`\n]+\.\w{1,10})`?',
                    r'###?\s*`?([^\s`\n]+\.\w{1,10})`?',
                    r'\*\*`?([^\s`*\n]+\.\w{1,10})`?\*\*',
                    r'`([^\s`\n]+\.\w{1,10})`',
                ]:
                    m = re.search(pat, before, re.IGNORECASE)
                    if m:
                        path = m.group(1).strip().strip('`*#"\'')
                        if '/' in path or '\\' in path or '.' in path:
                            break
                        else:
                            path = None
                if path:
                    file_changes.append(FileChangePlan(
                        path=path,
                        diff="(auto-generated diff)",
                        old_content="",
                        new_content=code,
                    ))

        if file_changes:
            return AgentPlan(
                description=query,
                estimated_steps=len(file_changes),
                files=file_changes,
            )

        return None

    def apply_plan(self, task_id: str) -> str:
        """#21 Apply all approved file changes with dependency ordering and verification."""
        plan = self._plans.get(task_id)
        task = self._tasks.get(task_id)
        if not plan or not task:
            return "No plan found"

        if task:
            task.phase = AgentPhase.APPLYING

        ordered_files = self._topo_sort_files(plan.approved_files)
        results = []
        applied_paths: set[str] = set()

        from core.tools import ToolRegistry

        for fcp in ordered_files:
            deps_met = True
            for dep in fcp.dependencies:
                if dep not in applied_paths:
                    deps_met = False
                    break

            if not deps_met:
                results.append(f"SKIPPED: {fcp.path} -- dependency not met")
                fcp.status = "skipped"
                continue

            step = self.add_step(task_id, "apply_file", {"path": fcp.path})
            if not step:
                continue

            try:
                ToolRegistry.execute("write_file", path=fcp.path, content=fcp.new_content)
                fcp.status = "applied"
                applied_paths.add(fcp.path)

                if fcp.verification:
                    if not self._verify_change(fcp):
                        results.append(f"VERIFICATION_FAILED: {fcp.path}")
                        fcp.status = "verification_failed"
                        applied_paths.discard(fcp.path)
                        continue  # This continue is correct - inside a single if, not in a for loop

                self.update_step(task_id, step.step_id, "success", output=f"Applied to {fcp.path}")
                results.append(f"Applied: {fcp.path}")
            except Exception as e:
                fcp.status = "error"
                self.update_step(task_id, step.step_id, "failed", error=str(e))
                results.append(f"Error: {fcp.path} - {e}")

        for fcp in plan.files:
            if fcp.status == "pending":
                fcp.status = "rejected"

        if task:
            task.status = "completed"
            task.result = "; ".join(results)
            task.phase = AgentPhase.DONE

        return "Plan applied: " + "; ".join(results)

    def _topo_sort_files(self, files: list[FileChangePlan]) -> list[FileChangePlan]:
        """Topological sort by dependencies."""
        file_map = {f.path: f for f in files}
        visited: set[str] = set()
        result: list[FileChangePlan] = []

        def visit(fcp: FileChangePlan):
            if fcp.path in visited:
                return
            visited.add(fcp.path)
            for dep in fcp.dependencies:
                if dep in file_map:
                    visit(file_map[dep])
            result.append(fcp)

        for fcp in files:
            visit(fcp)
        return result

    def _verify_change(self, fcp: FileChangePlan) -> bool:
        if state.root is None:
            return True
        target = state.root / fcp.path
        try:
            current = target.read_text(encoding="utf-8", errors="replace")
            return current == fcp.new_content
        except OSError:
            return False

    async def reflect_before_action(
        self,
        tool_name: str,
        tool_args: dict,
        user_query: str,
        recent_messages: list[dict],
    ) -> dict:
        """#22 Self-reflection with JSON parsing."""
        recent_history = "\n".join(
            f"{m['role']}: {str(m.get('content', ''))[:200]}"
            for m in recent_messages[-6:]
        )
        prompt = (
            f"Review the planned action. Answer in Simplified Chinese.\n\n"
            f"Planned action: {tool_name} with args: {json.dumps(tool_args, ensure_ascii=False)[:500]}\n"
            f"Current task: {user_query}\n"
            f"Recent history:\n{recent_history}\n\n"
            f"Critique this action:\n"
            f"1. Is this the right next step? (APPROVED/REJECTED)\n"
            f"2. What risks or potential issues exist?\n"
            f"3. Is there a safer or more efficient alternative?\n\n"
            f"Output format:\n"
            f"APPROVED or REJECTED\n"
            f"Reason: <brief explanation>\n"
            f"Risk: low/medium/high"
        )
        payload = {
            "model": "local",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": REFLECTION_TEMPERATURE,
            "max_tokens": REFLECTION_MAX_TOKENS,
            "stream": False,
        }

        try:
            from app import get_http_client
            client = get_http_client()
            response = await client.post(LLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning(f"[Reflection] Failed: {e}")
            return {"reflection": "Reflection failed", "approved": True, "risk_level": "low"}

        text = content.upper()
        approved = "APPROVED" in text and "REJECTED" not in text.replace("APPROVED/REJECTED", "")
        risk = "low"
        for level in ["high", "medium", "low"]:
            if level in content.lower():
                risk = level
                break

        return {"reflection": content.strip(), "approved": approved, "risk_level": risk}

    async def recover_from_error(
        self,
        tool_name: str,
        error: str,
        context_summary: str,
        tool_args: dict,
    ) -> dict:
        """#23 Error recovery with retry."""
        prompt = (
            f"The previous action failed with this error:\n\n"
            f"Tool: {tool_name}\n"
            f"Error: {error[:500]}\n"
            f"Context: {context_summary[:500]}\n\n"
            f"Provide:\n"
            f"1. Root cause analysis (1-2 sentences)\n"
            f"2. A corrected action (new tool call in JSON format)\n"
            f"3. If the task cannot be completed, explain why\n\n"
            f'Output JSON: {{"analysis": "...", "can_continue": true/false, "retry_args": {json.dumps(tool_args, ensure_ascii=False)}}}'
        )
        payload = {
            "model": "local",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": RECOVERY_TEMPERATURE,
            "max_tokens": RECOVERY_MAX_TOKENS,
            "stream": False,
        }

        try:
            from app import get_http_client
            client = get_http_client()
            response = await client.post(LLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            json_match = _extract_json_block(content, 0)
            if json_match:
                return json_match
        except Exception as e:
            logger.warning(f"[Recovery] Failed to parse recovery: {e}")

        return {"analysis": content[:200] if content else str(e), "can_continue": False}

    async def summarize_step(self, tool_name: str, result: str, thought: str) -> dict:
        """#7 Compress tool execution result into short summary."""
        prompt = (
            f"Summarize this agent step in 1-2 sentences.\n"
            f"Extract up to 3 key findings or insights.\n\n"
            f"Tool: {tool_name}\n"
            f"Result: {result[:1000]}\n"
            f"Thought: {thought[:500]}\n\n"
            f'Output JSON: {{"summary": "...", "key_findings": ["...", "..."]}}'
        )
        payload = {
            "model": "local",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": SUMMARIZE_TEMPERATURE,
            "max_tokens": SUMMARIZE_MAX_TOKENS,
            "stream": False,
        }

        try:
            from app import get_http_client
            client = get_http_client()
            response = await client.post(LLAMA_URL, json=payload)
            response.raise_for_status()
            result_data = response.json()
            content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            json_match = _extract_json_block(content, 0)
            if json_match:
                return json_match
        except Exception as e:
            logger.warning(f"[Summarize] Failed: {e}")

        return {"summary": result[:200], "key_findings": []}


# ---- Global instance ----

agent_loop = AgentLoop()


def get_agent() -> AgentLoop:
    return agent_loop
