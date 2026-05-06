# Local Coder

基于本地 llama.cpp 的轻量级代码阅读助手，支持语义搜索、流式输出、多模式交互。

## 功能特性

- **语义搜索**：BM25 增强检索 + ONNX 语义重排（可选）
- **流式输出**：实时显示 thinking，回答逐字渲染
- **多模式交互**：
  - **Ask** 💬 — 问答模式，解答代码相关问题
  - **Plan** 📋 — 规划模式，分析代码结构并生成实现方案
  - **Craft** ✏️ — 编辑模式，可直接修改代码文件
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
├── .gitignore
├── static/
│   ├── index.html      # 页面入口
│   ├── app.js          # 前端逻辑
│   └── styles.css      # 样式
└── models/             # ONNX 语义模型（可选，不纳入 git）
    └── bge-small-zh-v1.5/
```

## 模式说明

| 模式 | 功能 | 适用场景 |
|------|------|----------|
| **Ask** 💬 | 回答关于代码的问题 | 理解代码逻辑、查找实现细节 |
| **Plan** 📋 | 分析代码结构，生成实现方案 | 架构分析、功能规划 |
| **Craft** ✏️ | 直接编辑代码文件 | 批量修改、重构 |

### Craft 模式使用

1. 切换到 Craft 模式
2. 在下方「文件路径」输入目标文件（如 `src/main.py`）
3. 在「代码修改」区域输入新内容
4. 点击「应用修改」写入文件

## 搜索模式

| 模式 | 说明 |
|------|------|
| **BM25**（默认） | 基于词频的增强检索，无需额外下载 |
| **ONNX 语义** | 需下载 bge-small-zh-v1.5 到 `models/` 目录，语义匹配更精准 |

### 启用 ONNX 语义搜索

```powershell
# 下载模型文件到 models/bge-small-zh-v1.5/
# 需要文件：model.onnx, tokenizer.json
# 重启服务后自动启用
```

## 依赖

- Python 3.11+
- onnxruntime >= 1.25（可选，ONNX 语义搜索需要）
- numpy >= 1.26
- fastapi, uvicorn, httpx

## 常见问题

**Q: 提示 "llama.cpp server is not running"**
> 确保 llama.cpp 服务已启动：`.\start-llama-server.ps1`

**Q: 搜索结果不准确**
> 尝试下载 ONNX 模型启用语义搜索，或使用更具体的关键词

**Q: 回答速度慢**
> 检查本地模型性能，或减少索引文件数量

---

*Powered by llama.cpp + FastAPI*
