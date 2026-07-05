/* ─── DOM refs ────────────────────────────────────────────────── */
const folderInput   = document.querySelector("#folderInput");
const browseBtn     = document.querySelector("#browseBtn");
const setFolderBtn  = document.querySelector("#setFolderBtn");
const folderStatus  = document.querySelector("#folderStatus");
const fileCount     = document.querySelector("#fileCount");
const embeddingMode = document.querySelector("#embeddingMode");
const treeView      = document.querySelector("#treeView");
const askForm       = document.querySelector("#askForm");
const questionInput = document.querySelector("#questionInput");
const askBtn        = document.querySelector("#askBtn");
const messages      = document.querySelector("#messages");
if (messages) {
  messages.addEventListener("click", (e) => {
    const link = e.target.closest("a.file-path");
    if (!link) return;
    e.preventDefault();
    const p = link.getAttribute("data-path");
    if (!p || typeof window.openFileViewer !== "function") return;
    const name = p.split(/[/\\]/).pop() || p;
    window.openFileViewer(p, name, "");
  });
}
const modeSelect    = document.querySelector("#modeSelect");
const workspace     = document.querySelector(".workspace");
const clearBtn      = document.querySelector("#clearBtn");
const themeToggle   = document.querySelector("#themeToggle");

// Settings panel
const settingsToggle = document.querySelector("#settingsToggle");
const settingsContent = document.querySelector("#settingsContent");
const maxTokensSelect = document.querySelector("#maxTokensSelect");
const temperatureSelect = document.querySelector("#temperatureSelect");
const contextLimitSelect = document.querySelector("#contextLimitSelect");
const promptAsk = document.querySelector("#promptAsk");
const promptPlan = document.querySelector("#promptPlan");
const promptCraft = document.querySelector("#promptCraft");
const contextUsed = document.querySelector("#contextUsed");
const contextTotal = document.querySelector("#contextTotal");
const contextBarUsed = document.querySelector("#contextBarUsed");

// Directory browser
const dirOverlay    = document.querySelector("#dirOverlay");
const dirCloseBtn   = document.querySelector("#dirCloseBtn");
const dirPathInput  = document.querySelector("#dirPathInput");
const dirGoBtn      = document.querySelector("#dirGoBtn");
const dirList       = document.querySelector("#dirList");
const dirSelectBtn  = document.querySelector("#dirSelectBtn");
const dirCurrentLabel = document.querySelector("#dirCurrentLabel");

// Terminal
const toggleTerminalBtn = document.querySelector("#toggleTerminalBtn");
const terminalPanel     = document.querySelector("#terminalPanel");
const closeTerminalBtn  = document.querySelector("#closeTerminalBtn");

// Agent
const agentPanel        = document.querySelector("#agentPanel");
const agentPauseBtn     = document.querySelector("#agentPauseBtn");
const agentStopBtn      = document.querySelector("#agentStopBtn");
const closeAgentBtn     = document.querySelector("#closeAgentBtn");
const agentOutput       = document.querySelector("#agentOutput");

// Agent state
let agentTaskId = null;
let agentPaused = false;
const terminalContainer = document.querySelector("#terminalContainer");
const workspaceContent  = document.querySelector(".workspace-content");

// Editor / Tabs
const tabList           = document.querySelector("#tabList");
const editorArea        = document.querySelector("#editorArea");
const editorContainer   = document.querySelector("#editorContainer");
const newFileTabBtn     = document.querySelector("#newFileTabBtn");
const messagesArea      = document.querySelector("#messages");

/* ─── Error reporting ────────────────────────────────────────── */
if (typeof window.__codelens_ready__ === "undefined") {
  window.addEventListener("error", (e) => {
    console.error("[CodeLens] Unhandled error:", e.message, "at", e.filename, ":", e.lineno, e.colno);
  });
  window.addEventListener("unhandledrejection", (e) => {
    console.error("[CodeLens] Unhandled promise rejection:", e.reason);
  });
}

/* ─── State ───────────────────────────────────────────────────── */
let isBusy = false;
let currentMode = "overview";
let messageHistory = JSON.parse(localStorage.getItem("codelens-chat-history") || "[]");

function saveChatHistory() {
  localStorage.setItem("codelens-chat-history", JSON.stringify(messageHistory.slice(-100)));
}
let currentTreeData = null;  // Store tree JSON for re-rendering
let terminalHistory = [];
let terminalHistoryIndex = -1;
let terminalHistoryBrowse = null; // null = editing fresh; number = browsing history index

// Model settings (loaded from server)
let modelSettings = {
  maxTokens: 4096,
  temperature: 0.15,
  contextLimit: 42000,
  systemPrompts: {
    ask: "",
    plan: "",
    craft: ""
  }
};

// Current context usage
let currentContextUsed = 0;

/* ─── File icon map ───────────────────────────────────────────── */
const FILE_ICONS = {
  ".py": "🐍", ".js": "🟨", ".ts": "🔷", ".jsx": "⚛️", ".tsx": "⚛️",
  ".vue": "💚", ".svelte": "🔥", ".html": "🌐", ".css": "🎨", ".scss": "🎨",
  ".json": "📋", ".yaml": "📋", ".yml": "📋", ".toml": "📋",
  ".md": "📝", ".txt": "📄", ".sql": "🗃️", ".sh": "🖥️", ".ps1": "🖥️",
  ".java": "☕", ".kt": "🟣", ".go": "🔵", ".rs": "🦀",
  ".c": "⚙️", ".h": "⚙️", ".cpp": "⚙️", ".hpp": "⚙️",
  ".cs": "🟢", ".rb": "💎", ".php": "🐘", ".swift": "🍊",
};

function getFileIcon(ext) {
  return FILE_ICONS[ext] || "📄";
}

/* ─── Language map for highlight.js ────────────────────────────── */
const EXT_TO_LANG = {
  ".py": "python", ".js": "javascript", ".ts": "typescript",
  ".jsx": "javascript", ".tsx": "typescript", ".vue": "html",
  ".html": "html", ".css": "css", ".scss": "scss",
  ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "ini",
  ".md": "markdown", ".sql": "sql", ".sh": "bash", ".ps1": "powershell",
  ".java": "java", ".kt": "kotlin", ".go": "go", ".rs": "rust",
  ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
  ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift",
  ".xml": "xml", ".svelte": "html",
};

/* ─── Busy control ────────────────────────────────────────────── */
function setBusy(busy) {
  isBusy = busy;
  if (setFolderBtn) setFolderBtn.disabled = busy;
  const ready = folderStatus?.dataset?.ready;
  if (askBtn) askBtn.disabled = busy || !ready;
  if (questionInput) questionInput.disabled = busy || !ready;
  if (clearBtn) clearBtn.disabled = busy;
}

/* ─── Mode switching (composer dropdown) ──────────────────────── */
if (modeSelect) {
  modeSelect.addEventListener("change", () => {
    currentMode = modeSelect.value;
    // Set workspace data-mode (for future CSS hooks)
    if (workspace) workspace.setAttribute("data-mode", currentMode);
    // Update mode badge
    const badge = document.getElementById("workspaceMode");
    if (badge) {
      const labels = { overview: "Overview", ask: "Ask", file_lens: "File Lens", risks: "Risks", agent: "Agent" };
      badge.textContent = labels[currentMode] || "Overview";
    }
    // Switch views: agent mode → view-agent; else → view-chat
    const viewChat = document.getElementById("viewChat");
    const viewAgent = document.getElementById("viewAgent");
    const viewOverview = document.getElementById("viewOverview");
    const viewFileLens = document.getElementById("viewFileLens");
    [viewChat, viewAgent, viewOverview, viewFileLens].forEach(v => v && v.classList.remove("active"));
    if (currentMode === "agent") {
      viewAgent && viewAgent.classList.add("active");
    } else if (currentMode === "overview" || currentMode === "risks") {
      viewOverview && viewOverview.classList.add("active");
    } else if (currentMode === "file_lens") {
      viewFileLens && viewFileLens.classList.add("active");
    } else {
      viewChat && viewChat.classList.add("active");
    }
    const hints = {
      overview: "加载代码库后先查看项目全景；也可以输入问题切到 Ask。",
      ask:   "输入你的代码问题… (Enter 发送 / Shift+Enter 换行)",
      file_lens: "输入要解析的相对文件路径… (Enter 解析)",
      risks: "查看项目风险；输入问题会进入 Ask。",
      agent: "高风险模式：描述要完成的任务，Agent 将自主执行多步操作…",
    };
    if (questionInput) questionInput.placeholder = hints[currentMode] || hints.ask;
    // askBtn is an SVG button, not text; keep as is
  });
}

/* ─── Settings panel (collapsible) ────────────────────────────── */
if (settingsToggle) {
  settingsToggle.addEventListener("click", () => {
    const isCollapsed = settingsContent.classList.contains("collapsed");
    if (isCollapsed) {
      settingsContent.classList.remove("collapsed");
      settingsToggle.querySelector(".settings-arrow").textContent = "▾";
    } else {
      settingsContent.classList.add("collapsed");
      settingsToggle.querySelector(".settings-arrow").textContent = "▸";
    }
  });
}

// Settings change handlers
if (maxTokensSelect) {
  maxTokensSelect.addEventListener("change", () => {
    modelSettings.maxTokens = parseInt(maxTokensSelect.value, 10);
  });
}
if (temperatureSelect) {
  temperatureSelect.addEventListener("change", () => {
    modelSettings.temperature = parseFloat(temperatureSelect.value);
  });
}
if (contextLimitSelect) {
  contextLimitSelect.addEventListener("change", () => {
    modelSettings.contextLimit = parseInt(contextLimitSelect.value, 10);
    updateContextDisplay(0, modelSettings.contextLimit);
  });
}

/* ─── Update context usage display ────────────────────────────── */
function updateContextDisplay(used, total) {
  currentContextUsed = used;
  const totalChars = total || modelSettings.contextLimit;
  if (contextUsed) contextUsed.textContent = used.toLocaleString();
  if (contextTotal) contextTotal.textContent = totalChars.toLocaleString();
  const percent = totalChars > 0 ? Math.min((used / totalChars) * 100, 100) : 0;
  if (contextBarUsed) contextBarUsed.style.width = percent + "%";

  // Color based on usage
  if (!contextBarUsed) return;
  if (percent > 85) {
    contextBarUsed.style.background = "var(--error)";
  } else if (percent > 60) {
    contextBarUsed.style.background = "var(--warning)";
  } else {
    contextBarUsed.style.background = "var(--success)";
  }
}

/* ─── Load settings from server ───────────────────────────────── */
async function loadSettings() {
  try {
    const resp = await fetch("/api/settings");
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    
    // Update system prompts display
    if (data.system_prompts) {
      modelSettings.systemPrompts = data.system_prompts;
      if (promptAsk) promptAsk.textContent = data.system_prompts.ask || "";
      if (promptPlan) promptPlan.textContent = data.system_prompts.plan || "";
      if (promptCraft) promptCraft.textContent = data.system_prompts.craft || "";
    }
    
    // Update default settings
    if (data.defaults) {
      modelSettings.maxTokens = data.defaults.max_tokens || 4096;
      modelSettings.temperature = data.defaults.temperature || 0.15;
      modelSettings.contextLimit = data.defaults.context_limit || 42000;
      
      if (maxTokensSelect) maxTokensSelect.value = modelSettings.maxTokens;
      if (temperatureSelect) temperatureSelect.value = modelSettings.temperature;
      if (contextLimitSelect) contextLimitSelect.value = modelSettings.contextLimit;
    }
    
    updateContextDisplay(0, modelSettings.contextLimit);
  } catch (err) {
    console.error("Failed to load settings:", err);
    // Use fallback prompts
    if (promptAsk) promptAsk.textContent = "本地代码阅读助手，用中文回答问题。";
    if (promptPlan) promptPlan.textContent = "代码架构规划助手，用中文输出结构化计划。";
    if (promptCraft) promptCraft.textContent = "代码编辑助手，用中文输出修改内容。";
    updateContextDisplay(0, 42000);
  }
}

/* ─── Clear conversation ─────────────────────────────────────── */
if (clearBtn) {
  clearBtn.addEventListener("click", () => {
    if (isBusy) return;
    if (!confirm("确定要清空所有对话记录吗？此操作不可撤销。")) return;
    messageHistory = [];
    saveChatHistory();
    messages.innerHTML = "";
    addInfoMessage("对话已清空。");
  });
}

/* ─── HTML escaping ───────────────────────────────────────────── */
function escapeHtml(v) {
  return v
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* ─── Markdown renderer ──────────────────────────────────────── */
function renderMarkdown(md) {
  if (!md) return "";

  const codeBlocks = [];
  let text = md.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push({ lang: lang || "", code: code.trimEnd() });
    return `\n%%CB${idx}%%\n`;
  });

  const inlineCodes = [];
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    const idx = inlineCodes.length;
    inlineCodes.push(code);
    return `%%IC${idx}%%`;
  });

  const lines = text.split(/\r?\n/);
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let listOrdered = false;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (listItems.length) {
      const tag = listOrdered ? "ol" : "ul";
      blocks.push(`<${tag}>${listItems.map(i => `<li>${renderInline(i)}</li>`).join("")}</${tag}>`);
      listItems = [];
      listOrdered = false;
    }
  };

  for (const line of lines) {
    const cbMatch = line.match(/^%%CB(\d+)%%$/);
    if (cbMatch) {
      flushParagraph(); flushList();
      const b = codeBlocks[Number(cbMatch[1])];
      const langLabel = b.lang ? `<span>${escapeHtml(b.lang)}</span>` : "";
      blocks.push(`<pre class="code-block">${langLabel}<code>${escapeHtml(b.code)}</code></pre>`);
      continue;
    }
    if (/^---+$/.test(line.trim()) || /^\*\*\*+$/.test(line.trim())) {
      flushParagraph(); flushList(); blocks.push("<hr>"); continue;
    }
    if (!line.trim()) { flushParagraph(); flushList(); continue; }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph(); flushList();
      blocks.push(`<h${heading[1].length}>${renderInline(heading[2])}</h${heading[1].length}>`);
      continue;
    }
    const bq = line.match(/^>\s?(.*)$/);
    if (bq) {
      flushParagraph(); flushList();
      blocks.push(`<blockquote><p>${renderInline(bq[1])}</p></blockquote>`);
      continue;
    }
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      flushParagraph(); flushList();
      const cells = line.split("|").filter(c => c.trim() !== "");
      if (cells.every(c => /^[-:\s]+$/.test(c))) continue;
      const isHeader = blocks.length > 0 && blocks[blocks.length - 1].startsWith("<table");
      if (!isHeader) {
        blocks.push(`<table><thead><tr>${cells.map(c => `<th>${renderInline(c.trim())}</th>`).join("")}</tr></thead><tbody>`);
      } else {
        blocks[blocks.length - 1] = blocks[blocks.length - 1].replace("</tbody>", "");
        blocks.push(`<tr>${cells.map(c => `<td>${renderInline(c.trim())}</td>`).join("")}</tr></tbody></table>`);
      }
      continue;
    }
    const olItem = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (olItem) { flushParagraph(); if (!listOrdered && listItems.length) flushList(); listOrdered = true; listItems.push(olItem[1]); continue; }
    const ulItem = line.match(/^\s*[-*+]\s+(.+)$/);
    if (ulItem) { flushParagraph(); if (listOrdered && listItems.length) flushList(); listOrdered = false; listItems.push(ulItem[1]); continue; }
    flushList(); paragraph.push(line.trim());
  }
  flushParagraph(); flushList();

  let html = blocks.join("\n");
  html = html.replace(/%%IC(\d+)%%/g, (_, idx) => `<code>${escapeHtml(inlineCodes[Number(idx)])}</code>`);
  return html;
}

