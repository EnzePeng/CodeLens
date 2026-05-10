"""
Complete route — /api/complete (code completion).

Improvements:
- #61 Connection pooling via shared httpx client
"""
from __future__ import annotations

import re as re2
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as PydanticBaseModel

from config import LLAMA_URL
from app import get_http_client  # #61

router = APIRouter()


class CompleteRequest(PydanticBaseModel):
    code: str
    cursor_pos: int = 0
    file_path: str = ""


class CompleteResponse(PydanticBaseModel):
    completions: list[dict]
    is_incomplete: bool = False


@router.post("/api/complete")
async def code_complete(req: CompleteRequest) -> CompleteResponse:
    if not req.code or not req.code.strip():
        return CompleteResponse(completions=[])

    before_cursor = req.code[:req.cursor_pos]
    after_cursor = req.code[req.cursor_pos:]

    prompt = f"""Complete the following code. Provide up to 5 possible completions for the cursor position.
Return ONLY a JSON array: [{"text": "completion", "description": "what this does"}]

Current code (| is cursor):
```
{before_cursor}|{after_cursor}
```
File: {req.file_path}

Completions:"""

    try:
        client = get_http_client()  # #61 connection pooling (sync function, no await)
        response = await client.post(
            LLAMA_URL,
            json={
                "messages": [
                    {"role": "system", "content": "You are a code completion assistant. Return valid JSON array of completions."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            },
            timeout=30.0,
        )

        if response.status_code != 200:
            return CompleteResponse(completions=[])

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        json_match = re2.search(r'\[[\s\S]*\]', content)
        if json_match:
            try:
                completions = json.loads(json_match.group())
                formatted = [{"text": c.get("text", ""), "description": c.get("description", "")} for c in completions[:5]]
                return CompleteResponse(completions=formatted, is_incomplete=False)
            except Exception:
                pass

        return CompleteResponse(completions=[])

    except Exception as e:
        print(f"[Complete] Error: {e}")
        return CompleteResponse(completions=[])
