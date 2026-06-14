"""
Optimizer - Self-optimization suggestion generator

Analyzes bottlenecks and generates optimization suggestions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
import time


class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OptimizationType(Enum):
    TOOL_OPTIMIZATION = "tool_optimization"
    CONTEXT_MANAGEMENT = "context_management"
    PROMPT_ENGINEERING = "prompt_engineering"
    CACHING = "caching"
    PARALLELIZATION = "parallelization"
    MEMORY_MANAGEMENT = "memory_management"


@dataclass
class Bottleneck:
    """性能瓶颈"""
    name: str
    severity: float  # 0-1
    impact: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationSuggestion:
    """优化建议"""
    id: str
    type: OptimizationType
    priority: Priority
    title: str
    description: str
    expected_improvement: float  # 预期提升百分比
    implementation_complexity: str  # low/medium/high
    prerequisites: list[str] = field(default_factory=list)
    metrics_impacted: list[str] = field(default_factory=list)


class SelfOptimizer:
    """自我优化器"""
    
    def __init__(self):
        self._bottlenecks: list[Bottleneck] = []
        self._suggestions: list[OptimizationSuggestion] = []
        self._applied_optimizations: list[str] = []
        self._optimization_history: list[dict] = []
    
    def analyze_bottlenecks(self, metrics_data: dict[str, Any]) -> list[Bottleneck]:
        """分析性能瓶颈"""
        bottlenecks = []
        
        # 分析延迟瓶颈
        if "latency" in metrics_data:
            latency_stats = metrics_data["latency"]
            if isinstance(latency_stats, dict):
                p90 = latency_stats.get("p90", 0)
                if p90 > 2000:  # > 2秒
                    bottlenecks.append(Bottleneck(
                        name="high_latency",
                        severity=min(p90 / 5000, 1.0),
                        impact="用户响应时间过长",
                        evidence={"p90_latency": p90},
                    ))
        
        # 分析成功率
        if "success_rate" in metrics_data:
            rate = metrics_data["success_rate"]
            if rate < 0.8:
                bottlenecks.append(Bottleneck(
                    name="low_success_rate",
                    severity=1.0 - rate,
                    impact="任务完成率过低",
                    evidence={"success_rate": rate},
                ))
        
        # 分析工具调用效率
        if "tool_stats" in metrics_data:
            for tool_name, stats in metrics_data["tool_stats"].items():
                if isinstance(stats, dict):
                    failure_rate = stats.get("failure_rate", 0)
                    if failure_rate > 0.2:
                        bottlenecks.append(Bottleneck(
                            name=f"tool_failure_{tool_name}",
                            severity=failure_rate,
                            impact=f"工具 {tool_name} 失败率过高",
                            evidence={"tool": tool_name, "failure_rate": failure_rate},
                        ))
        
        # 分析上下文使用
        if "context_usage" in metrics_data:
            usage = metrics_data["context_usage"]
            if isinstance(usage, dict):
                overflow_rate = usage.get("overflow_rate", 0)
                if overflow_rate > 0.1:
                    bottlenecks.append(Bottleneck(
                        name="context_overflow",
                        severity=overflow_rate,
                        impact="上下文溢出频繁",
                        evidence={"overflow_rate": overflow_rate},
                    ))
        
        self._bottlenecks = bottlenecks
        return bottlenecks
    
    def generate_suggestions(self, bottlenecks: list[Bottleneck]) -> list[OptimizationSuggestion]:
        """基于瓶颈生成优化建议"""
        suggestions = []
        
        for bottleneck in bottlenecks:
            if bottleneck.name == "high_latency":
                suggestions.append(OptimizationSuggestion(
                    id=f"sug_{len(suggestions)}",
                    type=OptimizationType.CACHING,
                    priority=Priority.HIGH,
                    title="启用响应缓存",
                    description="对重复查询启用LRU缓存，减少LLM调用次数",
                    expected_improvement=30.0,
                    implementation_complexity="low",
                    metrics_impacted=["latency", "llm_calls"],
                ))
                suggestions.append(OptimizationSuggestion(
                    id=f"sug_{len(suggestions)}",
                    type=OptimizationType.PARALLELIZATION,
                    priority=Priority.MEDIUM,
                    title="并行工具执行",
                    description="对独立的只读工具调用使用asyncio.gather并行执行",
                    expected_improvement=20.0,
                    implementation_complexity="medium",
                    metrics_impacted=["latency", "tool_execution_time"],
                ))
            
            elif bottleneck.name == "low_success_rate":
                suggestions.append(OptimizationSuggestion(
                    id=f"sug_{len(suggestions)}",
                    type=OptimizationType.PROMPT_ENGINEERING,
                    priority=Priority.CRITICAL,
                    title="优化系统提示词",
                    description="基于失败案例分析，改进Agent的系统提示词",
                    expected_improvement=25.0,
                    implementation_complexity="medium",
                    metrics_impacted=["success_rate", "task_completion"],
                ))
                suggestions.append(OptimizationSuggestion(
                    id=f"sug_{len(suggestions)}",
                    type=OptimizationType.CONTEXT_MANAGEMENT,
                    priority=Priority.HIGH,
                    title="改进上下文选择",
                    description="使用语义搜索和依赖图优化上下文选择算法",
                    expected_improvement=15.0,
                    implementation_complexity="high",
                    metrics_impacted=["success_rate", "context_quality"],
                ))
            
            elif "tool_failure" in bottleneck.name:
                tool_name = bottleneck.evidence.get("tool", "unknown")
                suggestions.append(OptimizationSuggestion(
                    id=f"sug_{len(suggestions)}",
                    type=OptimizationType.TOOL_OPTIMIZATION,
                    priority=Priority.HIGH,
                    title=f"优化工具 {tool_name}",
                    description=f"分析工具 {tool_name} 的失败模式并改进错误处理",
                    expected_improvement=20.0,
                    implementation_complexity="medium",
                    metrics_impacted=["tool_success_rate", "success_rate"],
                ))
            
            elif bottleneck.name == "context_overflow":
                suggestions.append(OptimizationSuggestion(
                    id=f"sug_{len(suggestions)}",
                    type=OptimizationType.MEMORY_MANAGEMENT,
                    priority=Priority.HIGH,
                    title="实现滑动窗口上下文",
                    description="使用滑动窗口管理对话历史，自动压缩旧消息",
                    expected_improvement=25.0,
                    implementation_complexity="medium",
                    metrics_impacted=["context_overflow", "memory_usage"],
                ))
        
        # 按优先级排序
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }
        suggestions.sort(key=lambda s: priority_order[s.priority])
        
        self._suggestions = suggestions
        return suggestions
    
    def select_next_optimization(self) -> Optional[OptimizationSuggestion]:
        """选择下一个要应用的优化"""
        applied = set(self._applied_optimizations)
        
        for suggestion in self._suggestions:
            if suggestion.id not in applied:
                # 检查前置条件
                prereqs_met = all(p in applied for p in suggestion.prerequisites)
                if prereqs_met:
                    return suggestion
        
        return None
    
    def mark_applied(self, suggestion_id: str, success: bool, actual_improvement: float = 0) -> None:
        """标记优化已应用"""
        self._applied_optimizations.append(suggestion_id)
        
        self._optimization_history.append({
            "suggestion_id": suggestion_id,
            "success": success,
            "actual_improvement": actual_improvement,
            "timestamp": time.time(),
        })
    
    def get_optimization_report(self) -> dict[str, Any]:
        """获取优化报告"""
        return {
            "total_bottlenecks": len(self._bottlenecks),
            "total_suggestions": len(self._suggestions),
            "applied_count": len(self._applied_optimizations),
            "pending_count": len(self._suggestions) - len(self._applied_optimizations),
            "bottlenecks": [
                {"name": b.name, "severity": b.severity, "impact": b.impact}
                for b in self._bottlenecks
            ],
            "suggestions": [
                {
                    "id": s.id,
                    "type": s.type.value,
                    "priority": s.priority.value,
                    "title": s.title,
                    "expected_improvement": s.expected_improvement,
                }
                for s in self._suggestions
            ],
            "history": self._optimization_history,
        }


# 全局实例
self_optimizer = SelfOptimizer()
