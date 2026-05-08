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

// File viewer
const fileOverlay     = document.querySelector("#fileOverlay");
const fileViewerTitle = document.querySelector("#fileViewerTitle");
const fileViewerMeta  = document.querySelector("#fileViewerMeta");
const fileCloseBtn    = document.querySelector("#fileCloseBtn");
const codeBody        = document.querySelector("#codeBody");

// Terminal
const toggleTerminalBtn = document.querySelector("#toggleTerminalBtn");
const terminalPanel     = document.querySelector("#terminalPanel");
const closeTerminalBtn  = document.querySelector("#closeTerminalBtn");
const terminalContainer = document.querySelector("#terminalContainer");
const workspaceContent  = document.querySelector(".workspace-content");

// Editor / Tabs
const tabList           = document.querySelector("#tabList");
const editorArea        = document.querySelector("#editorArea");
const editorContainer   = document.querySelector("#editorContainer");
const newFileTabBtn     = document.querySelector("#newFileTabBtn");
const messagesArea      = document.querySelector("#messages");

/* ─── State ───────────────────────────────────────────────────── */
let isBusy = false;
let currentMode = "ask";
let messageHistory = [];
let currentTreeData = null;  // Store tree JSON for re-rendering

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
  setFolderBtn.disabled = busy;
  askBtn.disabled = busy || !folderStatus.dataset.ready;
  questionInput.disabled = busy || !folderStatus.dataset.ready;
  if (clearBtn) clearBtn.disabled = busy;
}