function renderInline(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  html = html.replace(/&lt;([^&]+)&gt;/g, "<kbd>$1</kbd>");
  return html;
}

/* ─── Collapsible file tree (VS Code style) ───────────────────── */
function renderTree(node, container, depth) {
  if (!node || !node.children) return;

  for (const child of node.children) {
    const row = document.createElement("div");
    row.className = "tree-row";

    if (child.type === "dir") {
      // Directory node
      const indent = document.createElement("span");
      indent.className = "tree-indent";
      indent.style.width = (depth * 16) + "px";

      const arrow = document.createElement("span");
      arrow.className = "tree-arrow";
      arrow.textContent = "▸";

      const icon = document.createElement("span");
      icon.className = "tree-icon dir-icon";
      icon.textContent = "📁";

      const name = document.createElement("span");
      name.className = "tree-name dir-name";
      name.textContent = child.name;
      name.title = child.path;

      row.append(indent, arrow, icon, name);
      row.classList.add("tree-dir-row");

      // Children container (collapsed by default)
      const childContainer = document.createElement("div");
      childContainer.className = "tree-children collapsed";

      row.addEventListener("click", (e) => {
        e.stopPropagation();
        const isCollapsed = childContainer.classList.contains("collapsed");
        if (isCollapsed) {
          childContainer.classList.remove("collapsed");
          arrow.textContent = "▾";
          icon.textContent = "📂";
          // Lazy-load children on first expand
          if (childContainer.children.length === 0) {
            renderTree(child, childContainer, depth + 1);
          }
        } else {
          childContainer.classList.add("collapsed");
          arrow.textContent = "▸";
          icon.textContent = "📁";
        }
      });

      container.appendChild(row);
      container.appendChild(childContainer);

    } else {
      // File node
      const indent = document.createElement("span");
      indent.className = "tree-indent";
      indent.style.width = (depth * 16) + "px";

      const arrow = document.createElement("span");
      arrow.className = "tree-arrow tree-arrow-file";

      const icon = document.createElement("span");
      icon.className = "tree-icon file-icon";
      icon.textContent = getFileIcon(child.ext);

      const name = document.createElement("span");
      name.className = "tree-name file-name";
      name.textContent = child.name;
      name.title = child.path;

      row.append(indent, arrow, icon, name);
      row.classList.add("tree-file-row");
      row.dataset.filePath = child.path;
      row.dataset.fileSize = child.size;

      row.addEventListener("click", (e) => {
        e.stopPropagation();
        window.openFileViewer(child.path, child.name, child.size);
      });

      container.appendChild(row);
    }
  }
}

function updateTreeView(treeData) {
  currentTreeData = treeData;
  treeView.innerHTML = "";

  if (!treeData || !treeData.children || treeData.children.length === 0) {
    treeView.innerHTML = '<div class="tree-empty">无文件</div>';
    return;
  }

  // Render root node
  const rootRow = document.createElement("div");
  rootRow.className = "tree-row tree-dir-row tree-root";
  const rootArrow = document.createElement("span");
  rootArrow.className = "tree-arrow";
  rootArrow.textContent = "▾";
  const rootIcon = document.createElement("span");
  rootIcon.className = "tree-icon dir-icon";
  rootIcon.textContent = "📂";
  const rootName = document.createElement("span");
  rootName.className = "tree-name dir-name";
  rootName.textContent = treeData.name;
  rootRow.append(rootArrow, rootIcon, rootName);

  const rootChildren = document.createElement("div");
  rootChildren.className = "tree-children";

  rootRow.addEventListener("click", () => {
    const isCollapsed = rootChildren.classList.contains("collapsed");
    if (isCollapsed) {
      rootChildren.classList.remove("collapsed");
      rootArrow.textContent = "▾";
      rootIcon.textContent = "📂";
    } else {
      rootChildren.classList.add("collapsed");
      rootArrow.textContent = "▸";
      rootIcon.textContent = "📁";
    }
  });

  treeView.appendChild(rootRow);
  treeView.appendChild(rootChildren);

  // Render first level
  renderTree(treeData, rootChildren, 0);
}

/* ─── File viewer (opens in editor tab) ─────────────────────── */
async function openFileViewer(filePath, fileName, fileSize) {
  try {
    const resp = await fetch("/api/read-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: filePath }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    openFileInTab(filePath, data.path || fileName, data.content || "");
  } catch (err) {
    addInfoMessage(`❌ 打开文件失败: ${err.message}`);
  }
}

// Escape key closes dir overlay, also exits fullscreen modes
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (agentPanel && agentPanel.classList.contains("fullscreen")) {
      agentPanel.classList.remove("fullscreen");
      const afb = document.querySelector("#agentFullscreenBtn");
      if (afb) { afb.textContent = "⛶"; afb.title = "全屏"; }
      return;
    }
    if (editorArea && editorArea.classList.contains("fullscreen")) {
      editorArea.classList.remove("fullscreen");
      const tabBar = document.querySelector(".tab-bar");
      if (tabBar) tabBar.classList.remove("editor-fullscreen-visible");
      if (editorFullscreenBtn) {
        editorFullscreenBtn.textContent = "⛶";
        editorFullscreenBtn.title = "编辑器全屏";
      }
      setTimeout(() => { if (codeMirrorEditor) codeMirrorEditor.refresh(); }, 300);
      return;
    }
    if (!dirOverlay.classList.contains("hidden")) {
      dirOverlay.classList.add("hidden");
    }
  }
});

/* ─── Add a user message bubble ──────────────────────────────── */
function addUserMessage(text) {
  messageHistory.push({ role: "user", mode: currentMode, content: text, timestamp: Date.now() });
  saveChatHistory();

  const article = document.createElement("article");
  article.className = "message user";
  const header = document.createElement("div");
  header.className = "message-header";
  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = "You";
  const modeTag = document.createElement("span");
  modeTag.className = `mode-tag ${currentMode}`;
  modeTag.textContent = currentMode.toUpperCase();
  const timeEl = document.createElement("span");
  timeEl.className = "time";
  timeEl.textContent = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  header.append(roleEl, modeTag, timeEl);
  const contentEl = document.createElement("div");
  contentEl.className = "content";
  contentEl.textContent = text;
  article.append(header, contentEl);
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
}

/* ─── Add a system info message ──────────────────────────────── */
function addInfoMessage(text) {
  const article = document.createElement("article");
  article.className = "message assistant system-msg";
  const header = document.createElement("div");
  header.className = "message-header";
  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = "System";
  header.append(roleEl);
  const contentEl = document.createElement("div");
  contentEl.className = "content";
  contentEl.textContent = text;
  article.append(header, contentEl);
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
}

/* ─── Create a streaming assistant bubble ─────────────────────── */
function createStreamingBubble() {
  const article = document.createElement("article");
  article.className = "message assistant streaming";

  const header = document.createElement("div");
  header.className = "message-header";
  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = "Assistant";
  const modeTag = document.createElement("span");
  modeTag.className = `mode-tag ${currentMode}`;
  modeTag.textContent = currentMode.toUpperCase();
  const speedBadge = document.createElement("div");
  speedBadge.className = "speed-badge hidden";
  header.append(roleEl, modeTag, speedBadge);

  const thinkingPanel = document.createElement("details");
  thinkingPanel.className = "thinking live";
  thinkingPanel.open = true;
  const thinkingSummary = document.createElement("summary");
  thinkingSummary.textContent = "思考中…";
  const thinkingPre = document.createElement("pre");
  thinkingPanel.append(thinkingSummary, thinkingPre);

  const contentEl = document.createElement("div");
  contentEl.className = "content markdown";

  const sourcesEl = document.createElement("div");
  sourcesEl.className = "sources hidden";

  const cursor = document.createElement("span");
  cursor.className = "stream-cursor";
  cursor.textContent = "▋";

  article.append(header, thinkingPanel, contentEl, cursor, sourcesEl);
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;

  return { article, speedBadge, thinkingPanel, thinkingSummary, thinkingPre, contentEl, sourcesEl, cursor, modeTag };
}

/* ─── Streaming ask ───────────────────────────────────────────── */
async function streamAsk(question) {
  setBusy(true);
  askBtn.textContent = "…";

  const bubble = createStreamingBubble();
  let rawBuffer = "";

  const body = {
    question,
    mode: currentMode,
    history: messageHistory,
    max_tokens: modelSettings.maxTokens,
    temperature: modelSettings.temperature,
    context_limit: modelSettings.contextLimit
  };

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = "";
    let contextCharsUsed = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });

      const lines = sseBuffer.split("\n");
      sseBuffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const jsonStr = line.slice(5).trim();
        if (!jsonStr) continue;
        let evt;
        try { evt = JSON.parse(jsonStr); } catch { continue; }

        if (evt.type === "sources") {
          if (evt.sources?.length) {
            bubble.sourcesEl.textContent = `参考文件：${evt.sources.map(s => s.path).join("，")}`;
            bubble.sourcesEl.classList.remove("hidden");
            // Use actual context chars from server if available, otherwise estimate
            contextCharsUsed = evt.context_chars || evt.sources.reduce((sum, s) => sum + (s.size || 0), 0);
            updateContextDisplay(contextCharsUsed, modelSettings.contextLimit);
          }
        } else if (evt.type === "delta") {
          rawBuffer += evt.content;
          _processRawBuffer(rawBuffer, bubble);
        } else if (evt.type === "done") {
          _finalRender(evt, bubble);
        } else if (evt.type === "error") {
          throw new Error(evt.message);
        }
        messages.scrollTop = messages.scrollHeight;
      }
    }
  } catch (err) {
    bubble.cursor.remove();
    bubble.thinkingPanel.remove();
    bubble.contentEl.textContent = `请求失败：${err.message}`;
  } finally {
    bubble.cursor.remove();
    bubble.article.classList.remove("streaming");
    const btnLabels = { ask: "发送", plan: "规划", craft: "编辑", agent: "执行" };
    askBtn.textContent = btnLabels[currentMode] || "发送";
    setBusy(false);
    questionInput.focus();
    setTimeout(() => updateContextDisplay(0, modelSettings.contextLimit), 1500);
  }
}

/* ─── Process raw stream buffer into thinking / answer ───────── */
function _processRawBuffer(raw, bubble) {
  let thinkingText = "";
  let answerText = "";

  const openTag = "<think>";
  const closeTag = "</think>";

  let tStart = raw.indexOf(openTag);
  let tEnd = -1;

  if (tStart !== -1) {
    tEnd = raw.indexOf(closeTag, tStart);
  }

  if (tStart !== -1 && tEnd !== -1) {
    thinkingText = raw.slice(tStart + openTag.length, tEnd);
    answerText = (raw.slice(0, tStart) + raw.slice(tEnd + closeTag.length)).trim();
  } else if (tStart !== -1) {
    thinkingText = raw.slice(tStart + openTag.length);
    answerText = raw.slice(0, tStart);
  } else {
    answerText = raw;
  }

  if (thinkingText.trim()) {
    bubble.thinkingPanel.classList.remove("hidden");
    bubble.thinkingPre.textContent = thinkingText;
  } else {
    bubble.thinkingPanel.classList.add("hidden");
  }

  bubble.contentEl.innerHTML = makeFilePathsClickable(renderMarkdown(answerText));
}

/* ─── Final render after stream complete ─────────────────────── */
function _finalRender(evt, bubble) {
  bubble.cursor.remove();
  bubble.article.classList.remove("streaming");

  const answerText = evt.answer || "";
  messageHistory.push({ role: "assistant", mode: currentMode, content: answerText, timestamp: Date.now() });
  saveChatHistory();

  if (evt.thinking?.trim()) {
    bubble.thinkingPanel.classList.remove("hidden");
    bubble.thinkingPanel.open = false;
    bubble.thinkingSummary.textContent = "查看 thinking";
    bubble.thinkingPre.textContent = evt.thinking;
  } else {
    bubble.thinkingPanel.remove();
  }

  bubble.contentEl.innerHTML = makeFilePathsClickable(renderMarkdown(evt.answer || ""));

  if (evt.metrics?.tokens_per_second) {
    bubble.speedBadge.textContent = `${evt.metrics.tokens_per_second} tok/s`;
    bubble.speedBadge.title = `${evt.metrics.completion_tokens || 0} tokens in ${evt.metrics.elapsed_seconds || 0}s`;
    bubble.speedBadge.classList.remove("hidden");
  }

  if ((currentMode === "plan" || currentMode === "craft") && answerText.includes("```")) {
    addBuildButton(bubble.article, answerText);
  }
}

/* ─── Parse code blocks from Plan/Craft answer ────────────────── */
function parsePlanCodeBlocks(answerText) {
  const files = [];
  const regex = /```(\S*)\n([\s\S]*?)```/g;
  let match;

  const knownLangs = new Set([
    "python", "py", "javascript", "js", "typescript", "ts", "jsx", "tsx",
    "java", "kotlin", "go", "rust", "c", "cpp", "h", "hpp", "cs", "ruby", "rb",
    "php", "swift", "sql", "sh", "bash", "powershell", "html", "css", "json",
    "yaml", "yml", "toml", "xml", "markdown", "md", "text", "plain",
  ]);

  while ((match = regex.exec(answerText)) !== null) {
    const lang = match[1] || "";
    const code = match[2].trim();
    if (!code || code.length < 5) continue;

    let filePath = "";

    // Strategy 1: lang tag looks like a file path
    if (lang && !knownLangs.has(lang.toLowerCase()) && (lang.includes("/") || lang.includes("\\") || lang.includes("."))) {
      filePath = lang;
    }

    // Strategy 2: scan text before code block for file path mentions
    if (!filePath) {
      const textBefore = answerText.slice(Math.max(0, match.index - 500), match.index);
      const pathPatterns = [
        /(?:修改|编辑|创建|更新|新增|文件|File|file|Path|path)\s*[：:]\s*`?([^\s`\n]+\.\w+)`?/gi,
        /###\s*(?:修改文件|文件|File)\s*[：:]?\s*`?([^\s`\n]+\.\w+)`?/gi,
        /###\s*`?([^\s`\n]+\.\w+)`?/g,
        /\*\*`?([^\s`\n]+\.\w+)`?\*\*/g,
      ];
      for (const pat of pathPatterns) {
        let m;
        while ((m = pat.exec(textBefore)) !== null) {
          filePath = m[1];
        }
        if (filePath) break;
      }
    }

    // Strategy 3: first-line comment with filename
    if (!filePath) {
      const firstLine = code.split("\n")[0] || "";
      const commentMatch = firstLine.match(/(?:#|\/\/|\/\*)\s*(?:file\s*:\s*)?([^\s*]+\.\w+)/i);
      if (commentMatch) filePath = commentMatch[1];
    }

    // Strategy 4: if lang tag is a known language but there's a path-like mention right before
    if (!filePath && lang && knownLangs.has(lang.toLowerCase())) {
      const textBefore = answerText.slice(Math.max(0, match.index - 300), match.index);
      const pathMatch = textBefore.match(/([^\s\n]+\.[\w]+)\s*$/);
      if (pathMatch) {
        const candidate = pathMatch[1].replace(/[`*]/g, "");
        if (candidate.includes("/") || candidate.includes("\\") || candidate.includes(".")) {
          filePath = candidate;
        }
      }
    }

    if (filePath) {
      filePath = filePath.replace(/^[\s`*#]+|[\s`*#]+$/g, "");
      files.push({ filePath, code });
    }
  }

  return files;
}

