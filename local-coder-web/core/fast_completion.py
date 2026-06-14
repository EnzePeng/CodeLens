"""
快速代码补全 - 使用llama.cpp的infill端点实现低延迟补全

优化点：
1. 使用正确的/infill端点（FIM格式）
2. 语言感知的提示词
3. 更好的后处理
4. 自动回退到主模型
"""
from __future__ import annotations

import re
import time
from typing import Optional
from dataclasses import dataclass

import httpx

from config import FAST_MODEL_URL, MAIN_MODEL_URL, MODELS


@dataclass
class CompletionResult:
    text: str
    latency_ms: float
    model: str
    confidence: float = 1.0


class FastCompletionProvider:
    """快速代码补全提供者 - 使用llama.cpp的infill端点"""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._fast_endpoint = "http://127.0.0.1:8081"
        self._main_endpoint = "http://127.0.0.1:8080"
        self._fast_model_name = MODELS["fast"].name if "fast" in MODELS else "Qwen3-1.7B"
        self._main_model_name = MODELS["main"].name if "main" in MODELS else "Qwen3.5-9B"
        self._fast_available: Optional[bool] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def _check_fast_model(self) -> bool:
        """检查快速模型是否可用"""
        if self._fast_available is not None:
            return self._fast_available
        
        try:
            client = await self._get_client()
            response = await client.get(f"{self._fast_endpoint}/health", timeout=3.0)
            self._fast_available = response.status_code == 200
        except:
            self._fast_available = False
        
        return self._fast_available

    async def complete(
        self,
        prefix: str,
        suffix: str = "",
        max_tokens: int = 64,
        temperature: float = 0.2,
        stop: Optional[list[str]] = None,
        language: str = "",
    ) -> CompletionResult:
        """
        执行代码补全 - 使用FIM (Fill-In-The-Middle) 格式
        
        Args:
            prefix: 光标前的代码
            suffix: 光标后的代码
            max_tokens: 最大生成token数
            temperature: 温度
            stop: 停止词
            language: 编程语言
        """
        start_time = time.time()
        
        # 检查快速模型是否可用
        use_fast = await self._check_fast_model()
        base_url = self._fast_endpoint if use_fast else self._main_endpoint
        model_name = self._fast_model_name if use_fast else self._main_model_name
        
        try:
            client = await self._get_client()
            
            # 使用llama.cpp的infill端点
            infill_url = f"{base_url}/infill"
            
            payload = {
                "input_prefix": prefix,
                "input_suffix": suffix,
                "n_predict": max_tokens,
                "temperature": temperature,
                "stream": False,
                "stop": stop or ["\n\n", "篑", "焌", "endoftext"],
            }
            
            response = await client.post(infill_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            latency = (time.time() - start_time) * 1000
            content = data.get("content", "")
            
            # 后处理
            content, confidence = self._post_process(content, suffix, prefix)
            
            return CompletionResult(
                text=content,
                latency_ms=latency,
                model=data.get("model", model_name),
                confidence=confidence,
            )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return CompletionResult(text="", latency_ms=latency, model=model_name, confidence=0)

    def _post_process(self, text: str, suffix: str, prefix: str) -> tuple[str, float]:
        """
        后处理补全结果
        
        Returns:
            (处理后的文本, 置信度)
        """
        if not text:
            return "", 0.0
        
        confidence = 1.0
        
        # 移除特殊token
        for token in ["\n\n", "篑", "焌", "<end_of_turn>", "endoftext"]:
            idx = text.find(token)
            if idx >= 0:
                text = text[:idx]
                confidence *= 0.9
        
        # 避免与后文重复
        if suffix:
            suffix_lines = suffix.split("\n")
            text_lines = text.split("\n")
            
            # 检查是否与后文第一行重复
            if suffix_lines and text_lines:
                first_suffix_line = suffix_lines[0].strip()
                if first_suffix_line and text_lines[-1].strip() == first_suffix_line:
                    text_lines.pop()
                    text = "\n".join(text_lines)
                    confidence *= 0.8
        
        # 避免与前文重复
        if prefix:
            prefix_lines = prefix.split("\n")
            text_lines = text.split("\n")
            
            # 检查最后一行是否重复
            if prefix_lines and text_lines:
                last_prefix_line = prefix_lines[-1].strip()
                if last_prefix_line and text_lines[0].strip() == last_prefix_line:
                    text_lines.pop(0)
                    text = "\n".join(text_lines)
                    confidence *= 0.8
        
        # 清理多余的空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 移除末尾多余空白（但保留换行）
        text = text.rstrip()
        if text and not text.endswith('\n'):
            text += '\n'
        
        return text.strip(), confidence

    async def close(self):
        if self._client:
            await self._client.aclose()


fast_completion = FastCompletionProvider()
