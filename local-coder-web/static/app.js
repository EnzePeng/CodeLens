/* ─── DOM refs ────────────────────────────────────────────────── */
const folderInput   = document.querySelector("#folderInput");
const folderPicker  = document.querySelector("#folderPicker");
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
const craftPanel    = document.querySelector("#craftPanel");
const craftFile     = document.querySelector("#craftFile");
const craftCode     = document.querySelector("#craftCode");
const applyBtn      = document.querySelector("#applyBtn");
const modeTabs      = document.querySelectorAll(".mode-tab");
const workspace     = document.querySelector(".workspace");

/* ─── State ───────────────────────────────────────────────────── */
let isBusy = false;
let currentMode = "ask";   // ask | plan | craft

/* ─── Busy control ────────────────────────────────────────────── */
function setBusy(busy) {
  isBusy = busy;
  setFolderBtn.disabled = busy;
  askBtn.disabled = busy || !folderStatus.dataset.ready;
  questionInput.disabled = busy || !folderStatus.dataset.ready;
  craftFile.disabled = busy || !folderStatus.dataset.ready;
  craftCode.disabled = busy || !folderStatus.dataset.ready;
  applyBtn.disabled  = busy || !folderStatus.dataset.ready;
}

/* ─── Mode switching ──────────────────────────────────────────── */
modeTabs.forEach(tab => {
  tab.addEventListener("click", () => {
    const mode = tab.dataset.mode;
    if (mode === currentMode) return;
    currentMode = mode;
    modeTabs.forEach(t => t.classList.toggle("active", t === tab));
    workspace.className = `workspace ${mode}-mode`;
    // Show/hide craft panel
    craftPanel.classList.toggle("hidden", mode !== "craft");
    // Update placeholder
    const hints = {
      ask:   "输入你的代码问题… (Enter 发送 / Shift+Enter 换行)",
      plan:  "描述你需要规划的功能或架构… (Enter 发送)",
      craft: "描述你要做的代码修改… (Enter 发送，下方填代码)",
    };
    questionInput.placeholder = hints[mode] || hints.ask;
  });
});

/* ─── HTML escaping ───────────────────────────────────────────── */
function escapeHtml(v) {
  return v
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* ─── Markdown renderer (improved) ────────────────────────────── */
function renderMarkdown(md) {
  if (!md) return "";

  // Phase 1: Extract and protect code blocks
  const codeBlocks = [];
  let text = md.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push({ lang: lang || "", code: code.trimEnd() });
    return `\n%%CB${idx}%%\n`;
  });

  // Phase 2: Extract and protect inline code
  const inlineCodes = [];
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    const idx = inlineCodes.length;
    inlineCodes.push(code);
    return `%%IC${idx}%%`;
  });

  // Phase 3: Line-by-line block parsing
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
    // Code block placeholder
    const cbMatch = line.match(/^%%CB(\d+)%%$/);
    if (cbMatch) {
      flushParagraph(); flushList();
      const b = codeBlocks[Number(cbMatch[1])];
      const langLabel = b.lang ? `<span>${escapeHtml(b.lang)}</span>` : "";
      blocks.push(`<pre class="code-block">${langLabel}<code>${escapeHtml(b.code)}</code></pre>`);
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim()) || /^\*\*\*+$/.test(line.trim())) {
      flushParagraph(); flushList();
      blocks.push("<hr>");
      continue;
    }

    // Blank line
    if (!line.trim()) { flushParagraph(); flushList(); continue; }

    // Heading
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph(); flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    // Blockquote
    const bq = line.match(/^>\s?(.*)$/);
    if (bq) {
      flushParagraph(); flushList();
      blocks.push(`<blockquote><p>${renderInline(bq[1])}</p></blockquote>`);
      continue;
    }

    // Table row
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      flushParagraph(); flushList();
      const cells = line.split("|").filter(c => c.trim() !== "");
      if (cells.every(c => /^[-:\s]+$/.test(c))) continue; // separator
      const isHeader = blocks.length > 0 && blocks[blocks.length - 1].startsWith("<table");
      if (!isHeader) {
        blocks.push(`<table><thead><tr>${cells.map(c => `<th>${renderInline(c.trim())}</th>`).join("")}</tr></thead><tbody>`);
      } else {
        blocks[blocks.length - 1] = blocks[blocks.length - 1].replace("</tbody>", "");
        blocks.push(`<tr>${cells.map(c => `<td>${renderInline(c.trim())}</td>`).join("")}</tr></tbody></table>`);
      }
      continue;
    }

    // Ordered list
    const olItem = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (olItem) {
      flushParagraph();
      if (!listOrdered && listItems.length) flushList();
      listOrdered = true;
      listItems.push(olItem[1]);
      continue;
    }

    // Unordered list
    const ulItem = line.match(/^\s*[-*+]\s+(.+)$/);
    if (ulItem) {
      flushParagraph();
      if (listOrdered && listItems.length) flushList();
      listOrdered = false;
      listItems.push(ulItem[1]);
      continue;
    }

    // Regular text
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph(); flushList();

  // Phase 4: Restore inline code
  let html = blocks.join("\n");
  html = html.replace(/%%IC(\d+)%%/g, (_, idx) => {
    return `<code>${escapeHtml(inlineCodes[Number(idx)])}</code>`;
  });

  return html;
}

