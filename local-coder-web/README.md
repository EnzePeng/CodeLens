# Local Coder Web

基于本地 llama.cpp 的轻量级代码阅读助手，支持语义搜索、流式输出、Agent 自主规划执行。

## 功能特性

- **语义搜索**：BM25 增强检索 + ONNX 语义重排（可选），支持 camelCase 分词
- **流式输出**：实时显示 thinking，回答逐字渲染
- **多模式交互**：
  - **Ask** 💬 — 问答模式，解答代码相关问题
  - **Plan** 📋 — 规划模式，分析代码结构并生成实现方案，支持 Build 一键执行
  - **Craft** ✏️ — 编辑模式，可直接修改代码文件
  - **Agent** 🤖 — 自主 Agent 模式，支持 Plan-then-Apply 架构
- **Agent 模式能力**：
  - **Plan-then-Apply**：先生成修改计划，逐项预览 diff，确认后批量执行
  - **Phase 指示器**：实时显示分析 → 规划 → 预览 → 执行 → 完成
  - **Diff 预览**：逐项 approve/reject，支持全部批准/全部拒绝，剩余计数 + 超时提醒
  - **Self-Reflection**：写入工具执行前自我反思，Read-only 工具智能跳过（避免重复 LLM 调用）
  - **错误恢复**：工具执行失败后自动分析并重试（最多 N 次）
  - **4 策略 Plan 解析**：plan/json 块、文件路径标签、已知语言标签 + 上下文路径提取
  - **14 种工具**：read_file, write_file, edit_file, apply_diff, search_files, list_directory, run_command, git_operation, undo_edit, diff_preview, file_operations, code_analysis, test, project
  - **安全白名单**：run_command 支持命令白名单 + 危险模式检测
  - **Undo/Redo**：持久化编辑历史到 JSON，支持撤销和重做
  - **执行可视化**：实时显示步骤时间线、工具调用、执行进度
  - **全屏分栏**：Agent 面板全屏模式左右分栏（预览/应用 | 时间线/输出）
- **对话历史管理**：`ChatHistory` 服务，跨会话上下文管理，自动裁剪
- **目录选择**：内置文件夹浏览器，一键选择代码目录
- **离线运行**：无需联网，本地模型即可工作
- **深色主题**：点击标题栏太阳/月亮图标切换明暗主题，主题偏好自动保存
- **模型参数设置**：可调整 max_tokens、temperature、context_limit
- **上下文余量显示**：实时显示已用/总字符数，颜色随使用率变化
- **集成终端**：内置 xterm.js 终端，支持 32 种 Unix→Windows 命令转换
- **代码编辑器**：集成 CodeMirror 编辑器，支持语法高亮、多标签页编辑
- **文件标签页**：点击文件树打开标签页，Ctrl+S 保存，Ctrl+W 关闭
- **AI 代码补全**：Ctrl+Space 触发 AI 补全建议，支持 Tab/Enter 确认
- **增量索引**：文件哈希检测，只处理变更文件

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
4. 切换顶部模式标签：Ask / Plan / Craft / Agent

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 发送消息 |
| `Shift+Enter` | 换行 |
| `Ctrl+Space` | AI 代码补全 |
| `Ctrl+S` | 保存当前文件 |
| `Ctrl+W` | 关闭当前标签页 |
| `Tab` | 接受 AI 补全 |
| `Escape` | 关闭补全面板 |
| `↑/↓` | 选择 AI 补全 |

## 目录结构