/* ─── Mode switching (composer dropdown) ──────────────────────── */
modeSelect.addEventListener("change", () => {
  currentMode = modeSelect.value;
  workspace.className = `workspace ${currentMode}-mode`;
  const hints = {
    ask:   "输入你的代码问题… (Enter 发送 / Shift+Enter 换行)",
    plan:  "描述你需要规划的功能或架构… (Enter 发送)",
    craft: "描述你要做的代码修改，我将生成完整文件… (Enter 发送)",
  };
  questionInput.placeholder = hints[currentMode] || hints.ask;
  const btnLabels = { ask: "发送", plan: "规划", craft: "编辑" };
  askBtn.textContent = btnLabels[currentMode] || "发送";
});

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
  contextUsed.textContent = used.toLocaleString();
  contextTotal.textContent = totalChars.toLocaleString();
  const percent = totalChars > 0 ? Math.min((used / totalChars) * 100, 100) : 0;
  contextBarUsed.style.width = percent + "%";
  
  // Color based on usage
  if (percent > 85) {
    contextBarUsed.style.background = "#e8a8a8";
  } else if (percent > 60) {
    contextBarUsed.style.background = "#e8c88a";
  } else {
    contextBarUsed.style.background = "var(--accent)";
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
    messageHistory = [];
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
        openFileViewer(child.path, child.name, child.size);
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

/* ─── File viewer ─────────────────────────────────────────────── */
async function openFileViewer(filePath, fileName, fileSize) {
  fileOverlay.classList.remove("hidden");
  fileViewerTitle.textContent = fileName || filePath;
  fileViewerMeta.textContent = "加载中…";
  codeBody.innerHTML = "";

  try {
    const resp = await fetch("/api/read-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: filePath }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);

    fileViewerTitle.textContent = data.path;
    const sizeStr = data.size > 1024 ? `${(data.size / 1024).toFixed(1)} KB` : `${data.size} B`;
    const lineCount = data.content.split("\n").length;
    fileViewerMeta.textContent = `${sizeStr} · ${lineCount} 行 · ${data.ext || "未知类型"}`;

    renderCodeTable(data.content, data.ext);
  } catch (err) {
    fileViewerMeta.textContent = "";
    codeBody.innerHTML = `<tr><td class="line-num"></td><td class="code-line error-line">加载失败：${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderCodeTable(content, ext) {
  codeBody.innerHTML = "";

  const lang = EXT_TO_LANG[ext] || "";
  const lines = content.split("\n");

  // Try highlight.js if available
  let highlighted = null;
  if (lang && typeof hljs !== "undefined" && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(content, { language: lang }).value;
    } catch {}
  }

  if (highlighted) {
    // Split highlighted HTML by newlines to create line-by-line table
    const hlLines = highlighted.split("\n");
    for (let i = 0; i < hlLines.length; i++) {
      const tr = document.createElement("tr");
      const tdNum = document.createElement("td");
      tdNum.className = "line-num";
      tdNum.textContent = i + 1;
      const tdCode = document.createElement("td");
      tdCode.className = "code-line hljs";
      tdCode.innerHTML = hlLines[i] || " ";
      tr.append(tdNum, tdCode);
      codeBody.appendChild(tr);
    }
  } else {
    // Fallback: plain text with line numbers
    for (let i = 0; i < lines.length; i++) {
      const tr = document.createElement("tr");
      const tdNum = document.createElement("td");
      tdNum.className = "line-num";
      tdNum.textContent = i + 1;
      const tdCode = document.createElement("td");
      tdCode.className = "code-line";
      tdCode.textContent = lines[i] || " ";
      tr.append(tdNum, tdCode);
      codeBody.appendChild(tr);
    }
  }
}

fileCloseBtn.addEventListener("click", () => {
  fileOverlay.classList.add("hidden");
});

fileOverlay.addEventListener("click", (e) => {
  if (e.target === fileOverlay) fileOverlay.classList.add("hidden");
});

// Escape key closes file viewer
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!fileOverlay.classList.contains("hidden")) {
      fileOverlay.classList.add("hidden");
    } else if (!dirOverlay.classList.contains("hidden")) {
      dirOverlay.classList.add("hidden");
    }
  }
});

/* ─── Add a user message bubble ──────────────────────────────── */
function addUserMessage(text) {
  messageHistory.push({ role: "user", mode: currentMode, content: text, timestamp: Date.now() });

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
  header.append(roleEl, modeTag);
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
    const btnLabels = { ask: "发送", plan: "规划", craft: "编辑" };
    askBtn.textContent = btnLabels[currentMode] || "发送";
    setBusy(false);
    questionInput.focus();
    // Reset context display after request completes
    setTimeout(() => updateContextDisplay(0, modelSettings.contextLimit), 1500);
  }
}

/* ─── Process raw stream buffer into thinking / answer ───────── */
function _processRawBuffer(raw, bubble) {
  let thinkingText = "";
  let answerText = "";

  let tStart = -1;
  let tEnd = -1;
  for (let i = 0; i < raw.length - 1; i++) {
    if (raw.charCodeAt(i) === 0x0925 && raw.charCodeAt(i + 1) === 0x0947 && tStart === -1) {
      tStart = i;
    }
    if (raw.charCodeAt(i) === 0x0935 && raw.charCodeAt(i + 1) === 0x0947 && tEnd === -1 && tStart !== -1) {
      tEnd = i;
    }
  }

  if (tStart !== -1 && tEnd !== -1) {
    thinkingText = raw.slice(tStart + 2, tEnd);
    answerText = (raw.slice(0, tStart) + raw.slice(tEnd + 2)).trim();
  } else if (tStart !== -1) {
    thinkingText = raw.slice(tStart + 2);
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

  bubble.contentEl.textContent = answerText;
}

/* ─── Final render after stream complete ─────────────────────── */
function _finalRender(evt, bubble) {
  bubble.cursor.remove();
  bubble.article.classList.remove("streaming");

  const answerText = evt.answer || "";
  messageHistory.push({ role: "assistant", mode: currentMode, content: answerText, timestamp: Date.now() });

  if (evt.thinking?.trim()) {
    bubble.thinkingPanel.classList.remove("hidden");
    bubble.thinkingPanel.open = false;
    bubble.thinkingSummary.textContent = "查看 thinking";
    bubble.thinkingPre.textContent = evt.thinking;
  } else {
    bubble.thinkingPanel.remove();
  }

  bubble.contentEl.innerHTML = renderMarkdown(evt.answer || "");

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
        updateTreeView(data.tree);
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

browseBtn.addEventListener("click", () => {
  dirOverlay.classList.remove("hidden");
  const startPath = folderInput.value.trim() || "";
  loadDirListing(startPath || "");
});

dirCloseBtn.addEventListener("click", () => {
  dirOverlay.classList.add("hidden");
});

dirOverlay.addEventListener("click", (e) => {
  if (e.target === dirOverlay) dirOverlay.classList.add("hidden");
});

dirGoBtn.addEventListener("click", () => {
  const path = dirPathInput.value.trim();
  if (path) loadDirListing(path);
});

dirPathInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    const path = dirPathInput.value.trim();
    if (path) loadDirListing(path);
  }
});

dirSelectBtn.addEventListener("click", () => {
  if (currentDirPath) {
    folderInput.value = currentDirPath;
    dirOverlay.classList.add("hidden");
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
    dirList.innerHTML = `<div class="dir-error">加载失败：${escapeHtml(err.message)}</div>`;
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
setFolderBtn.addEventListener("click", async () => {
  const path = folderInput.value.trim();
  if (!path) { addInfoMessage("请先选择或输入代码文件夹路径。"); return; }

  setBusy(true);
  setFolderBtn.textContent = "索引中…";
  try {
    const resp = await fetch("/api/set-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);

    folderStatus.textContent = data.folder;
    folderStatus.dataset.ready = "1";
    fileCount.textContent = String(data.file_count);
    if (embeddingMode) embeddingMode.textContent = data.embedding_mode === "onnx" ? "ONNX 语义" : "BM25";
    updateTreeView(data.tree);
    questionInput.disabled = false;
    askBtn.disabled = false;
    addInfoMessage(`已索引 ${data.file_count} 个文件，搜索模式：${data.embedding_mode === "onnx" ? "ONNX 语义搜索" : "BM25 增强搜索"}。`);
  } catch (err) {
    addInfoMessage(`设置失败：${err.message}`);
  } finally {
    setFolderBtn.textContent = "加载代码库";
    setBusy(false);
  }
});

/* ─── Submit: Enter = send, Shift+Enter = newline ─────────────── */
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!isBusy && !questionInput.disabled) {
      askForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  }
});

askForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question || isBusy) return;
  questionInput.value = "";
  addUserMessage(question);
  await streamAsk(question);
});

/* ─── Init: restore folder state ──────────────────────────────── */
fetch("/api/status")
  .then(r => r.json())
  .then(data => {
    if (data.folder) {
      folderInput.value = data.folder;
      folderStatus.textContent = data.folder;
      folderStatus.dataset.ready = "1";
      fileCount.textContent = String(data.file_count);
      if (embeddingMode) embeddingMode.textContent = data.embedding_mode === "onnx" ? "ONNX 语义" : "BM25";
      updateTreeView(data.tree);
      questionInput.disabled = false;
      askBtn.disabled = false;
    }
  })
  .catch(() => {});

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
  
  // Welcome message
  term.writeln('\x1b[1;36m╔════════════════════════════════════════════════╗\x1b[0m');
  term.writeln('\x1b[1;36m║\x1b[0m  \x1b[1;33mLocal Coder Terminal\x1b[0m                         \x1b[1;36m║\x1b[0m');
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
      if (currentLine.trim()) {
        executeCommand(currentLine.trim());
      } else {
        term.write('\x1b[1;32m$\x1b[0m ');
      }
      currentLine = '';
    } else if (code === 127 || code === 8) { // Backspace
      if (currentLine.length > 0) {
        currentLine = currentLine.slice(0, -1);
        term.write('\b \b');
      }
    } else if (code === 3) { // Ctrl+C
      term.writeln('^C');
      term.write('\x1b[1;32m$\x1b[0m ');
      currentLine = '';
    } else if (code >= 32) { // Printable characters
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
  const originalCwd = currentCwd;
  
  // Convert Unix commands to Windows equivalents
  let windowsCmd = cmd;
  const isWindows = navigator.platform.toLowerCase().includes('win');
  
  if (isWindows) {
    // Common Unix -> Windows command conversions
    const cmdMap = [
      ['ls -la', 'dir /a'],
      ['ls -l', 'dir /l'],
      ['ls -F', 'dir /b'],
      ['ls', 'dir /b'],
      ['ll', 'dir /b'],
      ['la', 'dir /a'],
      ['pwd', 'cd'],
      ['clear', 'cls'],
      ['cat ', 'type '],
      ['rm -rf ', 'rmdir /s /q '],
      ['rm ', 'del /f '],
      ['mkdir ', 'mkdir '],
      ['touch ', 'echo. > '],
      ['which ', 'where '],
      ['grep ', 'findstr '],
      ['head -n', 'more +'],
      ['tail -n', 'for /f'],
    ];
    
    for (const [unix, win] of cmdMap) {
      if (cmd.startsWith(unix + ' ') || cmd === unix) {
        windowsCmd = cmd.replace(unix, win);
        break;
      }
    }
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
      
      // Update cwd if command was cd
      if (cmd.startsWith('cd ')) {
        const newPath = cmd.slice(3).trim();
        
        if (newPath === '-' && originalCwd) {
          // cd -: go to previous directory
          currentCwd = originalCwd;
        } else if (newPath === '~' || newPath === '') {
          // cd ~ or cd: go to home
          currentCwd = "";
        } else if (newPath.startsWith('/')) {
          // Absolute path
          currentCwd = newPath;
        } else if (newPath.match(/^[a-zA-Z]:/)) {
          // Windows drive letter
          currentCwd = newPath;
        } else {
          // Relative path
          currentCwd = currentCwd ? currentCwd + '/' + newPath : newPath;
        }
        
        // Show new directory
        term.writeln(`\x1b[36m📁 ${currentCwd || '~'}\x1b[0m`);
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
  // Remove existing editor
  const existingWrapper = editorContainer.querySelector(".CodeMirror-wrapper");
  if (existingWrapper) {
    existingWrapper.remove();
  }
  
  // Create wrapper
  const wrapper = document.createElement("div");
  wrapper.className = "CodeMirror-wrapper";
  wrapper.style.height = "100%";
  editorContainer.appendChild(wrapper);
  
  // Create textarea for CodeMirror
  const textarea = document.createElement("textarea");
  wrapper.appendChild(textarea);
  
  // Initialize CodeMirror
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
    },
  });
  
  codeMirrorEditor.setValue(content);
  
  // Handle changes
  codeMirrorEditor.on("change", () => {
    if (activeTabIndex >= 0 && openTabs[activeTabIndex]) {
      openTabs[activeTabIndex].content = codeMirrorEditor.getValue();
      openTabs[activeTabIndex].modified = true;
      updateTabUI();
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
  });
  
  switchToTab(openTabs.length - 1);
  
  // Show editor, hide welcome
  const welcome = editorContainer.querySelector(".editor-welcome");
  if (welcome) welcome.style.display = "none";
  
  // Adjust messages area
  messagesArea.classList.add("has-editor");
}

function switchToTab(index) {
  if (index < 0 || index >= openTabs.length) return;
  
  activeTabIndex = index;
  const tab = openTabs[index];
  
  // Initialize CodeMirror with tab content
  initCodeMirror(tab.content, tab.mode);
  
  // Update tab UI
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
    // No more tabs, show welcome
    const welcome = editorContainer.querySelector(".editor-welcome");
    if (welcome) welcome.style.display = "block";
    
    // Remove editor
    const wrapper = editorContainer.querySelector(".CodeMirror-wrapper");
    if (wrapper) wrapper.remove();
    codeMirrorEditor = null;
    
    messagesArea.classList.remove("has-editor");
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

// Override file viewer click to open in editor
const originalOpenFileViewer = openFileViewer;
window.openFileViewer = async function(filePath, fileName, fileSize) {
  // Load file content first
  try {
    const resp = await fetch("/api/read-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: filePath }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    
    // Open in tab instead of viewer
    openFileInTab(filePath, data.path || fileName, data.content || "");
    
  } catch (err) {
    addInfoMessage(`❌ 打开文件失败: ${err.message}`);
  }
};

// New file tab button
if (newFileTabBtn) {
  newFileTabBtn.addEventListener("click", () => {
    const fileName = prompt("请输入新文件名:", "untitled.py");
    if (!fileName) return;
    
    openFileInTab(fileName, fileName, "# 新文件\n");
  });
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

// Handle Tab key to accept completion
const originalInitCodeMirror = initCodeMirror;
window.initCodeMirror = function(content = "", mode = "text") {
  const editor = originalInitCodeMirror(content, mode);
  
  // Add Tab handler for completion
  editor.addKeyMap({
    "Tab": function(cm) {
      if (completions.length > 0 && selectedCompletionIndex >= 0) {
        applyCompletion(selectedCompletionIndex);
        return;
      }
      // Default: insert tab
      cm.replaceSelection("  ", "end");
    },
    "Escape": function(cm) {
      hideCompletionPanel();
    },
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
  });
  
  return editor;
};