/* ─── Add Build button to assistant bubble ────────────────────── */
function addBuildButton(article, answerText) {
  const parsedFiles = parsePlanCodeBlocks(answerText);
  if (parsedFiles.length === 0) return;

  const buildActions = document.createElement("div");
  buildActions.className = "build-actions";

  const fileList = document.createElement("div");
  fileList.className = "build-file-list";
  parsedFiles.forEach(f => {
    const item = document.createElement("div");
    item.className = "build-file-item";
    item.innerHTML = `<span class="build-file-path">${escapeHtml(f.filePath)}</span><span class="build-file-size">${f.code.length} chars</span>`;
    fileList.appendChild(item);
  });
  buildActions.appendChild(fileList);

  const buildBtn = document.createElement("button");
  buildBtn.className = "build-btn";
  buildBtn.innerHTML = `🚀 Build (${parsedFiles.length} 个文件)`;
  buildBtn.title = "将代码写入对应文件";
  buildBtn.onclick = () => showBuildConfirm(parsedFiles, article, buildActions);
  buildActions.appendChild(buildBtn);

  article.appendChild(buildActions);
}

/* ─── Build confirmation dialog ──────────────────────────────── */
function showBuildConfirm(files, article, buildActions) {
  // Remove any existing build-confirm overlay to prevent duplicates
  document.querySelectorAll(".build-confirm-overlay").forEach(el => el.remove());

  const overlay = document.createElement("div");
  overlay.className = "build-confirm-overlay";

  const dialog = document.createElement("div");
  dialog.className = "build-confirm-dialog";

  const title = document.createElement("h3");
  title.textContent = "确认 Build 修改";
  dialog.appendChild(title);

  const desc = document.createElement("p");
  desc.textContent = `即将修改 ${files.length} 个文件：`;
  dialog.appendChild(desc);

  const list = document.createElement("ul");
  list.className = "build-confirm-list";
  files.forEach(f => {
    const li = document.createElement("li");
    li.innerHTML = `<code>${escapeHtml(f.filePath)}</code> <span class="build-confirm-size">(${f.code.length} chars)</span>`;
    list.appendChild(li);
  });
  dialog.appendChild(list);

  const warning = document.createElement("p");
  warning.className = "build-confirm-warning";
  warning.textContent = "⚠️ 此操作将覆盖现有文件内容，请确保已备份。";
  dialog.appendChild(warning);

  const btnRow = document.createElement("div");
  btnRow.className = "build-confirm-btns";

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "build-confirm-cancel";
  cancelBtn.textContent = "取消";
  cancelBtn.onclick = () => overlay.remove();

  const confirmBtn = document.createElement("button");
  confirmBtn.className = "build-confirm-ok";
  confirmBtn.textContent = "🚀 确认 Build";
  confirmBtn.onclick = () => {
    overlay.remove();
    executePlanBuild(files, article, buildActions);
  };

  btnRow.append(cancelBtn, confirmBtn);
  dialog.appendChild(btnRow);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
}

/* ─── Execute Plan Build ─────────────────────────────────────── */
async function executePlanBuild(files, article, buildActions) {
  if (!files || files.length === 0) return;

  setBusy(true);

  const buildBtn = buildActions.querySelector(".build-btn");
  if (buildBtn) {
    buildBtn.disabled = true;
    buildBtn.innerHTML = "⏳ Build 执行中…";
  }

  let successCount = 0;
  let failCount = 0;
  const results = [];

  for (const file of files) {
    try {
      const resp = await fetch("/api/craft-apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: file.filePath, content: file.code }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      results.push({ path: data.path, bytes: data.bytes_written, ok: true });
      successCount++;
    } catch (err) {
      results.push({ path: file.filePath, error: err.message, ok: false });
      failCount++;
    }
  }

  const fileItems = buildActions.querySelectorAll(".build-file-item");
  results.forEach((r, i) => {
    if (fileItems[i]) {
      const sz = fileItems[i].querySelector(".build-file-size");
      if (r.ok) {
        fileItems[i].classList.add("build-success");
        if (sz) sz.textContent = `✅ ${r.bytes} bytes`;
      } else {
        fileItems[i].classList.add("build-fail");
        if (sz) sz.textContent = `❌ ${r.error}`;
      }
    }
  });

  if (buildBtn) {
    if (failCount === 0) {
      buildBtn.innerHTML = `✅ Build 完成 (${successCount} 个文件)`;
      buildBtn.classList.add("build-done");
    } else {
      buildBtn.innerHTML = `⚠️ 部分失败 (✅${successCount} ❌${failCount})`;
      buildBtn.classList.add("build-partial");
    }
  }

  if (successCount > 0) {
    try {
      const resp = await fetch("/api/reindex", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok) {
        fileCount.textContent = String(data.file_count);
        if (embeddingMode) embeddingMode.textContent = data.embedding_mode === "onnx" ? "ONNX 语义" : "BM25";
        updateTreeView(typeof data.tree === "string" ? JSON.parse(data.tree) : data.tree);
        addInfoMessage(`🔄 索引已更新，共 ${data.file_count} 个文件。`);
      }
    } catch (err) {
      addInfoMessage(`⚠️ 索引更新失败：${err.message}`);
    }
  }

  setBusy(false);
}

/* ─── Directory browser ───────────────────────────────────────── */
let currentDirPath = "";

if (browseBtn) browseBtn.addEventListener("click", () => {
  if (dirOverlay) dirOverlay.classList.remove("hidden");
  const startPath = folderInput ? folderInput.value.trim() || "" : "";
  loadDirListing(startPath || "");
});

// Also open directory browser when clicking the folder input field
if (folderInput) folderInput.addEventListener("click", () => {
  if (dirOverlay) dirOverlay.classList.remove("hidden");
  const startPath = folderInput.value.trim() || "";
  loadDirListing(startPath || "");
});

if (dirCloseBtn) dirCloseBtn.addEventListener("click", () => {
  if (dirOverlay) dirOverlay.classList.add("hidden");
});

if (dirOverlay) {
  dirOverlay.addEventListener("click", (e) => {
    if (e.target === dirOverlay) dirOverlay.classList.add("hidden");
  });
}

if (dirGoBtn) dirGoBtn.addEventListener("click", () => {
  const path = dirPathInput ? dirPathInput.value.trim() : "";
  if (path) loadDirListing(path);
});

if (dirPathInput) dirPathInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    const path = dirPathInput.value.trim();
    if (path) loadDirListing(path);
  }
});

if (dirSelectBtn) dirSelectBtn.addEventListener("click", () => {
  if (currentDirPath && folderInput) {
    folderInput.value = currentDirPath;
    if (dirOverlay) dirOverlay.classList.add("hidden");
    // Auto-trigger folder loading
    if (setFolderBtn) setFolderBtn.click();
  }
});

async function loadDirListing(path) {
  dirList.innerHTML = '<div class="dir-loading">加载中…</div>';

  try {
    const resp = await fetch("/api/browse-dirs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);

    currentDirPath = data.current;
    dirPathInput.value = currentDirPath;
    dirCurrentLabel.textContent = `当前: ${currentDirPath}`;

    dirList.innerHTML = "";

    if (data.parent) {
      const item = createDirItem("📁 ..", data.parent, true);
      dirList.appendChild(item);
    }

    if (data.dirs.length === 0) {
      const empty = document.createElement("div");
      empty.className = "dir-empty";
      empty.textContent = "此目录下没有子文件夹";
      dirList.appendChild(empty);
    } else {
      data.dirs.forEach(d => {
        const item = createDirItem(`📁 ${d.name}`, d.path, false);
        dirList.appendChild(item);
      });
    }
  } catch (err) {
    // Show error but also provide a way to manually enter a path
    dirList.innerHTML = "";
    const errorDiv = document.createElement("div");
    errorDiv.className = "dir-error";
    errorDiv.innerHTML = `加载失败：${escapeHtml(err.message)}<br><small>请在上方路径栏手动输入路径后按 Enter 跳转</small>`;
    dirList.appendChild(errorDiv);
    // Ensure dirPathInput is focusable for manual entry
    if (dirPathInput && !currentDirPath) {
      dirPathInput.value = path || "";
      dirPathInput.focus();
    }
  }
}

function createDirItem(label, path, isParent) {
  const item = document.createElement("div");
  item.className = "dir-item" + (isParent ? " dir-parent" : "");
  item.textContent = label;
  item.title = path;
  item.onclick = () => loadDirListing(path);
  return item;
}

/* ─── Set folder ──────────────────────────────────────────────── */
if (setFolderBtn) {
  setFolderBtn.addEventListener("click", async () => {
    const path = folderInput ? folderInput.value.trim() : "";
    if (!path) {
      addInfoMessage("请先选择或输入代码文件夹路径。");
      // Auto-open directory browser if no path entered
      if (dirOverlay) {
        dirOverlay.classList.remove("hidden");
        loadDirListing("");
      }
      return;
    }

    setBusy(true);
    setFolderBtn.textContent = "索引中…";
    try {
      const resp = await fetch("/api/index/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      const statusResp = await fetch("/api/status");
      const statusData = await statusResp.json().catch(() => ({}));

      if (folderStatus) {
        folderStatus.textContent = statusData.folder || path;
        folderStatus.dataset.ready = "1";
      }
      if (fileCount) fileCount.textContent = String(data.file_count || statusData.file_count || 0);
      if (embeddingMode) embeddingMode.textContent = statusData.embedding_mode === "onnx" ? "ONNX 语义" : "BM25";
      try {
        const treeData = typeof statusData.tree === "string" ? JSON.parse(statusData.tree) : statusData.tree;
        updateTreeView(treeData);
      } catch (treeErr) {
        console.error("[CodeLens] Tree parse error:", treeErr);
        updateTreeView(null);
      }
      // Always enable input after successful folder load
      if (questionInput) questionInput.disabled = false;
      if (askBtn) askBtn.disabled = false;
      if (window.CodeLensWorkbench && typeof window.CodeLensWorkbench.loadProjectBrief === "function") {
        await window.CodeLensWorkbench.loadProjectBrief();
      }
      if (modeSelect) {
        modeSelect.value = "overview";
        modeSelect.dispatchEvent(new Event("change"));
      }
      addInfoMessage(`已索引 ${data.file_count || statusData.file_count || 0} 个文件，项目全景已生成。`);
    } catch (err) {
      addInfoMessage(`设置失败：${err.message}`);
    } finally {
      setFolderBtn.textContent = "加载代码库";
      setBusy(false);
    }
  });
}

/* ─── Submit: Enter = send, Shift+Enter = newline ─────────────── */
if (questionInput) {
  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isBusy && !questionInput.disabled) {
        askForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
      }
    }
  });
}

if (askForm) {
  askForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = questionInput ? questionInput.value.trim() : "";
    if (!question || isBusy) return;
    if (questionInput) questionInput.value = "";

    if (currentMode === "agent") {
      addUserMessage(question);
      await startAgentTask(question);
    } else if (currentMode === "file_lens") {
      if (window.CodeLensWorkbench && typeof window.CodeLensWorkbench.loadFileLens === "function") {
        await window.CodeLensWorkbench.loadFileLens(question);
      }
    } else {
      addUserMessage(question);
      await streamAsk(question);
    }
  });
}

// Comment generation button
const commentBtn = document.querySelector("#commentBtn");
if (commentBtn) {
  commentBtn.addEventListener("click", async () => {
    // Get selected code from editor
    const editor = document.querySelector(".CodeMirror");
    if (!editor || !editor.CodeMirror) {
      alert("请先在编辑器中打开文件并选中代码");
      return;
    }
    
    const cm = editor.CodeMirror;
    const selection = cm.getSelection();
    
    if (!selection || !selection.trim()) {
      alert("请先选中需要生成注释的代码");
      return;
    }
    
    if (isBusy) return;
    setBusy(true);
    
    try {
      // Detect language from current file
      const currentFile = document.querySelector(".tab.active");
      const language = currentFile ? currentFile.dataset.language || "" : "";
      
      const response = await fetch("/api/comment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: selection,
          language: language,
          style: "detailed"
        })
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const result = await response.json();
      
      if (result.commented_code) {
        // Replace selected code with commented version
        cm.replaceSelection(result.commented_code);
        addUserMessage(`✅ 注释已生成 (耗时: ${result.latency_ms.toFixed(0)}ms)`);
      }
    } catch (err) {
      addUserMessage(`❌ 注释生成失败: ${err.message}`);
    } finally {
      setBusy(false);
    }
  });
}

/* ─── Init: restore folder state ──────────────────────────────── */
// Show loading state
if (folderStatus) folderStatus.textContent = "连接中...";
if (questionInput) questionInput.placeholder = "正在连接服务器...";

fetch("/api/status")
  .then(r => r.json())
  .then(data => {
    if (data.folder) {
      folderInput.value = data.folder;
      folderStatus.textContent = data.folder;
      folderStatus.dataset.ready = "1";
      questionInput.disabled = false;
      askBtn.disabled = false;
      fileCount.textContent = String(data.file_count);
      if (embeddingMode) embeddingMode.textContent = data.embedding_mode === "onnx" ? "ONNX 语义" : "BM25";
      try {
        const statusTree = typeof data.tree === "string" ? JSON.parse(data.tree) : data.tree;
        updateTreeView(statusTree);
      } catch (treeErr) {
        console.error("[CodeLens] Failed to parse tree:", treeErr);
        updateTreeView(null);
      }
    } else {
      folderStatus.textContent = "未设置";
      questionInput.disabled = false;
      askBtn.disabled = false;
      questionInput.placeholder = "请先在左侧设置代码文件夹...";
    }
  })
  .catch((err) => {
    console.error("[CodeLens] /api/status failed:", err);
    folderStatus.textContent = "连接失败";
    folderStatus.style.color = "var(--error)";
    questionInput.disabled = false;
    questionInput.placeholder = "服务器连接失败，请刷新页面重试...";
  });

/* ─── Theme toggle ────────────────────────────────────────────── */
function initTheme() {
  const savedTheme = localStorage.getItem("codelens-theme") || "light";
  if (savedTheme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
}

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute("data-theme");
  const newTheme = current === "dark" ? "light" : "dark";
  
  if (newTheme === "dark") {
    html.setAttribute("data-theme", "dark");
  } else {
    html.removeAttribute("data-theme");
  }
  
  localStorage.setItem("codelens-theme", newTheme);
}

if (themeToggle) {
  themeToggle.addEventListener("click", toggleTheme);
}

// Initialize theme on load
initTheme();

// Load settings and system prompts on startup
loadSettings();

/* ─── Terminal (xterm.js) ─────────────────────────────────────── */
let term = null;
let fitAddon = null;
let currentCwd = "";