/* ─── Inline markdown ─────────────────────────────────────────── */
function renderInline(text) {
  let html = escapeHtml(text);
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Italic
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  // Inline code (already extracted, skip)
  // Links
  html = html.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer">$1</a>'
  );
  // kbd
  html = html.replace(/&lt;([^&]+)&gt;/g, "<kbd>$1</kbd>");
  return html;
}

/* ─── Add a user message bubble ──────────────────────────────── */
function addUserMessage(text) {
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

/* ─── Add a simple assistant info message ─────────────────────── */
function addInfoMessage(text) {
  const article = document.createElement("article");
  article.className = "message assistant";
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

  // Thinking panel
  const thinkingPanel = document.createElement("details");
  thinkingPanel.className = "thinking live";
  thinkingPanel.open = true;
  const thinkingSummary = document.createElement("summary");
  thinkingSummary.textContent = "思考中…";
  const thinkingPre = document.createElement("pre");
  thinkingPanel.append(thinkingSummary, thinkingPre);

  // Main answer area
  const contentEl = document.createElement("div");
  contentEl.className = "content markdown";

  // Sources footer
  const sourcesEl = document.createElement("div");
  sourcesEl.className = "sources hidden";

  // Cursor
  const cursor = document.createElement("span");
  cursor.className = "stream-cursor";
  cursor.textContent = "▋";

  article.append(header, thinkingPanel, contentEl, cursor, sourcesEl);
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;

  return { article, speedBadge, thinkingPanel, thinkingSummary, thinkingPre, contentEl, sourcesEl, cursor };
}

/* ─── Streaming ask ───────────────────────────────────────────── */
async function streamAsk(question) {
  setBusy(true);
  askBtn.textContent = "…";

  const bubble = createStreamingBubble();
  let rawBuffer = "";

  // Build request body with mode
  const body = { question, mode: currentMode };
  // Craft mode: include file + code if provided
  if (currentMode === "craft" && craftFile.value.trim()) {
    body.file_path = craftFile.value.trim();
    body.new_content = craftCode.value;
  }

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
    askBtn.textContent = "发送";
    setBusy(false);
    questionInput.focus();
  }
}

