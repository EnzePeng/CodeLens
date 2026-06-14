"""Tests for optimizer module."""
from core.optimizer import (
    SelfOptimizer, Bottleneck, OptimizationSuggestion,
    Priority, OptimizationType,
)


def test_analyze_bottlenecks_high_latency():
    optimizer = SelfOptimizer()
    metrics = {
        "latency": {"p90": 3000},
    }
    
    bottlenecks = optimizer.analyze_bottlenecks(metrics)
    assert len(bottlenecks) == 1
    assert bottlenecks[0].name == "high_latency"
    assert bottlenecks[0].severity > 0.5


def test_analyze_bottlenecks_low_success_rate():
    optimizer = SelfOptimizer()
    metrics = {"success_rate": 0.6}
    
    bottlenecks = optimizer.analyze_bottlenecks(metrics)
    assert len(bottlenecks) == 1
    assert bottlenecks[0].name == "low_success_rate"


def test_analyze_bottlenecks_tool_failure():
    optimizer = SelfOptimizer()
    metrics = {
        "tool_stats": {
            "read_file": {"failure_rate": 0.4},
        }
    }
    
    bottlenecks = optimizer.analyze_bottlenecks(metrics)
    assert len(bottlenecks) == 1
    assert "tool_failure" in bottlenecks[0].name


def test_analyze_bottlenecks_context_overflow():
    optimizer = SelfOptimizer()
    metrics = {
        "context_usage": {"overflow_rate": 0.2},
    }
    
    bottlenecks = optimizer.analyze_bottlenecks(metrics)
    assert len(bottlenecks) == 1
    assert bottlenecks[0].name == "context_overflow"


def test_generate_suggestions():
    optimizer = SelfOptimizer()
    bottlenecks = [
        Bottleneck(name="high_latency", severity=0.8, impact="响应慢"),
        Bottleneck(name="low_success_rate", severity=0.4, impact="成功率低"),
    ]
    
    suggestions = optimizer.generate_suggestions(bottlenecks)
    assert len(suggestions) > 0
    # 应该按优先级排序
    priorities = [s.priority for s in suggestions]
    assert priorities == sorted(priorities, key=lambda p: p.value)


def test_select_next_optimization():
    optimizer = SelfOptimizer()
    bottlenecks = [Bottleneck(name="high_latency", severity=0.8, impact="响应慢")]
    optimizer.generate_suggestions(bottlenecks)
    
    suggestion = optimizer.select_next_optimization()
    assert suggestion is not None
    assert suggestion.id not in optimizer._applied_optimizations


def test_mark_applied():
    optimizer = SelfOptimizer()
    bottlenecks = [Bottleneck(name="high_latency", severity=0.8, impact="响应慢")]
    optimizer.generate_suggestions(bottlenecks)
    
    suggestion = optimizer.select_next_optimization()
    optimizer.mark_applied(suggestion.id, success=True, actual_improvement=25.0)
    
    assert suggestion.id in optimizer._applied_optimizations
    assert len(optimizer._optimization_history) == 1


def test_optimization_report():
    optimizer = SelfOptimizer()
    # First analyze bottlenecks to populate _bottlenecks
    metrics = {"latency": {"p90": 3000}}
    optimizer.analyze_bottlenecks(metrics)
    optimizer.generate_suggestions(optimizer._bottlenecks)
    
    report = optimizer.get_optimization_report()
    assert report["total_bottlenecks"] == 1
    assert report["total_suggestions"] > 0


def test_no_bottlenecks():
    optimizer = SelfOptimizer()
    metrics = {"success_rate": 0.95, "latency": {"p90": 500}}
    
    bottlenecks = optimizer.analyze_bottlenecks(metrics)
    assert len(bottlenecks) == 0
    
    suggestions = optimizer.generate_suggestions(bottlenecks)
    assert len(suggestions) == 0
