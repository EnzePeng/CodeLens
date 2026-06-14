"""
Self-Improvement Engine - Core iteration loop for continuous optimization

Coordinates metrics collection, bottleneck analysis, and optimization application.
"""
from __future__ import annotations
import time
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from pathlib import Path

from core.metrics import enhanced_metrics
from core.optimizer import self_optimizer, OptimizationSuggestion, Priority


@dataclass
class IterationConfig:
    """迭代配置"""
    max_iterations: int = 48  # 24小时 / 30分钟
    iteration_interval: int = 1800  # 30分钟
    min_tasks_for_analysis: int = 10
    auto_apply_threshold: float = 0.7  # 自动应用优化的置信度阈值


@dataclass
class IterationState:
    """迭代状态"""
    current_iteration: int = 0
    is_running: bool = False
    last_iteration_time: float = 0
    total_improvements: int = 0
    applied_optimizations: list[str] = field(default_factory=list)


class SelfImprovementEngine:
    """自我改进引擎"""
    
    def __init__(self, config: Optional[IterationConfig] = None):
        self.config = config or IterationConfig()
        self.state = IterationState()
        self._optimization_handlers: dict[str, Callable] = {}
        self._baseline_metrics: dict[str, Any] = {}
        self._improvement_log: list[dict] = []
        self._load_state()
    
    def register_optimization(self, optimization_type: str, handler: Callable) -> None:
        """注册优化处理器"""
        self._optimization_handlers[optimization_type] = handler
    
    def capture_baseline(self) -> dict[str, Any]:
        """捕获基线指标"""
        self._baseline_metrics = {
            "success_rate": enhanced_metrics._gauges.get("success_rate", 0),
            "avg_latency": enhanced_metrics.get_histogram_stats("latency").get("mean", 0),
            "tool_success_rate": enhanced_metrics._gauges.get("tool_success_rate", 0),
        }
        return self._baseline_metrics
    
    def run_iteration(self) -> dict[str, Any]:
        """运行单次迭代"""
        iteration_id = enhanced_metrics.start_iteration()
        start_time = time.time()
        
        result = {
            "iteration_id": iteration_id,
            "start_time": start_time,
            "status": "running",
        }
        
        try:
            # 1. 收集当前指标
            current_metrics = self._collect_metrics()
            
            # 2. 分析瓶颈
            bottlenecks = self_optimizer.analyze_bottlenecks(current_metrics)
            
            # 3. 生成优化建议
            suggestions = self_optimizer.generate_suggestions(bottlenecks)
            
            # 4. 选择并应用优化
            applied = []
            processed = set()
            suggestion = self_optimizer.select_next_optimization()
            while suggestion and len(applied) < 3:  # 每次最多应用3个优化
                if suggestion.id in processed:
                    break  # 防止无限循环
                processed.add(suggestion.id)
                
                if self._should_apply_optimization(suggestion):
                    success = self._apply_optimization(suggestion)
                    if success:
                        applied.append(suggestion.id)
                        self_optimizer.mark_applied(suggestion.id, success=True)
                    else:
                        # 标记为已处理（即使失败），防止无限循环
                        self_optimizer.mark_applied(suggestion.id, success=False)
                else:
                    # 不需要应用，也标记为已处理
                    self_optimizer.mark_applied(suggestion.id, success=False)
                
                suggestion = self_optimizer.select_next_optimization()
            
            # 5. 验证改进
            improvements = self._verify_improvements(applied)
            
            # 6. 记录结果
            end_time = time.time()
            enhanced_metrics.end_iteration(improvements=improvements)
            
            result.update({
                "status": "completed",
                "end_time": end_time,
                "duration": end_time - start_time,
                "bottlenecks_found": len(bottlenecks),
                "suggestions_generated": len(suggestions),
                "optimizations_applied": len(applied),
                "improvements": improvements,
            })
            
            self.state.current_iteration += 1
            self.state.total_improvements += len(improvements)
            self.state.applied_optimizations.extend(applied)
            self.state.last_iteration_time = end_time
            
        except Exception as e:
            result.update({
                "status": "failed",
                "error": str(e),
            })
        
        self._improvement_log.append(result)
        self._save_state()
        
        return result
    
    def _collect_metrics(self) -> dict[str, Any]:
        """收集当前指标"""
        # 获取工具名称列表
        tool_names = set()
        for k in list(enhanced_metrics._counters.keys()):
            if k.startswith("tool_") and k.endswith("_calls"):
                parts = k.split("_")
                if len(parts) >= 3:
                    tool_names.add(parts[1])
        
        tool_stats = {}
        for name in tool_names:
            calls = enhanced_metrics._counters.get(f"tool_{name}_calls", 0)
            failures = enhanced_metrics._counters.get(f"tool_{name}_failures", 0)
            tool_stats[name] = {
                "call_count": calls,
                "failure_rate": failures / max(calls, 1),
            }
        
        return {
            "success_rate": enhanced_metrics._gauges.get("success_rate", 0),
            "latency": enhanced_metrics.get_histogram_stats("latency"),
            "tool_stats": tool_stats,
            "context_usage": {
                "overflow_rate": enhanced_metrics._gauges.get("context_overflow_rate", 0),
            },
        }
    
    def _should_apply_optimization(self, suggestion: OptimizationSuggestion) -> bool:
        """判断是否应该应用优化"""
        # 高优先级优化自动应用
        if suggestion.priority in (Priority.CRITICAL, Priority.HIGH):
            return True
        
        # 中等优先级需要置信度检查
        if suggestion.priority == Priority.MEDIUM:
            return suggestion.expected_improvement > 15.0
        
        # 低优先级不自动应用
        return False
    
    def _apply_optimization(self, suggestion: OptimizationSuggestion) -> bool:
        """应用优化"""
        handler = self._optimization_handlers.get(suggestion.type.value)
        if handler:
            try:
                handler(suggestion)
                return True
            except Exception:
                return False
        return False
    
    def _verify_improvements(self, applied_ids: list[str]) -> list[str]:
        """验证改进效果"""
        improvements = []
        
        current_metrics = self._collect_metrics()
        
        # 对比基线
        for metric_name, baseline_value in self._baseline_metrics.items():
            current_value = current_metrics.get(metric_name, 0)
            
            if isinstance(baseline_value, (int, float)) and isinstance(current_value, (int, float)):
                if baseline_value > 0:
                    change = (current_value - baseline_value) / baseline_value * 100
                    if metric_name == "success_rate" and change > 5:
                        improvements.append(f"成功率提升 {change:.1f}%")
                    elif metric_name == "avg_latency" and change < -10:
                        improvements.append(f"延迟降低 {abs(change):.1f}%")
        
        return improvements
    
    def get_improvement_report(self) -> dict[str, Any]:
        """获取改进报告"""
        return {
            "total_iterations": self.state.current_iteration,
            "total_improvements": self.state.total_improvements,
            "applied_optimizations": len(self.state.applied_optimizations),
            "baseline": self._baseline_metrics,
            "current": self._collect_metrics(),
            "improvement_log": self._improvement_log[-10:],  # 最近10次
            "optimization_report": self_optimizer.get_optimization_report(),
        }
    
    def _save_state(self) -> None:
        """保存状态"""
        try:
            state_path = Path.home() / ".codelens" / "self_improve_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "state": {
                    "current_iteration": self.state.current_iteration,
                    "total_improvements": self.state.total_improvements,
                    "applied_optimizations": self.state.applied_optimizations,
                    "last_iteration_time": self.state.last_iteration_time,
                },
                "baseline": self._baseline_metrics,
                "improvement_log": self._improvement_log[-50:],
            }
            
            state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _load_state(self) -> None:
        """加载状态"""
        try:
            state_path = Path.home() / ".codelens" / "self_improve_state.json"
            if state_path.exists():
                data = json.loads(state_path.read_text(encoding="utf-8"))
                
                state_data = data.get("state", {})
                self.state.current_iteration = state_data.get("current_iteration", 0)
                self.state.total_improvements = state_data.get("total_improvements", 0)
                self.state.applied_optimizations = state_data.get("applied_optimizations", [])
                self.state.last_iteration_time = state_data.get("last_iteration_time", 0)
                
                self._baseline_metrics = data.get("baseline", {})
                self._improvement_log = data.get("improvement_log", [])
        except Exception:
            pass


# 全局实例
self_improvement_engine = SelfImprovementEngine()
