# CodeLens — Fully Offline AI Coding Agent & Code Intelligence Platform

> **100% local, privacy-first AI coding assistant** powered by llama.cpp + Qwen3.5-9B. Autonomous agent with ReAct reasoning, hierarchical memory, self-improvement, and 20+ development tools.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CUDA](https://img.shields.io/badge/CUDA-accelerated-green.svg)](https://developer.nvidia.com/cuda-zone)

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
  - [Autonomous Agent Engine](#autonomous-agent-engine)
  - [20+ Development Tools](#20-development-tools)
  - [Hybrid Search Pipeline](#hybrid-search-pipeline)
  - [FIM Code Completion](#fim-code-completion)
  - [VS Code Extension](#vs-code-extension)
  - [4 Interaction Modes](#4-interaction-modes)
- [Architecture](#architecture)
  - [System Architecture](#system-architecture)
  - [Agent Execution Pipeline](#agent-execution-pipeline)
  - [ReAct Loop Deep Dive](#react-loop-deep-dive)
  - [Memory System](#memory-system)
  - [Context Window Management](#context-window-management)
  - [Self-Improvement Loop](#self-improvement-loop)
- [Directory Structure](#directory-structure)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Configuration](#configuration)
- [Security](#security)
- [Technology Stack](#technology-stack)
- [Design Inspirations](#design-inspirations)
- [FAQ](#faq)
- [License](#license)

---

## Overview

CodeLens is a **fully offline, privacy-preserving AI coding agent** that runs entirely on your local machine. No cloud dependencies, no data leakage, no API keys required. Built on llama.cpp + Qwen3.5-9B
(quantized Q4_K_M), it provides:

- **Autonomous Agent** with multi-step planning, tool orchestration, and self-improvement
- **4 Interaction Modes**: Ask (Q&A), Plan (architecture analysis), Craft (direct editing), Agent (autonomous execution)
- **Advanced ReAct Loop** with task decomposition, parallel execution, and result aggregation
- **Hierarchical Memory** (working + episodic + semantic layers) for long-context reasoning
- **Self-Improvement Engine** that automatically optimizes performance over time
- **20+ Development Tools**: file operations, code search, AST analysis, LSP-like intelligence, Git integration
- **VS Code Extension** for inline FIM (Fill-In-the-Middle) code completion
- **Hybrid Retrieval**: BM25 keyword search + ONNX semantic reranking (bge-small-zh-v1.5)

---

## Key Features

### Autonomous Agent Engine

The heart of CodeLens is a sophisticated **multi-agent orchestration system** that goes far beyond simple tool-calling. It is composed of six tightly integrated subsystems:

#### Task Router — Intelligent Execution Strategy Selection

The `TaskRouter` classifies incoming queries into three execution modes using a **heuristic-first, LLM-optional** approach:

| Mode           | When Used                            | Example Queries                                              |
| -------------- | ------------------------------------ | ------------------------------------------------------------ |
| **Simple**     | Single-turn or few tool calls        | "Explain this function", "Find all imports"                  |
| **Multi-Step** | Requires planning + serial execution | "Add authentication to the API", "Refactor the database layer" |
| **Map-Reduce** | Batch operations that parallelize    | "Analyze all Python files for errors", "Generate docs for every module" |

**Heuristic signals detected:**
- **Batch indicators**: "all", "every", "each", glob patterns (`**/*.py`), "N files" where N >= 3
- **Multi-step indicators**: "implement", "refactor", "modify", "add feature"
- **Disambiguation**: When both signals fire, checks for explicit write intent (verb + target noun) to prefer multi-step over map-reduce
- **LLM fallback** (optional): For ambiguous queries, asks the LLM to classify via structured JSON prompt

#### Task Decomposer — Breaking Down Complex Tasks

For non-simple queries, the `TaskDecomposer` generates a structured subtask graph:

- **Map-Reduce decomposition**: Resolves batch targets via filesystem glob snapshots, creates one parallel subtask per target file, plus a final "report" subtask that depends on all others
- **Multi-step decomposition**: Template matching first (e.g., "search + rename", "read + modify + test" patterns), then LLM fallback for custom decomposition into 2-6 ordered subtasks with dependency
indices
- Each `SubTask` carries: id, description, kind, inputs, dependencies, parallelizability flag, and focus prompt

#### ReAct Loop — Reason-Act-Observe Cycle

The `ReActLoop` is the core execution engine implementing the **ReAct pattern** (Reason-Act-Observe) with advanced optimizations:

```
Initialize Context Slots (system prompt, user query, context)
    |
    v
+-- Iteration (up to max_iterations, default 15) ---+
|                                                     |
|  1. Render context window -> OpenAI messages        |
|  2. Call LLM (streaming)                            |
|  3. Detect repetitive generation -> truncate        |
|  4. Parse tool calls (multi-strategy)               |
|  5. No tool calls? -> Task complete (final answer)  |
|  6. Deduplicate (MD5 hash of tool+args)             |
|  7. Loop detection (warn at 3 identical calls)      |
|  8. Execute tools:                                  |
|     - Read-only: parallel (up to 6)                 |
|     - Write: sequential                             |
|  9. Inject results -> context + memory              |
| 10. Context overflow? -> compress old messages      |
|                                                     |
+-----------------------------------------------------+
    |
    v
Return final answer + work summary
```

**Key mechanisms:**
- **Repetition detection**: Word-level and n-gram cycling detection with automatic truncation
- **Argument normalization**: Maps common LLM parameter mistakes (e.g., `filename` -> `path`, `query` -> `pattern`, `cmd` -> `command`) to canonical names
- **Soft cap behavior**: If iterations exhaust, returns last LLM output + work summary marked as `hit_limit` (partial result, not a hard failure)

#### Hierarchical Memory System

The `HierarchicalMemory` system provides three-layer structured memory inspired by human cognition:

| Layer        | Purpose                                            | Capacity        | Lifetime        |
| ------------ | -------------------------------------------------- | --------------- | --------------- |
| **Working**  | Recent messages for the current subtask            | 8 entries       | Current subtask |
| **Episodic** | Completed subtask results with structured metadata | Ordered by time | Session         |
| **Semantic** | Core findings promoted from episodic results       | Flat list       | Session         |

**Key operations:**
- `set_active_subtask(id)` — Switches focus and clears working memory for fresh context
- `complete_subtask(...)` — Records structured results (status, summary, findings, files read/written, tools used, errors, duration) and accumulates global statistics
- `promote_subtask(id)` — Merges key findings from episodic to semantic layer for long-term retention
- `render_work_summary(max_chars)` — Generates a structured summary of completed work for injection into the context window
- `render_episodic_digest(max_chars)` — Compact digest of all subtask results for final report assembly

#### Result Aggregator — Synthesizing Final Reports

The `ReportAggregator` assembles the final output after all subtasks complete:

| Mode               | Condition         | Method                                                       |
| ------------------ | ----------------- | ------------------------------------------------------------ |
| **Concatenation**  | Large task counts | Structured Markdown with TOC, per-subtask sections, consolidated findings |
| **LLM Synthesis**  | <= 6 subtasks     | Sends compressed digests to LLM for integrated analysis report |
| **Auto** (default) | Automatic         | Uses LLM synthesis for small counts, concatenation for large ones |

The concatenation mode produces a report with status marks (checkmark/triangle/cross), per-subtask sections (description, status, duration, files involved, summary, findings, errors), and a consolidated
findings summary across all subtasks, capped at 25,000 characters.

#### Self-Improvement Engine — Continuous Optimization

The `SelfImprovementEngine` runs a closed-loop iteration cycle that automatically optimizes agent performance:

```
+-- Baseline Metrics -----------------------------------+
|  (success rate, avg latency, tool success rate)        |
|                                                        |
|  1. Collect current metrics from EnhancedMetrics       |
|  2. Analyze bottlenecks via SelfOptimizer              |
|     - High latency (p90 > 2s)                          |
|     - Low success rate (< 80%)                         |
|     - Tool failure rates (> 20%)                       |
|     - Context overflow rate (> 10%)                    |
|  3. Generate optimization suggestions                  |
|  4. Apply up to 3 optimizations per iteration          |
|     - CRITICAL/HIGH: auto-applied                      |
|     - MEDIUM: only if expected improvement > 15%       |
|  5. Verify improvements by comparing against baseline  |
|  6. Record iteration results                           |
|  7. Persist state to ~/.codelens/                      |
+--------------------------------------------------------+
```

**Optimization types:** tool optimization, context management, prompt engineering, caching, parallelization, memory management

**Default configuration:** 48 iterations over 24 hours (30 minutes per iteration). Run via CLI:

```bash
python local-coder-web/scripts/run_self_improvement.py --duration 24 --interval 30
```

---

### 20+ Development Tools

CodeLens provides a comprehensive toolkit for autonomous code development:

#### File Operations
| Tool              | Description                                                  |
| ----------------- | ------------------------------------------------------------ |
| `read_file`       | Read file contents with line numbers                         |
| `write_file`      | Write complete file contents (with path traversal protection) |
| `edit_file`       | Surgical string replacement in files                         |
| `apply_diff`      | Apply unified diff patches                                   |
| `diff_preview`    | Preview diff before applying                                 |
| `glob`            | Find files matching glob patterns (e.g., `**/*.py`), max 200 results |
| `file_operations` | Copy, move, delete, mkdir                                    |
| `undo_edit`       | JSON-persisted undo/redo for file edits                      |

#### Code Intelligence
| Tool             | Description                                                  |
| ---------------- | ------------------------------------------------------------ |
| `search_files`   | BM25 + ONNX semantic search across the codebase              |
| `list_directory` | List directory contents with metadata                        |
| `grep`           | Content search with regex patterns, file filters, directory scoping |
| `lsp`            | Symbol extraction, definition finding, reference search (Python/JS/TS/Go/Rust/Java/Kotlin) |
| `code_analysis`  | Count lines, find references, analyze structure              |
| `project`        | Read project configuration (package.json, pyproject.toml, etc.) |

#### Execution & Version Control
| Tool            | Description                                                  |
| --------------- | ------------------------------------------------------------ |
| `run_command`   | Execute shell commands (with whitelist + dangerous pattern detection) |
| `git_operation` | Git commands (status, diff, log, add, commit, etc.)          |
| `test`          | Run test suites (pytest, jest, go test, etc.)                |

#### Tool Call Parsing — Multi-Strategy Extraction

The tool call parser extracts structured tool invocations from LLM output using 4 cascading strategies
