"""
Comment generation route — /api/comment (generate code comments)

Uses the main model to generate detailed Chinese comments for code.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel as PydanticBaseModel

from config import LLAMA_URL

router = APIRouter()


class CommentRequest(PydanticBaseModel):
    code: str
    language: str = ""
    style: str = "detailed"  # detailed, brief, docstring


class CommentResponse(PydanticBaseModel):
    commented_code: str
    latency_ms: float = 0


@router.post("/api/comment")
async def generate_comment(req: CommentRequest) -> CommentResponse:
    """
    为代码生成注释
    
    Args:
        code: 需要添加注释的代码
        language: 编程语言
        style: 注释风格 (detailed/brief/docstring)
    """
    import time
    import httpx
    
    start_time = time.time()
    
    # 构建提示词 - 使用英文提示以获得更好的英文注释
    style_prompts = {
        "detailed": "Add detailed English comments to this code. Explain: 1) What it does, 2) Parameters, 3) Return value, 4) Key logic. Use ONLY English.",
        "brief": "Add brief English comments to this code explaining the main functionality. Use ONLY English.",
        "docstring": "Add an English docstring to this function with description, parameters, and return value. Use ONLY English.",
    }
    
    style_prompt = style_prompts.get(req.style, style_prompts["detailed"])
    
    prompt = f"""{style_prompt}

Code:
```{req.language or 'python'}
{req.code}
```

Output the code with English comments added:"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                LLAMA_URL,
                json={
                    "model": "qwen3.5-9b",
                    "messages": [
                        {"role": "system", "content": "You are a code comment assistant. Add comments to code. Output only the code with comments, no explanations."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.2,
                    "stream": False,
                }
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            
            # 清理输出：移除thinking标签和代码块标记
            import re
            content = re.sub(r'<think>[\s\S]*?</think>', '', content)
            content = re.sub(r'^```[\s\S]*?\n', '', content)
            content = re.sub(r'\n```$', '', content)
            
            latency = (time.time() - start_time) * 1000
            
            return CommentResponse(
                commented_code=content.strip(),
                latency_ms=latency,
            )
            
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return CommentResponse(
            commented_code=f"注释生成失败: {str(e)}",
            latency_ms=latency,
        )
