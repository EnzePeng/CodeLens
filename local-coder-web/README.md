# Local Coder Web

基于本地 llama.cpp 的轻量级代码阅读助手，支持语义搜索、流式输出、多模式交互。

## 功能特性

- **语义搜索**：BM25 增强检索 + ONNX 语义重排（可选）
- **流式输出**：实时显示 thinking，回答逐字渲染
- **多模式交互**：
  - **Ask** 💬 — 问答模式，解答代码相关问题
  - **Plan** 📋 — 规划模式，分析代码结构并生成实现方案，支持 Build 一键执行
  - **Craft** ✏️ — 编辑模式，可直接修改代码文件
- **共享上下文**：跨模式对话历史共享，最近 10 条消息作为上下文
- **目录选择**：内置文件夹浏览器，一键选择代码目录
- **离线运行**：无需联网，本地模型即可工作

## 快速开始

### 1. 启动 llama.cpp 服务

```powershell
.\start-llama-server.ps1
```

默认监听 `http://127.0.0.1:8080`

### 2. 启动 Web 服务

```powershell
.\start-local-coder-web.ps1
```

打开浏览器访问 `http://127.0.0.1:8765`

### 3. 使用方式

1. 点击侧边栏「📁」按钮选择代码目录，或手动输入路径
2. 点击「加载代码库」，等待索引完成
3. 在底部输入框提问，按 Enter 发送
4. 切换顶部模式标签：Ask / Plan / Craft

## 目录结构

```
local-coder-web/
├── app.py              # FastAPI 后端（搜索、流式输出、Craft API）
├── README.md           # 本文档
├── static/
│   ├── index.html      # 页面入口
│   ├── app.js          # 前端逻辑（流式渲染、Markdown、Build 执行）
│   └── styles.css      # 样式（三模式主题色）
└── models/             # ONNX 语义模型（可选，不纳入 git）
    └── bge-small-zh-v1.5/
        ├── model.onnx
        └── tokenizer.json
```

## 模式说明

| 模式 | 功能 | Temperature | Max Tokens | 适用场景 |
|------|------|-------------|------------|----------|
| **Ask** 💬 | 回答关于代码的问题 | 0.15 | 1800 | 理解代码逻辑、查找实现细节 |
| **Plan** 📋 | 分析代码结构，生成实现方案 | 0.25 | 2400 | 架构分析、功能规划 |
| **Craft** ✏️ | 直接编辑代码文件 | 0.25 | 2400 | 批量修改、重构 |

### Craft 模式使用

1. 切换到 Craft 模式
2. 在下方「文件路径」输入目标文件（如 `src/main.py`）
3. 在「代码修改」区域输入新内容
4. 点击「应用修改」写入文件

> 也可以直接在输入框描述修改需求，LLM 会生成代码建议。

### Plan 模式 Build 功能

Plan 模式的回答中如果包含代码块，会自动出现 **🚀 Build** 按钮：
- 代码块语言标签为文件路径时（如 ` ```src/main.py`），自动识别
- 点击 Build 可一键将所有代码块写入对应文件
- 无文件路径的代码块显示为单独 Build 按钮

## 搜索模式

| 模式 | 说明 | 性能 |
|------|------|------|
| **BM25**（默认） | 基于词频的增强检索，无需额外下载 | 毫秒级 |
| **ONNX 语义** | 需下载 bge-small-zh-v1.5 到 `models/` 目录，语义匹配更精准 | 索引时秒级，查询时毫秒级 |

### 检索流程

```
用户提问
   │
   ▼
分词 + 停用词过滤
   │
   ▼
BM25 初筛 Top-30 候选
   │  (路径匹配 +3.0, 符号匹配 +2.0)
   │
   ▼
ONNX 语义重排 (可选)
   │  (bge-small-zh-v1.5 cosine similarity)
   │
   ▼
选取 Top-14 / 42K 字符
   │
   ▼
