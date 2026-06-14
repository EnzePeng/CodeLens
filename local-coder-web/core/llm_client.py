"""
统一 LLM 客户端 - 支持流式/非流式调用、模型切换、重试机制
"""
from __future__ import annotations

import json
import time
import asyncio
from typing import AsyncGenerator, Optional, Any
from dataclasses import dataclass

import httpx

from config import (
    LLAMA_URL, FAST_MODEL_URL, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
)
from core.model_manager import model_manager, ModelConfig


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str
    usage: dict[str, int]
    latency_ms: float
    finish_reason: str


@dataclass
class LLMChunk:
    """流式 LLM 响应块"""
    content: str
    finish_reason: Optional[str] = None


class LLMClient:
    """
    统一 LLM 客户端
    
    支持:
    - 流式/非流式调用
    - 自动模型选择
    - 重试机制
    - 超时处理
    - 延迟统计
    """
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._stats: dict[str, list[float]] = {}
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # 9B 模型在长上下文（32k）下单次推理可能很久；
            # connect/read/write 分别设大，避免批量任务中途超时。
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=60.0),
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            )
        return self._client
    
    async def call(
        self,
        messages: list[dict[str, str]],
        model_purpose: str = "main",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        task_type: str = "general",
        **kwargs
    ) -> LLMResponse:
        """
        非流式调用 LLM
        
        Args:
            messages: 消息列表
            model_purpose: 模型用途 (main/fast)
            max_tokens: 最大生成 token 数
            temperature: 温度
            task_type: 任务类型 (用于模型选择)
        
        Returns:
            LLMResponse 对象
        """
        # 选择模型
        model = await model_manager.select_best_model(task_type)
        endpoint = model.endpoint
        
        start_time = time.time()
        
        try:
            client = await self._get_client()
            
            payload = {
                "model": model.name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
                "repeat_penalty": 1.1,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1,
                **kwargs
            }
            
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            
            data = response.json()
            latency = (time.time() - start_time) * 1000
            
            # 记录延迟
            self._record_latency(model_purpose, latency)
            
            return LLMResponse(
                content=data["choices"][0]["message"]["content"],
                model=data.get("model", model.name),
                usage=data.get("usage", {}),
                latency_ms=latency,
                finish_reason=data["choices"][0].get("finish_reason", "stop")
            )
            
        except httpx.TimeoutException:
            raise LLMError(f"LLM 调用超时: {endpoint}")
        except httpx.HTTPStatusError as e:
            raise LLMError(f"LLM 调用失败: {e.response.status_code}")
        except Exception as e:
            raise LLMError(f"LLM 调用异常: {str(e)}")
    
    async def call_streaming(
        self,
        messages: list[dict[str, str]],
        model_purpose: str = "main",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        task_type: str = "general",
        **kwargs
    ) -> AsyncGenerator[LLMChunk, None]:
        """
        流式调用 LLM
        
        Args:
            messages: 消息列表
            model_purpose: 模型用途
            max_tokens: 最大生成 token 数
            temperature: 温度
            task_type: 任务类型
        
        Yields:
            LLMChunk 对象
        """
        # 选择模型
        model = await model_manager.select_best_model(task_type)
        endpoint = model.endpoint
        
        start_time = time.time()
        
        try:
            client = await self._get_client()
            
            payload = {
                "model": model.name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                "repeat_penalty": 1.1,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1,
                **kwargs
            }
            
            async with client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()
                
                full_content = ""
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    if line.startswith("data: "):
                        data_str = line[6:]
                        
                        if data_str.strip() == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                full_content += content
                                yield LLMChunk(content=content)
                            
                            finish_reason = data.get("choices", [{}])[0].get("finish_reason")
                            if finish_reason:
                                yield LLMChunk(content="", finish_reason=finish_reason)
                                
                        except json.JSONDecodeError:
                            continue
                
                # 记录延迟
                latency = (time.time() - start_time) * 1000
                self._record_latency(model_purpose, latency)
                
        except httpx.TimeoutException:
            raise LLMError(f"LLM 流式调用超时: {endpoint}")
        except Exception as e:
            raise LLMError(f"LLM 流式调用异常: {str(e)}")
    
    def _record_latency(self, purpose: str, latency_ms: float):
        """记录延迟统计"""
        if purpose not in self._stats:
            self._stats[purpose] = []
        self._stats[purpose].append(latency_ms)
        
        # 保留最近 100 条记录
        if len(self._stats[purpose]) > 100:
            self._stats[purpose] = self._stats[purpose][-100:]
    
    def get_stats(self) -> dict[str, dict[str, float]]:
        """获取延迟统计"""
        stats = {}
        for purpose, latencies in self._stats.items():
            if latencies:
                stats[purpose] = {
                    "avg_ms": sum(latencies) / len(latencies),
                    "min_ms": min(latencies),
                    "max_ms": max(latencies),
                    "count": len(latencies)
                }
        return stats
    
    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()


class LLMError(Exception):
    """LLM 调用错误"""
    pass


# 全局 LLM 客户端实例
llm_client = LLMClient()
