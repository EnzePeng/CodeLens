"""
ReActLoop — 精简重构的 ReAct 执行循环。

关键修复（对比 routes/agent.py 旧实现）
-----------------------------------
1. 显式参数 initial_context，告别脆弱的闭包作用域捕获（修 _context_for_injection bug）
2. 去掉"强制 list_directory / read_file"代码块 — 模型不调工具时直接视为完成
3. max_iterations 可配置（simple=6 / subtask=10 / root=25），不再硬编码 10
4. 全量只读工具 + 按需写工具（不再 max_tools=6 限制）
5. 上下文通过 ContextWindow 槽位管理，不再 messages[:1]+messages[-6:] 暴力截断
6. 工具结果通过 HierarchicalMemory 持久化，跨迭代不丢关键信息
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from logger import logger


# ---- 配置 ----

@dataclass
class ReActConfig:
    """
    ReAct 循环配置。

    设计理念（G1 简化后）：迭代上限是「软兜底」而非正常终止条件。
    正常情况下，任务在模型不再调用工具时自然结束（react.py 的 done 事件）。
    max_iterations 仅在以下异常情况触发，防止本地小模型无限循环：
      - 模型反复调用相同工具（死循环，已在前方检测并警告）
      - 模型持续产生重复内容（_is_repetitive 检测）
      - 真正的任务确实需要很多步（少数情况）
    上限值由任务级的 max_steps 决定（默认 15），经 capped() 应用。
    """
    max_iterations: int = 15          # 软兜底上限（经 capped(max_steps) 覆盖）
    max_tokens: int = 4096            # 单次 LLM 输出上限
    temperature: float = 0.0
    max_parallel_read: int = 6        # 并行读工具上限
    max_tool_result_chars: int = 8000 # 单工具结果截断
    max_retries_on_error: int = 2     # 工具失败重试次数

    def capped(self, max_steps: Optional[int]) -> "ReActConfig":
        """Apply a per-task iteration cap. Returns self (mutates in place)."""
        if max_steps is not None and max_steps > 0:
            self.max_iterations = min(self.max_iterations, int(max_steps))
        return self


# ---- 事件数据类 ----

@dataclass
class ReActEvent:
    """ReAct 循环输出的事件，供上层（engine）转成 AgentEvent 或 SSE。"""
    type: str
    data: Any = None
    timestamp: float = field(default_factory=time.time)


# ---- 工具发现 ----

# 全量只读工具 — 始终在 system prompt 里暴露
_READ_ONLY_TOOLS = {
    "read_file", "list_directory", "search_files",
    "code_analysis", "project", "diff_preview",
    "glob", "grep", "lsp",
}

# 写工具 — 按需加入
_WRITE_TOOLS = {
    "write_file", "edit_file", "apply_diff",
    "run_command", "git_operation", "file_operations",
    "undo_edit",
}


def select_tools_for_task(query: str, kind: str = "simple") -> list[dict]:
    """
    选择本轮 ReAct 要暴露给模型的工具。

    规则：
    - 只读工具全量暴露
    - 写工具根据 kind 和 query 判断：
        * kind == "simple" 且 query 不含写意图 → 不暴露写工具
        * 否则暴露全部写工具
    """
    from core.tools import ToolRegistry

    all_tools = {t["name"]: t for t in ToolRegistry.list_tools()}

    selected: list[str] = list(_READ_ONLY_TOOLS & set(all_tools.keys()))

    # 写意图判断
    write_intent = False
    if kind != "simple":
        write_intent = True
    else:
        q = query.lower()
        write_keywords = [
            "write", "create", "edit", "modify", "add", "delete", "rename",
            "refactor", "implement", "run", "execute", "commit", "push",
            "写", "创建", "修改", "添加", "删除", "重命名", "重构", "实现",
            "运行", "执行", "提交",
        ]
        write_intent = any(kw in q for kw in write_keywords)

    if write_intent:
        selected.extend(sorted(_WRITE_TOOLS & set(all_tools.keys())))

    # 按名字排序输出，保持 prompt 稳定
    selected = sorted(set(selected))
    return [all_tools[name] for name in selected if name in all_tools]


def build_system_prompt(tools: list[dict], focus_prompt: str = "") -> str:
    """构造 ReAct 的 system prompt — 精简、结构清晰，便于小模型正确跟随。"""
    # 工具列表：只显示工具名 + 参数名（不显示类型/描述，避免干扰）
    tool_lines: list[str] = []
    for t in tools:
        name = t["name"]
        params = t.get("parameters", {})
        if isinstance(params, dict) and params:
            param_names = [str(k) for k in params.keys()]
            tool_lines.append(f"- {name}({', '.join(param_names[:3])})")
        else:
            tool_lines.append(f"- {name}()")
    tools_desc = "\n".join(tool_lines)

    focus_section = ""
    if focus_prompt:
        focus_section = f"\n\n当前子任务:\n{focus_prompt}"

    return f"""你是一个代码助手。用工具完成任务，不要只描述你要做什么。