function initTerminal() {
  if (term) return;
  
  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: '"Cascadia Code", Consolas, "Courier New", monospace',
    theme: {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#d4d4d4',
      selection: '#264f78',
      black: '#000000',
      red: '#cd3131',
      green: '#0dbc79',
      yellow: '#e5e510',
      blue: '#2472c8',
      magenta: '#bc3fbc',
      cyan: '#11a8cd',
      white: '#d4d4d4',
      brightBlack: '#666666',
      brightRed: '#f14c4c',
      brightGreen: '#23d18b',
      brightYellow: '#f5f543',
      brightBlue: '#3b8eea',
      brightMagenta: '#d670d6',
      brightCyan: '#29b8db',
      brightWhite: '#ffffff',
    },
    convertEol: true,
    scrollback: 5000,
  });
  
  fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(terminalContainer);
  fitAddon.fit();

  function redrawTerminalInputLine() {
    term.write("\r\x1b[2K");
    term.write("\x1b[1;32m$\x1b[0m ");
    term.write(currentLine);
  }

  term.attachCustomKeyEventHandler((domEvent) => {
    if (domEvent.type !== "keydown") return false;
    if (domEvent.key === "ArrowUp") {
      domEvent.preventDefault();
      if (terminalHistory.length === 0) return true;
      if (terminalHistoryBrowse === null) {
        terminalHistoryBrowse = terminalHistory.length - 1;
      } else {
        terminalHistoryBrowse = Math.max(0, terminalHistoryBrowse - 1);
      }
      currentLine = terminalHistory[terminalHistoryBrowse] || "";
      redrawTerminalInputLine();
      return true;
    }
    if (domEvent.key === "ArrowDown") {
      domEvent.preventDefault();
      if (terminalHistoryBrowse === null) return true;
      if (terminalHistoryBrowse >= terminalHistory.length - 1) {
        terminalHistoryBrowse = null;
        currentLine = "";
      } else {
        terminalHistoryBrowse += 1;
        currentLine = terminalHistory[terminalHistoryBrowse] || "";
      }
      redrawTerminalInputLine();
      return true;
    }
    return false;
  });
  
  // Welcome message
  term.writeln('\x1b[1;36m╔════════════════════════════════════════════════╗\x1b[0m');
  term.writeln('\x1b[1;36m║\x1b[0m  \x1b[1;33mCodeLens Terminal\x1b[0m                            \x1b[1;36m║\x1b[0m');
  term.writeln('\x1b[1;36m║\x1b[0m  Type commands and press Enter to execute   \x1b[1;36m║\x1b[0m');
  term.writeln('\x1b[1;36m║\x1b[0m  Press Ctrl+C to cancel current command      \x1b[1;36m║\x1b[0m');
  term.writeln('\x1b[1;36m╚════════════════════════════════════════════════╝\x1b[0m');
  term.writeln('');
  term.write('\x1b[1;32m$\x1b[0m ');
  
  // Handle user input
  let currentLine = '';
  
  term.onData(data => {
    const code = data.charCodeAt(0);
    
    if (code === 13) { // Enter
      term.writeln('');
      terminalHistoryBrowse = null;
      if (currentLine.trim()) {
        executeCommand(currentLine.trim());
      } else {
        term.write('\x1b[1;32m$\x1b[0m ');
      }
      currentLine = '';
    } else if (code === 127 || code === 8) { // Backspace
      terminalHistoryBrowse = null;
      if (currentLine.length > 0) {
        currentLine = currentLine.slice(0, -1);
        term.write('\b \b');
      }
    } else if (code === 3) { // Ctrl+C
      term.writeln('^C');
      term.write('\x1b[1;32m$\x1b[0m ');
      currentLine = '';
      terminalHistoryBrowse = null;
    } else if (code >= 32) { // Printable characters
      terminalHistoryBrowse = null;
      currentLine += data;
      term.write(data);
    }
  });
  
  // Handle resize
  window.addEventListener('resize', () => {
    if (fitAddon) fitAddon.fit();
  });
}

async function executeCommand(cmd) {
  if (cmd) {
    // Check for dangerous commands
    const dangerousPatterns = [/rm\s+-rf/i, /rmdir\s+\/s/i, /del\s+\/f/i, /format\s+[a-z]:/i, /shutdown/i, /reboot/i, /kill/i];
    const isDangerous = dangerousPatterns.some(p => p.test(cmd));
    if (isDangerous) {
      const confirmed = confirm(`⚠️ 检测到危险命令:\n\n${cmd}\n\n确定要执行吗？`);
      if (!confirmed) {
        term.write('\x1b[31m已取消\x1b[0m\r\n');
        term.write('\x1b[1;32m$\x1b[0m ');
        return;
      }
    }
    
    terminalHistory.push(cmd);
    terminalHistoryIndex = terminalHistory.length;
  }
  const originalCwd = currentCwd;
  
  // Convert Unix commands to Windows equivalents
  let windowsCmd = cmd;
  const isWindows = navigator.platform.toLowerCase().includes('win');
  
  if (isWindows) {
    // Common Unix -> Windows command conversions (expanded to ~30)
    const cmdMap = [
      ['ls -la', 'dir /a'],
      ['ls -l', 'dir /l'],
      ['ls -F', 'dir /b'],
      ['ls -lah', 'dir /a'],
      ['ls -lha', 'dir /a'],
      ['ls -ltr', 'dir /a'],
      ['ls -lh', 'dir /l'],
      ['ls', 'dir /b'],
      ['ll', 'dir /b'],
      ['la', 'dir /a'],
      ['pwd', 'cd'],
      ['clear', 'cls'],
      ['cat ', 'type '],
      ['rm -rf ', 'rmdir /s /q '],
      ['rm -r ', 'rmdir /s /q '],
      ['rm ', 'del /f '],
      ['mkdir ', 'mkdir '],
      ['touch ', 'echo. > '],
      ['which ', 'where '],
      ['grep -ri ', 'findstr /s /i '],
      ['grep -r ', 'findstr /s /i '],
      ['grep -i ', 'findstr /i '],
      ['grep -v ', 'findstr /v '],
      ['grep ', 'findstr '],
      ['head -n', 'more +'],
      ['tail -n', 'for /f'],
      ['tail -f', 'Get-Content -Wait'],
      ['find . -name', 'dir /s /b'],
      ['du -sh', 'Get-ChildItem -Recurse | Measure-Object -Property Length -Sum'],
      ['wc -l', 'Get-Content | Measure-Object -Line'],
      ['cp -r ', 'xcopy /E /I '],
      ['mv ', 'move '],
      ['ln -s ', 'New-Item -ItemType SymbolicLink'],
      ['chmod ', 'icacls'],
      ['ps aux', 'Get-Process'],
      ['kill ', 'Stop-Process -Id '],
      ['df -h', 'Get-PSDrive'],
      ['uptime', 'Get-CimInstance Win32_OperatingSystem'],
    ];
    
    for (const [unix, win] of cmdMap) {
      if (cmd.startsWith(unix + ' ') || cmd === unix) {
        windowsCmd = cmd.replace(unix, win);
        break;
      }
    }
  }
  
  // Handle cd/chdir/pwd locally (no backend call needed)
  const cmdLower = cmd.trim().toLowerCase();
  if (cmdLower === 'cd' || cmdLower === 'chdir' || cmdLower === 'pwd' || 
      cmdLower.startsWith('cd ') || cmdLower.startsWith('chdir ') || cmdLower === 'cd -') {
    // Determine the target path
    let targetPath = '';
    if (cmdLower === 'cd' || cmdLower === 'chdir' || cmdLower === 'pwd') {
      // No argument: show current directory
      term.writeln(`\x1b[36m${currentCwd || '~'}\x1b[0m`);
      term.write('\x1b[1;32m$\x1b[0m ');
      return;
    }
    
    // Extract path argument
    const spaceIndex = cmd.indexOf(' ');
    const arg = cmd.slice(spaceIndex + 1).trim();
    
    if (arg === '-') {
      // cd -: go to previous directory
      targetPath = originalCwd || currentCwd;
    } else if (arg === '~' || arg === '') {
      // cd ~ or cd: go to home
      targetPath = '';
    } else if (arg.startsWith('/')) {
      // Absolute path
      targetPath = arg;
    } else if (arg.match(/^[a-zA-Z]:/)) {
      // Windows drive letter
      targetPath = arg;
    } else {
      // Relative path
      targetPath = currentCwd ? currentCwd + '/' + arg : arg;
    }
    
    currentCwd = targetPath;
    term.writeln(`\x1b[36m📁 ${currentCwd || '~'}\x1b[0m`);
    term.write('\x1b[1;32m$\x1b[0m ');
    return;
  }
  
  // Show executing status with color
  const displayCmd = isWindows && windowsCmd !== cmd ? `${cmd} → ${windowsCmd}` : cmd;
  term.write(`\x1b[33m⚡ Executing: ${displayCmd}...\x1b[0m\r\n`);
  
  try {
    const resp = await fetch("/api/exec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        command: cmd,
        cwd: currentCwd || folderInput.value || ""
      }),
    });
    
    const data = await resp.json().catch(() => ({}));
    
    if (resp.ok) {
      if (data.stdout) {
        term.writeln(data.stdout);
      }
      if (data.stderr) {
        term.writeln(`\x1b[31m${data.stderr}\x1b[0m`);
      }
      
      if (data.returncode !== 0) {
        term.writeln(`\x1b[33m[Exit code: ${data.returncode}]\x1b[0m`);
      }
    } else {
      term.writeln(`\x1b[31mError: ${data.detail || resp.statusText}\x1b[0m`);
    }
  } catch (err) {
    term.writeln(`\x1b[31mFailed to execute: ${err.message}\x1b[0m`);
  }
  
  term.write('\x1b[1;32m$\x1b[0m ');
}

function toggleTerminal() {
  const isHidden = terminalPanel.classList.contains("hidden");
  
  if (isHidden) {
    terminalPanel.classList.remove("hidden");
    workspaceContent.classList.add("terminal-open");
    
    // Initialize terminal if not done
    if (!term) {
      initTerminal();
    } else {
      // Refit after showing
      setTimeout(() => {
        if (fitAddon) fitAddon.fit();
      }, 100);
    }
  } else {
    terminalPanel.classList.add("hidden");
    workspaceContent.classList.remove("terminal-open");
  }
}

if (toggleTerminalBtn) {
  toggleTerminalBtn.addEventListener("click", toggleTerminal);
}

if (closeTerminalBtn) {
  closeTerminalBtn.addEventListener("click", toggleTerminal);
}

/* ─── Tab bar + CodeMirror editor ─────────────────────────────── */
// Open file tabs state
let openTabs = [];  // { path, name, content, modified }
let activeTabIndex = -1;
let codeMirrorEditor = null;
let editorClosed = false;

// Editor close button
const editorCloseBtn = document.querySelector("#editorCloseBtn");
const editorFullscreenBtn = document.querySelector("#editorFullscreenBtn");

if (editorCloseBtn) {
  editorCloseBtn.addEventListener("click", () => {
    const tabBar = document.querySelector(".tab-bar");
    if (editorArea.classList.contains("fullscreen")) {
      editorArea.classList.remove("fullscreen");
      if (tabBar) tabBar.classList.remove("editor-fullscreen-visible");
    }
    editorArea.classList.add("collapsed");
    editorArea.classList.remove("has-editor");
    editorClosed = true;
    messagesArea.classList.remove("has-editor");
    messagesArea.style.maxHeight = "";
    messagesArea.style.flex = "1";
  });
}

if (editorFullscreenBtn) {
  editorFullscreenBtn.addEventListener("click", () => {
    const tabBar = document.querySelector(".tab-bar");
    if (editorArea.classList.contains("fullscreen")) {
      // Exit fullscreen
      editorArea.classList.remove("fullscreen");
      editorFullscreenBtn.textContent = "⛶";
      editorFullscreenBtn.title = "编辑器全屏";
      if (tabBar) tabBar.classList.remove("editor-fullscreen-visible");
      if (editorClosed) {
        editorArea.classList.add("collapsed");
      }
    } else {
      // Enter fullscreen
      editorArea.classList.remove("collapsed");
      editorClosed = false;
      editorArea.classList.add("fullscreen");
      if (tabBar) tabBar.classList.add("editor-fullscreen-visible");
      editorFullscreenBtn.textContent = "⛶";
      editorFullscreenBtn.title = "退出全屏";
      messagesArea.classList.add("has-editor");
    }
    // Refit CodeMirror after transition
    setTimeout(() => {
      if (codeMirrorEditor) codeMirrorEditor.refresh();
    }, 300);
  });
}

// CodeMirror mode map
const CM_MODE_MAP = {
  ".py": "python",
  ".js": "javascript",
  ".ts": "typescript",
  ".jsx": "javascript",
  ".tsx": "typescript",
  ".html": "htmlmixed",
  ".css": "css",
  ".scss": "css",
  ".json": "application/json",
  ".md": "markdown",
  ".sql": "sql",
  ".sh": "shell",
  ".ps1": "shell",
  ".go": "go",
  ".rs": "rust",
  ".java": "text/x-java",
  ".c": "text/x-csrc",
  ".cpp": "text/x-c++src",
  ".h": "text/x-csrc",
  ".xml": "xml",
  ".yaml": "yaml",
  ".yml": "yaml",
};

function getCmMode(ext) {
  return CM_MODE_MAP[ext] || "text";
}

function initCodeMirror(content = "", mode = "text") {
  const existingWrapper = editorContainer.querySelector(".CodeMirror-wrapper");
  if (existingWrapper) {
    existingWrapper.remove();
  }
  
  const wrapper = document.createElement("div");
  wrapper.className = "CodeMirror-wrapper";
  wrapper.style.height = "100%";
  editorContainer.appendChild(wrapper);
  
  const textarea = document.createElement("textarea");
  wrapper.appendChild(textarea);
  
  codeMirrorEditor = CodeMirror.fromTextArea(textarea, {
    mode: mode,
    theme: "material-darker",
    lineNumbers: true,
    lineWrapping: true,
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    styleActiveLine: true,
    matchBrackets: true,
    autoCloseBrackets: true,
    extraKeys: {
      "Ctrl-S": saveCurrentFile,
      "Cmd-S": saveCurrentFile,
      "Tab": function(cm) {
        if (completions.length > 0 && selectedCompletionIndex >= 0) {
          applyCompletion(selectedCompletionIndex);
          return;
        }
        cm.replaceSelection("  ", "end");
      },
      "Escape": function(cm) { hideCompletionPanel(); },
      "Down": function(cm) {
        if (completionPanel && completions.length > 0) {
          selectCompletion((selectedCompletionIndex + 1) % completions.length);
          return true;
        }
      },
      "Up": function(cm) {
        if (completionPanel && completions.length > 0) {
          selectCompletion((selectedCompletionIndex - 1 + completions.length) % completions.length);
          return true;
        }
      },
      "Enter": function(cm) {
        if (completionPanel && completions.length > 0 && selectedCompletionIndex >= 0) {
          applyCompletion(selectedCompletionIndex);
          return true;
        }
      },
    },
  });
  
  codeMirrorEditor.setValue(content);
  
  codeMirrorEditor.on("change", () => {
    if (activeTabIndex >= 0 && openTabs[activeTabIndex]) {
      openTabs[activeTabIndex].content = codeMirrorEditor.getValue();
      if (!openTabs[activeTabIndex].modified) {
        openTabs[activeTabIndex].modified = true;
        const tabEl = tabList.querySelector(`.tab[data-index="${activeTabIndex}"] .tab-name`);
        if (tabEl) tabEl.textContent = "● " + openTabs[activeTabIndex].name;
      }
    }
  });
  
  return codeMirrorEditor;
}

function openFileInTab(filePath, fileName, content) {
  // Check if already open
  const existingIndex = openTabs.findIndex(t => t.path === filePath);

  if (existingIndex >= 0) {
    // Switch to existing tab
    switchToTab(existingIndex);
    return;
  }

  // Get file extension
  const ext = fileName.includes(".") ? "." + fileName.split(".").pop().toLowerCase() : "";
  const mode = getCmMode(ext);

  // Add new tab
  openTabs.push({
    path: filePath,
    name: fileName,
    content: content,
    modified: false,
    mode: mode,
    cursorPos: null,
    scrollTop: 0,
  });

  switchToTab(openTabs.length - 1);

  // Auto-show editor if it was closed
  if (editorClosed) {
    editorArea.classList.remove("collapsed");
    editorArea.classList.remove("fullscreen");
    editorClosed = false;
    const tabBar = document.querySelector(".tab-bar");
    if (tabBar) tabBar.classList.remove("editor-fullscreen-visible");
    if (editorFullscreenBtn) {
      editorFullscreenBtn.textContent = "⛶";
      editorFullscreenBtn.title = "编辑器全屏";
    }
  }

  // Show editor
  editorArea.classList.add("has-editor");

  // Hide welcome, show editor
  const welcome = editorContainer.querySelector(".editor-welcome");
  if (welcome) welcome.style.display = "none";

  // Adjust messages area
  messagesArea.classList.add("has-editor");
}

