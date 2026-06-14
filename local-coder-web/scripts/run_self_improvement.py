#!/usr/bin/env python3
"""
24小时自我迭代优化运行脚本

Usage:
    python scripts/run_self_improvement.py --duration 24
    python scripts/run_self_improvement.py --iterations 48
"""
import argparse
import asyncio
import signal
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.self_improve import self_improvement_engine, IterationConfig
from core.metrics import enhanced_metrics


class SelfImprovementRunner:
    """自我改进运行器"""
    
    def __init__(self, duration_hours: float = 24, interval_minutes: int = 30):
        self.duration_seconds = duration_hours * 3600
        self.interval_seconds = interval_minutes * 60
        self.is_running = False
        self.start_time = 0
        
        # 配置
        config = IterationConfig(
            max_iterations=int(self.duration_seconds / self.interval_seconds),
            iteration_interval=self.interval_seconds,
        )
        self._engine = self_improvement_engine
        self._engine.config = config
        
        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理停止信号"""
        print("\n收到停止信号，正在优雅退出...")
        self.is_running = False
    
    async def run(self):
        """运行自我改进循环"""
        print(f"=" * 60)
        print(f"Agent 自我迭代优化系统")
        print(f"=" * 60)
        print(f"持续时间: {self.duration_seconds / 3600:.1f} 小时")
        print(f"迭代间隔: {self.interval_seconds / 60:.0f} 分钟")
        print(f"最大迭代次数: {self._engine.config.max_iterations}")
        print(f"=" * 60)
        
        self.is_running = True
        self.start_time = time.time()
        
        # 捕获基线
        print("\n[初始化] 捕获基线指标...")
        baseline = self._engine.capture_baseline()
        print(f"基线: {baseline}")
        
        iteration = 0
        while self.is_running and iteration < self._engine.config.max_iterations:
            elapsed = time.time() - self.start_time
            remaining = self.duration_seconds - elapsed
            
            if remaining <= 0:
                print("\n[完成] 已达到设定的持续时间")
                break
            
            print(f"\n{'='*60}")
            print(f"[迭代 {iteration + 1}/{self._engine.config.max_iterations}]")
            print(f"已运行: {elapsed / 3600:.1f} 小时")
            print(f"剩余: {remaining / 3600:.1f} 小时")
            print(f"{'='*60}")
            
            # 运行迭代
            result = self._engine.run_iteration()
            
            # 打印结果
            print(f"\n状态: {result['status']}")
            print(f"耗时: {result.get('duration', 0):.1f} 秒")
            print(f"发现瓶颈: {result.get('bottlenecks_found', 0)}")
            print(f"生成建议: {result.get('suggestions_generated', 0)}")
            print(f"应用优化: {result.get('optimizations_applied', 0)}")
            
            if result.get('improvements'):
                print(f"\n改进:")
                for imp in result['improvements']:
                    print(f"  ✓ {imp}")
            
            iteration += 1
            
            # 等待下次迭代
            if self.is_running and iteration < self._engine.config.max_iterations:
                wait_time = min(self.interval_seconds, remaining)
                if wait_time > 0:
                    print(f"\n等待 {wait_time / 60:.0f} 分钟后进行下次迭代...")
                    await asyncio.sleep(wait_time)
        
        # 打印最终报告
        self._print_final_report()
    
    def _print_final_report(self):
        """打印最终报告"""
        print("\n" + "=" * 60)
        print("24小时自我迭代优化报告")
        print("=" * 60)
        
        report = self._engine.get_improvement_report()
        
        print(f"\n总迭代次数: {report['total_iterations']}")
        print(f"总改进数: {report['total_improvements']}")
        print(f"已应用优化: {report['applied_optimizations']}")
        
        print(f"\n基线指标:")
        for key, value in report['baseline'].items():
            print(f"  {key}: {value}")
        
        print(f"\n当前指标:")
        for key, value in report['current'].items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")
        
        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Agent 24小时自我迭代优化")
    parser.add_argument("--duration", type=float, default=24, help="持续时间（小时）")
    parser.add_argument("--interval", type=float, default=30, help="迭代间隔（分钟）")
    parser.add_argument("--iterations", type=int, default=None, help="最大迭代次数")
    
    args = parser.parse_args()
    
    runner = SelfImprovementRunner(
        duration_hours=args.duration,
        interval_minutes=args.interval,
    )
    
    if args.iterations:
        runner._engine.config.max_iterations = args.iterations
    
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
