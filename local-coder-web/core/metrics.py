"""
Agent Metrics - Enhanced self-iteration optimization system

Collects metrics, analyzes bottlenecks, and suggests optimizations.
Supports iteration tracking for continuous self-improvement.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path
from collections import defaultdict, deque
from threading import Lock


@dataclass
class TaskRecord:
    """Record of a single task execution."""
    task_id: str
    query: str
    intent_type: str
    steps: int
    duration: float
    success: bool
    tools_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolStats:
    """Statistics for a tool."""
    name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration: float = 0
    total_duration: float = 0


@dataclass
class PerformanceMetric:
    """单次性能指标"""
    name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentIteration:
    """单次迭代记录"""
    iteration_id: int
    start_time: float
    end_time: float = 0
    tasks_completed: int = 0
    success_rate: float = 0
    avg_latency: float = 0
    improvements: list[str] = field(default_factory=list)
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)


class AgentMetrics:
    """
    Collects and analyzes agent execution metrics.
    Supports self-iteration optimization.
    """

    def __init__(self, persist_path: Optional[str] = None):
        self._task_history: list[TaskRecord] = []
        self._tool_stats: dict[str, ToolStats] = {}
        self._error_patterns: dict[str, int] = defaultdict(int)
        self._persist_path = persist_path
        self._load()

    def record_task(self, record: TaskRecord) -> None:
        """Record a completed task."""
        self._task_history.append(record)
        
        # Update tool stats
        for tool_name in record.tools_used:
            if tool_name not in self._tool_stats:
                self._tool_stats[tool_name] = ToolStats(name=tool_name)
            stats = self._tool_stats[tool_name]
            stats.call_count += 1
        
        # Track errors
        for error in record.errors:
            self._error_patterns[error[:100]] += 1
        
        # Keep only last 1000 records
        if len(self._task_history) > 1000:
            self._task_history = self._task_history[-1000:]
        
        self._save()

    def record_tool_call(self, tool_name: str, success: bool, duration: float) -> None:
        """Record a single tool call."""
        if tool_name not in self._tool_stats:
            self._tool_stats[tool_name] = ToolStats(name=tool_name)
        
        stats = self._tool_stats[tool_name]
        stats.call_count += 1
        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
        stats.total_duration += duration
        stats.avg_duration = stats.total_duration / stats.call_count

    def analyze_bottlenecks(self) -> dict[str, Any]:
        """Analyze performance bottlenecks."""
        analysis = {
            "slow_tools": [],
            "failing_tools": [],
            "hard_tasks": [],
            "context_overflow_rate": 0,
            "avg_task_duration": 0,
            "success_rate": 0,
        }

        if not self._task_history:
            return analysis

        # Calculate success rate
        total_tasks = len(self._task_history)
        successful_tasks = sum(1 for t in self._task_history if t.success)
        analysis["success_rate"] = successful_tasks / total_tasks if total_tasks > 0 else 0

        # Calculate average duration
        analysis["avg_task_duration"] = sum(t.duration for t in self._task_history) / total_tasks

        # Find slow tools
        for name, stats in self._tool_stats.items():
            if stats.call_count >= 5:
                if stats.avg_duration > 2.0:
                    analysis["slow_tools"].append({
                        "tool": name,
                        "avg_duration": stats.avg_duration,
                        "call_count": stats.call_count,
                    })
                if stats.failure_count / stats.call_count > 0.3:
                    analysis["failing_tools"].append({
                        "tool": name,
                        "failure_rate": stats.failure_count / stats.call_count,
                        "call_count": stats.call_count,
                    })

        # Find hard tasks (long duration or many steps)
        for task in self._task_history:
            if task.duration > 60 or task.steps > 10:
                analysis["hard_tasks"].append({
                    "query": task.query[:100],
                    "duration": task.duration,
                    "steps": task.steps,
                    "success": task.success,
                })

        # Sort by severity
        analysis["slow_tools"].sort(key=lambda x: x["avg_duration"], reverse=True)
        analysis["failing_tools"].sort(key=lambda x: x["failure_rate"], reverse=True)
        analysis["hard_tasks"].sort(key=lambda x: x["duration"], reverse=True)

        return analysis

    def suggest_optimizations(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate optimization suggestions based on analysis."""
        suggestions = []

        # Slow tools - suggest optimization
        for tool_info in analysis.get("slow_tools", [])[:3]:
            suggestions.append({
                "type": "tool_optimization",
                "tool": tool_info["tool"],
                "issue": f"Average duration {tool_info['avg_duration']:.1f}s",
                "suggestion": "Consider caching results or optimizing implementation",
                "priority": "high" if tool_info["avg_duration"] > 5 else "medium",
            })

        # Failing tools - suggest fix
        for tool_info in analysis.get("failing_tools", [])[:3]:
            suggestions.append({
                "type": "tool_fix",
                "tool": tool_info["tool"],
                "issue": f"Failure rate {tool_info['failure_rate']:.0%}",
                "suggestion": "Review error patterns and add better error handling",
                "priority": "high",
            })

        # Low success rate
        if analysis.get("success_rate", 1) < 0.7:
            suggestions.append({
                "type": "agent_improvement",
                "issue": f"Low success rate: {analysis['success_rate']:.0%}",
                "suggestion": "Review failing tasks and improve error recovery",
                "priority": "high",
            })

        # Many hard tasks
        hard_tasks = analysis.get("hard_tasks", [])
        if len(hard_tasks) > len(self._task_history) * 0.3:
            suggestions.append({
                "type": "task_decomposition",
                "issue": f"{len(hard_tasks)} tasks took >60s or >10 steps",
                "suggestion": "Consider breaking complex tasks into smaller subtasks",
                "priority": "medium",
            })

        return suggestions

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of metrics."""
        if not self._task_history:
            return {"total_tasks": 0}

        return {
            "total_tasks": len(self._task_history),
            "success_rate": sum(1 for t in self._task_history if t.success) / len(self._task_history),
            "avg_duration": sum(t.duration for t in self._task_history) / len(self._task_history),
            "avg_steps": sum(t.steps for t in self._task_history) / len(self._task_history),
            "tool_stats": {
                name: {
                    "calls": stats.call_count,
                    "success_rate": stats.success_count / stats.call_count if stats.call_count > 0 else 0,
                    "avg_duration": stats.avg_duration,
                }
                for name, stats in self._tool_stats.items()
            },
            "recent_tasks": [
                {
                    "query": t.query[:50],
                    "success": t.success,
                    "duration": t.duration,
                }
                for t in self._task_history[-5:]
            ],
        }

    def _save(self) -> None:
        """Persist metrics to disk."""
        if not self._persist_path:
            return
        
        try:
            path = Path(self._persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "query": t.query,
                        "intent_type": t.intent_type,
                        "steps": t.steps,
                        "duration": t.duration,
                        "success": t.success,
                        "tools_used": t.tools_used,
                        "errors": t.errors,
                        "timestamp": t.timestamp,
                    }
                    for t in self._task_history
                ],
                "tool_stats": {
                    name: {
                        "call_count": s.call_count,
                        "success_count": s.success_count,
                        "failure_count": s.failure_count,
                        "avg_duration": s.avg_duration,
                        "total_duration": s.total_duration,
                    }
                    for name, s in self._tool_stats.items()
                },
            }
            
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load(self) -> None:
        """Load metrics from disk."""
        if not self._persist_path:
            return
        
        try:
            path = Path(self._persist_path)
            if not path.exists():
                return
            
            data = json.loads(path.read_text(encoding="utf-8"))
            
            for t in data.get("tasks", []):
                self._task_history.append(TaskRecord(
                    task_id=t["task_id"],
                    query=t["query"],
                    intent_type=t.get("intent_type", ""),
                    steps=t["steps"],
                    duration=t["duration"],
                    success=t["success"],
                    tools_used=t.get("tools_used", []),
                    errors=t.get("errors", []),
                    timestamp=t.get("timestamp", 0),
                ))
            
            for name, s in data.get("tool_stats", {}).items():
                self._tool_stats[name] = ToolStats(
                    name=name,
                    call_count=s.get("call_count", 0),
                    success_count=s.get("success_count", 0),
                    failure_count=s.get("failure_count", 0),
                    avg_duration=s.get("avg_duration", 0),
                    total_duration=s.get("total_duration", 0),
                )
        except Exception:
            pass


class EnhancedMetrics:
    """增强的指标收集器 - 支持迭代追踪"""

    def __init__(self, persist_path: Optional[str] = None):
        self._lock = Lock()
        self._metrics: deque[PerformanceMetric] = deque(maxlen=10000)
        self._iterations: list[AgentIteration] = []
        self._current_iteration: Optional[AgentIteration] = None
        self._persist_path = persist_path
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        
    def record(self, name: str, value: float, unit: str = "", **metadata) -> None:
        """记录性能指标"""
        with self._lock:
            metric = PerformanceMetric(
                name=name,
                value=value,
                unit=unit,
                metadata=metadata,
            )
            self._metrics.append(metric)
            
            # 更新直方图
            self._histograms[name].append(value)
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]
    
    def increment(self, name: str, amount: int = 1) -> None:
        """递增计数器"""
        with self._lock:
            self._counters[name] += amount
    
    def gauge(self, name: str, value: float) -> None:
        """设置仪表盘值"""
        with self._lock:
            self._gauges[name] = value
    
    def start_iteration(self) -> int:
        """开始新的迭代"""
        with self._lock:
            iteration_id = len(self._iterations)
            self._current_iteration = AgentIteration(
                iteration_id=iteration_id,
                start_time=time.time(),
            )
            return iteration_id
    
    def end_iteration(self, improvements: list[str] = None) -> Optional[AgentIteration]:
        """结束当前迭代"""
        with self._lock:
            if not self._current_iteration:
                return None
            
            self._current_iteration.end_time = time.time()
            self._current_iteration.improvements = improvements or []
            
            # 计算汇总指标
            duration = self._current_iteration.end_time - self._current_iteration.start_time
            self._current_iteration.metrics_snapshot = {
                "duration_seconds": duration,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }
            
            self._iterations.append(self._current_iteration)
            iteration = self._current_iteration
            self._current_iteration = None
            
            self._save()
            return iteration
    
    def get_histogram_stats(self, name: str) -> dict[str, float]:
        """获取直方图统计"""
        values = self._histograms.get(name, [])
        if not values:
            return {}
        
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "count": n,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "mean": sum(sorted_vals) / n,
            "p50": sorted_vals[n // 2],
            "p90": sorted_vals[int(n * 0.9)],
            "p99": sorted_vals[int(n * 0.99)],
        }
    
    def get_iteration_trend(self, last_n: int = 10) -> list[dict]:
        """获取最近N次迭代的趋势"""
        recent = self._iterations[-last_n:]
        return [
            {
                "iteration": it.iteration_id,
                "duration": it.end_time - it.start_time if it.end_time else 0,
                "tasks": it.tasks_completed,
                "success_rate": it.success_rate,
                "improvements": len(it.improvements),
            }
            for it in recent
        ]
    
    def _save(self) -> None:
        """持久化指标"""
        if not self._persist_path:
            return
        
        try:
            path = Path(self._persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "iterations": [
                    {
                        "iteration_id": it.iteration_id,
                        "start_time": it.start_time,
                        "end_time": it.end_time,
                        "tasks_completed": it.tasks_completed,
                        "success_rate": it.success_rate,
                        "avg_latency": it.avg_latency,
                        "improvements": it.improvements,
                        "metrics_snapshot": it.metrics_snapshot,
                    }
                    for it in self._iterations
                ],
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }
            
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass


# Global instances
import os
_metrics_path = os.path.join(os.path.expanduser("~"), ".codelens", "metrics.json")
agent_metrics = AgentMetrics(persist_path=_metrics_path)

_enhanced_metrics_path = os.path.join(os.path.expanduser("~"), ".codelens", "enhanced_metrics.json")
enhanced_metrics = EnhancedMetrics(persist_path=_enhanced_metrics_path)


def get_agent_metrics() -> AgentMetrics:
    return agent_metrics


def get_enhanced_metrics() -> EnhancedMetrics:
    return enhanced_metrics