function switchToTab(index) {
  if (index < 0 || index >= openTabs.length) return;
  
  const prevIndex = activeTabIndex;
  activeTabIndex = index;
  const tab = openTabs[index];
  
  if (codeMirrorEditor) {
    if (prevIndex >= 0 && openTabs[prevIndex]) {
      openTabs[prevIndex].cursorPos = codeMirrorEditor.getCursor();
      openTabs[prevIndex].scrollTop = codeMirrorEditor.getScrollInfo().top;
    }
    codeMirrorEditor.setValue(tab.content);
    codeMirrorEditor.setOption("mode", tab.mode);
    if (tab.cursorPos) codeMirrorEditor.setCursor(tab.cursorPos);
    if (tab.scrollTop) codeMirrorEditor.scrollTo(0, tab.scrollTop);
  } else {
    initCodeMirror(tab.content, tab.mode);
  }
  
  updateTabUI();
}

function closeTab(index) {
  if (index < 0 || index >= openTabs.length) return;
  
  const tab = openTabs[index];
  
  // If modified, ask for confirmation
  if (tab.modified) {
    if (!confirm(`${tab.name} 有未保存的修改，确定要关闭吗？`)) {
      return;
    }
  }
  
  // Remove tab
  openTabs.splice(index, 1);
  
  // Update active index
  if (activeTabIndex >= openTabs.length) {
    activeTabIndex = openTabs.length - 1;
  }
  
  if (activeTabIndex >= 0) {
    switchToTab(activeTabIndex);
  } else {
    // Exit fullscreen if no more tabs
    if (editorArea.classList.contains("fullscreen")) {
      editorArea.classList.remove("fullscreen");
      const tabBar = document.querySelector(".tab-bar");
      if (tabBar) tabBar.classList.remove("editor-fullscreen-visible");
      if (editorFullscreenBtn) {
        editorFullscreenBtn.textContent = "⛶";
        editorFullscreenBtn.title = "编辑器全屏";
      }
    }

    // No more tabs, show welcome (but keep editor visible unless manually closed)
    if (!editorClosed) {
      const welcome = editorContainer.querySelector(".editor-welcome");
      if (welcome) welcome.style.display = "block";
    }

    // Remove editor
    const wrapper = editorContainer.querySelector(".CodeMirror-wrapper");
    if (wrapper) wrapper.remove();
    codeMirrorEditor = null;

    messagesArea.classList.remove("has-editor");
    editorArea.classList.remove("has-editor");
    if (!editorClosed) {
      messagesArea.style.maxHeight = "";
    }
  }
  
  updateTabUI();
}

function updateTabUI() {
  if (!tabList) return;
  
  tabList.innerHTML = "";
  
  openTabs.forEach((tab, index) => {
    const tabEl = document.createElement("button");
    tabEl.className = "tab" + (index === activeTabIndex ? " active" : "");
    tabEl.dataset.index = index;
    
    const icon = document.createElement("span");
    icon.className = "tab-icon";
    icon.textContent = getFileIcon(tab.name.includes(".") ? "." + tab.name.split(".").pop() : "");
    
    const name = document.createElement("span");
    name.className = "tab-name";
    name.textContent = (tab.modified ? "● " : "") + tab.name;
    
    const closeBtn = document.createElement("span");
    closeBtn.className = "tab-close";
    closeBtn.textContent = "✕";
    closeBtn.onclick = (e) => {
      e.stopPropagation();
      closeTab(index);
    };
    
    tabEl.append(icon, name, closeBtn);
    tabEl.onclick = () => switchToTab(index);
    
    tabList.appendChild(tabEl);
  });
}

async function saveCurrentFile() {
  if (activeTabIndex < 0 || !openTabs[activeTabIndex]) return;
  
  const tab = openTabs[activeTabIndex];
  
  try {
    const resp = await fetch("/api/craft-apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: tab.path, content: tab.content }),
    });
    
    const data = await resp.json().catch(() => ({}));
    
    if (resp.ok) {
      tab.modified = false;
      updateTabUI();
      addInfoMessage(`✅ 已保存: ${tab.name}`);
    } else {
      addInfoMessage(`❌ 保存失败: ${data.detail || resp.statusText}`);
    }
  } catch (err) {
    addInfoMessage(`❌ 保存失败: ${err.message}`);
  }
}

// New file tab button
if (newFileTabBtn) {
  newFileTabBtn.addEventListener("click", () => {
    showNewFileDialog();
  });
}

function showNewFileDialog() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog">
      <h3>新建文件</h3>
      <input type="text" id="newFileNameInput" class="modal-input" value="untitled.py" placeholder="输入文件名..." />
      <div class="modal-actions">
        <button class="modal-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="modal-confirm" id="newFileConfirmBtn">创建</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  
  const input = document.getElementById("newFileNameInput");
  input.focus();
  input.select();
  
  document.getElementById("newFileConfirmBtn").onclick = () => {
    const fileName = input.value.trim();
    if (fileName) {
      openFileInTab(fileName, fileName, "# 新文件\n");
    }
    overlay.remove();
  };
  
  input.onkeydown = (e) => {
    if (e.key === "Enter") {
      document.getElementById("newFileConfirmBtn").click();
    } else if (e.key === "Escape") {
      overlay.remove();
    }
  };
  
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
}

// Keyboard shortcuts
document.addEventListener("keydown", (e) => {
  // Ctrl+W: close current tab
  if ((e.ctrlKey || e.metaKey) && e.key === "w") {
    e.preventDefault();
    if (activeTabIndex >= 0) {
      closeTab(activeTabIndex);
    }
  }
  // Ctrl+S: save current file
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    saveCurrentFile();
  }
  // Ctrl+Space: trigger AI completion
  if ((e.ctrlKey || e.metaKey) && e.key === " ") {
    e.preventDefault();
    requestCompletion();
  }
});

/* ─── AI Code Completion ─────────────────────────────────────── */
let completionPanel = null;
let completions = [];
let selectedCompletionIndex = -1;

async function requestCompletion() {
  if (!codeMirrorEditor || activeTabIndex < 0 || !openTabs[activeTabIndex]) {
    addInfoMessage("请先打开一个文件再使用 AI 补全");
    return;
  }
  
  const cursor = codeMirrorEditor.getCursor();
  const code = codeMirrorEditor.getValue();
  const cursorPos = codeMirrorEditor.indexFromPos(cursor);
  
  // Don't trigger if code is empty
  if (!code || !code.trim()) {
    return;
  }
  
  // Show loading
  showCompletionLoading();
  
  try {
    const resp = await fetch("/api/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: code,
        cursor_pos: cursorPos,
        file_path: openTabs[activeTabIndex].path || "",
      }),
    });
    
    const data = await resp.json().catch(() => ({}));
    
    if (resp.ok && data.completions && data.completions.length > 0) {
      completions = data.completions;
      showCompletionPanel(completions);
    } else {
      hideCompletionPanel();
    }
  } catch (err) {
    console.error("Completion error:", err);
    hideCompletionPanel();
  }
}

function showCompletionLoading() {
  hideCompletionPanel();
  
  const cursor = codeMirrorEditor.getCursor();
  const coords = codeMirrorEditor.cursorCoords(cursor, "page");
  
  completionPanel = document.createElement("div");
  completionPanel.className = "completion-panel";
  completionPanel.style.left = coords.left + "px";
  completionPanel.style.top = (coords.top + 20) + "px";
  completionPanel.innerHTML = '<div class="completion-loading">🤔 思考中...</div>';
  
  document.body.appendChild(completionPanel);
}

function showCompletionPanel(items) {
  hideCompletionPanel();
  
  if (items.length === 0) return;
  
  const cursor = codeMirrorEditor.getCursor();
  const coords = codeMirrorEditor.cursorCoords(cursor, "page");
  
  completionPanel = document.createElement("div");
  completionPanel.className = "completion-panel";
  completionPanel.style.left = coords.left + "px";
  completionPanel.style.top = (coords.top + 20) + "px";
  
  const header = document.createElement("div");
  header.className = "completion-header";
  header.textContent = "AI 建议 (Tab 选中)";
  completionPanel.appendChild(header);
  
  items.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "completion-item";
    div.dataset.index = index;
    
    const text = document.createElement("div");
    text.className = "completion-text";
    text.textContent = item.text.substring(0, 100);
    
    div.appendChild(text);
    
    if (item.description) {
      const desc = document.createElement("div");
      desc.className = "completion-desc";
      desc.textContent = item.description;
      div.appendChild(desc);
    }
    
    div.onclick = () => applyCompletion(index);
    div.onmouseenter = () => selectCompletion(index);
    
    completionPanel.appendChild(div);
  });
  
  document.body.appendChild(completionPanel);
  selectedCompletionIndex = 0;
  updateCompletionSelection();
}

function hideCompletionPanel() {
  if (completionPanel) {
    completionPanel.remove();
    completionPanel = null;
  }
  completions = [];
  selectedCompletionIndex = -1;
}

function selectCompletion(index) {
  selectedCompletionIndex = index;
  updateCompletionSelection();
}

function updateCompletionSelection() {
  if (!completionPanel) return;
  
  const items = completionPanel.querySelectorAll(".completion-item");
  items.forEach((item, i) => {
    if (i === selectedCompletionIndex) {
      item.classList.add("selected");
    } else {
      item.classList.remove("selected");
    }
  });
}

function applyCompletion(index) {
  if (index < 0 || index >= completions.length) return;
  
  const completion = completions[index];
  const cursor = codeMirrorEditor.getCursor();
  
  // Insert completion text at cursor
  codeMirrorEditor.replaceSelection(completion.text);
  
  hideCompletionPanel();
  codeMirrorEditor.focus();
}

/* ─── Agent Mode Functions ──────────────────────────────────────── */

async function startAgentTask(query) {
  if (!folderStatus?.dataset?.ready) {
    alert("请先设置代码文件夹");
    return;
  }

  setBusy(true);

  // Reset v2 agent view
  const agentStream = document.getElementById("agentStream");
  if (agentStream) agentStream.innerHTML = "";
  const outputEl = document.getElementById("agentOutput");
  if (outputEl) {
    outputEl.classList.add("hidden");
    const outputContent = document.getElementById("agentOutputContent");
    if (outputContent) outputContent.innerHTML = "";
  }
  const thinkingEl = document.getElementById("thinkingContent");
  if (thinkingEl) thinkingEl.textContent = "";
  const thinkingLen = document.getElementById("thinkingLen");
  if (thinkingLen) thinkingLen.textContent = "";
  const thinkingBlock = document.getElementById("agentThinking");
  if (thinkingBlock) thinkingBlock.classList.add("collapsed");
  // Reset route badge
  const badge = document.getElementById("agentRouteBadge");
  if (badge) { badge.className = "agent-route-badge hidden"; badge.textContent = ""; }
  // Reset phase bar
  document.querySelectorAll(".phase-step").forEach(el => {
    el.classList.remove("active", "done");
  });
  // Reset todo list
  const todoList = document.getElementById("agentTodoList");
  if (todoList) todoList.innerHTML = '<div class="agent-todo-empty">等待任务开始...</div>';
  const todoProgress = document.getElementById("agentTodoProgress");
  if (todoProgress) todoProgress.textContent = "0/0";
  // Restore side column (may have been hidden by previous task's done event)
  const sideCol = document.getElementById("agentSideCol");
  const body = document.querySelector(".agent-body");
  if (sideCol) sideCol.style.display = "";
  if (body) body.style.gridTemplateColumns = "";

  agentPaused = false;
  renderPauseButtonIcon();
  // Notify renderer to reset its state (thinkingLen, todoItems, tool grouping)
  window.dispatchEvent(new Event("agent:reset"));
  resetToolGrouping();
  // Start heartbeat/status pill
  startAgentHeartbeat();
  // Load task history into the side panel
  if (typeof loadAgentHistory === "function") loadAgentHistory();

  // Switch to view-agent
  const viewChat = document.getElementById("viewChat");
  const viewAgent = document.getElementById("viewAgent");
  if (viewChat) viewChat.classList.remove("active");
  if (viewAgent) viewAgent.classList.add("active");
  if (modeSelect) modeSelect.value = "agent";
  if (workspace) workspace.setAttribute("data-mode", "agent");
  const modeBadge = document.getElementById("workspaceMode");
  if (modeBadge) modeBadge.textContent = "Agent";

  try {
    const startRes = await fetch("/api/agent/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, max_steps: 30 }),
    });
    if (!startRes.ok) {
      const err = await startRes.json();
      throw new Error(err.detail || "Failed to start agent");
    }
    const startData = await startRes.json();
    agentTaskId = startData.task_id;

    await streamAgentExecution(agentTaskId);
  } catch (err) {
    v2AppendCard("error", "启动失败", err.message);
  } finally {
    setBusy(false);
  }
}

// Agent control button event listeners
// Render the pause/resume button's SVG icon depending on `agentPaused` state.
// Running (agentPaused=false) shows ‖ (pause); Paused (agentPaused=true) shows ▶ (resume).
function renderPauseButtonIcon() {
  if (!agentPauseBtn) return;
  agentPauseBtn.innerHTML = agentPaused
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
  agentPauseBtn.title = agentPaused ? "继续" : "暂停";
}

