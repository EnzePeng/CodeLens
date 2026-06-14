"""
Tool Call Parser - Structured extraction of tool calls from LLM output

Supports multiple parsing strategies for robust tool call extraction.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


def _extract_json_block(text: str, start: int, max_len: int = 2000) -> Optional[dict]:
    """Extract a complete JSON object from text starting at position `start` using brace depth counting."""
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
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
    return None


class ParseStrategy(Enum):
    """解析策略"""
    JSON_BLOCK = "json_block"
    XML_TAG = "xml_tag"
    MARKDOWN_CODE = "markdown_code"
    NATURAL_LANGUAGE = "natural_language"


@dataclass
class ToolCall:
    """结构化工具调用"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    strategy: ParseStrategy = ParseStrategy.JSON_BLOCK
    raw_text: str = ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.name,
            "args": self.args,
            "confidence": self.confidence,
        }


@dataclass
class ParseResult:
    """解析结果"""
    tool_calls: list[ToolCall] = field(default_factory=list)
    text_before: str = ""
    text_after: str = ""
    has_tool_calls: bool = False
    parse_warnings: list[str] = field(default_factory=list)
    raw_text: str = ""


class ToolCallParser:
    """
    从LLM输出中提取结构化工具调用
    
    支持多种解析策略:
    1. JSON代码块: ```json\n{"tool": "name", "args": {...}}\n```
    2. XML标签: <tool_call>{"tool": "name", "args": {...}}</tool_call>
    3. Markdown代码块: ```tool_name\nargs...\n```
    4. 自然语言: "I need to read file src/main.py"
    """
    
    def __init__(self, available_tools: list[str] = None):
        self._available_tools = set(available_tools) if available_tools else set()
        self._tool_aliases: dict[str, str] = {
            "read": "read_file",
            "write": "write_file",
            "edit": "edit_file",
            "search": "search_files",
            "list": "list_directory",
            "run": "run_command",
            "exec": "run_command",
            "execute": "run_command",
            "git": "git_operation",
            "glob": "glob",
            "grep": "grep",
        }
    
    def parse(self, text: str) -> ParseResult:
        """
        解析LLM输出，提取工具调用
        
        Args:
            text: LLM的完整输出
            
        Returns:
            ParseResult包含工具调用列表和元数据
        """
        result = ParseResult(raw_text=text)
        
        # Remove <think>...</think> blocks to avoid interference with JSON parsing
        import re
        clean_text = re.sub(r'<think>[\s\S]*?</think>', '', text)
        
        # Normalize garbled JSON: strip spaces before quotes, fix common issues
        normalized_text = re.sub(r'\s+"', '"', clean_text)
        normalized_text = re.sub(r":\s+", ": ", normalized_text)
        
        # 尝试所有解析策略 (try normalized first, then original)
        strategies = [
            self._parse_json_blocks,
            self._parse_xml_tags,
            self._parse_markdown_code_blocks,
            self._parse_natural_language,
        ]
        
        for strategy in strategies:
            try:
                # Try normalized text first
                calls = strategy(normalized_text)
                if calls:
                    result.tool_calls.extend(calls)
                    result.has_tool_calls = True
                    continue
                # Fallback to original text
                calls = strategy(clean_text)
                if calls:
                    result.tool_calls.extend(calls)
                    result.has_tool_calls = True
            except Exception as e:
                result.parse_warnings.append(f"{strategy.__name__}: {str(e)}")
        
        # 去重（基于工具名和参数）
        result.tool_calls = self._deduplicate(result.tool_calls)
        
        # 提取工具调用前后的文本
        if result.tool_calls:
            result.text_before = self._extract_text_before(text, result.tool_calls)
            result.text_after = self._extract_text_after(text, result.tool_calls)
        
        return result
    
    def _parse_json_blocks(self, text: str) -> list[ToolCall]:
        """解析JSON代码块"""
        calls = []
        
        # 匹配 ```json ... ``` 或 ``` ... ```
        pattern = r'```(?:json)?\s*\n([\s\S]*?)```'
        for match in re.finditer(pattern, text):
            content = match.group(1).strip()
            try:
                data = json.loads(content)
                call = self._parse_tool_call_dict(data)
                if call:
                    calls.append(call)
            except json.JSONDecodeError:
                # Try to fix garbled JSON
                fixed = self._repair_json(content)
                if fixed:
                    try:
                        data = json.loads(fixed)
                        call = self._parse_tool_call_dict(data)
                        if call:
                            calls.append(call)
                    except json.JSONDecodeError:
                        pass
                if not calls:
                    call = self._extract_json_from_text(content)
                    if call:
                        calls.append(call)
        
        # 匹配独立的JSON对象（支持嵌套）
        seen = set()
        for i, ch in enumerate(text):
            if ch == '{':
                obj = _extract_json_block(text, i)
                # Check for "tool" key (may have leading whitespace in garbled JSON)
                has_tool_key = obj and any(k.strip() == "tool" for k in obj.keys())
                if has_tool_key:
                    key = json.dumps(obj, sort_keys=True)
                    if key not in seen:
                        seen.add(key)
                        call = self._parse_tool_call_dict(obj)
                        if call:
                            calls.append(call)
        
        # Fallback: try to extract tool call from garbled text
        if not calls:
            call = self._extract_json_from_text(text)
            if call:
                calls.append(call)
        
        return calls
    
    def _repair_json(self, text: str) -> Optional[str]:
        """尝试修复常见的JSON格式问题"""
        fixed = text.strip()
        
        # Remove leading/trailing garbage
        fixed = re.sub(r'^[^{]*', '', fixed)
        fixed = re.sub(r'[^}]*$', '', fixed)
        
        # Fix missing quotes around keys: tool -> "tool"
        fixed = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r' "\1":', fixed)
        
        # Fix missing quotes around string values (not numbers/bools)
        fixed = re.sub(r':\s*([A-Za-z_]\w*)\s*([,}])', r': "\1"\2', fixed)
        # But undo for true/false/null and numbers
        fixed = re.sub(r': "(true|false|null)"', r': \1', fixed)
        fixed = re.sub(r': "(\d+\.?\d*)"', r': \1', fixed)
        
        # Remove trailing commas
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        
        # Try to balance braces
        depth = 0
        for c in fixed:
            if c == '{': depth += 1
            elif c == '}': depth -= 1
        while depth > 0:
            fixed += '}'
            depth -= 1
        
        # Validate it contains "tool"
        if '"tool"' not in fixed and "'tool'" not in fixed:
            return None
        
        return fixed
    
    def _parse_xml_tags(self, text: str) -> list[ToolCall]:
        """解析XML标签"""
        calls = []
        
        # 匹配 <tool_call>...</tool_call>
        pattern = r'<tool_call>\s*([\s\S]*?)\s*</tool_call>'
        for match in re.finditer(pattern, text):
            content = match.group(1).strip()
            try:
                data = json.loads(content)
                call = self._parse_tool_call_dict(data)
                if call:
                    calls.append(call)
            except json.JSONDecodeError:
                continue
        
        # 匹配 <tool name="...">...</tool>
        pattern = r'<tool\s+name="([^"]+)">\s*([\s\S]*?)\s*</tool>'
        for match in re.finditer(pattern, text):
            tool_name = match.group(1)
            content = match.group(2).strip()
            try:
                args = json.loads(content) if content else {}
                calls.append(ToolCall(
                    name=self._resolve_tool_name(tool_name),
                    args=args,
                    strategy=ParseStrategy.XML_TAG,
                ))
            except json.JSONDecodeError:
                # 尝试作为简单参数
                calls.append(ToolCall(
                    name=self._resolve_tool_name(tool_name),
                    args={"content": content},
                    strategy=ParseStrategy.XML_TAG,
                    confidence=0.7,
                ))
        
        return calls
    
    def _parse_markdown_code_blocks(self, text: str) -> list[ToolCall]:
        """解析Markdown代码块"""
        calls = []
        
        # 匹配 ```tool_name\n...\n```
        pattern = r'```(\w+)\s*\n([\s\S]*?)```'
        for match in re.finditer(pattern, text):
            lang = match.group(1).lower()
            content = match.group(2).strip()
            
            # 检查是否是已知工具名
            tool_name = self._resolve_tool_name(lang)
            if tool_name and tool_name in self._available_tools:
                # 尝试解析参数
                args = self._parse_tool_args(tool_name, content)
                calls.append(ToolCall(
                    name=tool_name,
                    args=args,
                    strategy=ParseStrategy.MARKDOWN_CODE,
                    confidence=0.8,
                ))
        
        return calls
    
    def _parse_natural_language(self, text: str) -> list[ToolCall]:
        """解析自然语言描述的工具调用"""
        calls = []
        
        # 只有在没有其他解析结果时才使用自然语言解析
        # 这是最后的fallback，置信度较低
        
        # 匹配带反引号的文件路径（更可靠）
        patterns = [
            (r'read\s+(?:file\s+)?`([^\s`]+)`', 'read_file', ['path']),
            (r'write\s+(?:to\s+)?`([^\s`]+)`', 'write_file', ['path']),
            (r'edit\s+`([^\s`]+)`', 'edit_file', ['path']),
            (r'search\s+(?:for\s+)?`([^\s`]+)`', 'search_files', ['pattern']),
            (r'run\s+`([^`]+)`', 'run_command', ['command']),
            (r'execute\s+`([^`]+)`', 'run_command', ['command']),
        ]
        
        for pattern, tool_name, arg_keys in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if tool_name in self._available_tools:
                    args = {}
                    for i, group in enumerate(match.groups()):
                        if i < len(arg_keys):
                            args[arg_keys[i]] = group
                    calls.append(ToolCall(
                        name=tool_name,
                        args=args,
                        strategy=ParseStrategy.NATURAL_LANGUAGE,
                        confidence=0.5,  # 自然语言解析置信度较低
                    ))
        
        return calls
    
    def _parse_tool_call_dict(self, data: dict) -> Optional[ToolCall]:
        """从字典解析工具调用"""
        if not isinstance(data, dict):
            return None
        
        # Strip whitespace from keys
        data = {k.strip(): v for k, v in data.items()}
        
        tool_name = data.get("tool") or data.get("name") or data.get("function")
        if not tool_name:
            return None
        
        args = data.get("args") or data.get("arguments") or data.get("parameters") or {}
        # Strip whitespace from arg keys too
        if isinstance(args, dict):
            args = {k.strip(): v for k, v in args.items()}
        
        tool_name = self._resolve_tool_name(tool_name)
        if not tool_name:
            return None
        
        return ToolCall(
            name=tool_name,
            args=args,
            strategy=ParseStrategy.JSON_BLOCK,
        )
    
    def _extract_json_from_text(self, text: str) -> Optional[ToolCall]:
        """从文本中提取部分JSON - 更健壮的版本"""
        # Strip ALL spaces before quotes to normalize garbled JSON
        normalized = re.sub(r'\s+"', '"', text)
        # Also strip spaces after colons/commas for cleaner parsing
        normalized = re.sub(r':\s+', ': ', normalized)
        
        # 尝试找到tool和args
        tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', normalized)
        if not tool_match:
            tool_match = re.search(r'"name"\s*:\s*"([^"]+)"', normalized)
        
        if not tool_match:
            return None
        
        tool_name = self._resolve_tool_name(tool_match.group(1))
        if not tool_name:
            return None
        
        # 尝试提取args - 使用更宽松的匹配
        args = {}
        # 尝试找到 "args" 后面的 JSON 对象
        args_match = re.search(r'"args"\s*:\s*(\{)', normalized)
        if args_match:
            start = args_match.start(1)
            # 使用 brace counting 来提取完整的 JSON 对象
            depth = 0
            end = start
            for i in range(start, min(start + 2000, len(normalized))):
                if normalized[i] == '{':
                    depth += 1
                elif normalized[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > start:
                try:
                    args = json.loads(normalized[start:end])
                except json.JSONDecodeError:
                    # 尝试修复常见的问题（尾部逗号等）
                    args_str = normalized[start:end]
                    args_str = re.sub(r',\s*}', '}', args_str)
                    args_str = re.sub(r',\s*]', ']', args_str)
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        pass
        
        return ToolCall(
            name=tool_name,
            args=args,
            confidence=0.7,
        )
    
    def _resolve_tool_name(self, name: str) -> Optional[str]:
        """解析工具名（处理别名和模糊匹配）"""
        name = name.lower().strip()
        
        # 直接匹配
        if name in self._available_tools:
            return name
        
        # 别名匹配
        if name in self._tool_aliases:
            resolved = self._tool_aliases[name]
            if resolved in self._available_tools:
                return resolved
        
        # Normalize: remove separators and trailing s/ies
        def _norm(s):
            s = s.lower().replace("-", "_").replace(" ", "_")
            if s.endswith("ies"):
                s = s[:-3] + "y"
            elif s.endswith("es"):
                s = s[:-2]
            elif s.endswith("s"):
                s = s[:-1]
            return s
        
        normalized = _norm(name)
        if normalized in self._available_tools:
            return normalized
        
        # 尝试部分匹配
        name_flat = name.replace("_", "").replace("-", "").replace(" ", "")
        for tool in self._available_tools:
            tool_flat = tool.replace("_", "")
            if tool_flat in name_flat or name_flat in tool_flat:
                return tool
        
        return None
    
    def _parse_tool_args(self, tool_name: str, content: str) -> dict[str, Any]:
        """解析工具参数"""
        # 尝试JSON解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # 根据工具名推断参数
        if tool_name == "read_file":
            return {"path": content.strip()}
        elif tool_name == "write_file":
            # 尝试分割路径和内容
            lines = content.split("\n", 1)
            if len(lines) == 2:
                return {"path": lines[0].strip(), "content": lines[1]}
            return {"content": content}
        elif tool_name == "run_command":
            return {"command": content.strip()}
        elif tool_name == "search_files":
            return {"pattern": content.strip()}
        
        return {"content": content}
    
    def _deduplicate(self, calls: list[ToolCall]) -> list[ToolCall]:
        """去重工具调用 - 优先保留高置信度的调用"""
        if not calls:
            return []
        
        # 按置信度排序，高置信度优先
        sorted_calls = sorted(calls, key=lambda c: c.confidence, reverse=True)
        
        seen = set()
        result = []
        
        for call in sorted_calls:
            # 创建去重键：工具名 + 参数的关键部分
            args_key = json.dumps(call.args, sort_keys=True)
            key = (call.name, args_key)
            
            if key not in seen:
                seen.add(key)
                result.append(call)
            elif call.confidence > 0.8:
                # 如果是高置信度调用，替换低置信度的
                for i, existing in enumerate(result):
                    existing_key = (existing.name, json.dumps(existing.args, sort_keys=True))
                    if existing_key == key and existing.confidence < call.confidence:
                        result[i] = call
                        break
        
        return result
    
    def _extract_text_before(self, text: str, calls: list[ToolCall]) -> str:
        """提取工具调用前的文本"""
        # 简单实现：取前1000字符
        return text[:1000] if len(text) > 1000 else text
    
    def _extract_text_after(self, text: str, calls: list[ToolCall]) -> str:
        """提取工具调用后的文本"""
        # 简单实现：取后500字符
        return text[-500:] if len(text) > 500 else ""


# 全局实例
def create_parser(available_tools: list[str] = None) -> ToolCallParser:
    """创建工具调用解析器"""
    return ToolCallParser(available_tools)


# 默认解析器（会在Agent初始化时配置）
_default_parser: Optional[ToolCallParser] = None


def get_parser() -> ToolCallParser:
    """获取默认解析器"""
    global _default_parser
    if _default_parser is None:
        _default_parser = ToolCallParser()
    return _default_parser


def set_parser(parser: ToolCallParser) -> None:
    """设置默认解析器"""
    global _default_parser
    _default_parser = parser
