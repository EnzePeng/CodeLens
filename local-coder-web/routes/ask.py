"""
Ask/Craft routes — /api/ask, /api/craft-apply.
"""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import LLAMA_URL, SYSTEM_PROMPTS, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from models import state
from services.search import select_context, render_context

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    mode: str = "ask"
    file_path: str | None = None
    new_content: str | None = None
    history: list[dict] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    context_limit: int | None = None


class CraftApplyRequest(BaseModel):
    file_path: str
    content: str


def _split_answer(answer: str) -> dict[str, str]:
    """Split model output into thinking + visible answer."""
    answer = answer.strip()
    think_parts: list[str] = []
    visible = answer

    open_tag = '<think>'
    close_tag = '</think>'
    if open_tag in answer and close_tag in answer:
        parts = []
        remaining = answer
        while open_tag in remaining and close_tag in remaining:
            si = remaining.index(open_tag)
            ei = remaining.index(close_tag)
            if ei <= si:
                break
            parts.append(remaining[si + len(open_tag):ei])
            remaining = remaining[:si] + remaining[ei + len(close_tag):]
        think_parts = parts
        visible = remaining.strip()
    elif open_tag in answer:
        si = answer.index(open_tag)
        think_content = answer[si + len(open_tag):]
        visible = answer[:si].strip()
        if think_content.strip() and not visible:
            return {"thinking": think_content.strip(), "answer": ""}
        think_parts = [think_content] if think_content.strip() else []

    thinking = "\n\n".join(part.strip() for part in think_parts if part.strip())
    return {"thinking": thinking, "answer": visible}


def estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    import re
    if not text:
        return 0
    words = re.findall(r"[A-Za-z0-9_]+", text)
    cjk_count = len(re.findall(r"[一-鿿]", text))
    word_chars = sum(len(word) for word in words)
    other_count = max(len(text) - cjk_count - word_chars, 0)
    return max(1, int(cjk_count * 0.75 + len(words) * 1.25 + other_count * 0.2))


async def _stream_llama(
    payload: dict, sources: list[dict], mode: str = "ask", context_chars: int = 0,
) -> AsyncIterator[str]:
    def _sse(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    yield _sse({"type": "sources", "sources": sources, "mode": mode, "context_chars": context_chars})

    started = time.perf_counter()
    token_count = 0
    full_text = ""

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", LLAMA_URL, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    yield _sse({"type": "error", "message": f"HTTP {response.status_code}: {body.decode()[:200]}"})
                    return

                async for raw_line in response.aiter_lines():
                    if not raw_line.startswith("data:"):
                        continue
                    chunk_str = raw_line[5:].strip()
                    if chunk_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_str)
                    except json.JSONDecodeError:
                        continue

                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        token_count += 1
                        yield _sse({"type": "delta", "content": content})

    except httpx.ConnectError:
        yield _sse({"type": "error", "message": "Cannot connect to LLM service at 127.0.0.1:8080. Ensure start-llama-server.ps1 is running."})
        return
    except httpx.TimeoutException:
        yield _sse({"type": "error", "message": "Request timed out"})
        return
    except httpx.HTTPStatusError as exc:
        yield _sse({"type": "error", "message": f"Model error ({exc.response.status_code}): {exc.response.text[:200]}"})
        return
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Unknown error: {str(exc)[:100]}"})
        return

    elapsed = max(time.perf_counter() - started, 0.001)
    parsed = _split_answer(full_text)

    yield _sse({
        "type": "done",
        "answer": parsed["answer"] or "(Model did not return an answer)",
        "thinking": parsed["thinking"],
        "mode": mode,
        "metrics": {
            "elapsed_seconds": round(elapsed, 2),
            "completion_tokens": token_count,
            "tokens_per_second": round(token_count / elapsed, 2) if token_count else None,
        },
    })


def _get_onnx():
    import app as _app_module
    return _app_module.get_onnx_session()


@router.post("/api/ask")
async def ask(req: AskRequest):
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty")

    mode = req.mode if req.mode in SYSTEM_PROMPTS else "ask"
    context_limit = req.context_limit if req.context_limit else None
    selected = select_context(
        question, state.files, state.idf, state.avg_dl,
        state.embedding_ready, *_get_onnx(), context_limit,
    )
    context = render_context(selected, context_limit)

    user_content = (
        f"Repository root: {state.root}\n\n"
        f"File tree summary:\n{json.dumps(state.tree)[:9000]}\n\n"
        f"Relevant code snippets:\n{context}\n\n"
        f"User question: {question}"
    )

    if mode == "craft" and req.file_path and req.new_content is not None:
        user_content += (
            f"\n\nTarget file: {req.file_path}\n"
            f"Proposed new content:\n```\n{req.new_content}\n```"
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPTS[mode]}]

    if req.history:
        recent = req.history[-10:]
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            msg_mode = msg.get("mode", "ask")
            if not content:
                continue
            if role == "user":
                if msg_mode != mode:
                    messages.append({"role": "user", "content": f"[{msg_mode.upper()} mode] {content}"})
                else:
                    messages.append({"role": "user", "content": content})
            elif role == "assistant":
                messages.append({"role": "assistant", "content": content[:800]})

    messages.append({"role": "user", "content": user_content})

    temperature = req.temperature if req.temperature is not None else (0.15 if mode == "ask" else 0.25)
    max_tokens = req.max_tokens if req.max_tokens is not None else (2400 if mode in ("plan", "craft") else 1800)

    payload = {
        "model": "local",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    sources = [{"path": f.rel, "size": f.size, "symbols": f.symbols[:8]} for f in selected]
    context_chars = len(context)

    return StreamingResponse(
        _stream_llama(payload, sources, mode, context_chars),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/craft-apply")
def craft_apply(req: CraftApplyRequest) -> dict[str, Any]:
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    target = (state.root / req.file_path).resolve()
    try:
        target.relative_to(state.root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path is outside the repository root")

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        target.write_text(req.content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Write failed: {exc}") from exc

    return {"path": req.file_path, "bytes_written": len(req.content.encode("utf-8"))}
