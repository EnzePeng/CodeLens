"""
模型管理器 - 支持双模型切换和动态选择
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional
from dataclasses import dataclass

import httpx

from config import ModelConfig, get_model, MODELS, FAST_MODEL_URL


@dataclass
class ModelStatus:
    """模型状态"""
    name: str
    endpoint: str
    available: bool
    latency_ms: float = 0
    last_check: float = 0


class ModelManager:
    """
    模型管理器 - 负责模型选择、切换和健康检查
    
    支持的用途:
    - main: 主推理（Agent/Ask/Plan/Craft）
    - fast: 快速补全（代码补全、快速反思）
    - auto: 自动选择（根据任务复杂度）
    """
    
    def __init__(self):
        self._status: dict[str, ModelStatus] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._current_model: dict[str, str] = {
            "main": "main",
            "fast": "fast"
        }
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def check_health(self, endpoint: str) -> ModelStatus:
        """检查模型健康状态"""
        try:
            client = await self._get_client()
            start = time.time()
            response = await client.get(endpoint.replace("/v1/chat/completions", "/health"))
            latency = (time.time() - start) * 1000
            
            return ModelStatus(
                name=endpoint,
                endpoint=endpoint,
                available=response.status_code == 200,
                latency_ms=latency,
                last_check=time.time()
            )
        except Exception as e:
            return ModelStatus(
                name=endpoint,
                endpoint=endpoint,
                available=False,
                last_check=time.time()
            )
    
    async def check_all_models(self) -> dict[str, ModelStatus]:
        """检查所有模型状态"""
        tasks = []
        for name, model in MODELS.items():
            tasks.append(self.check_health(model.endpoint))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        status = {}
        for name, result in zip(MODELS.keys(), results):
            if isinstance(result, Exception):
                status[name] = ModelStatus(
                    name=name,
                    endpoint=MODELS[name].endpoint,
                    available=False
                )
            else:
                status[name] = result
        
        self._status = status
        return status
    
    def get_available_model(self, purpose: str = "main") -> Optional[ModelConfig]:
        """获取可用的模型"""
        if purpose == "fast":
            # 优先使用快速模型
            fast_status = self._status.get("fast")
            if fast_status and fast_status.available:
                return MODELS["fast"]
            # 回退到主模型
            return MODELS.get("main")
        
        # 主模型
        main_status = self._status.get("main")
        if main_status and main_status.available:
            return MODELS["main"]
        
        # 备选模型
        fallback_status = self._status.get("fallback")
        if fallback_status and fallback_status.available:
            return MODELS["fallback"]
        
        return None
    
    async def select_best_model(self, task_type: str = "general") -> ModelConfig:
        """
        根据任务类型选择最佳模型
        
        task_type:
            - general: 通用任务
            - code_completion: 代码补全
            - complex_reasoning: 复杂推理
            - quick_reflection: 快速反思
        """
        if task_type == "code_completion":
            # 代码补全优先使用快速模型
            model = self.get_available_model("fast")
            if model:
                return model
        
        elif task_type == "quick_reflection":
            # 快速反思使用快速模型
            model = self.get_available_model("fast")
            if model:
                return model
        
        elif task_type == "complex_reasoning":
            # 复杂推理使用主模型
            model = self.get_available_model("main")
            if model:
                return model
        
        # 默认返回主模型
        model = self.get_available_model("main")
        if model:
            return model
        
        # 最后回退
        return MODELS["fallback"]
    
    def get_endpoint(self, purpose: str = "main") -> str:
        """获取指定用途的端点"""
        model = self.get_available_model(purpose)
        if model:
            return model.endpoint
        return get_model("main").endpoint
    
    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()


# 全局模型管理器实例
model_manager = ModelManager()
