# local-coder-web/routes/ask.py
# Fixed: BUG-01 (client undefined), BUG-02 (JSON body parsing),
# BUG-03 (context search integration), BUG-19 (SSE format)

import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncIterator

from models import AskRequest
from services.search import select_context, render_context
from config import SYSTEM_PROMPTS

logger = logging.getLogger(__name__)
router = APIRouter()

LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"

# Default configuration
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.15
DEFAULT_TIMEOUT = 600  # Increased to 600 seconds


def _sse(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_llama(
    query: str,
    context_info: list[dict],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    mode: str = "ask",
) -> AsyncIterator[str]:
    """
    Stream LLM response in SSE format matching frontend expectations:
      - sources event with referenced file info
      - context_plan/evidence/confidence events for project-understanding UI
      - delta events with content chunks
      - done event with accumulated answer at end
    """
    if context_info:
        yield _sse({
            "type": "context_plan",
            "strategy": "hybrid_search_with_evidence",
            "files": [item.get("path", "") for item in context_info[:10]],
            "message": "已选择最相关的代码文件作为只读上下文。",
        })
        yield _sse({
            "type": "evidence",
            "evidence": [
                {
                    "path": item.get("path", ""),
                    "start_line": item.get("start_line", 1),
                    "end_line": item.get("end_line", 1),
                    "symbol": item.get("symbol", ""),
                    "reason": item.get("reason", "selected context"),
                }
                for item in context_info[:10]
            ],
        })
        yield _sse({
            "type": "confidence",
            "level": "medium" if len(context_info) < 3 else "high",
            "reason": f"基于 {len(context_info)} 个上下文来源。",
        })

    # Yield context/sources event first
    if context_info:
        yield _sse({"type": "sources", "sources": context_info})

    # Use mode-specific system prompt
    system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS.get("ask", "You are a professional code assistant."))
    
    optimized_max_tokens = min(max_tokens, 4096)

    # 构建更简洁的提示词
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    # 使用completion端点（比chat端点更快）
    # 将消息转换为单个prompt
    prompt_text = ""
    for msg in messages:
        if msg["role"] == "system":
            prompt_text += f"System: {msg['content']}\n\n"
        elif msg["role"] == "user":
            prompt_text += f"User: {msg['content']}\n\n"
    prompt_text += "Assistant:"

    payload = {
        "model": "qwen3.5-9b",
        "prompt": prompt_text,
        "max_tokens": optimized_max_tokens,
        "temperature": temperature,
        "stream": True,
        "cache_prompt": True,
        "top_p": 0.9,
        "repeat_penalty": 1.1,
        "stop": ["User:", "System:"],
    }

    try:
        from app import get_http_client
        client = get_http_client()
        all_content = []
        done_sent = False

        completion_url = LLAMA_URL.replace("/v1/chat/completions", "/completion")

        async with client.stream("POST", completion_url, json=payload) as response:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                sse_tail = ""
                async for chunk in response.aiter_text(chunk_size=4096):
                    if not chunk:
                        continue
                    sse_tail += chunk.replace("\r\n", "\n")
                    while "\n" in sse_tail:
                        line, sse_tail = sse_tail.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue
                        line = line[6:]
                        if line == "[DONE]":
                            break

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        content = data.get("content", "")
                        stop = data.get("stop", False)

                        if content:
                            all_content.append(content)
                            yield _sse({"type": "delta", "content": content})

                        if stop:
                            answer = "".join(all_content)
                            yield _sse({"type": "done", "answer": answer, "finish_reason": "stop"})
                            done_sent = True
                            return

                if sse_tail.strip():
                    line = sse_tail.strip()
                    if line.startswith("data: "):
                        line = line[6:]
                        if line != "[DONE]":
                            try:
                                data = json.loads(line)
                                content = data.get("content", "")
                                if content:
                                    all_content.append(content)
                                    yield _sse({"type": "delta", "content": content})
                            except json.JSONDecodeError:
                                pass

        if not done_sent:
            answer = "".join(all_content)
            yield _sse({"type": "done", "answer": answer, "finish_reason": "stop"})

    except asyncio.TimeoutError:
        logger.error(f"LLM request timeout: {DEFAULT_TIMEOUT}s")
        yield _sse({"type": "error", "message": f"LLM request timeout ({DEFAULT_TIMEOUT}s)"})
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        yield _sse({"type": "error", "message": str(e)})


@router.post("/api/ask")
async def ask(req: AskRequest):
    """
    Ask mode: user asks a question, LLM answers with code context.
    """
    from models import state
    from services.indexer import build_bm25_index
    import app as _app_module

    question = req.question
    max_tokens = req.max_tokens if req.max_tokens is not None else DEFAULT_MAX_TOKENS
    temperature = req.temperature if req.temperature is not None else DEFAULT_TEMPERATURE

    # BUG-03: Build context from codebase
    context_chunks = []
    context_sources = []
    if state.root and state.files and state.idf:
        idf, avg_dl, _ = build_bm25_index(state.files)
        ort_sess, ort_tok = _app_module.get_onnx_session()

        # Build history context
        history_str = ""
        if req.history:
            history_str = "\n".join(
                f"{h.get('role', 'user')}: {h.get('content', '')}"
                for h in req.history[-10:]
            )

        context_question = question
        if history_str:
            context_question = f"{history_str}\n\nCurrent question: {question}"

        optimized_limit = min(req.context_limit, 42000) if req.context_limit else 42000
        
        selected = select_context(
            question=context_question,
            files=state.files,
            idf=idf,
            avg_dl=avg_dl,
            embedding_ready=state.embedding_ready,
            session=ort_sess,
            tokenizer=ort_tok,
            context_limit=optimized_limit,
            dep_graph=state.dep_graph,
        )
        context = render_context(selected)
        if context:
            context_chunks.append(f"Code context:\n{context}")
            # Build sources info for frontend
            for cf in selected[:10]:
                symbol = cf.symbols[0] if cf.symbols else ""
                context_sources.append({
                    "path": cf.rel,
                    "size": cf.size,
                    "start_line": 1,
                    "end_line": min(len(cf.text.splitlines()), 80),
                    "symbol": symbol,
                    "reason": "matched ask query",
                })

    if req.mode == "craft" and req.file_path and req.new_content:
        context_chunks.append(f"Craft mode - file: {req.file_path}\nContent: {req.new_content[:2000]}")

    context_str = "\n\n".join(context_chunks)
    if context_str:
        full_query = f"{context_str}\n\nUser question: {question}"
    else:
        full_query = question

    # If craft mode, apply the file change first
    if req.mode == "craft" and req.file_path and req.new_content:
        try:
            from core.tools import ToolRegistry
            ToolRegistry.execute("write_file", path=req.file_path, content=req.new_content)
        except Exception as e:
            logger.warning(f"Craft apply failed: {e}")

    return StreamingResponse(
        _stream_llama(full_query, context_sources, max_tokens, temperature, req.mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
