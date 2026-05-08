from __future__ import annotations

import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


APP_DIR = Path(__file__).resolve().parent
LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080/v1/chat/completions")

# ---------------------------------------------------------------------------
# Optional: ONNX embedding model (bge-small-zh-v1.5)
# ---------------------------------------------------------------------------
MODEL_DIR = APP_DIR / "models" / "bge-small-zh-v1.5"
_ort_session = None
_ort_tokenizer = None


def _try_load_onnx_model() -> bool:
    global _ort_session, _ort_tokenizer
    onnx_path = MODEL_DIR / "model.onnx"
    tokenizer_path = MODEL_DIR / "tokenizer.json"
    if not onnx_path.exists() or not tokenizer_path.exists():
        return False
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        _ort_session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        _ort_tokenizer = Tokenizer.from_file(str(tokenizer_path))
        _ort_tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=512)
        _ort_tokenizer.enable_truncation(max_length=512)
        print("[Embedding] ONNX model loaded from", onnx_path)
        return True
    except Exception as exc:
        print(f"[Embedding] ONNX load failed ({exc}), using BM25 fallback")
        return False


_onnx_available = _try_load_onnx_model()

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    "node_modules", "dist", "build", ".next", ".nuxt", ".turbo",
    ".cache", "target", "bin", "obj", "coverage",
}

CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".java", ".kt", ".kts", ".go", ".rs", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".php", ".rb", ".swift", ".m", ".mm",
    ".sql", ".sh", ".ps1", ".bat", ".cmd",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml",
    ".xml", ".md", ".txt",
}

MAX_FILE_BYTES = 220_000
MAX_INDEX_FILES = 5000
MAX_CONTEXT_CHARS = 42_000
BM25_K1 = 1.5
BM25_B = 0.75

# Mode-specific system prompts
SYSTEM_PROMPTS = {
    "ask": (
        "You are a local codebase reading assistant. Answer in Simplified Chinese. "
        "Use the provided file tree and code snippets to answer. Prefer concrete paths, "
        "function names, call relationships, and clear conclusions. If the context is "
        "insufficient, say which files should be inspected. Do not invent implementation "
        "details that are not supported by the context."
    ),
    "plan": (
        "You are a code architecture planning assistant. Answer in Simplified Chinese. "
        "Given the codebase context, produce a structured implementation plan. Include: "
        "1) current state analysis, 2) proposed changes with file paths and function names, "
        "3) step-by-step implementation order, 4) risk assessment. Be specific and reference "
        "actual code paths. Do not invent details not supported by the context."
    ),
    "craft": (
        "You are a code editing assistant. Answer in Simplified Chinese. "
        "When the user asks for code modifications, output the exact modified file content. "
        "IMPORTANT OUTPUT FORMAT:\n"
        "1. Briefly explain what you changed and why (1-3 sentences)\n"
        "2. For each modified file, output a fenced code block with the RELATIVE file path "
        "as the language tag, like:\n"
        "```src/main.py\n# complete file content here\n```\n"
        "3. If only a function/section changed, still provide the COMPLETE file with the change applied, "
        "so the user can write the entire file safely.\n"
        "4. For multiple files, label each clearly:\n"
        "### 修改文件: src/main.py\n```src/main.py\n...\n```\n"
        "5. Preserve ALL existing code that is not being modified. Do NOT omit unchanged parts.\n"
        "6. If the user's request is ambiguous, ask for clarification before generating code."
    ),
}

# Default model settings
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.15
DEFAULT_CONTEXT_LIMIT = 42000


@dataclass
class CodeFile:
    path: Path
    rel: str
    size: int
    text: str
    symbols: list[str]
    tf: dict[str, float] = field(default_factory=dict)
    embedding: np.ndarray | None = None


class FolderRequest(BaseModel):
    path: str


