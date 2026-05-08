# CodeLens — 本地离线代码阅读助手

> 基于 llama.cpp + Qwen3.5 的完全离线代码理解工具，无需联网即可运行。

## 项目简介

CodeLens 是一套本地部署的 AI 代码阅读与编辑工具集，核心能力包括：

- **语义搜索** — BM25 增强检索 + ONNX 语义重排（bge-small-zh-v1.5）
- **代码问答** — Ask / Plan / Craft 三种交互模式
- **流式输出** — 实时显示 thinking 过程，回答逐字渲染
- **代码编辑** — Craft 模式可直接写入文件，Plan 模式支持 Build 一键执行
- **完全离线** — 所有模型本地运行，不依赖任何云服务

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                   CodeLens                       │
│                                                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  llama.cpp   │  │    local-coder-web       │ │
│  │  推理服务     │  │    FastAPI Web 界面       │ │
│  │  :8080       │◄─┤    :8765                  │ │
│  │              │  │                          │ │
│  │  Qwen3.5-9B  │  │  BM25 + ONNX 语义搜索   │ │
│  │  Q4_K_M      │  │  Ask / Plan / Craft      │ │
│  └──────────────┘  └──────────────────────────┘ │
│                                                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │   Aider      │  │    模型文件               │ │
│  │  CLI 编辑器  │  │  Qwen3.5-9B.Q4_K_M.gguf │ │
│  │  (可选)      │  │  bge-small-zh-v1.5 ONNX  │ │
│  └──────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## 目录结构

```
CodeLens/
├── README.md                    # 本文档
├── LICENSE                      # MIT License
├── Qwen3.5-9B.Q4_K_M.gguf     # 主模型（Qwen3.5-9B 量化）
├── start-llama-server.ps1       # 启动推理服务
├── start-aider.ps1              # 启动 Aider CLI
├── start-local-coder-web.ps1    # 启动 Web 界面
│
├── llama.cpp/                   # llama.cpp 推理引擎
│   ├── llama-server.exe         # OpenAI 兼容 API 服务
│   └── *.dll                    # 运行时依赖
│
├── local-coder-web/             # Web 界面（FastAPI + 原生前端）
│   ├── app.py                   # 后端：搜索、流式输出、Craft API
│   ├── README.md                # Web 模块详细文档
│   ├── static/
│   │   ├── index.html           # 页面入口
│   │   ├── app.js               # 前端交互逻辑
│   │   └── styles.css           # 样式
│   └── models/
│       └── bge-small-zh-v1.5/  # ONNX 语义模型（可选）
│
├── Aider离线包/                  # Aider CLI 离线安装包
│   └── wheels/                  # Python wheel 文件
│
└── local-coder/                  # 旧版脚本/下载目录
    ├── downloads/
    ├── llama.cpp/
    ├── models/
    └── scripts/
```

## 快速开始

### 前置要求

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10/11 |
| **GPU** | NVIDIA GPU（CUDA），推荐 8GB+ 显存 |
| **内存** | 16GB+ RAM |
| **Python** | 3.11+（local-coder-web 需要） |

### 1. 启动推理服务

```powershell
.\start-llama-server.ps1
```

启动参数：
- 模型：`Qwen3.5-9B.Q4_K_M.gguf`
- 上下文长度：32768 tokens
- 全部层离载到 GPU（`-ngl 999`）
- 监听地址：`http://127.0.0.1:8080`
- 禁用 reasoning 格式（`--reasoning-format none`）

> 首次启动需等待模型加载，约需 10-30 秒。

### 2. 启动 Web 界面

```powershell
.\start-local-coder-web.ps1
```

- 自动使用 `.venv` 中的 Python
- 监听地址：`http://127.0.0.1:8765`
- 支持热重载（`--reload`）

### 3. 打开浏览器

访问 `http://127.0.0.1:8765`，即可使用。

### 4.（可选）启动 Aider CLI

```powershell
.\start-aider.ps1
```

Aider 是一个 AI 配对编程 CLI 工具，通过 OpenAI 兼容接口连接本地 llama.cpp 服务。

## 使用方式

1. 点击左侧 **📁** 按钮选择代码目录，或手动输入路径
2. 点击 **「加载代码库」**，等待索引完成
3. 在底部输入框提问，按 **Enter** 发送
4. 切换顶部模式标签选择交互模式

### 交互模式

| 模式 | 功能 | 适用场景 |
|------|------|----------|
| **Ask** 💬 | 回答代码相关问题 | 理解代码逻辑、查找实现细节 |
| **Plan** 📋 | 分析代码结构，生成实现方案 | 架构分析、功能规划 |
| **Craft** ✏️ | 直接编辑代码文件 | 批量修改、重构 |

### 搜索模式

| 模式 | 说明 | 前置条件 |
|------|------|----------|
| **BM25**（默认） | 基于词频的增强检索 | 无需额外下载 |
| **ONNX 语义** | 语义匹配更精准 | 需放置 bge-small-zh-v1.5 到 `models/` 目录 |

## 技术栈

| 组件 | 技术 |
|------|------|
| 推理引擎 | llama.cpp (CUDA) |
| 语言模型 | Qwen3.5-9B Q4_K_M |
| 语义模型 | bge-small-zh-v1.5 (ONNX Runtime) |
| 后端 | Python 3.11+ / FastAPI / Uvicorn / httpx |
| 前端 | 原生 HTML/CSS/JS（无框架依赖） |
| 检索 | BM25 (k1=1.5, b=0.75) + ONNX 向量重排 |
| CLI | Aider (OpenAI 兼容接口) |

## 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 上下文长度 | 32768 | llama-server 最大上下文 |
| 最大索引文件 | 5000 | 单次扫描文件上限 |
| 单文件大小上限 | 220 KB | 超过则跳过 |
| 上下文字符上限 | 42000 | 送入 LLM 的代码总字符数 |
| BM25 Top-K | 30 | 初筛候选文件数 |
| 最终选取 | 14 文件 | 送入 LLM 的文件数上限 |
| ONNX 批量大小 | 32 | Embedding 计算批量 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLAMA_URL` | `http://127.0.0.1:8080/v1/chat/completions` | llama.cpp 服务地址 |

## 常见问题

**Q: 提示 "llama.cpp server is not running"**
> 确保先运行 `.\start-llama-server.ps1`，等待模型加载完成。

**Q: GPU 显存不足**
> 修改 `start-llama-server.ps1` 中的 `-ngl` 参数，减少 GPU 层数。

**Q: 搜索结果不准确**
> 下载 bge-small-zh-v1.5 ONNX 模型启用语义搜索，或使用更具体的关键词。

**Q: 回答速度慢**
> 检查 GPU 利用率，确认 CUDA 正常工作；减少索引文件数量。

**Q: 如何更新模型**
> 替换 `Qwen3.5-9B.Q4_K_M.gguf` 文件，修改 `start-llama-server.ps1` 中的模型路径即可。

## License

MIT License — Copyright (c) 2026 Enze Peng

---

*Powered by llama.cpp + Qwen3.5 + FastAPI*
