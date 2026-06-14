"""Tests for enhanced metrics system."""
import time
from core.metrics import EnhancedMetrics, PerformanceMetric, AgentIteration


def test_record_metric():
    metrics = EnhancedMetrics()
    metrics.record("latency", 150.5, unit="ms")
    assert len(metrics._metrics) == 1
    assert metrics._metrics[0].name == "latency"
    assert metrics._metrics[0].value == 150.5


def test_increment_counter():
    metrics = EnhancedMetrics()
    metrics.increment("tool_calls")
    metrics.increment("tool_calls")
    assert metrics._counters["tool_calls"] == 2


def test_gauge():
    metrics = EnhancedMetrics()
    metrics.gauge("memory_usage", 0.75)
    assert metrics._gauges["memory_usage"] == 0.75


def test_histogram_stats():
    metrics = EnhancedMetrics()
    for i in range(100):
        metrics.record("response_time", float(i))
    
    stats = metrics.get_histogram_stats("response_time")
    assert stats["count"] == 100
    assert stats["min"] == 0.0
    assert stats["max"] == 99.0
    assert stats["mean"] == 49.5


def test_iteration_lifecycle():
    metrics = EnhancedMetrics()
    iter_id = metrics.start_iteration()
    assert iter_id == 0
    
    metrics.increment("tasks")
    time.sleep(0.01)  # Ensure some time passes
    iteration = metrics.end_iteration(improvements=["test improvement"])
    
    assert iteration.iteration_id == 0
    assert iteration.end_time >= iteration.start_time
    assert "test improvement" in iteration.improvements


def test_iteration_trend():
    metrics = EnhancedMetrics()
    
    for i in range(5):
        metrics.start_iteration()
        time.sleep(0.01)
        metrics.end_iteration()
    
    trend = metrics.get_iteration_trend(last_n=3)
    assert len(trend) == 3


def test_multiple_iterations():
    metrics = EnhancedMetrics()
    
    for i in range(3):
        metrics.start_iteration()
        metrics.gauge("success_rate", 0.8 + i * 0.05)
        metrics.end_iteration(improvements=[f"improvement_{i}"])
    
    assert len(metrics._iterations) == 3
    assert metrics._iterations[2].improvements == ["improvement_2"]


def test_histogram_percentiles():
    metrics = EnhancedMetrics()
    for i in range(100):
        metrics.record("latency", float(i * 10))
    
    stats = metrics.get_histogram_stats("latency")
    # p50 is at index 50 (0-indexed), which is value 500
    assert stats["p50"] == 500.0
    assert stats["p90"] == 900.0
    assert stats["p99"] == 990.0
