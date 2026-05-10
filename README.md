# CodeLens — Local Offline Code Reading Assistant + AI Coding Agent (v0.3.1)

> Fully offline code understanding tool powered by llama.cpp + Qwen3.5, running entirely on your local machine.

## Features

- **Semantic Search** — BM25 enhanced retrieval + ONNX semantic reranking (bge-small-zh-v1.5)
- **4 Interaction Modes** — Ask / Plan / Craft / Agent
- **Streaming Output** — Real-time thinking display with per-character rendering
- **Code Editing** — Craft mode writes files directly, Plan mode supports one-click Build execution
- **Autonomous Agent** 🤖 — Multi-step self-directed execution with tool-calling system, diff editing, self-reflection, and error recovery
- **Fully Offline** — All models run locally, no cloud dependencies

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   CodeLens                       │
│                                                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  llama.cpp   │  │    local-coder-web       │ │
│  │  Inference   │  │    FastAPI Web Interface │ │
│  │  :8080       │◄─┤    :8765                  │ │
│  │              │  │                          │ │
│  │  Qwen3.5-9B  │  │  BM25 + ONNX Semantic    │ │
│  │  Q4_K_M      │  │  Ask / Plan / Craft      │ │
│  └──────────────┘  │  Agent (ReAct + Self-    │ │
│                    │  Reflection + Memory)     │ │
│                    └──────────────────────────┘ │
│                                                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │   Aider      │  │    Model Files            │ │
│  │  CLI Editor  │  │  Qwen3.5-9B.Q4_K_M.gguf │ │
│  │  (optional)  │  │  bge-small-zh-v1.5 ONNX  │ │
│  └──────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## Directory Structure

```
CodeLens/
├── README.md                    # This file
├── LICENSE                      # MIT License
├── Qwen3.5-9B.Q4_K_M.gguf     # Main model (Qwen3.5-9B quantized)
├── start-llama-server.ps1       # Start inference server
├── start-aider.ps1              # Start Aider CLI
├── start-local-coder-web.ps1    # Start Web interface
│
├── llama.cpp/                   # llama.cpp inference engine
│   ├── llama-server.exe         # OpenAI-compatible API server
│   └── *.dll                    # Runtime dependencies
│
├── local-coder-web/             # Web interface (FastAPI + vanilla frontend)
│   ├── app.py                   # Entry point: config loading, route registration
│   ├── config.py                # Centralized configuration constants
│   ├── core/
│   │   ├── agent.py             # AgentLoop (Plan-then-Apply + ReAct + Self-Reflection)
│   │   └── tools/
│   │       ├── base.py          # Tool ABC + ToolRegistry + Tool Recommendation
│   │       ├── read_file.py
│   │       ├── write_file.py
│   │       ├── edit_file.py
│   │       ├── apply_diff.py
│   │       ├── diff_preview.py
│   │       ├── search_files.py
│   │       ├── list_directory.py
│   │       ├── run_command.py     # Command whitelist + dangerous pattern + metacharacter filter
│   │       ├── git_operation.py
│   │       ├── undo_edit.py      # JSON-persisted undo/redo
│   │       ├── file_operations.py # copy/move/delete/mkdir
│   │       ├── code_analysis.py   # count_lines/find_references
│   │       ├── test.py             # Run tests
│   │       └── project.py          # Read config/package info
│   ├── services/
│   │   ├── indexer.py      # Unified indexing: scan + BM25 + embeddings
│   │   ├── search.py       # BM25 + ONNX semantic search
│   │   ├── memory.py       # Hierarchical memory (working + episodic)
│   │   ├── chat_history.py # Conversation history management
│   │   ├── file_watcher.py # File change monitoring
│   │   └── context_manager.py
│   ├── routes/
│   │   ├── main.py         # UI + status + settings
│   │   ├── ask.py          # /api/ask + /api/craft-apply
│   │   ├── files.py        # /api/set-folder + /api/read-file + /api/exec
│   │   ├── complete.py     # /api/complete (AI code completion)
│   │   └── agent.py        # /api/agent/* (Agent lifecycle + SSE streaming)
│   ├── static/
│   │   ├── index.html      # SPA entry point
│   │   ├── app.js          # Frontend logic (Agent phase panel, Diff preview)
│   │   └── styles.css      # Styles (dark/light themes)
│   ├── models/
│   │   └── bge-small-zh-v1.5/  # ONNX semantic model (optional)
│   └── tests/              # 71 test cases
│
├── Aider离线包/                 # Aider CLI offline package
│   └── wheels/                  # Python wheel files
│
└── local-coder/                  # Legacy scripts/downloads
    ├── downloads/
    ├── llama.cpp/
    ├── models/
    └── scripts/
```