class AskRequest(BaseModel):
    question: str
    mode: str = "ask"
    file_path: str | None = None
    new_content: str | None = None
    history: list[dict] | None = None  # 消息历史，用于共享上下文
    max_tokens: int | None = None
    temperature: float | None = None
    context_limit: int | None = None  # 用户自定义的上下文字符上限


class CraftApplyRequest(BaseModel):
    file_path: str
    content: str


class AppState:
    root: Path | None = None
    files: list[CodeFile] = []
    tree: str = ""
    idf: dict[str, float] = {}
    avg_dl: float = 0.0
    embedding_ready: bool = False


state = AppState()
app = FastAPI(title="Local Coder Web")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "folder": str(state.root) if state.root else "",
        "file_count": len(state.files),
        "tree": state.tree,
        "embedding_mode": "onnx" if (_onnx_available and state.embedding_ready) else "bm25",
    }


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    """Get system prompts and default settings."""
    return {
        "system_prompts": SYSTEM_PROMPTS,
        "defaults": {
            "max_tokens": DEFAULT_MAX_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
            "context_limit": DEFAULT_CONTEXT_LIMIT,
        },
    }


class ReadFileRequest(BaseModel):
    path: str


@app.post("/api/read-file")
def read_file(req: ReadFileRequest) -> dict[str, Any]:
    """Read a file's content within the indexed repository."""
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    target = (state.root / req.path).resolve()
    try:
        target.relative_to(state.root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path is outside the repository root")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Read failed: {exc}") from exc

    return {
        "path": req.path,
        "name": target.name,
        "ext": target.suffix.lower(),
        "size": target.stat().st_size,
        "content": content,
    }


@app.post("/api/set-folder")
def set_folder(req: FolderRequest) -> dict[str, Any]:
    root = Path(req.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="Folder does not exist")

    files = scan_repo(root)
    state.root = root
    state.files = files
    state.tree = build_tree(root, files)
    build_bm25_index(state)

    state.embedding_ready = False
    if _onnx_available:
        try:
            _build_embeddings(files)
            state.embedding_ready = True
        except Exception as exc:
            print(f"[Embedding] build failed: {exc}")

    return {
        "folder": str(root),
        "file_count": len(files),
        "tree": state.tree,
        "embedding_mode": "onnx" if state.embedding_ready else "bm25",
    }


@app.post("/api/ask")
async def ask(req: AskRequest):
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty")

    mode = req.mode if req.mode in SYSTEM_PROMPTS else "ask"
    # Use user-specified context limit if provided
    context_limit = req.context_limit if req.context_limit else None
    selected = select_context(question, state, context_limit)
    context = render_context(selected, context_limit)

    # 构建用户内容
    user_content = (
        f"Repository root: {state.root}\n\n"
        f"File tree summary:\n{state.tree[:9000]}\n\n"
        f"Relevant code snippets:\n{context}\n\n"
        f"User question: {question}"
    )

    # Craft mode: if file_path + new_content provided, include them
    if mode == "craft" and req.file_path and req.new_content is not None:
        user_content += (
            f"\n\nTarget file: {req.file_path}\n"
            f"Proposed new content:\n```\n{req.new_content}\n```"
        )

    # 构建消息列表，支持跨模式共享上下文
    messages = [{"role": "system", "content": SYSTEM_PROMPTS[mode]}]

    # 添加历史消息（最近10条，跨模式共享）
    if req.history:
        recent = req.history[-10:]
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            msg_mode = msg.get("mode", "ask")
            if not content:
                continue
            if role == "user":
                # 标注来源模式，帮助 LLM 理解上下文
                if msg_mode != mode:
                    messages.append({"role": "user", "content": f"[{msg_mode.upper()}模式] {content}"})
                else:
                    messages.append({"role": "user", "content": content})
            elif role == "assistant":
                # 助手回复截断，避免上下文过长
                messages.append({"role": "assistant", "content": content[:800]})

    # 添加当前问题
    messages.append({"role": "user", "content": user_content})

    # Use user settings if provided, otherwise use mode defaults
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