/* ─── Process raw stream buffer into thinking / answer ───────── */
function _processRawBuffer(raw, bubble) {
  let thinkingText = "";
  let answerText = "";

  // Qwen3-style: hle...hle
  const tStart = raw.indexOf("<think>");
  const tEnd = raw.indexOf("</think>");

  if (tStart !== -1 && tEnd !== -1) {
    // Both tags present - extract thinking, answer is after close tag
    thinkingText = raw.slice(tStart + 7, tEnd);
    answerText = (raw.slice(0, tStart) + raw.slice(tEnd + 8)).trim();
  } else if (tStart !== -1) {
    // Only open tag - model still thinking
    thinkingText = raw.slice(tStart + 7);
    answerText = raw.slice(0, tStart);
  } else {
    answerText = raw;
  }

  // Update thinking panel
  if (thinkingText.trim()) {
    bubble.thinkingPanel.classList.remove("hidden");
    bubble.thinkingPre.textContent = thinkingText;
  } else {
    bubble.thinkingPanel.classList.add("hidden");
  }

  // Update answer as plain text during stream for performance
  bubble.contentEl.textContent = answerText;
}


/* ─── Final render after stream complete ─────────────────────── */
function _finalRender(evt, bubble) {
  bubble.cursor.remove();
  bubble.article.classList.remove("streaming");

  if (evt.thinking?.trim()) {
    bubble.thinkingPanel.classList.remove("hidden");
    bubble.thinkingPanel.open = false;
    bubble.thinkingSummary.textContent = "查看 thinking";
    bubble.thinkingPre.textContent = evt.thinking;
  } else {
    bubble.thinkingPanel.remove();
  }

  // Final answer with full markdown
  bubble.contentEl.innerHTML = renderMarkdown(evt.answer || "");

  if (evt.metrics?.tokens_per_second) {
    bubble.speedBadge.textContent = `${evt.metrics.tokens_per_second} tok/s`;
    bubble.speedBadge.title = `${evt.metrics.completion_tokens || 0} tokens in ${evt.metrics.elapsed_seconds || 0}s`;
    bubble.speedBadge.classList.remove("hidden");
  }

  // If craft mode and response contains file info, auto-fill craft panel
  if (currentMode === "craft" && evt.craft_result) {
    addInfoMessage(`文件 ${evt.craft_result.path} 已修改 (${evt.craft_result.bytes_written} bytes)`);
  }
}

/* ─── Folder browser ──────────────────────────────────────────── */
browseBtn.addEventListener("click", () => {
  folderPicker.click();
});

folderPicker.addEventListener("change", () => {
  const files = folderPicker.files;
  if (files.length === 0) return;
  // webkitdirectory gives us full path in webkitRelativePath
  // Extract root folder from first file
  const firstPath = files[0].webkitRelativePath || "";
  const rootFolder = firstPath.split("/")[0];
  // We can't get absolute path from File API for security reasons
  // Show a hint to user
  folderInput.value = rootFolder || "(选择完成，请输入完整路径)";
  folderInput.removeAttribute("readonly");
  folderInput.focus();
  folderInput.select();
});

// Also allow manual path input
folderInput.addEventListener("focus", () => {
  folderInput.removeAttribute("readonly");
});
folderInput.addEventListener("blur", () => {
  folderInput.setAttribute("readonly", "");
});

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
    treeView.textContent = data.tree;
    questionInput.disabled = false;
    askBtn.disabled = false;
    addInfoMessage(
      `已索引 ${data.file_count} 个文件，搜索模式：${data.embedding_mode === "onnx" ? "ONNX 语义搜索" : "BM25 增强搜索"}。`
    );
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

/* ─── Craft: Apply code change ────────────────────────────────── */
applyBtn.addEventListener("click", async () => {
  const filePath = craftFile.value.trim();
  const content = craftCode.value;
  if (!filePath || !content) {
    addInfoMessage("请填写文件路径和代码内容。");
    return;
  }
  setBusy(true);
  applyBtn.textContent = "应用中…";
  try {
    const resp = await fetch("/api/craft-apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: filePath, content }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    addInfoMessage(`✅ 已写入 ${data.path} (${data.bytes_written} bytes)`);
    craftCode.value = "";
  } catch (err) {
    addInfoMessage(`写入失败：${err.message}`);
  } finally {
    applyBtn.textContent = "应用修改";
    setBusy(false);
  }
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
      treeView.textContent = data.tree;
      questionInput.disabled = false;
      askBtn.disabled = false;
    }
  })
  .catch(() => {});