## Quick Start

### Prerequisites

| Item | Requirement |
|------|-------------|
| **OS** | Windows 10/11 |
| **GPU** | NVIDIA GPU (CUDA), 8GB+ VRAM recommended |
| **RAM** | 16GB+ |
| **Python** | 3.11+ (for local-coder-web) |

### 1. Start Inference Server

```powershell
.\start-llama-server.ps1
```

Startup parameters:
- Model: `Qwen3.5-9B.Q4_K_M.gguf`
- Context length: 32768 tokens
- All layers offloaded to GPU (`-ngl 999`)
- KV cache reuse enabled (`--cache-reuse 3000`, `--cache-type-k q4_0`)
- Listening on: `http://127.0.0.1:8080`
- Disabled reasoning format (`--reasoning-format none`)

> First startup requires model loading (~10-30 seconds).

### 2. Start Web Interface

```powershell
.\start-local-coder-web.ps1
```

- Uses `.venv` Python automatically
- Listening on: `http://127.0.0.1:8765`
- Hot reload enabled (`--reload`)

### 3. Open Browser

Visit `http://127.0.0.1:8765`.

### 4. (Optional) Start Aider CLI

```powershell
.\start-aider.ps1
```

Aider is an AI pair programming CLI tool connecting to the local llama.cpp via the OpenAI-compatible interface.

## Usage

1. Click the **📁** button on the left sidebar to select a code directory, or enter the path manually
2. Click **"Load Repository"** and wait for indexing to complete
3. Type your question in the bottom input box and press **Enter**
4. Switch between mode tabs at the top

### Interaction Modes

| Mode | Function | Use Case |
|------|----------|----------|
| **Ask** 💬 | Answer code-related questions | Understanding code logic, finding implementation details |
| **Plan** 📋 | Analyze code structure, generate implementation plans | Architecture analysis, feature planning |
| **Craft** ✏️ | Edit code files directly | Batch modifications, refactoring |
| **Agent** 🤖 | Autonomous multi-step execution | Complex tasks with self-directed tool use |

### Agent Mode Capabilities

CodeLens Agent goes beyond simple tool-calling with advanced autonomous execution:

