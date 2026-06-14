"""Tests for ToolCallParser."""
import json
from core.tool_call_parser import ToolCallParser, ToolCall, ParseStrategy


def test_parse_json_block():
    parser = ToolCallParser(available_tools=["read_file", "write_file"])
    
    text = '''Here is my plan:

```json
{"tool": "read_file", "args": {"path": "src/main.py"}}
```

Let me know what you think.'''
    
    result = parser.parse(text)
    
    assert result.has_tool_calls
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].args["path"] == "src/main.py"


def test_parse_xml_tag():
    parser = ToolCallParser(available_tools=["read_file"])
    
    text = '''I'll read the file.

<tool_call>
{"tool": "read_file", "args": {"path": "test.py"}}
</tool_call>'''
    
    result = parser.parse(text)
    
    assert result.has_tool_calls
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "read_file"


def test_parse_markdown_code():
    parser = ToolCallParser(available_tools=["read_file", "write_file"])
    
    text = '''Let me write the file:

```write_file
{"path": "output.txt", "content": "Hello World"}
```'''
    
    result = parser.parse(text)
    
    assert result.has_tool_calls
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "write_file"


def test_parse_multiple_calls():
    parser = ToolCallParser(available_tools=["read_file", "write_file", "search_files"])
    
    text = '''First I'll search:

```json
{"tool": "search_files", "args": {"pattern": "TODO"}}
```

Then read the file:

```json
{"tool": "read_file", "args": {"path": "src/main.py"}}
```'''
    
    result = parser.parse(text)
    
    assert result.has_tool_calls
    assert len(result.tool_calls) == 2


def test_tool_alias():
    parser = ToolCallParser(available_tools=["read_file", "write_file"])
    
    text = '''```json
{"tool": "read", "args": {"path": "test.py"}}
```'''
    
    result = parser.parse(text)
    
    assert result.has_tool_calls
    assert result.tool_calls[0].name == "read_file"


def test_no_tool_calls():
    parser = ToolCallParser(available_tools=["read_file"])
    
    text = '''This is a normal response without any tool calls.'''
    
    result = parser.parse(text)
    
    assert not result.has_tool_calls
    assert len(result.tool_calls) == 0


def test_tool_call_to_dict():
    call = ToolCall(
        name="read_file",
        args={"path": "test.py"},
        confidence=0.9,
    )
    
    d = call.to_dict()
    
    assert d["tool"] == "read_file"
    assert d["args"]["path"] == "test.py"
    assert d["confidence"] == 0.9


def test_deduplication():
    parser = ToolCallParser(available_tools=["read_file"])
    
    text = '''```json
{"tool": "read_file", "args": {"path": "test.py"}}
```

```json
{"tool": "read_file", "args": {"path": "test.py"}}
```'''
    
    result = parser.parse(text)
    
    # 应该去重
    assert len(result.tool_calls) == 1
