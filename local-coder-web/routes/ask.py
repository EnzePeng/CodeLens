# local-coder-web/routes/ask.py
# 完整文件内容，仅修改了超时时间参数

import asyncio
import json
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncIterator

logger = logging.getLogger(__name__)
router = APIRouter()

LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"

# 默认配置
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.15
DEFAULT_TIMEOUT = 600  # 增加到 600 秒

async def _stream_llama(
    query: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> AsyncIterator[str]:
    """
    流式调用 LLM，返回字符级流式响应。
    
    Args:
        query: 用户查询
        max_tokens: 最大 token 数
        temperature: 温度参数
        
    Yields:
        每个字符的响应
    """
    payload = {
        "model": "qwen3.5-9b",
        "messages": [
            {"role": "system", "content": "你是一个专业的代码助手。"},
            {"role": "user", "content": query}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    
    try:
        async with client.stream("POST", LLAMA_URL, json=payload) as response:
            # 增加超时时间到 600 秒
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async for chunk in response.aiter_text(chunk_size=4096):
                    if chunk:
                        yield chunk
    except asyncio.TimeoutError:
        logger.error(f"LLM 请求超时：{DEFAULT_TIMEOUT}秒")
        raise HTTPException(status_code=504, detail="LLM 请求超时")
    except Exception as e:
        logger.error(f"LLM 请求失败：{e}")
        raise HTTPException(status_code=502, detail=str(e))

@router.post("/api/ask")
async def ask(query: str, max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float = DEFAULT_TEMPERATURE):
    """
    问答模式：用户提问，LLM 回答。
    """
    return StreamingResponse(
        _stream_llama(query, max_tokens, temperature),
        media_type="text/event-stream"
    )