- **Plan-then-Apply Architecture** — Generates a modification plan first, previews diffs for each file, then executes confirmed changes in dependency order
- **Self-Reflection** 🧠 — Before each tool execution, the LLM evaluates its own planned action, identifies risks, and self-corrects (based on [Self-Refine](https://arxiv.org/abs/2303.17651))
- **Error Recovery** 🔄 — When a tool fails, the LLM analyzes the root cause and proposes a corrected action (up to 2 recovery attempts)
- **Hierarchical Memory** 📚 — Working memory (recent 4 steps) + episodic memory (compressed historical summaries) to keep context within budget
- **Tool Recommendation** 🎯 — Only presents the 4-6 most relevant tools per step (based on [ToolTalk](https://arxiv.org/abs/2401.06201)), saving ~1-2K tokens per call
- **Batch Tool Calls** — Allows batching up to 3 independent read-only tool calls per response, reducing LLM round-trips by ~30%
- **Dependency-Ordered Execution** — Files with dependencies are applied in topological order; each file change is verified after writing
- **Phase Indicator** — Real-time display: parsing → planning → preview → applying → done
- **16 Tools** — read_file, write_file, edit_file, apply_diff, search_files, list_directory, run_command, git_operation, undo_edit, diff_preview, file_operations, code_analysis, test, project
- **SSE Streaming** — Real-time step timeline, tool call display, execution progress
- **Security** — Command whitelist, dangerous pattern detection, shell metacharacter filtering, path traversal protection

### Advanced Agent Flow (ReAct Loop)

```
User Query
   │
   ▼
Intent Classification (simple vs complex)
   │
   ├── Simple → ReAct Loop
   │     │
   │     ├── LLM generates tool call(s)
   │     ├── Self-Reflection: evaluate planned action
   │     ├── If approved → Execute tool
   │     ├── If rejected → Rethink (max 2 consecutive)
   │     ├── On error → Root-cause analysis + retry (max 2 attempts)
   │     └── Compress context → MemoryStore (episodic summary)
   │
   └── Complex → Plan-then-Apply
         │
         ├── Generate modification plan (with dependencies)
         ├── Show diff preview per file
         ├── User approves/rejects each file
         ├── Apply in topological order
         └── Verify each file after write
```

## Search Modes

| Mode | Description | Prerequisites |
|------|-------------|---------------|
| **BM25** (default) | TF-IDF enhanced retrieval | No extra download needed |
| **ONNX Semantic** | More accurate semantic matching | Place bge-small-zh-v1.5 in `models/` directory |

### Retrieval Pipeline

```
User Query
   │
   ▼
Tokenization + Stop-word Filtering
   │
   ▼
BM25 Initial Screening → Top-30 Candidates
   │  (path match +3.0, symbol match +2.0)
   │
   ▼
ONNX Semantic Reranking (optional)
   │  (bge-small-zh-v1.5 cosine similarity)
   │
   ▼
Select Top-14 / 42K Characters
   │
   ▼
Injected into LLM Context
```

### Enabling ONNX Semantic Search

```powershell
# Download model files to models/bge-small-zh-v1.5/
# Required: model.onnx, tokenizer.json
# Service auto-enables after restart
```

ONNX model parameters:
- Max sequence length: 512 tokens
- Automatic Padding + Truncation
- CLS token output, L2-normalized
- Batch size: 32

## Technology Stack

| Component | Technology |
|-----------|------------|
| Inference Engine | llama.cpp (CUDA) |
| Language Model | Qwen3.5-9B Q4_K_M |
| Semantic Model | bge-small-zh-v1.5 (ONNX Runtime) |
| Backend | Python 3.11+ / FastAPI / Uvicorn / httpx |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Retrieval | BM25 (k1=1.5, b=0.75) + ONNX Vector Reranking |
| CLI | Aider (OpenAI-compatible interface) |
| Agent | ReAct + Plan-then-Apply + Self-Reflection + Hierarchical Memory |

## Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| Context Length | 32768 | llama.cpp maximum context |
| Max Index Files | 5000 | Single scan file limit |
| Max File Size | 220 KB | Skipped if exceeds |
| Context Characters | 42000 | Max code characters sent to LLM |
| BM25 Top-K | 30 | Initial candidate file count |
| Final Selection | 14 files | Max files sent to LLM |
| ONNX Batch Size | 32 | Embedding computation batch |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMA_URL` | `http://127.0.0.1:8080/v1/chat/completions` | llama.cpp service address |

## Security

- Craft mode file writes validate the target path is within the repository root (path traversal protection)
- All services bind to `127.0.0.1` only, not exposed to the network
- `run_command` has command whitelist + dangerous pattern detection
- All file tools perform path resolution validation before operations

## FAQ

**Q: "llama.cpp server is not running" error**
> Ensure `.\start-llama-server.ps1` was run first and wait for model loading to complete.

**Q: GPU VRAM insufficient**
> Modify the `-ngl` parameter in `start-llama-server.ps1` to reduce GPU layer count.

**Q: Search results inaccurate**
> Download bge-small-zh-v1.5 ONNX model to enable semantic search, or use more specific keywords.

**Q: Slow response time**
> Check GPU utilization, confirm CUDA is working correctly; reduce the number of indexed files.

**Q: How to update the model**
> Replace the `Qwen3.5-9B.Q4_K_M.gguf` file and update the model path in `start-llama-server.ps1`.

## License

MIT License — Copyright (c) 2026 Enze Peng

---

*Powered by llama.cpp + Qwen3.5 + FastAPI*
