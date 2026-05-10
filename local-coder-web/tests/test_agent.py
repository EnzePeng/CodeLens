"""
Tests for Agent core functionality.
"""
import pytest
import time

from core.agent import AgentLoop, AgentConfig, get_agent
from models import AgentState


def test_agent_config():
    """Test Agent configuration."""
    config = AgentConfig()
    assert config.max_steps == 15
    assert config.timeout == 60
    
    config2 = AgentConfig(max_steps=10, timeout=30)
    assert config2.max_steps == 10
    assert config2.timeout == 30


def test_agent_loop_creation():
    """Test Agent loop creation."""
    agent = AgentLoop()
    assert agent.config.max_steps == 15
    assert len(agent._tasks) == 0


def test_start_task():
    """Test starting a new task."""
    agent = AgentLoop()
    task_id = agent.start_task("Test query")
    
    assert task_id is not None
    assert len(task_id) > 0
    
    task = agent.get_task(task_id)
    assert task is not None
    assert task.user_query == "Test query"
    assert task.status == "running"


def test_get_all_tasks():
    """Test getting all tasks."""
    agent = AgentLoop()
    
    id1 = agent.start_task("Query 1")
    id2 = agent.start_task("Query 2")
    
    tasks = agent.get_all_tasks()
    assert len(tasks) == 2
    assert id1 in tasks
    assert id2 in tasks


def test_pause_resume_task():
    """Test pausing and resuming task."""
    agent = AgentLoop()
    task_id = agent.start_task("Test query")
    
    # Pause
    assert agent.pause_task(task_id) is True
    task = agent.get_task(task_id)
    assert task.status == "paused"
    
    # Resume
    assert agent.resume_task(task_id) is True
    task = agent.get_task(task_id)
    assert task.status == "running"


def test_stop_task():
    """Test stopping task."""
    agent = AgentLoop()
    task_id = agent.start_task("Test query")
    
    result = agent.stop_task(task_id, "user_stopped")
    assert result is True
    
    task = agent.get_task(task_id)
    assert task.status == "stopped"
    assert task.result == "user_stopped"


def test_add_step():
    """Test adding steps to task."""
    agent = AgentLoop()
    task_id = agent.start_task("Test query")
    
    step = agent.add_step(task_id, "read_file", {"path": "main.py"})
    assert step is not None
    assert step.tool_name == "read_file"
    assert step.status == "running"
    
    task = agent.get_task(task_id)
    assert len(task.steps) == 1


def test_update_step():
    """Test updating step status."""
    agent = AgentLoop()
    task_id = agent.start_task("Test query")
    
    step = agent.add_step(task_id, "read_file", {"path": "main.py"})
    
    # Update to success
    result = agent.update_step(task_id, 0, "success", "File content here")
    assert result is True
    
    task = agent.get_task(task_id)
    assert task.steps[0].status == "success"
    assert task.steps[0].tool_output == "File content here"
    assert task.steps[0].duration >= 0


def test_should_continue():
    """Test task continuation logic."""
    agent = AgentLoop(config=AgentConfig(max_steps=3))
    task_id = agent.start_task("Test query")
    
    # Initially should continue
    assert agent.should_continue(task_id) is True
    
    # Add steps
    agent.add_step(task_id, "tool1", {})
    agent.add_step(task_id, "tool2", {})
    agent.add_step(task_id, "tool3", {})
    
    # Should stop (max steps reached)
    assert agent.should_continue(task_id) is False
    
    task = agent.get_task(task_id)
    assert task.status == "failed"
    assert "Max steps" in task.result


def test_should_continue_when_stopped():
    """Test should_continue when task is stopped."""
    agent = AgentLoop()
    task_id = agent.start_task("Test query")
    
    agent.stop_task(task_id, "completed")
    assert agent.should_continue(task_id) is False


def test_parse_tool_calls():
    """Test parsing tool calls from LLM output."""
    agent = AgentLoop()
    
    from core.agent import parse_tool_calls

    # Test JSON format
    text = '{"tool": "read_file", "args": {"path": "main.py"}}'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "read_file"
    assert calls[0]["args"]["path"] == "main.py"

    # Test multiple tool calls
    text2 = '''
    {"tool": "read_file", "args": {"path": "a.py"}}
    {"tool": "write_file", "args": {"path": "b.py", "content": "test"}}
    '''
    calls2 = parse_tool_calls(text2)
    assert len(calls2) == 2


def test_generate_system_prompt():
    """Test system prompt generation."""
    agent = AgentLoop()
    
    tools = [
        {"name": "read_file", "description": "Read a file", "parameters": {"path": {"type": "string"}}},
        {"name": "write_file", "description": "Write a file", "parameters": {"path": {}, "content": {}}},
    ]
    
    prompt = agent.generate_system_prompt(tools)
    
    assert "read_file" in prompt
    assert "write_file" in prompt
    assert "tool_name" in prompt
    assert "args" in prompt


def test_get_agent_singleton():
    """Test get_agent returns singleton."""
    agent1 = get_agent()
    agent2 = get_agent()
    
    assert agent1 is agent2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])