```
local-coder-web/
├── app.py              # 入口：加载配置、注册路由、启动
├── config.py           # 配置常量集中管理
├── models/
│   └── __init__.py     # Pydantic 模型 + CodeFile + extract_symbols
├── core/
│   ├── agent.py        # Agent 引擎（Plan-then-Apply + Self-Reflection + 4 策略 Plan 解析）
│   ├── tools/
│   │   ├── base.py     # Tool ABC + ToolRegistry
│   │   ├── read_file.py
│   │   ├── write_file.py
│   │   ├── edit_file.py
│   │   ├── apply_diff.py
│   │   ├── diff_preview.py    # 新增：Diff 预览
│   │   ├── search_files.py
│   │   ├── list_directory.py
│   │   ├── run_command.py     # 命令白名单安全
│   │   ├── git_operation.py
│   │   ├── undo_edit.py      # JSON 持久化 + Redo
│   │   ├── file_operations.py # 新增：copy/move/delete/mkdir
│   │   ├── code_analysis.py   # 新增：count_lines/find_references
│   │   ├── test.py             # 新增：运行测试
│   │   └── project.py          # 新增：读取配置/包信息
├── services/
│   ├── indexer.py      # 统一索引：scan + BM25 + embeddings
│   ├── search.py       # BM25 + ONNX 语义搜索
│   ├── chat_history.py # 对话历史管理（新增）
│   └── file_watcher.py # 文件监控
├── routes/
│   ├── main.py         # UI + 状态 + 设置
│   ├── ask.py          # /api/ask + /api/craft-apply
│   ├── files.py        # /api/set-folder + /api/read-file + /api/exec
│   ├── complete.py     # /api/complete
│   └── agent.py        # /api/agent/*（Agent 生命周期，共享 ReAct 循环）
├── static/
│   ├── index.html      # 页面入口（Agent 分栏布局）
│   ├── app.js          # 前端逻辑（编程式 DOM Diff 预览）
│   └── styles.css      # 样式（Agent 全屏分栏）
└── tests/
    ├── unit/           # 单元测试
    └── integration/    # 集成测试
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
| `/api/settings` | GET | 获取模型参数和 System Prompt 配置 |
| `/api/set-folder` | POST | 设置代码目录，触发索引构建 |
| `/api/ask` | POST | 提问，返回 SSE 流式响应 |
| `/api/craft-apply` | POST | Craft 模式写入文件 |
| `/api/exec` | POST | 执行终端命令，返回 stdout/stderr |
| `/api/complete` | POST | AI 代码补全，返回候选列表 |
| `/api/reindex` | POST | 重新索引当前代码库 |
| `/api/browse-dirs` | POST | 浏览目录结构 |
| `/api/read-file` | POST | 读取文件内容 |

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

| `/api/agent/start` | POST | 启动 Agent 任务 |
| `/api/agent/status/{task_id}` | GET | 获取任务状态 |
| `/api/agent/action` | POST | 用户确认/拒绝（approve/reject/cancel） |
| `/api/agent/stop/{task_id}` | POST | 停止 Agent 任务 |
| `/api/agent/execute/{task_id}` | POST | 执行 Agent（SSE 流式，含 phase_change/plan_data/apply_progress 事件） |
| `/api/agent/tools` | GET | 列出可用工具 |
| `/api/agent/undo` | POST | 撤销编辑 |

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

## 版本历史

### v0.6.1 (2026-05-13) - Agent 稳定性与 UI 优化
- 🐛 **Bug 修复**：tools 变量未定义导致 Plan 生成崩溃（`routes/agent.py:366`）
- 🧠 **逻辑修复**：Read-only 工具跳过 self-reflection，消除重复 LLM 调用（`READ_ONLY_TOOLS`）
- 🔄 **代码去重**：抽取 `_run_react_loop` 异步生成器，消除两处 ~150 行 ReAct 循环重复
- 📋 **Plan 解析增强**：`generate_plan` 支持 4 种解析策略（plan/json 块、文件路径标签、已知语言标签 + 路径提取）
- 🎨 **Diff 预览重写**：`renderDiffPreview` 使用编程式 DOM 构建，解决 `data-path` HTML 转义损坏问题
- ✅ **审批流程完善**：显示剩余文件计数、3 分钟超时提醒、全部决定后自动执行
- 📐 **编辑器全屏修复**：Tab bar z-index 管理，全屏模式下关闭按钮可见
- 🖥️ **Agent 全屏分栏**：全屏模式左右分栏（45% 预览/应用 + 55% 时间线/输出）
- 🧹 **测试清理**：移除过时测试文件，新建 unit/integration 测试目录

### v0.6 (2026-05-09) - 全面重构 (Cursor-级别 Agent)
- 🏗️ **架构重构**：拆分 routes 模块（ask.py/files.py/complete.py），新建 services/indexer.py 统一索引逻辑
- 🤖 **Plan-then-Apply**：Agent 模式支持计划生成、Diff 预览、逐项 approve/reject、批量执行
- 📊 **Phase 指示器**：实时显示 parsing → planning → preview → applying → done 阶段
- 🔧 **工具系统增强**：14 种工具，支持统一注册、命令白名单、JSON 持久化 undo/redo
- 🔍 **搜索改进**：embedding 窗口扩大到 4000 字符，camelCase 分词，增强符号提取
- 💬 **对话历史**：ChatHistory 服务，跨会话上下文管理
- 🧪 **测试覆盖**：从 39 到 71 个测试用例，新增 indexer/search/chat_history/diff 测试
- ⚡ **性能优化**：工具统一注册入口、新增 file_operations/code_analysis/test/project 工具
- 🛡️ **安全增强**：run_command 命令白名单、危险命令模式检测

### v0.5.2 (2026-05-08) - Bug 修复
- ✨ **AI 代码补全**：Ctrl+Space 触发 AI 补全建议
- 🤖 **智能建议**：基于 LLM 生成代码补全，Tab/Enter 确认
- ⌨️ **补全导航**：上下键选择，Escape 关闭面板

### v0.5.1 (2026-05-08) - 细节打磨
- 🔒 **终端安全**：阻止危险命令 (rm -rf /, mkfs, curl|sh 等)
- 💻 **cd 命令增强**：支持 cd -, cd ~, cd .., 绝对/相对路径
- 🎨 **终端显示优化**：⚡ 执行状态，📁 当前目录
- 🐛 **Bug 修复**：CodeMirror 快捷键重复、AI 补全空值处理

### v0.5.2 (2026-05-08) - Bug 修复
- 💻 **Windows 终端兼容**：ls → dir, pwd → cd, clear → cls 等命令自动转换
- 🐛 **后端错误处理**：区分连接错误、超时、HTTP 错误，错误消息中文本地化
- ⚡ **启动提示**：如果 llama.cpp 未运行，给出明确提示

### v0.4 (2026-05-08)
- ✨ **代码编辑器**：集成 CodeMirror 5 编辑器，支持语法高亮
- 📑 **文件标签页**：点击文件树直接打开标签页，支持多文件编辑
- ⌨️ **快捷键**：Ctrl+S 保存文件，Ctrl+W 关闭标签页
- 🆕 **新建文件**：支持通过 + 按钮创建新文件

### v0.3 (2026-05-08)
- ✨ **集成终端**：内置 xterm.js 终端，支持执行 shell 命令
- 🔌 **后端 API**：新增 `/api/exec` 端点执行命令，支持 cwd、60秒超时
- 💻 **终端交互**：支持 cd 切换目录、Ctrl+C 取消命令
- 🎨 **终端样式**：深色主题，与 VS Code 风格一致

### v0.2 (2026-05-08)
- ✨ **深色主题**：支持明暗主题切换，主题偏好自动保存到 localStorage
- 🎨 **布局优化**：侧边栏宽度从 300px 调整为 280px，增加编辑器空间
- ⚙️ **模型参数设置**：可调整 max_tokens、temperature、context_limit
- 📊 **上下文余量显示**：实时进度条，显示已用/总字符数

### v0.1 (2026-05-07)
- 初始版本
- BM25 + ONNX 语义搜索
- Ask/Plan/Craft 三模式
- 流式输出 + thinking 显示
- 文件树 + 代码预览
- Build 确认弹窗

---

*Powered by llama.cpp + FastAPI*
