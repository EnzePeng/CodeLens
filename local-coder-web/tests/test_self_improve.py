"""Tests for self-improvement engine."""
import time
from core.self_improve import SelfImprovementEngine, IterationConfig


def test_create_engine():
    config = IterationConfig(max_iterations=10, iteration_interval=60)
    engine = SelfImprovementEngine(config)
    
    assert engine.config.max_iterations == 10
    assert engine.config.iteration_interval == 60


def test_capture_baseline():
    engine = SelfImprovementEngine()
    baseline = engine.capture_baseline()
    
    assert isinstance(baseline, dict)
    assert "success_rate" in baseline


def test_run_iteration():
    engine = SelfImprovementEngine()
    engine.capture_baseline()
    initial_iteration = engine.state.current_iteration
    
    result = engine.run_iteration()
    
    assert result["status"] == "completed"
    assert result["iteration_id"] >= 0
    assert "duration" in result
    assert engine.state.current_iteration == initial_iteration + 1


def test_improvement_report():
    engine = SelfImprovementEngine()
    engine.capture_baseline()
    initial_iteration = engine.state.current_iteration
    engine.run_iteration()
    
    report = engine.get_improvement_report()
    
    assert report["total_iterations"] == initial_iteration + 1
    assert "baseline" in report
    assert "current" in report


def test_register_optimization():
    engine = SelfImprovementEngine()
    
    def handler(suggestion):
        pass
    
    engine.register_optimization("caching", handler)
    assert "caching" in engine._optimization_handlers


def test_multiple_iterations():
    engine = SelfImprovementEngine()
    engine.capture_baseline()
    initial_iteration = engine.state.current_iteration
    
    for i in range(3):
        result = engine.run_iteration()
        assert result["status"] == "completed"
    
    assert engine.state.current_iteration == initial_iteration + 3
    assert len(engine._improvement_log) >= 3
