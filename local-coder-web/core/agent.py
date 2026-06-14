"""
Tool-call parsing utilities.

Historically this module held the full AgentLoop plus a large set of data
classes (AgentConfig, AgentPlan, FileChangePlan, TaskIntent, AgentPhase,
AgentEvent, get_agent). After the engine was split into core.engine +
core.react, all of those became dead code and were removed.

What remains is the one piece still depended upon at runtime:
  - parse_tool_calls / _extract_json_block  ← used by core.react.ReActLoop
"""
from __future__ import annotations

import json
from typing import Any, Optional


# ---- JSON 提取工具 ----

def _extract_json_block(text: str, start: int, max_len: int = 2000) -> Optional[dict]:
    """用 brace depth 计数提取完整 JSON 对象。"""
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


def parse_tool_calls(text: str, available_tools: list[str] | None = None) -> list[dict[str, Any]]:
    """
    从 LLM 输出解析工具调用列表。

    兼容层：委托给 core.tool_call_parser.ToolCallParser。
    """
    from core.tool_call_parser import ToolCallParser

    if available_tools is None:
        from core.tools import ToolRegistry
        available_tools = [t["name"] for t in ToolRegistry.list_tools()]

    parser = ToolCallParser(available_tools)
    result = parser.parse(text)
    return [call.to_dict() for call in result.tool_calls]
