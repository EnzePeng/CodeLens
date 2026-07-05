(function () {
  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderEvidence(evidence) {
    const list = $("evidenceList");
    if (!list) return;
    if (!evidence || evidence.length === 0) {
      list.innerHTML = '<div class="empty-state compact">暂无证据来源。</div>';
      return;
    }
    list.innerHTML = evidence.slice(0, 30).map((item) => `
      <button class="evidence-item" data-path="${esc(item.path)}">
        <span class="evidence-path">${esc(item.path)}:${esc(item.start_line || 1)}</span>
        <span class="evidence-reason">${esc(item.reason || item.symbol || "evidence")}</span>
      </button>
    `).join("");
    list.querySelectorAll(".evidence-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const path = btn.getAttribute("data-path");
        if (path && typeof window.openFileViewer === "function") {
          window.openFileViewer(path, path.split(/[\\/]/).pop() || path, "");
        }
      });
    });
  }

  function card(title, body) {
    return `<section class="overview-card"><h3>${esc(title)}</h3>${body}</section>`;
  }

  function renderProjectBrief(brief) {
    const container = $("overviewContent");
    if (!container) return;
    const modules = (brief.modules || []).map((m) => `
      <li><strong>${esc(m.path)}</strong><span>${esc(m.role || "")}</span><em>${esc(m.file_count || 0)} files</em></li>
    `).join("");
    const entrypoints = (brief.entrypoints || []).map((e) => `
      <li><button class="linkish" data-path="${esc(e.path)}">${esc(e.path)}</button><span>${esc(e.reason || "")}</span></li>
    `).join("");
    const flows = (brief.flows || []).map((f) => `
      <li><strong>${esc(f.from)}</strong><span>${esc((f.to || []).join(", "))}</span></li>
    `).join("");
    const risks = (brief.risks || []).map((r) => `
      <li><strong>${esc(r.title)}</strong><span>${esc(r.path || "")}</span><em>${esc(r.severity || "low")}</em></li>
    `).join("");
    const readNext = (brief.read_next || []).map((r) => `
      <li><button class="linkish" data-path="${esc(r.path)}">${esc(r.path)}</button><span>${esc(r.reason || "")}</span></li>
    `).join("");

    container.innerHTML = [
      card("Overview", `<p>${esc(brief.overview || "暂无概览。")}</p>`),
      card("Modules", `<ul class="overview-list">${modules || "<li>暂无模块。</li>"}</ul>`),
      card("Entrypoints", `<ul class="overview-list">${entrypoints || "<li>暂无入口点。</li>"}</ul>`),
      card("Flows", `<ul class="overview-list">${flows || "<li>暂无导入流。</li>"}</ul>`),
      card("Risks", `<ul class="overview-list">${risks || "<li>暂无明显风险。</li>"}</ul>`),
      card("Read Next", `<ul class="overview-list">${readNext || "<li>暂无推荐。</li>"}</ul>`),
    ].join("");
    container.querySelectorAll("[data-path]").forEach((btn) => {
      btn.addEventListener("click", () => loadFileLens(btn.getAttribute("data-path")));
    });
    renderEvidence(brief.evidence || []);
  }

  async function loadProjectBrief() {
    const container = $("overviewContent");
    if (container) container.innerHTML = '<div class="empty-state">正在生成项目全景...</div>';
    try {
      const brief = await window.CodeLensAPI.getProjectBrief();
      renderProjectBrief(brief);
    } catch (err) {
      if (container) container.innerHTML = `<div class="empty-state error">项目全景暂不可用：${esc(err.message)}</div>`;
    }
  }

  function renderFileLens(lens) {
    const container = $("fileLensContent");
    if (!container) return;
    const group = (title, items) => card(title, `<ul class="overview-list">${
      (items || []).map((item) => `
        <li><button class="linkish" data-path="${esc(item.path || item.target || "")}">${esc(item.path || item.target || item.name || "")}</button><span>${esc(item.reason || item.name || item.symbol || "")}</span></li>
      `).join("") || "<li>暂无。</li>"
    }</ul>`);
    container.innerHTML = [
      card("Summary", `<p>${esc(lens.summary || "")}</p>`),
      group("Imports", lens.imports),
      group("Imported By", lens.imported_by),
      group("Callers", lens.callers),
      group("Callees", lens.callees),
      group("Related Tests", lens.related_tests),
      group("Related Configs", lens.related_configs),
    ].join("");
    container.querySelectorAll("[data-path]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const path = btn.getAttribute("data-path");
        if (path && typeof window.openFileViewer === "function") {
          window.openFileViewer(path, path.split(/[\\/]/).pop() || path, "");
        }
      });
    });
    renderEvidence(lens.evidence || []);
  }

  async function loadFileLens(path) {
    const input = $("fileLensPathInput");
    const normalized = (path || (input && input.value) || "").trim();
    if (!normalized) return;
    if (input) input.value = normalized;
    const container = $("fileLensContent");
    if (container) container.innerHTML = '<div class="empty-state">正在串联上下游模块...</div>';
    try {
      const lens = await window.CodeLensAPI.getFileLens(normalized, 2);
      renderFileLens(lens);
      const mode = $("modeSelect");
      if (mode) {
        mode.value = "file_lens";
        mode.dispatchEvent(new Event("change"));
      }
    } catch (err) {
      if (container) container.innerHTML = `<div class="empty-state error">File Lens 暂不可用：${esc(err.message)}</div>`;
    }
  }

  function init() {
    const refresh = $("refreshBriefBtn");
    if (refresh) refresh.addEventListener("click", loadProjectBrief);
    const lensBtn = $("fileLensBtn");
    if (lensBtn) lensBtn.addEventListener("click", () => loadFileLens());
    const lensInput = $("fileLensPathInput");
    if (lensInput) {
      lensInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          loadFileLens();
        }
      });
    }
  }

  window.CodeLensWorkbench = {
    loadProjectBrief,
    loadFileLens,
    renderProjectBrief,
    renderFileLens,
  };
  init();
})();