@app.post("/api/craft-apply")
def craft_apply(req: CraftApplyRequest) -> dict[str, Any]:
    """Write content to a file within the indexed repository."""
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    # Security: ensure the path stays within the repo root
    target = (state.root / req.file_path).resolve()
    try:
        target.relative_to(state.root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path is outside the repository root")

    # Create parent directories if needed
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        target.write_text(req.content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Write failed: {exc}") from exc

    return {"path": req.file_path, "bytes_written": len(req.content.encode("utf-8"))}


@app.post("/api/reindex")
def reindex() -> dict[str, Any]:
    """Re-index the current repository after file modifications."""
    if state.root is None:
        raise HTTPException(status_code=400, detail="Please set a folder first")

    files = scan_repo(state.root)
    state.files = files
    state.tree = build_tree(state.root, files)
    build_bm25_index(state)

    state.embedding_ready = False
    if _onnx_available:
        try:
            _build_embeddings(files)
            state.embedding_ready = True
        except Exception as exc:
            print(f"[Embedding] rebuild failed: {exc}")

    return {
        "folder": str(state.root),
        "file_count": len(files),
        "tree": state.tree,
        "embedding_mode": "onnx" if state.embedding_ready else "bm25",
    }


class BrowseRequest(BaseModel):
    path: str = ""


@app.post("/api/browse-dirs")
def browse_dirs(req: BrowseRequest) -> dict[str, Any]:
    """List subdirectories of a given path for directory browsing."""
    base = Path(req.path).expanduser().resolve() if req.path else Path.home()

    # If path doesn't exist, fallback to home
    if not base.exists() or not base.is_dir():
        base = Path.home()

    dirs: list[dict[str, str]] = []
    try:
        for entry in sorted(base.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.is_dir() and not entry.name.startswith(".") and entry.name not in IGNORE_DIRS:
                try:
                    dirs.append({"name": entry.name, "path": str(entry)})
                except OSError:
                    continue
    except OSError:
        pass

    return {
        "current": str(base),
        "parent": str(base.parent) if str(base) != str(base.parent) else "",
        "dirs": dirs,
    }


# ---------------------------------------------------------------------------
# Terminal command execution
# ---------------------------------------------------------------------------

class ExecRequest(BaseModel):
    command: str
    cwd: str = ""


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    returncode: int


@app.post("/api/exec")
def exec_command(req: ExecRequest) -> ExecResponse:
    """Execute a shell command and return the output."""
    import subprocess
    
    # Security: block dangerous commands
    dangerous_patterns = [
        "rm -rf /", "mkfs", "dd if=", ">:", "|:",
        "curl.*| sh", "wget.*| sh", "python.*| sh",
    ]
    cmd_lower = req.command.lower()
    for pattern in dangerous_patterns:
        if pattern in cmd_lower:
            raise HTTPException(status_code=403, detail="Command not allowed for security reasons")
    
    # Default to workspace directory if no cwd specified
    cwd = req.cwd if req.cwd else str(APP_DIR)
    
    try:
        result = subprocess.run(
            req.command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout
        )
        return ExecResponse(
            stdout=result.stdout[:50000],  # Limit output size
            stderr=result.stderr[:10000],
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Command timed out after 60 seconds")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(exc)}")


# ---------------------------------------------------------------------------
# AI Code Completion
# ---------------------------------------------------------------------------

class CompleteRequest(BaseModel):
    code: str
    cursor_pos: int = 0
    file_path: str = ""


class CompleteResponse(BaseModel):
    completions: list[dict]
    is_incomplete: bool = False


@app.post("/api/complete")
def code_complete(req: CompleteRequest) -> CompleteResponse:
    """Get AI-powered code completions based on current context."""
    
    # Return empty if no code provided
    if not req.code or not req.code.strip():
        return CompleteResponse(completions=[])
    
    # Build prompt for completion
    prompt = f"""Complete the following code. Provide up to 5 possible completions.
Return in JSON format: [{{"text": "completion text", "description": "what this does"}}]

Current code:
```
{req.code}
```
Cursor position: {req.cursor_pos}

Completions:"""
    
    try:
        import httpx
        import asyncio
        
        # Use sync call with timeout
        response = httpx.post(
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
        
        # Parse JSON completions
        import re
        json_match = re.search(r'\[[\s\S]*\]', content)
        if json_match:
            import json
            try:
                completions = json.loads(json_match.group())
                # Format for frontend
                formatted = [{"text": c.get("text", ""), "description": c.get("description", "")} for c in completions[:5]]
                return CompleteResponse(completions=formatted, is_incomplete=False)
            except:
                pass
        
        return CompleteResponse(completions=[])
        
    except Exception as e:
        print(f"[Complete] Error: {e}")
        return CompleteResponse(completions=[])


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------

async def _stream_llama(payload: dict, sources: list[dict], mode: str = "ask", context_chars: int = 0) -> AsyncIterator[str]:
    started = time.perf_counter()
    token_count = 0
    full_text = ""

    def _sse(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    yield _sse({"type": "sources", "sources": sources, "mode": mode, "context_chars": context_chars})

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
        yield _sse({"type": "error", "message": "❌ 无法连接到 llama.cpp 服务 (127.0.0.1:8080)\n请确保已运行 start-llama-server.ps1"})
        return
    except httpx.TimeoutException:
        yield _sse({"type": "error", "message": "⏱️ 请求超时，模型响应时间过长"})
        return
    except httpx.HTTPStatusError as exc:
        yield _sse({"type": "error", "message": f"⚠️ 模型返回错误 ({exc.response.status_code}): {exc.response.text[:200]}"})
        return
    except Exception as exc:
        yield _sse({"type": "error", "message": f"❌ 未知错误: {str(exc)[:100]}"})
        return

    elapsed = max(time.perf_counter() - started, 0.001)
    parsed = split_answer(full_text)

    yield _sse({
        "type": "done",
        "answer": parsed["answer"] or "(模型没有返回正文，请重试或换一个更具体的问题。)",
        "thinking": parsed["thinking"],
        "mode": mode,
        "metrics": {
            "elapsed_seconds": round(elapsed, 2),
            "completion_tokens": token_count,
            "tokens_per_second": round(token_count / elapsed, 2) if token_count else None,
        },
    })


# ---------------------------------------------------------------------------
# BM25 index
# ---------------------------------------------------------------------------

def _tokenize_doc(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][\w$.-]*|[\u4e00-\u9fff]{1,}", text.lower())


def build_bm25_index(st: AppState) -> None:
    files = st.files
    N = len(files)
    if N == 0:
        st.idf = {}
        st.avg_dl = 0.0
        return

    df: dict[str, int] = defaultdict(int)
    total_len = 0
    for f in files:
        doc = f"{f.rel} {' '.join(f.symbols)} {f.text[:8000]}"
        tokens = _tokenize_doc(doc)
        f.tf = {}
        cnt = Counter(tokens)
        for term, freq in cnt.items():
            f.tf[term] = freq
            df[term] += 1
        total_len += len(tokens)

    st.avg_dl = total_len / N
    st.idf = {}
    for term, freq in df.items():
        st.idf[term] = math.log((N - freq + 0.5) / (freq + 0.5) + 1)


def bm25_score(query_terms: list[str], file: CodeFile, avg_dl: float, idf: dict[str, float]) -> float:
    dl = sum(file.tf.values())
    score = 0.0
    for term in query_terms:
        if term not in file.tf:
            continue
        tf = file.tf[term]
        idf_val = idf.get(term, 0.0)
        numerator = tf * (BM25_K1 + 1)
        denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / max(avg_dl, 1))
        score += idf_val * numerator / denominator
    return score


# ---------------------------------------------------------------------------
# ONNX embedding (optional)
# ---------------------------------------------------------------------------

def _embed_texts(texts: list[str]) -> np.ndarray:
    enc = _ort_tokenizer.encode_batch(texts)
    input_ids = np.array([e.ids for e in enc], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids, dtype=np.int64)
    outputs = _ort_session.run(None, {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    })
    embeddings = outputs[0][:, 0, :]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / np.maximum(norms, 1e-9)


def _build_embeddings(files: list[CodeFile]) -> None:
    BATCH = 32
    texts = [f"{f.rel}: {' '.join(f.symbols[:10])} {f.text[:400]}" for f in files]
    for i in range(0, len(texts), BATCH):
        batch_texts = texts[i:i + BATCH]
        batch_embs = _embed_texts(batch_texts)
        for j, emb in enumerate(batch_embs):
            files[i + j].embedding = emb
    print(f"[Embedding] Built embeddings for {len(files)} files")


# ---------------------------------------------------------------------------
# Context selection
# ---------------------------------------------------------------------------

def select_context(question: str, st: AppState, context_limit: int | None = None) -> list[CodeFile]:
    """Select relevant code files for the question.
    
    Args:
        question: The user's question
        st: Application state with indexed files
        context_limit: Optional user-specified context character limit
    """
    files = st.files
    if not files:
        return []

    query_terms = _tokenize_query(question)
    if not query_terms:
        return files[:10]

    bm25_scored: list[tuple[float, CodeFile]] = []
    for f in files:
        score = bm25_score(query_terms, f, st.avg_dl, st.idf)
        for term in query_terms:
            if term in f.rel.lower():
                score += 3.0
            if any(term in sym.lower() for sym in f.symbols):
                score += 2.0
        if score > 0:
            bm25_scored.append((score, f))

    if not bm25_scored:
        return files[:10]

    bm25_scored.sort(key=lambda x: x[0], reverse=True)
    candidates = [f for _, f in bm25_scored[:30]]

    if _onnx_available and st.embedding_ready and candidates:
        try:
            q_emb = _embed_texts([question])[0]
            scored_by_emb: list[tuple[float, CodeFile]] = []
            for f in candidates:
                sim = float(np.dot(q_emb, f.embedding)) if f.embedding is not None else 0.0
                scored_by_emb.append((sim, f))
            scored_by_emb.sort(key=lambda x: x[0], reverse=True)
            candidates = [f for _, f in scored_by_emb]
        except Exception as exc:
            print(f"[Embedding] re-rank failed: {exc}")

    # Use user-specified limit if provided, otherwise use default
    max_chars = context_limit if context_limit is not None else MAX_CONTEXT_CHARS
    
    selected: list[CodeFile] = []
    total = 0
    for f in candidates:
        selected.append(f)
        total += min(len(f.text), 7000)
        if len(selected) >= 14 or total >= max_chars:
            break
    return selected


def _tokenize_query(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z_][\w$.-]*|[\u4e00-\u9fff]{1,}", text.lower())
    stop = {
        "the", "and", "or", "for", "with", "this", "that",
        "代码", "项目", "文件", "函数", "哪里", "什么", "如何", "怎么",
        "请", "帮", "我", "是", "的", "在", "有", "了", "要", "看",
    }
    return [t for t in raw if t not in stop and len(t) >= 2][:60]


# ---------------------------------------------------------------------------
# File scanning and helpers
# ---------------------------------------------------------------------------

def scan_repo(root: Path) -> list[CodeFile]:
    result: list[CodeFile] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".aider")]
        current_path = Path(current)
        for name in sorted(filenames):
            if len(result) >= MAX_INDEX_FILES:
                return result
            path = current_path / name
            if not should_read_file(path):
                continue
            try:
                size = path.stat().st_size
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            result.append(CodeFile(path=path, rel=rel, size=size, text=text, symbols=extract_symbols(text)))
    return result


def should_read_file(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return False
    except OSError:
        return False
    if path.name.startswith(".") and path.name not in {".env.example", ".gitignore"}:
        return False
    return path.suffix.lower() in CODE_EXTS


def extract_symbols(text: str) -> list[str]:
    patterns = [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w$]*)",
        r"^\s*(?:export\s+)?class\s+([A-Za-z_][\w$]*)",
        r"^\s*def\s+([A-Za-z_]\w*)",
        r"^\s*class\s+([A-Za-z_]\w*)",
        r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\],\s]+\s+([A-Za-z_]\w*)\s*\(",
        r"^\s*func\s+([A-Za-z_]\w*)",
    ]
    symbols: list[str] = []
    for line in text.splitlines()[:1600]:
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                name = match.group(1)
                if name not in symbols:
                    symbols.append(name)
                break
        if len(symbols) >= 30:
            break
    return symbols