可用工具（括号内是参数名，必须精确使用）：
{tools_desc}

工具调用格式（直接写一行 JSON，不要代码块）：
{{"tool": "工具名", "args": {{"参数名": "值"}}}}

示例：
{{"tool": "read_file", "args": {{"path": "core/agent.py"}}}}
{{"tool": "list_directory", "args": {{"path": "core"}}}}
{{"tool": "grep", "args": {{"pattern": "class.*Engine"}}}}

重要：参数名必须严格匹配（read_file用path不是filename，search/grep用pattern不是query）。可一次调用多个工具，每行一个JSON。
- 用相对路径（core/agent.py 而非 ./core/agent.py）
- 需要读文件必须调 read_file
- 找不到文件先用 glob 或 list_directory 定位
- 任务完成用中文写总结，不要再调工具
{focus_section}"""


# ---- 工具调用解析（复用现有 parse_tool_calls）+ 参数归一化 ----

# 常见的 LLM 误用参数名 → 规范参数名
_PARAM_ALIASES = {
    # path 类的别名
    "filename": "path",
    "file_path": "path",
    "file": "path",
    "filepath": "path",
    "dir": "path",
    "directory": "path",
    "folder": "path",
    "target": "path",
    # pattern 类的别名
    "query": "pattern",
    "search": "pattern",
    "keyword": "pattern",
    "regex": "pattern",
    "term": "pattern",
    # command 类的别名
    "cmd": "command",
    "shell": "command",
    # content 类的别名
    "text": "content",
    "body": "content",
    "data": "content",
    # old_str / new_str 的常见别名
    "old_text": "old_str",
    "old_content": "old_str",
    "old": "old_str",
    "new_text": "new_str",
    "new_content": "new_str",
    "new": "new_str",
    "replacement": "new_str",
}


def _normalize_args(tool_name: str, args: dict) -> dict:
    """把常见的参数别名归一化到规范参数名。"""
    if not isinstance(args, dict):
        return args
    from core.tools import ToolRegistry
    try:
        defn = ToolRegistry.get_definition(tool_name)
        valid_params = set(defn.parameters.keys())
    except Exception:
        valid_params = set()

    normalized: dict = {}
    for k, v in args.items():
        # 已是规范名 → 直接用
        if k in valid_params:
            normalized[k] = v
            continue
        # 别名映射
        mapped = _PARAM_ALIASES.get(k.lower())
        if mapped and (mapped not in normalized):
            normalized[mapped] = v
            continue
        # 未知参数：保留（可能工具本身接受额外参数）
        normalized[k] = v
    return normalized


def _parse_tool_calls(text: str) -> list[dict[str, Any]]:
    from core.agent import parse_tool_calls
    raw = parse_tool_calls(text)
    # 归一化每个工具调用的参数
    for call in raw:
        name = call.get("tool", "")
        args = call.get("args", {}) or {}
        if isinstance(args, dict) and args:
            call["args"] = _normalize_args(name, args)
    return raw


# ---- 重复/循环检测 ----

def _is_repetitive(text: str) -> bool:
    """检测流式生成是否进入重复模式（如 "aaa" 或短语循环）。"""
    if len(text) < 60:
        return False

    words = text.split()
    # 1. 单词连续 5+ 次（放宽阈值，避免误报代码中的重复模式）
    if len(words) >= 5:
        for i in range(len(words) - 4):
            w = words[i].lower().strip(".,;:!?\"'`")
            if len(w) < 3:
                continue
            if (w == words[i+1].lower().strip(".,;:!?\"'`") ==
                words[i+2].lower().strip(".,;:!?\"'`") ==
                words[i+3].lower().strip(".,;:!?\"'`") ==
                words[i+4].lower().strip(".,;:!?\"'`")):
                return True

    # 2. 2-gram/3-gram 循环 4+ 次（仅检查尾部，避免历史内容误报）
    tail_words = words[-24:]  # 只检查最后 24 个单词
    if len(tail_words) >= 6:
        for n in [2, 3]:
            if len(tail_words) >= n * 4:
                for start in range(len(tail_words) - n * 4 + 1):
                    chunk = " ".join(tail_words[start:start+n]).lower()
                    count = 0
                    for j in range(start, len(tail_words) - n + 1):
                        if " ".join(tail_words[j:j+n]).lower() == chunk:
                            count += 1
                    if count >= 4:  # 提高阈值到 4 次，减少误报
                        return True
    return False


def _strip_think(text: str) -> str:
    """去除 <think>...</think> 块（包括未闭合的）。"""
    text = re.sub(r"<think>[\s\S]*?</think>\s*", "", text)
    text = re.sub(r"<think>[\s\S]*$", "", text)
    return text.strip()


def _strip_tool_call_json(text: str) -> str:
    """去除文本中的工具调用 JSON 块，保留自然语言部分。"""
    text = re.sub(r'\{"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{[\s\S]*?\}\s*\}', "", text)
    text = re.sub(r'```(?:json)?\s*\n\{[\s\S]*?```', "", text)
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
    return text.strip()


# ---- 主循环 ----

class ReActLoop:
    """
    ReAct 执行循环。

    典型用法：
        loop = ReActLoop(config=ReActConfig.for_simple(), memory=memory, context=ctx)
        async for event in loop.run(query, tools, initial_context=ctx_text):
            yield event
    """

    def __init__(
        self,
        config: ReActConfig,
        memory,          # HierarchicalMemory
        context,         # ContextWindow
        stop_checker: Optional[callable] = None,  # () -> bool, True 表示外部请求停止
    ) -> None:
        self.config = config
        self.memory = memory
        self.context = context
        self.stop_checker = stop_checker or (lambda: False)

    async def run(
        self,
        user_query: str,
        tools: list[dict],
        *,
        initial_context: str = "",
        subtask=None,   # 可选 SubTask
        focus_prompt: str = "",
    ) -> AsyncGenerator[ReActEvent, None]:
        """
        执行 ReAct 循环，产出 ReActEvent 流。

        initial_context
            注入到首轮上下文的信息（代码库 context 等）。显式参数，不走闭包。
        subtask
            当前执行的子任务（可选）。其 focus_prompt 会覆盖参数 focus_prompt。
        """
        # 初始化上下文槽位
        self.context.set_system(build_system_prompt(tools, focus_prompt or (subtask.focus_prompt if subtask else "")))
        self.context.set_user_query(
            subtask.description if subtask else user_query
        )
        if initial_context:
            self.context.set_work_summary(f"[初始上下文]\n{initial_context[:3000]}")

        # 状态
        iter_count = 0
        tool_calls_history: list[str] = []    # 工具名序列（循环检测）
        completed_work: set[str] = set()      # "tool:args_hash" 去重
        files_read: list[str] = []
        files_written: list[str] = []
        tools_used: list[str] = []

        def args_hash(tool_name: str, args: dict) -> str:
            canonical = json.dumps(args, sort_keys=True, ensure_ascii=False)
            h = hashlib.md5(canonical.encode()).hexdigest()[:12]
            return f"{tool_name}:{h}"

        while iter_count < self.config.max_iterations:
            if self.stop_checker():
                yield ReActEvent(type="stopped", data={"reason": "external_stop"})
                return

            iter_count += 1
            yield ReActEvent(type="iteration_start", data={"iteration": iter_count})

            # 1. 渲染上下文（槽位式）
            messages = self.context.render()

            # 2. 调 LLM（流式）
            full_response = ""
            repetitive_detected = False
            try:
                async for chunk in self._stream_llm(messages):
                    full_response += chunk
                    yield ReActEvent(type="thinking_chunk", data={"content": chunk})
                    if _is_repetitive(full_response):
                        repetitive_detected = True
                        yield ReActEvent(type="warning", data={"message": "检测到重复生成，提前停止"})
                        break
            except Exception as e:
                yield ReActEvent(type="error", data={"message": f"LLM 调用失败: {e}"})
                return

            # 处理重复：截掉重复尾部
            if repetitive_detected:
                full_response = self._truncate_repetitive(full_response)

            # 记录最新一次 LLM 输出，供迭代上限时作为兜底 summary
            self._last_llm_response = full_response

            yield ReActEvent(type="llm_response", data={"content": full_response})

            # 3. 解析工具调用
            tool_calls = _parse_tool_calls(full_response)

            # 4. 没有工具调用 → 任务完成（不再强制 list_directory）
            if not tool_calls:
                clean = _strip_think(full_response)
                clean = _strip_tool_call_json(clean)
                yield ReActEvent(type="done", data={"result": clean or full_response})
                return

            # 5. 去重（避免模型反复调用同工具同参数）
            deduped: list[dict] = []
            for tc in tool_calls:
                name = tc.get("tool", "")
                args = tc.get("args", {}) or {}
                h = args_hash(name, args)
                if h in completed_work and name != "read_file":
                    yield ReActEvent(type="warning", data={"message": f"跳过重复调用: {name}"})
                    continue
                # read_file 允许重读（内容可能截断），但同文件同参数也要去重
                if name == "read_file" and h in completed_work:
                    # 只有没带 start_line/end_line 的 read 才去重
                    if "start_line" not in args and "end_line" not in args:
                        yield ReActEvent(type="warning", data={"message": f"跳过重复读取: {args.get('path')}"})
                        continue
                deduped.append(tc)
            tool_calls = deduped

            if not tool_calls:
                clean = _strip_think(full_response)
                clean = _strip_tool_call_json(clean)
                yield ReActEvent(type="done", data={"result": clean or full_response})
                return

            # 6. 把 assistant 的完整输出塞上下文（截短）
            self.context.append_message("assistant", full_response[:3000])

            # 7. 执行工具（只读并行，写顺序）
            yield ReActEvent(type="tool_call_batch", data={
                "count": len(tool_calls),
                "tools": [tc.get("tool") for tc in tool_calls],
            })
            for tc in tool_calls:
                yield ReActEvent(type="tool_call", data={
                    "tool": tc.get("tool", ""),
                    "args": tc.get("args", {}),
                })

            results = await self._execute_tools(tool_calls)

            # 8. 处理结果：注入上下文 + 更新记忆 + 事件通知
            for res in results:
                name = res.get("tool", "")
                args = res.get("args", {}) or {}
                h = args_hash(name, args)
                completed_work.add(h)
                tools_used.append(name)
                self.memory.record_tool_use(name, args)

                if res.get("success"):
                    result_str = str(res.get("result", ""))
                    if len(result_str) > self.config.max_tool_result_chars:
                        result_str = result_str[: self.config.max_tool_result_chars] + "\n...(结果过长已截断)"
                    # 注入到 working 消息
                    self.context.append_message(
                        "user",
                        f"Tool {name} result:\n{result_str}",
                    )
                    # 更新统计
                    if name == "read_file" and args.get("path"):
                        files_read.append(args["path"])
                    elif name in ("write_file", "edit_file", "apply_diff") and args.get("path"):
                        files_written.append(args["path"])
                    yield ReActEvent(type="tool_result", data={
                        "tool": name,
                        "result": result_str[:2000],
                    })
                else:
                    error_msg = res.get("error", "Unknown error")
                    self.context.append_message(
                        "user",
                        f"Tool {name} FAILED with error:\n{error_msg}\n\n请检查参数后重试，或尝试其他方法。",
                    )
                    yield ReActEvent(type="tool_error", data={
                        "tool": name,
                        "error": error_msg,
                    })

            # 9. 更新 work_summary（反映最新进度）
            work_summary = self.memory.render_work_summary(max_chars=1200)
            if work_summary:
                self.context.set_work_summary(work_summary)

            # 10. 上下文溢出压缩
            if self.context.needs_compression():
                yield ReActEvent(type="info", data={"message": "上下文接近上限，压缩历史消息..."})
                self._compress_old_messages()

            # 11. 循环检测（连续相同工具+参数调用 3 次 → 警告）
            # 记录完整的调用签名（工具名+参数哈希），避免参数不同时误报
            tool_calls_history.extend(
                f"{tc.get('tool', '')}:{args_hash(tc.get('tool', ''), tc.get('args', {}) or {})}"
                for tc in tool_calls
            )
            if len(tool_calls_history) >= 3:
                last_three = tool_calls_history[-3:]
                if len(set(last_three)) == 1:
                    tool_name = tool_calls[0].get("tool", "") if tool_calls else "?"
                    warn = f"你已经连续 3 次以相同参数调用 {tool_name}。请换一种方法或结束任务。"
                    self.context.append_message("user", warn)
                    yield ReActEvent(type="warning", data={"message": warn})

        # 软兜底：达到迭代上限。把最后一次 LLM 输出 + 工作摘要一起返回。
        # 这是异常路径（正常应靠模型不再调用工具自然结束），标记 hit_limit
        # 让上层（_run_subtask）把 status 判为 partial 而非 success。
        last_llm_text = getattr(self, "_last_llm_response", "") or ""
        limit_msg = f"[已达到迭代上限 {self.config.max_iterations}（软兜底），任务可能未完全完成]\n\n"
        if last_llm_text:
            limit_msg += f"最后一次输出:\n{last_llm_text[:1500]}\n\n"
        limit_msg += f"工作摘要:\n{self.memory.render_work_summary(800)}"
        yield ReActEvent(type="done", data={"result": limit_msg, "hit_limit": True})

    # ---- 内部：LLM 流式调用 ----

    async def _stream_llm(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        from core.llm_client import llm_client
        try:
            async for chunk in llm_client.call_streaming(
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                task_type="agent",
            ):
                if chunk.content:
                    yield chunk.content
        except Exception:
            raise

    # ---- 内部：工具执行（只读并行，写顺序） ----

    async def _execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        from core.tools import ToolRegistry

        read_calls = [tc for tc in tool_calls if tc.get("tool") in _READ_ONLY_TOOLS]
        write_calls = [tc for tc in tool_calls if tc.get("tool") not in _READ_ONLY_TOOLS]

        results: list[dict] = []

        # 并行执行只读工具（带上限）
        if read_calls:
            sem = asyncio.Semaphore(self.config.max_parallel_read)

            async def _run_read(tc):
                async with sem:
                    return await asyncio.to_thread(self._exec_one, tc)

            read_results = await asyncio.gather(*[_run_read(tc) for tc in read_calls])
            results.extend(read_results)

        # 顺序执行写工具
        for tc in write_calls:
            results.append(await asyncio.to_thread(self._exec_one, tc))

        return results

    def _exec_one(self, tc: dict) -> dict:
        from core.tools import ToolRegistry
        name = tc.get("tool", "")
        args = tc.get("args", {}) or {}
        retries = self.config.max_retries_on_error
        last_err: Optional[str] = None
        for attempt in range(retries + 1):
            try:
                result = ToolRegistry.execute(name, **args)
                return {"tool": name, "args": args, "result": result, "success": True}
            except Exception as e:
                last_err = str(e)
                if attempt < retries:
                    logger.warning(f"[ReAct] 工具 {name} 第 {attempt+1} 次失败，重试: {e}")
                    continue
        return {"tool": name, "args": args, "error": last_err, "success": False}

    # ---- 内部：压缩 ----

    def _compress_old_messages(self) -> None:
        """把超出 recent_n 的旧消息压缩成 summary。"""
        from core.context import build_summary_message
        excess = self.context.excess_message_count()
        if excess <= 0:
            return
        popped = self.context.pop_oldest_messages(excess)
        if not popped:
            return
        summary = build_summary_message(popped)
        if summary:
            self.context.append_summary(summary)

    # ---- 内部：重复截断 ----

    def _truncate_repetitive(self, text: str) -> str:
        """智能截断重复文本：从尾部向前寻找重复起始点，保留更多有效内容。"""
        if len(text) < 100:
            return text

        words = text.split()
        # 从尾部开始，向前查找重复开始的最近位置
        # 找到最后一个"看起来正常"的段落边界
        best_cut = len(words) // 2  # 默认取前半段

        # 尝试在尾部找到重复段的起始点
        tail = words[-20:]  # 检查最后20个词
        for n in [2, 3]:
            if len(tail) < n * 3:
                continue
            for start in range(len(tail) - n * 3 + 1):
                chunk = " ".join(tail[start:start + n]).lower()
                count = 0
                for j in range(start, len(tail) - n + 1):
                    if " ".join(tail[j:j + n]).lower() == chunk:
                        count += 1
                if count >= 3:
                    # 在重复开始之前截断（在文本的绝对位置上）
                    abs_pos = len(words) - 20 + start
                    if abs_pos > 50:  # 至少保留50个词
                        best_cut = min(best_cut, abs_pos)

        return " ".join(words[:best_cut])