拼入 LLM 上下文
```

### 启用 ONNX 语义搜索

```powershell
# 下载模型文件到 models/bge-small-zh-v1.5/
# 需要：model.onnx, tokenizer.json
# 重启服务后自动启用
```

ONNX 模型参数：
- 最大序列长度：512 tokens
- 自动 Padding + Truncation
- 推理后取 CLS token 输出，L2 归一化
- 批量大小：32

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 页面入口 |
| `/api/status` | GET | 获取当前状态（文件夹、文件数、搜索模式） |
| `/api/set-folder` | POST | 设置代码目录，触发索引构建 |
| `/api/ask` | POST | 提问，返回 SSE 流式响应 |
| `/api/craft-apply` | POST | Craft 模式写入文件 |

### 请求体示例

**`/api/set-folder`**
```json
{ "path": "E:/Project/my-app" }
```

**`/api/ask`**
```json
{
  "question": "这个项目的入口文件在哪里？",
  "mode": "ask",
  "history": [{"role": "user", "mode": "ask", "content": "..."}],
  "file_path": null,
  "new_content": null
}
```

**`/api/craft-apply`**
```json
{
  "file_path": "src/main.py",
  "content": "print('hello')"
}
```

### SSE 流式事件

| 事件类型 | 说明 |
|----------|------|
| `sources` | 返回参考文件列表和当前模式 |
| `delta` | 增量文本片段 |
| `done` | 完成事件，含完整回答、thinking、性能指标 |
| `error` | 错误信息 |

## System Prompt

| 模式 | 核心指令 |
|------|----------|
| **Ask** | 代码库阅读助手，简体中文回答，引用具体路径和函数名 |
| **Plan** | 代码架构规划助手，输出结构化方案（现状→改动→步骤→风险） |
| **Craft** | 代码编辑助手，输出精确代码修改，代码块以文件路径为语言标签 |

## 索引配置

| 参数 | 值 | 说明 |
|------|-----|------|
| `MAX_INDEX_FILES` | 5000 | 单次扫描文件上限 |
| `MAX_FILE_BYTES` | 220,000 | 单文件大小上限（~220KB） |
| `MAX_CONTEXT_CHARS` | 42,000 | 送入 LLM 的代码总字符数 |
| `BM25_K1` | 1.5 | BM25 词频饱和参数 |
| `BM25_B` | 0.75 | BM25 文档长度归一化参数 |

### 忽略目录

```
.git, .hg, .svn, .venv, venv, env, __pycache__,
node_modules, dist, build, .next, .nuxt, .turbo,
.cache, target, bin, obj, coverage, .aider*
```

### 支持的文件扩展名

```
.py, .js, .jsx, .ts, .tsx, .vue, .svelte,
.java, .kt, .kts, .go, .rs, .c, .h, .cpp, .hpp,
.cs, .php, .rb, .swift, .m, .mm,
.sql, .sh, .ps1, .bat, .cmd,
.html, .css, .scss, .json, .yaml, .yml, .toml,
.xml, .md, .txt
```

## 符号提取

从代码文件中提取前 30 个符号（函数/类），用于增强搜索：

- `function name`（JS/TS）
- `class Name`（JS/TS）
- `def name`（Python）
- `class Name`（Python）
- `public/static Type name()`（Java/C#）
- `func name`（Go）

## 依赖

| 包 | 版本 | 必需 | 说明 |
|-----|------|------|------|
| Python | 3.11+ | ✅ | 运行时 |
| fastapi | — | ✅ | Web 框架 |
| uvicorn | — | ✅ | ASGI 服务器 |
| httpx | — | ✅ | HTTP 客户端（SSE 流式） |
| numpy | >= 1.26 | ✅ | BM25 计算 |
| pydantic | — | ✅ | 请求体验证 |
| onnxruntime | >= 1.25 | ❌ | ONNX 语义搜索 |
| tokenizers | — | ❌ | ONNX 分词器 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLAMA_URL` | `http://127.0.0.1:8080/v1/chat/completions` | llama.cpp API 地址 |

## 安全说明

- Craft 模式写入文件时，会验证目标路径在仓库根目录内（防路径穿越）
- 所有服务仅监听 `127.0.0.1`，不暴露到局域网

## 常见问题

**Q: 提示 "llama.cpp server is not running"**
> 确保 llama.cpp 服务已启动：`.\start-llama-server.ps1`

**Q: 搜索结果不准确**
> 尝试下载 ONNX 模型启用语义搜索，或使用更具体的关键词

**Q: 回答速度慢**
> 检查本地模型性能，或减少索引文件数量

**Q: ONNX 模型未启用**
> 确认 `models/bge-small-zh-v1.5/` 下有 `model.onnx` 和 `tokenizer.json`

**Q: Thinking 面板不显示**
> Qwen3.5 使用 `hle...hle` 标记 thinking，服务端自动解析；如模型不支持 thinking 则不显示

---

*Powered by llama.cpp + FastAPI*