def build_tree(root: Path, files: list[CodeFile]) -> dict:
    """Build a nested tree structure for the frontend to render as a collapsible tree."""
    tree: dict = {"name": root.name, "type": "dir", "path": "", "children": {}}

    for file in files[:2000]:
        parts = Path(file.rel).parts
        node = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # File leaf
                node["children"][part] = {
                    "name": part,
                    "type": "file",
                    "path": file.rel,
                    "size": file.size,
                    "ext": Path(part).suffix.lower(),
                }
            else:
                # Directory node
                if part not in node["children"]:
                    sub_path = str(Path(*parts[: i + 1]))
                    node["children"][part] = {
                        "name": part,
                        "type": "dir",
                        "path": sub_path,
                        "children": {},
                    }
                node = node["children"][part]

    # Convert children dicts to sorted lists
    def _sort_node(n: dict) -> dict:
        if n["type"] == "file":
            return {k: v for k, v in n.items() if k != "children"}
        child_list = sorted(
            n["children"].values(),
            key=lambda c: (c["type"] != "dir", c["name"].lower()),
        )
        return {
            "name": n["name"],
            "type": n["type"],
            "path": n["path"],
            "children": [_sort_node(c) for c in child_list],
        }

    return _sort_node(tree)


def render_context(files: list[CodeFile], context_limit: int | None = None) -> str:
    """Render selected files into context string.
    
    Args:
        files: List of selected code files
        context_limit: Optional user-specified character limit
    """
    max_chars = context_limit if context_limit is not None else MAX_CONTEXT_CHARS
    chunks: list[str] = []
    used = 0
    for file in files:
        budget = min(9000, max_chars - used)
        if budget <= 0:
            break
        text = file.text[:budget]
        chunks.append(f"--- FILE: {file.rel} ---\n{text}")
        used += len(text)
    return "\n\n".join(chunks)