if (agentPauseBtn) {
  renderPauseButtonIcon();
  agentPauseBtn.addEventListener("click", () => {
    if (!agentTaskId) return;
    // Decide action BEFORE flipping state: if not currently paused, we want to pause.
    const action = agentPaused ? "resume" : "pause";
    agentPaused = !agentPaused;
    fetch(`/api/agent/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: agentTaskId, action }),
    }).catch(e => {
      console.error("Pause/resume failed:", e);
      // Revert UI state on failure
      agentPaused = !agentPaused;
      renderPauseButtonIcon();
    });
    renderPauseButtonIcon();
  });
}

if (agentStopBtn) agentStopBtn.addEventListener("click", () => {
  if (!agentTaskId) return;
  fetch(`/api/agent/stop/${agentTaskId}`, { method: "POST" })
    .then(() => {
      if (typeof v2AppendCard === "function") {
        v2AppendCard("error", "⏹️ Agent 已停止", null, "用户停止");
      }
      agentTaskId = null;
      setBusy(false);
      stopAgentHeartbeat();
      setAgentStatus("paused", null);
    })
    .catch(e => console.error("Stop failed:", e));
});

if (closeAgentBtn) closeAgentBtn.addEventListener("click", () => {
  if (agentPanel) {
    agentPanel.classList.remove("fullscreen");
    agentPanel.classList.remove("preview-phase");
    agentPanel.classList.remove("active");
    agentPanel.classList.add("hidden");
  }
  const agentFullscreenBtn = document.querySelector("#agentFullscreenBtn");
  if (agentFullscreenBtn) {
    agentFullscreenBtn.textContent = "⛶";
    agentFullscreenBtn.title = "全屏";
  }
  if (window._approvalTimeout) clearTimeout(window._approvalTimeout);
});

// Agent fullscreen toggle
const agentFullscreenBtn = document.querySelector("#agentFullscreenBtn");
if (agentFullscreenBtn) {
  agentFullscreenBtn.addEventListener("click", () => {
    if (!agentPanel) return;
    if (agentPanel.classList.contains("fullscreen")) {
      // Exit fullscreen
      agentPanel.classList.remove("fullscreen");
      agentFullscreenBtn.textContent = "⛶";
      agentFullscreenBtn.title = "全屏";
    } else {
      // Enter fullscreen
      agentPanel.classList.add("fullscreen");
      agentFullscreenBtn.textContent = "⛶";
      agentFullscreenBtn.title = "退出全屏";
    }
    // Re-scroll output to bottom
    if (agentOutput) agentOutput.scrollTop = agentOutput.scrollHeight;
  });
}

async function streamAgentExecution(taskId) {
  if (typeof v2AppendCard === "function") {
    v2AppendCard("info", "🤖 Agent 正在思考...", null, "");
  }

  let sseBuffer = "";
  let reader = null;

  try {
    const response = await fetch(`/api/agent/execute/${taskId}`, {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      sseBuffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      const lines = sseBuffer.split("\n");
      sseBuffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const jsonStr = trimmed.slice(5).trim();
        if (!jsonStr || jsonStr === "[DONE]") continue;

        try {
          const data = JSON.parse(jsonStr);
          handleAgentEvent(data);
        } catch (e) {
          // Skip invalid JSON (partial line handled by buffer)
        }
      }
    }

  } catch (err) {
    if (typeof v2AppendCard === "function") {
      v2AppendCard("error", "执行错误", `<div>${err.message}</div>`, "");
    }
  } finally {
    if (reader) reader.releaseLock();
  }
}

// NOTE: The original v1 handleAgentEvent + helper functions (addAgentStep,
// updateAgentStep, appendAgentStepDetail, updateStepSummary, appendAgentOutput,
// the v1 Todo system, updatePhaseBar, showPlanPreview, showAgentThinking, and
// the diff approval functions: renderDiffPreview, hideDiffPreview, approveFile,
// rejectFile, showApplyProgress, updateApplyStep, hideApplyProgress) plus the
// v1.5 handleAgentEvent override were removed as dead code. The diff approval
// UI is no longer supported by the backend. The single source of truth for
// agent event rendering is the unified renderer defined below (formerly the v2
// IIFE). `handleAgentEvent` is assigned there.

/* ═══════════════════════════════════════════════════════════
   NEW: Frontend improvements for 100-point optimization
   ═══════════════════════════════════════════════════════════ */

/* ─── #36 Code block copy button ─────────────────────────── */
function initCopyButtons() {
  document.querySelectorAll('.code-block').forEach(block => {
    if (block.querySelector('.copy-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = '📋 复制';
    btn.onclick = () => {
      const code = block.querySelector('code');
      if (code) {
        navigator.clipboard.writeText(code.textContent).then(() => {
          btn.textContent = '✅ 已复制';
          btn.classList.add('copied');
          setTimeout(() => { btn.textContent = '📋 复制'; btn.classList.remove('copied'); }, 2000);
        });
      }
    };
    block.appendChild(btn);
  });
}

/* ─── #40 File tree search/filter ─────────────────────────── */
function initTreeSearch() {
  const input = document.getElementById('treeSearchInput');
  if (!input) return;

  input.addEventListener('input', () => {
    const query = input.value.toLowerCase().trim();
    const rows = treeView.querySelectorAll('.tree-file-row');
    const dirRows = treeView.querySelectorAll('.tree-dir-row');

    if (!query) {
      rows.forEach(r => r.style.display = '');
      dirRows.forEach(r => r.style.display = '');
      return;
    }

    // Show matching files and their parent dirs
    rows.forEach(row => {
      const name = row.querySelector('.tree-name')?.textContent || '';
      const match = name.toLowerCase().includes(query);
      row.style.display = match ? '' : 'none';
      if (match) {
        // Expand parent directories
        let parent = row.parentElement;
        while (parent && parent !== treeView) {
          if (parent.classList.contains('tree-children')) {
            parent.classList.remove('collapsed');
            const arrow = parent.previousElementSibling?.querySelector('.tree-arrow');
            const icon = parent.previousElementSibling?.querySelector('.dir-icon');
            if (arrow) arrow.textContent = '▾';
            if (icon) icon.textContent = '📂';
          }
          parent = parent.parentElement;
        }
      }
    });

    // Hide dirs that have no visible children
    dirRows.forEach(row => {
      const children = row.nextElementSibling;
      if (children && children.classList.contains('tree-children')) {
        const visibleChildren = children.querySelectorAll(':scope > .tree-file-row[style=""], :scope > .tree-dir-row[style=""]');
        // Simple approach: show all dirs when searching
      }
    });
  });
}

/* ─── #50 SSE retry ────────────────────────────────────── */
async function streamAskWithRetry(question, maxRetries = 2) {
  let lastError = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) {
      const retryEl = document.createElement('span');
      retryEl.className = 'sse-retrying';
      retryEl.textContent = ` 重试中 (${attempt}/${maxRetries})...`;
      messages.appendChild(retryEl);
      messages.scrollTop = messages.scrollHeight;
      await new Promise(r => setTimeout(r, 1000 * attempt));
      if (retryEl.parentNode) retryEl.remove();
    }

    try {
      await streamAsk(question);
      return; // Success
    } catch (err) {
      lastError = err;
    }
  }

  if (lastError) {
    addInfoMessage(`请求失败（已重试${maxRetries}次）：${lastError.message}`);
  }
}

/* ─── #55 Keyboard shortcuts overview modal ───────────────── */
function showShortcutsModal() {
  // Remove any existing shortcuts overlay to prevent duplicates
  document.querySelectorAll('.shortcuts-overlay').forEach(el => el.remove());

  const overlay = document.createElement('div');
  overlay.className = 'shortcuts-overlay';
  overlay.innerHTML = `
    <div class="shortcuts-dialog">
      <h2>快捷键</h2>
      <table class="shortcuts-table">
        <tr><td>发送消息</td><td><span class="kbd">Enter</span></td></tr>
        <tr><td>换行</td><td><span class="kbd">Shift</span> + <span class="kbd">Enter</span></td></tr>
        <tr><td>保存文件</td><td><span class="kbd">Ctrl</span> + <span class="kbd">S</span></td></tr>
        <tr><td>关闭标签</td><td><span class="kbd">Ctrl</span> + <span class="kbd">W</span></td></tr>
        <tr><td>AI 代码补全</td><td><span class="kbd">Ctrl</span> + <span class="kbd">Space</span></td></tr>
        <tr><td>切换终端</td><td><span class="kbd">Ctrl</span> + <span class="kbd">\`</span></td></tr>
        <tr><td>快捷键概览</td><td><span class="kbd">Ctrl</span> + <span class="kbd">?</span></td></tr>
        <tr><td>关闭弹窗</td><td><span class="kbd">Esc</span></td></tr>
      </table>
      <button class="shortcuts-close" onclick="this.closest('.shortcuts-overlay').remove()">关闭</button>
    </div>
  `;
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);
}

/* ─── #48 Persistent settings in localStorage ─────────────── */
function initPersistentSettings() {
  if (!maxTokensSelect || !temperatureSelect || !contextLimitSelect) return;
  const saved = localStorage.getItem('codelens-settings');
  if (saved) {
    try {
      const s = JSON.parse(saved);
      if (s.maxTokens) maxTokensSelect.value = s.maxTokens;
      if (s.temperature) temperatureSelect.value = s.temperature;
      if (s.contextLimit) contextLimitSelect.value = s.contextLimit;
      modelSettings.maxTokens = parseInt(s.maxTokens || '4096');
      modelSettings.temperature = parseFloat(s.temperature || '0.15');
      modelSettings.contextLimit = parseInt(s.contextLimit || '42000');
    } catch {}
  }

  // Save on change
  [maxTokensSelect, temperatureSelect, contextLimitSelect].forEach(sel => {
    if (sel) {
      sel.addEventListener('change', () => {
        localStorage.setItem('codelens-settings', JSON.stringify({
          maxTokens: maxTokensSelect.value,
          temperature: temperatureSelect.value,
          contextLimit: contextLimitSelect.value,
        }));
      });
    }
  });
}

/* ─── #49 System preference detection for theme ───────────── */
function initSystemThemePreference() {
  const saved = localStorage.getItem('codelens-theme');
  if (!saved) {
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      toggleTheme();
    }
  }
}

/* ─── #35 Markdown: collapsible details ───────────────────── */
function enhancedRenderMarkdown(md) {
  let html = renderMarkdown(md);

  // Wrap in <details> for collapsible sections
  html = html.replace(/<details><summary>(.*?)<\/summary>([\s\S]*?)<\/details>/g, (_, summary, content) => {
    return `<details><summary>${summary}</summary><div class="markdown-inner">${content}</div></details>`;
  });

  return html;
}

/* ─── #37,#38 Clickable file paths in rendered markdown ───── */
function looksLikeFilePath(p) {
  if (!p || p.length < 2 || /\s/.test(p)) return false;
  if (/[/\\]/.test(p)) return true;
  return /\.(py|js|mjs|cjs|ts|tsx|jsx|vue|svelte|html|htm|css|scss|sass|json|ya?ml|toml|md|txt|rs|go|java|kt|kts|cs|php|rb|swift|sql|sh|ps1|bat|cmd|xml|c|h|cpp|hpp|cc|hh)$/i.test(p);
}

function makeFilePathsClickable(html) {
  return html.replace(
    /<code>([^<]{1,512})<\/code>/gi,
    (full, inner) => {
      const path = inner
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&amp;/g, "&")
        .replace(/&quot;/g, '"')
        .replace(/&#039;/g, "'");
      if (!looksLikeFilePath(path)) return full;
      const safe = escapeHtml(path);
      return `<a class="file-path" href="#" data-path="${safe}">${safe}</a>`;
    }
  );
}

/* ─── Resizable panels ────────────────────────────────────── */
function initResizable() {
  // Sidebar resize
  const sidebarResize = document.getElementById("sidebarResize");
  const sidebar = document.querySelector(".sidebar");
  if (sidebarResize && sidebar) {
    let startX, startWidth;
    sidebarResize.addEventListener("mousedown", (e) => {
      startX = e.clientX;
      startWidth = sidebar.offsetWidth;
      sidebarResize.classList.add("active");
      const onMouseMove = (e) => {
        const newWidth = Math.max(200, Math.min(500, startWidth + e.clientX - startX));
        sidebar.style.width = newWidth + "px";
        sidebar.style.minWidth = newWidth + "px";
        document.documentElement.style.setProperty("--sidebar-width", newWidth + "px");
      };
      const onMouseUp = () => {
        sidebarResize.classList.remove("active");
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        localStorage.setItem("codelens-sidebar-width", sidebar.style.width);
      };
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
    // Restore saved width
    const savedWidth = localStorage.getItem("codelens-sidebar-width");
    if (savedWidth) {
      sidebar.style.width = savedWidth;
      sidebar.style.minWidth = savedWidth;
      document.documentElement.style.setProperty("--sidebar-width", savedWidth);
    }
  }

  // Split resize (chat/editor)
  const splitResize = document.getElementById("splitResize");
  const chatPanel = document.querySelector(".chat-panel");
  const editorArea = document.getElementById("editorArea");
  if (splitResize && chatPanel) {
    let startX, startChatWidth;
    splitResize.addEventListener("mousedown", (e) => {
      startX = e.clientX;
      startChatWidth = chatPanel.offsetWidth;
      splitResize.classList.add("active");
      const onMouseMove = (e) => {
        const mainSplit = document.querySelector(".main-split");
        const totalWidth = mainSplit.offsetWidth;
        const newChatWidth = Math.max(200, Math.min(totalWidth - 200, startChatWidth + e.clientX - startX));
        chatPanel.style.flex = "0 0 " + newChatWidth + "px";
      };
      const onMouseUp = () => {
        splitResize.classList.remove("active");
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      };
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
  }
}

/* ─── #42 Terminal: command history navigation ────────────── */
// Terminal handles history via the existing xterm API
// We extend the terminal to support Up/Down for history

/* ─── Initialize all new features ─────────────────────────── */
// D5: toggle the mobile side-column drawer via its drag handle (::before).
// The handle sits in the first 36px of the drawer; clicking toggles .expanded.
function initMobileAgentDrawer() {
  const sideCol = document.getElementById("agentSideCol");
  if (!sideCol) return;
  sideCol.addEventListener("click", (e) => {
    // Only react to clicks in the top handle zone (the ::before pseudo area).
    if (e.offsetY !== undefined && e.offsetY <= 36) {
      sideCol.classList.toggle("expanded");
    }
  });
}

function initNewFeatures() {
  initCopyButtons();
  initTreeSearch();
  initPersistentSettings();
  initSystemThemePreference();
  initResizable();
  initMobileAgentDrawer();
}

// Initialize on load
initNewFeatures();

// Use MutationObserver to add copy buttons to new code blocks
const _codeBlockObserver = new MutationObserver(() => {
  initCopyButtons();
});
if (messages) {
  _codeBlockObserver.observe(messages, { childList: true, subtree: true });
}

// Keyboard shortcut for shortcuts modal
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === '?') {
    e.preventDefault();
    showShortcutsModal();
  }
  // Ctrl+` for terminal toggle
  if ((e.ctrlKey || e.metaKey) && e.key === '`') {
    e.preventDefault();
    if (toggleTerminalBtn) toggleTerminalBtn.click();
  }
  // Ctrl+1/2/3/4 for mode switching
  if ((e.ctrlKey || e.metaKey) && ['1', '2', '3', '4'].includes(e.key)) {
    e.preventDefault();
    const modes = ['ask', 'plan', 'craft', 'agent'];
    const mode = modes[parseInt(e.key) - 1];
    if (modeSelect && mode) {
      modeSelect.value = mode;
      modeSelect.dispatchEvent(new Event('change'));
    }
  }

  // D4: Agent-view-only shortcuts.
  // Esc → stop current task; Ctrl/Cmd+P → pause/resume.
  // Only active when in agent mode and the input area is not focused.
  if (currentMode === "agent") {
    if (e.key === "Escape" && agentTaskId) {
      // Don't hijack Esc from focused inputs/terminal (let them blur first).
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
      const isInTerminal = e.target && e.target.closest && e.target.closest(".terminal-container, .xterm");
      if (tag === "input" || tag === "textarea" || isInTerminal) {
        // allow default (blur) — do nothing
      } else if (agentStopBtn) {
        e.preventDefault();
        agentStopBtn.click();
      }
    }
    // Ctrl/Cmd+P → toggle pause (override browser print only in agent mode)
    if ((e.ctrlKey || e.metaKey) && (e.key === "p" || e.key === "P") && agentTaskId) {
      e.preventDefault();
      if (agentPauseBtn) agentPauseBtn.click();
    }
  }
});

// Scroll to bottom button
const scrollBottomBtn = document.getElementById("scrollBottomBtn");
if (messages && scrollBottomBtn) {
  messages.addEventListener("scroll", () => {
    const isNearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 100;
    scrollBottomBtn.classList.toggle("hidden", isNearBottom);
  });
}


/* ======================================================================
   Unified Agent renderer (2026-06-14)
   Renders events into #agentStream (cards) + #agentTodoList + phase bar.
   This is the SINGLE implementation; the legacy v1/v1.5 renderers were removed.
   ====================================================================== */

// ---- helpers ----

// I3: smart auto-scroll state. When user scrolls up to inspect history,
// pause auto-scroll and show a "↓ 最新" button; resume when they jump back.
let agentAutoScroll = true;

// Append a card to the stream (or current subtask body). Returns the card.
// collapsed: if true, the card starts with body hidden (tool calls default collapsed).
function v2AppendCard(iconClass, title, bodyHtml, meta, collapsed) {
  // I2: append into the current subtask body container if one is open,
  // otherwise append directly to the stream.
  const stream = document.getElementById("agentStream");
  if (!stream) return null;
  const target = currentSubtaskBody || stream;

  const card = document.createElement("div");
  card.className = "agent-card agent-card-enter";
  if (collapsed) card.classList.add("collapsed");
  const metaHtml = meta ? `<span class="agent-card-meta">${meta}</span>` : "";
  const bodySection = bodyHtml
    ? `<div class="agent-card-body">${bodyHtml}</div>`
    : "";
  card.innerHTML = `
    <div class="agent-card-header">
      <span class="agent-card-icon ${iconClass}">●</span>
      <span class="agent-card-title">${title}</span>
      ${metaHtml}
    </div>
    ${bodySection}
  `;
  target.appendChild(card);
  // I3: only auto-scroll if user is following
  if (agentAutoScroll) {
    const mainCol = document.getElementById("agentMainCol");
    if (mainCol) mainCol.scrollTop = mainCol.scrollHeight;
  }
  // I4: remove the enter class after animation so hover transitions work
  setTimeout(() => card.classList.remove("agent-card-enter"), 250);
  return card;
}

// Escape HTML
function agentEsc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// Truncate + escape
function agentTrunc(s, n) {
  s = String(s || "");
  return s.length > n ? agentEsc(s.slice(0, n)) + "…" : agentEsc(s);
}

// Render markdown via marked.js + highlight.js; falls back to escaped <pre>.
function v2RenderMarkdown(md) {
  if (typeof md !== "string") md = String(md || "");
  if (window.marked && typeof window.marked.parse === "function") {
    try {
      // Configure once
      if (!window._v2MarkedConfigured) {
        window.marked.setOptions({
          breaks: true,
          gfm: true,
          highlight: function (code, lang) {
            if (window.hljs && lang && window.hljs.getLanguage(lang)) {
              try { return window.hljs.highlight(code, { language: lang }).value; } catch (e) {}
            }
            if (window.hljs) {
              try { return window.hljs.highlightAuto(code).value; } catch (e) {}
            }
            return agentEsc(code);
          },
        });
        window._v2MarkedConfigured = true;
      }
      return window.marked.parse(md);
    } catch (e) {
      // fall through
    }
  }
  // Fallback: escaped preformatted
  return `<pre style="white-space:pre-wrap">${agentEsc(md)}</pre>`;
}

function renderAgentFinalResult(resultText, options = {}) {
  const outputEl = document.getElementById("agentOutput");
  const content = document.getElementById("agentOutputContent");
  const sideCol = document.getElementById("agentSideCol");
  const body = document.querySelector(".agent-body");
  const mainCol = document.getElementById("agentMainCol");
  const stream = document.getElementById("agentStream");
  const thinkingBlock = document.getElementById("agentThinking");
  if (!outputEl || !content) return;

  const markdown = String(resultText || "\u6682\u65e0\u7ed3\u679c\u3002");
  if (body) {
    body.style.gridTemplateColumns = "";
    body.classList.add("result-focus");
  }
  if (sideCol) {
    sideCol.style.display = "";
    sideCol.classList.add("result-hidden");
  }
  if (stream && options.collapseStream !== false) {
    stream.querySelectorAll(".agent-card").forEach(c => c.classList.add("collapsed"));
    stream.querySelectorAll(".subtask-section").forEach(s => s.classList.add("collapsed"));
  }
  if (thinkingBlock) thinkingBlock.classList.add("collapsed");

  outputEl.classList.remove("hidden");
  outputEl.classList.add("reading-mode");
  content.innerHTML = v2RenderMarkdown(markdown);

  if (stream && outputEl.parentElement === mainCol && mainCol.firstElementChild !== outputEl) {
    mainCol.insertBefore(outputEl, stream);
  }

  outputEl.classList.remove("just-arrived");
  void outputEl.offsetWidth;
  outputEl.classList.add("just-arrived");

  setTimeout(() => {
    if (mainCol) {
      mainCol.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      outputEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, 80);

  const copyBtn = document.getElementById("copyResultBtn");
  if (copyBtn) {
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(markdown).catch(() => {});
      copyBtn.title = "\u5df2\u590d\u5236";
    };
  }
}

// ---- phase bar ----

let agentCurrentPhase = null;
const AGENT_PHASE_ORDER = ["routing", "decomposing", "executing", "aggregating", "done"];

function setPhase(phase) {
  const idx = AGENT_PHASE_ORDER.indexOf(phase);
  if (idx < 0) return;
  agentCurrentPhase = phase;
  document.querySelectorAll(".phase-step").forEach(el => {
    const p = el.getAttribute("data-phase");
    const pIdx = AGENT_PHASE_ORDER.indexOf(p);
    el.classList.toggle("active", p === phase);
    el.classList.toggle("done", pIdx >= 0 && pIdx < idx);
  });
}

// ---- todo list ----

// id -> {el, status}
const agentTodoItems = new Map();

function ensureTodoListCleared() {
  const list = document.getElementById("agentTodoList");
  if (!list) return;
  if (list.querySelector(".agent-todo-empty")) {
    list.innerHTML = "";
  }
}

function upsertTodo(id, desc, status, meta) {
  const list = document.getElementById("agentTodoList");
  const progress = document.getElementById("agentTodoProgress");
  if (!list) return;
  ensureTodoListCleared();

  // Ensure status is a valid string
  const safeStatus = String(status || "pending");

  let item = agentTodoItems.get(id);
  if (!item) {
    const el = document.createElement("div");
    el.className = "agent-todo-item status-" + safeStatus;
    el.dataset.id = id;
    el.innerHTML = `
      <span class="agent-todo-icon"></span>
      <span class="agent-todo-desc">${agentEsc(desc)}</span>
      <span class="agent-todo-meta">${agentEsc(meta || "")}</span>
    `;
    list.appendChild(el);
    item = { el, status: safeStatus };
    agentTodoItems.set(id, item);
  } else {
    item.el.className = "agent-todo-item status-" + safeStatus;
    if (desc) {
      const descEl = item.el.querySelector(".agent-todo-desc");
      if (descEl) descEl.textContent = String(desc);
    }
    if (meta !== undefined && meta !== null) {
      const metaEl = item.el.querySelector(".agent-todo-meta");
      if (metaEl) metaEl.textContent = String(meta);
    }
    item.status = safeStatus;
  }

  // Update progress
  if (progress) {
    const total = agentTodoItems.size;
    const done = [...agentTodoItems.values()].filter(t => t.status === "done").length;
    progress.textContent = `${done}/${total}`;
  }
}

// ---- thinking ----

let agentThinkingLen = 0;

// Reset renderer state when a new task starts.
function resetAgentRenderer() {
  agentThinkingLen = 0;
  agentTodoItems.clear();
  resetToolGrouping();
  const body = document.querySelector(".agent-body");
  const sideCol = document.getElementById("agentSideCol");
  const outputEl = document.getElementById("agentOutput");
  if (body) {
    body.style.gridTemplateColumns = "";
    body.classList.remove("result-focus");
  }
  if (sideCol) {
    sideCol.style.display = "";
    sideCol.classList.remove("result-hidden");
  }
  if (outputEl) outputEl.classList.add("hidden");
  // I2: clear subtask section state
  currentSubtaskBody = null;
  currentSubtaskHeader = null;
  currentSubtaskToolCount = 0;
  // I3: reset auto-scroll for the new task
  agentAutoScroll = true;
}

window.addEventListener("agent:reset", () => {
  resetAgentRenderer();
});

// I3: Smart scroll-following on #agentMainCol.
// When the user scrolls up to inspect history, pause auto-scroll and show
// the "↓ 最新" button; resume when they scroll back near the bottom.
(function initSmartScroll() {
  const mainCol = document.getElementById("agentMainCol");
  const scrollBtn = document.getElementById("agentScrollBottomBtn");
  if (!mainCol || !scrollBtn) return;

  mainCol.addEventListener("scroll", () => {
    const distFromBottom = mainCol.scrollHeight - mainCol.scrollTop - mainCol.clientHeight;
    if (distFromBottom < 80) {
      agentAutoScroll = true;
      scrollBtn.classList.add("hidden");
    } else {
      agentAutoScroll = false;
      scrollBtn.classList.remove("hidden");
    }
  });

  scrollBtn.addEventListener("click", () => {
    agentAutoScroll = true;
    mainCol.scrollTop = mainCol.scrollHeight;
    scrollBtn.classList.add("hidden");
  });
})();

// ---- main event handler ----

function handleAgentEvent(data) {
  const t = data.type;

  // Reset heartbeat on any event (D1)
  bumpAgentHeartbeat();

  // Phase progression
  if (t === "phase_change") {
    const phase = data.phase;
    setPhase(phase);
    setAgentStatus("running", null);
    // Don't emit a card for phase_change — the phase bar already shows it
    return;
  }

  // Analysis: show route badge + summary, and seed Todo list for simple routes
  if (t === "analysis") {
    const badge = document.getElementById("agentRouteBadge");
    if (badge) {
      badge.className = `agent-route-badge route-${data.intent_type || ""}`;
      const names = { simple: "SIMPLE", multi_step: "MULTI-STEP", map_reduce: "MAP-REDUCE" };
      badge.textContent = names[data.intent_type] || (data.intent_type || "").toUpperCase();
    }
    v2AppendCard(
      "info",
      `任务路由: ${data.intent_type || "?"}`,
      `<div>${agentEsc(data.description || "")}</div>`,
      `置信度 ${data.confidence || "?"}`
    );
    // For simple routes, the backend won't emit plan_generated.
    // Seed the Todo list with a single virtual item representing the task.
    if (data.intent_type === "simple") {
      const qEl = document.getElementById("questionInput");
      const query = qEl ? qEl.value : "任务";
      upsertTodo("virtual-root", query || "执行任务", "running", "simple");
    }
    return;
  }

  // Plan generated: populate todo list from subtasks
  if (t === "plan_generated") {
    const subtasks = data.subtasks || [];
    v2AppendCard(
      "subtask",
      `生成计划: ${subtasks.length} 个子任务`,
      null,
      `类型 ${data.kind || "?"}`
    );
    subtasks.forEach(st => {
      upsertTodo(st.id, st.description || st.id, "pending", st.kind || "");
    });
    return;
  }

  // Subtask start: mark todo as running + open a new subtask section (I2)
  if (t === "subtask_start") {
    upsertTodo(data.id, data.description || data.id, "running", data.kind || "");
    openSubtaskSection(data.id, data.description || data.id, data.index, data.total);
    return;
  }

  // Subtask done: update section status + mark todo as done/partial/failed (I2)
  if (t === "subtask_done") {
    const st = data.status || "done";
    // Raw summary for textContent (used in upsertTodo meta)
    const rawSummary = data.summary ? String(data.summary).slice(0, 60) : "";
    const findings = data.findings_count ? ` · ${data.findings_count} 个发现` : "";
    // Escaped summary for innerHTML (used in closeSubtaskSection)
    const escSummary = data.summary ? agentTrunc(data.summary, 300) : "";
    upsertTodo(data.id, null, st === "success" ? "done" : st, rawSummary + findings);
    closeSubtaskSection(data.id, st, escSummary);
    return;
  }

  // Iteration start: insert a separator line into thinking content (D3)
  if (t === "iteration_start") {
    const el = document.getElementById("thinkingContent");
    if (el) {
      const iter = data.iteration || "?";
      const sep = `\n\n── 迭代 ${iter} ──\n\n`;
      el.textContent += sep;
      agentThinkingLen += sep.length;
      const lenEl = document.getElementById("thinkingLen");
      if (lenEl) lenEl.textContent = `${agentThinkingLen} 字符`;
      el.scrollTop = el.scrollHeight;
    }
    return;
  }

  // Thinking chunks: stream into collapsible block
  if (t === "thinking_chunk") {
    const el = document.getElementById("thinkingContent");
    const lenEl = document.getElementById("thinkingLen");
    const block = document.getElementById("agentThinking");
    if (el && data.content) {
      const wasEmpty = agentThinkingLen === 0;
      el.textContent += data.content;
      agentThinkingLen += data.content.length;
      if (lenEl) lenEl.textContent = `${agentThinkingLen} 字符`;
      // Auto-expand on first chunk only (so user can manually collapse later)
      if (block && wasEmpty) {
        block.classList.remove("collapsed");
      }
      // Auto-scroll within thinking content
      el.scrollTop = el.scrollHeight;
    }
    return;
  }

  // LLM response: collapse thinking + show markdown card (default collapsed, I5)
  if (t === "llm_response") {
    const block = document.getElementById("agentThinking");
    if (block) block.classList.add("collapsed");
    const raw = String(data.content || "");
    let clean = raw.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
    clean = clean.replace(/\{"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{[\s\S]*?\}\s*\}/g, "").trim();
    if (clean && clean.length > 20) {
      const html = v2RenderMarkdown(clean);
      // Title shows a short preview; full content in collapsed body
      const preview = clean.slice(0, 50).replace(/\n/g, " ") + (clean.length > 50 ? "…" : "");
      const card = v2AppendCard("info", `💬 ${preview}`, `<div class="markdown">${html}</div>`, `${clean.length} 字符`, true);
      if (card) {
        const header = card.querySelector(".agent-card-header");
        if (header) {
          header.classList.add("clickable");
          header.addEventListener("click", () => card.classList.toggle("collapsed"));
        }
      }
    }
    return;
  }

  // Tool call batch — silent (I5): the subtask section header already shows
  // the tool count; emitting a separate card would be redundant noise.
  if (t === "tool_call_batch") {
    return;
  }

  // Tool call — try to fold into a repeated-tool group (D2)
  if (t === "tool_call") {
    const args = data.args || {};
    const argsStr = Object.entries(args).map(([k, v]) => `${k}=${agentTrunc(v, 60)}`).join(", ");
    appendToolCallCard(data.tool || "?", argsStr);
    return;
  }

  // Tool result (collapsible body) — also folds into repeated-tool group (D2)
  if (t === "tool_result") {
    const r = String(data.result || "");
    appendToolResultCard(data.tool || "?", r);
    return;
  }

  // Tool error
  if (t === "tool_error") {
    v2AppendCard("error", `✗ ${data.tool || "?"} 失败`, `<div>${agentEsc(data.error || "")}</div>`, "");
    return;
  }

  // Warning / info (skip if no content)
  if (t === "warning") {
    if (data.message) v2AppendCard("warn", `⚠ ${data.message}`, null, "");
    return;
  }
  if (t === "info") {
    if (data.message) v2AppendCard("info", data.message, null, "");
    return;
  }

  // Final done: render into #agentOutput + close out any virtual todo
  if (t === "done") {
    // Close virtual-root todo (simple routes)
    if (agentTodoItems.has("virtual-root")) {
      upsertTodo("virtual-root", null, "done", "完成");
    }
    renderAgentFinalResult(data.result || "");
    setPhase("done");
    setAgentStatus("done", null);
    stopAgentHeartbeat();
    // Reindex files after task completes (file tree may have changed)
    refreshFileTree();
    // Refresh history list (E3)
    if (typeof loadAgentHistory === "function") loadAgentHistory();
    return;
  }

  // Error
  if (t === "error") {
    v2AppendCard("error", "错误", `<div>${agentEsc(data.message || "")}</div>`, "");
    setAgentStatus("failed", null);
    stopAgentHeartbeat();
    return;
  }

  // Status / reflection / plan_data / batch_tool_call: silently ignore
  if (t === "status" || t === "reflection" || t === "plan_data" || t === "batch_tool_call") {
    return;
  }

  // Fallback: unknown event
  // console.log("[agent] unhandled event:", t, data);
}

// ---- D1: status pill / heartbeat ----

let agentHeartbeatTimer = null;
let agentHeartbeatStart = 0;
let agentLastEventTime = 0;

function setAgentStatus(state, elapsedSec) {
  const pill = document.getElementById("agentStatusPill");
  if (!pill) return;
  pill.classList.remove("state-running", "state-paused", "state-done", "state-failed", "state-stalled");
  if (state === "running") {
    pill.classList.add("state-running");
    pill.textContent = elapsedSec != null
      ? `运行中 · ${formatDuration(elapsedSec)}`
      : "运行中";
  } else if (state === "paused") {
    pill.classList.add("state-paused");
    pill.textContent = "已暂停";
  } else if (state === "done") {
    pill.classList.add("state-done");
    pill.textContent = elapsedSec != null
      ? `✓ 完成 · ${formatDuration(elapsedSec)}`
      : "✓ 完成";
  } else if (state === "failed") {
    pill.classList.add("state-failed");
    pill.textContent = "失败";
  } else if (state === "stalled") {
    pill.classList.add("state-stalled");
    pill.textContent = "似乎卡住了…";
  }
}

function formatDuration(sec) {
  sec = Math.max(0, Math.floor(sec));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m${s.toString().padStart(2, "0")}s`;
}

function bumpAgentHeartbeat() {
  agentLastEventTime = Date.now();
}

function startAgentHeartbeat() {
  stopAgentHeartbeat();
  agentHeartbeatStart = Date.now();
  agentLastEventTime = Date.now();
  setAgentStatus("running", 0);
  agentHeartbeatTimer = setInterval(() => {
    const elapsed = (Date.now() - agentHeartbeatStart) / 1000;
    const sinceLastEvent = (Date.now() - agentLastEventTime) / 1000;
    if (agentPaused) {
      setAgentStatus("paused", null);
    } else if (sinceLastEvent > 30) {
      setAgentStatus("stalled", elapsed);
    } else {
      setAgentStatus("running", elapsed);
    }
  }, 1000);
}

function stopAgentHeartbeat() {
  if (agentHeartbeatTimer) {
    clearInterval(agentHeartbeatTimer);
    agentHeartbeatTimer = null;
  }
}

// ---- D2: tool card grouping ----

// Track the last tool-name we rendered, to fold consecutive same-tool calls.
let lastToolName = null;
let lastToolGroupCard = null;     // collapsed group card for repeats
let lastToolGroupCount = 0;

function resetToolGrouping() {
  lastToolName = null;
  lastToolGroupCard = null;
  lastToolGroupCount = 0;
}

// I2: Subtask section management.
// Each subtask gets a header (with status icon) + a body container that
// holds its tool cards. currentSubtaskBody is where v2AppendCard routes cards.
let currentSubtaskBody = null;
let currentSubtaskHeader = null;
let currentSubtaskToolCount = 0;

function openSubtaskSection(id, title, index, total) {
  resetToolGrouping();
  const stream = document.getElementById("agentStream");
  if (!stream) return;

  // Close any previously open section
  currentSubtaskBody = null;

  // Header with status icon + title + tool counter
  const header = document.createElement("div");
  header.className = "agent-subtask-header status-running";
  header.dataset.id = id;
  const indexLabel = total ? `<span class="agent-subtask-index">${index || ""}/${total}</span>` : "";
  header.innerHTML = `
    <span class="agent-subtask-status-icon">○</span>
    ${indexLabel}
    <span class="agent-subtask-title">${agentEsc(title)}</span>
    <span class="agent-subtask-tool-count"></span>
  `;
  stream.appendChild(header);

  // Body container for this subtask's cards
  const body = document.createElement("div");
  body.className = "agent-subtask-body";
  stream.appendChild(body);

  currentSubtaskHeader = header;
  currentSubtaskBody = body;
  currentSubtaskToolCount = 0;

  if (agentAutoScroll) {
    const mainCol = document.getElementById("agentMainCol");
    if (mainCol) mainCol.scrollTop = mainCol.scrollHeight;
  }
}

function bumpSubtaskToolCount() {
  if (!currentSubtaskHeader) return;
  currentSubtaskToolCount += 1;
  const el = currentSubtaskHeader.querySelector(".agent-subtask-tool-count");
  if (el) el.textContent = `${currentSubtaskToolCount} 个工具`;
}

function closeSubtaskSection(id, status, summary) {
  if (!currentSubtaskHeader) return;
  // Map backend status to display
  const statusMap = {
    success: { cls: "status-done", icon: "✓" },
    done: { cls: "status-done", icon: "✓" },
    partial: { cls: "status-partial", icon: "△" },
    failed: { cls: "status-failed", icon: "✗" },
  };
  const s = statusMap[status] || statusMap.done;
  currentSubtaskHeader.classList.remove("status-running");
  currentSubtaskHeader.classList.add(s.cls);
  const iconEl = currentSubtaskHeader.querySelector(".agent-subtask-status-icon");
  if (iconEl) iconEl.textContent = s.icon;

  // If there's a summary, add a result card at the end of the section body
  if (summary && currentSubtaskBody) {
    const card = document.createElement("div");
    card.className = "agent-card agent-card-enter agent-subtask-summary";
    card.innerHTML = `
      <div class="agent-card-header">
        <span class="agent-card-icon success">●</span>
        <span class="agent-card-title">✓ 结果摘要</span>
      </div>
      <div class="agent-card-body"><div>${summary}</div></div>
    `;
    currentSubtaskBody.appendChild(card);
    setTimeout(() => card.classList.remove("agent-card-enter"), 250);
  }

  // Close this section so subsequent cards go to the stream root
  currentSubtaskBody = null;
  currentSubtaskHeader = null;

  if (agentAutoScroll) {
    const mainCol = document.getElementById("agentMainCol");
    if (mainCol) mainCol.scrollTop = mainCol.scrollHeight;
  }
}

// Render a tool_call card (default collapsed), folding consecutive same-tool calls.
function appendToolCallCard(toolName, argsStr) {
  bumpSubtaskToolCount();
  if (toolName === lastToolName && lastToolGroupCard) {
    // Increment count in existing group card
    lastToolGroupCount += 1;
    updateToolGroupCardMeta();
    // Stash detail as a hidden row inside the group body
    appendToolGroupDetail(`🔧 ${toolName}`, argsStr);
    return;
  }
  // New tool (or no group yet): start fresh — default collapsed (I1)
  lastToolName = toolName;
  lastToolGroupCount = 1;
  const card = v2AppendCard("tool", `🔧 ${toolName}`, null, argsStr, true);
  lastToolGroupCard = card;
  // Prepare a hidden body container for folded details
  const body = document.createElement("div");
  body.className = "agent-tool-group-body hidden";
  card.appendChild(body);
  // Click header to toggle the group body
  const header = card.querySelector(".agent-card-header");
  if (header) {
    header.classList.add("clickable");
    header.addEventListener("click", () => body.classList.toggle("hidden"));
  }
}

function appendToolGroupDetail(title, meta) {
  if (!lastToolGroupCard) return;
  const body = lastToolGroupCard.querySelector(".agent-tool-group-body");
  if (!body) return;
  const row = document.createElement("div");
  row.className = "agent-tool-group-row";
  row.textContent = `${title}  ·  ${meta}`;
  body.appendChild(row);
}

function updateToolGroupCardMeta() {
  if (!lastToolGroupCard) return;
  const metaEl = lastToolGroupCard.querySelector(".agent-card-meta");
  if (metaEl) metaEl.textContent = `× ${lastToolGroupCount} 次`;
}

// Render a tool_result: attach to current group body (I1 — no separate card).
function appendToolResultCard(toolName, result) {
  // If this result matches the current tool group, fold it in.
  if (toolName === lastToolName && lastToolGroupCard) {
    appendToolGroupDetail(`✓ ${toolName}`, agentTrunc(result, 80));
    return;
  }
  // Standalone result (no matching tool group) — collapsible card, default collapsed.
  const card = v2AppendCard(
    "success",
    `✓ ${toolName}`,
    `<div>${agentTrunc(result, 600)}</div>`,
    `${result.length} 字符`,
    true
  );
  if (card) {
    const header = card.querySelector(".agent-card-header");
    if (header) {
      header.classList.add("clickable");
      header.addEventListener("click", () => card.classList.toggle("collapsed"));
    }
  }
}

// ---- file tree refresh helper ----

function refreshFileTree() {
  fetch("/api/reindex", { method: "POST" })
    .then(r => r.json().catch(() => ({})))
    .then(d => {
      if (d.file_count !== undefined) {
        if (typeof fileCount !== "undefined" && fileCount) fileCount.textContent = String(d.file_count);
        if (typeof embeddingMode !== "undefined" && embeddingMode) {
          embeddingMode.textContent = d.embedding_mode === "onnx" ? "ONNX 语义" : "BM25";
        }
        try {
          const treeData = typeof d.tree === "string" ? JSON.parse(d.tree) : d.tree;
          if (typeof updateTreeView === "function") updateTreeView(treeData);
        } catch (e) {}
      }
    })
    .catch(() => {});
}

/* ======================================================================
   E1-E3: Task history panel
   Loads /api/agent/tasks and renders clickable history items in the
   side column. Click an item to view its result; delete button to remove.
   ====================================================================== */

// Format a unix timestamp (seconds) into a relative-time string.
function formatRelativeTime(ts) {
  if (!ts) return "";
  const now = Date.now() / 1000;
  const diff = Math.max(0, now - ts);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

const AGENT_STATUS_LABELS = {
  pending: "等待",
  running: "运行中",
  paused: "暂停",
  stopped: "已停止",
  completed: "完成",
  failed: "失败",
};

function statusToClass(status) {
  const map = {
    completed: "done",
    running: "running",
    paused: "paused",
    stopped: "failed",
    failed: "failed",
    pending: "pending",
  };
  return map[status] || "pending";
}

// Render the history list from a tasks array.
function renderAgentHistory(tasks) {
  const list = document.getElementById("agentHistoryList");
  if (!list) return;
  if (!tasks || tasks.length === 0) {
    list.innerHTML = '<div class="agent-history-empty">暂无历史任务</div>';
    return;
  }
  // Newest first
  const sorted = [...tasks].sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
  list.innerHTML = "";
  sorted.forEach(t => {
    const item = document.createElement("div");
    item.className = "agent-history-item";
    item.dataset.taskId = t.task_id;
    const statusLabel = AGENT_STATUS_LABELS[t.status] || t.status;
    const statusCls = statusToClass(t.status);
    const preview = t.result_preview ? agentEsc(t.result_preview) : "";
    item.innerHTML = `
      <div class="agent-history-item-main">
        <div class="agent-history-item-query">${agentEsc(t.user_query || "(无描述)")}</div>
        <div class="agent-history-item-meta">
          <span class="subtask-status ${statusCls}">${statusLabel}</span>
          <span class="agent-history-item-time">${formatRelativeTime(t.created_at)}</span>
          ${t.step_count ? `<span class="agent-history-item-steps">${t.step_count} 步</span>` : ""}
        </div>
        ${preview ? `<div class="agent-history-item-preview">${preview}</div>` : ""}
      </div>
      <button class="agent-history-item-del icon-btn" title="删除">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
        </svg>
      </button>
    `;
    // Click main area → view result
    item.querySelector(".agent-history-item-main").addEventListener("click", () => {
      viewTaskResult(t.task_id);
    });
    // Click delete button → remove
    const delBtn = item.querySelector(".agent-history-item-del");
    if (delBtn) {
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteTaskFromHistory(t.task_id);
      });
    }
    list.appendChild(item);
  });
}

// Fetch a task's full result and render it into #agentOutput.
async function viewTaskResult(taskId) {
  try {
    const resp = await fetch(`/api/agent/status/${taskId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const resultText = data.result || "\u6682\u65e0\u7ed3\u679c\u3002";
    renderAgentFinalResult(resultText, { collapseStream: false });
    // Highlight the selected history item
    document.querySelectorAll(".agent-history-item").forEach(el => el.classList.remove("selected"));
    const sel = document.querySelector(`.agent-history-item[data-task-id="${taskId}"]`);
    if (sel) sel.classList.add("selected");
  } catch (e) {
    console.error("viewTaskResult failed:", e);
  }
}

// Delete a task from history (backend + UI).
async function deleteTaskFromHistory(taskId) {
  try {
    const resp = await fetch(`/api/agent/tasks/${taskId}`, { method: "DELETE" });
    if (resp.ok) {
      loadAgentHistory();
    }
  } catch (e) {
    console.error("deleteTaskFromHistory failed:", e);
  }
}

// Load history from backend and render.
function loadAgentHistory() {
  fetch("/api/agent/tasks")
    .then(r => r.json().catch(() => ({ tasks: [] })))
    .then(d => renderAgentHistory(d.tasks || []))
    .catch(() => {});
}

// Wire up the refresh button (E3).
(function initHistoryRefresh() {
  const btn = document.getElementById("agentHistoryRefreshBtn");
  if (btn) {
    btn.addEventListener("click", () => loadAgentHistory());
  }
})();

/* ======================================================================
   H1/H2: Thinking expand toggle + Fullscreen overlay
   ====================================================================== */

// H1: Toggle the thinking block between normal (60vh) and expanded (85vh).
// Also ensures the block is visible (removes 'collapsed') when expanding.
(function initThinkingExpand() {
  const btn = document.getElementById("thinkingExpandBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const block = document.getElementById("agentThinking");
    if (!block) return;
    // Ensure block is visible before expanding
    const wasCollapsed = block.classList.contains("collapsed");
    if (wasCollapsed) {
      block.classList.remove("collapsed");
    }
    block.classList.toggle("expanded");
    const isExpanded = block.classList.contains("expanded");
    btn.title = isExpanded ? "恢复默认大小" : "放大查看";
    // Update icon: maximize ↔ minimize
    btn.innerHTML = isExpanded
      ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 14h6v6"/><path d="M20 10h-6V4"/><path d="M14 10l7-7"/><path d="M3 21l7-7"/></svg>'
      : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/></svg>';
  });
})();

// H2: Fullscreen overlay — shows report or thinking content in a full-panel view.
function openAgentFullscreen(title, bodyHtml, bodyClass) {
  const overlay = document.getElementById("agentFullscreenOverlay");
  const titleEl = document.getElementById("agentFullscreenTitle");
  const bodyEl = document.getElementById("agentFullscreenBody");
  if (!overlay || !bodyEl) return;
  if (titleEl) titleEl.textContent = title;
  bodyEl.className = "agent-fullscreen-body" + (bodyClass ? " " + bodyClass : "");
  bodyEl.innerHTML = bodyHtml;
  overlay.classList.remove("hidden");
  bodyEl.scrollTop = 0;
}

function closeAgentFullscreen() {
  const overlay = document.getElementById("agentFullscreenOverlay");
  if (overlay) overlay.classList.add("hidden");
}

(function initFullscreenControls() {
  // Report fullscreen button
  const reportBtn = document.getElementById("outputFullscreenBtn");
  if (reportBtn) {
    reportBtn.addEventListener("click", () => {
      const content = document.getElementById("agentOutputContent");
      if (!content) return;
      openAgentFullscreen("\u6700\u7ec8\u62a5\u544a", content.innerHTML, "markdown");
    });
  }
  // Close button
  const closeBtn = document.getElementById("agentFullscreenCloseBtn");
  if (closeBtn) {
    closeBtn.addEventListener("click", closeAgentFullscreen);
  }
  // Esc to close fullscreen (only when overlay is visible)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const overlay = document.getElementById("agentFullscreenOverlay");
      if (overlay && !overlay.classList.contains("hidden")) {
        e.preventDefault();
        e.stopPropagation();
        closeAgentFullscreen();
      }
    }
  });
})();