def split_answer(answer: str) -> dict[str, str]:
    """Split model output into thinking + visible answer.

    Handles multiple thinking tag styles:
    - Qwen3: <think>...</think> (actual model output)
    - Open tag at start without closing (still generating)
    """
    answer = answer.strip()
    think_parts: list[str] = []
    visible = answer

    # Pattern 1: <think>...</think> tags (Qwen3 style - actual model output)
    open_tag = '<think>'
    close_tag = '</think>'
    if open_tag in answer and close_tag in answer:
        # Extract all thinking blocks
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
        # Open tag but no close tag yet (still generating)
        si = answer.index(open_tag)
        think_content = answer[si + len(open_tag):]
        visible = answer[:si].strip()
        if think_content.strip() and not visible:
            return {"thinking": think_content.strip(), "answer": ""}
        think_parts = [think_content] if think_content.strip() else []

    thinking = "\n\n".join(part.strip() for part in think_parts if part.strip())
    return {"thinking": thinking, "answer": visible}


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    words = re.findall(r"[A-Za-z0-9_]+", text)
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    word_chars = sum(len(word) for word in words)
    other_count = max(len(text) - cjk_count - word_chars, 0)
    return max(1, int(cjk_count * 0.75 + len(words) * 1.25 + other_count * 0.2))