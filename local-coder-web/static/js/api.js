(function () {
  async function requestJson(url, options) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || `HTTP ${resp.status}`);
    }
    return data;
  }

  window.CodeLensAPI = {
    startIndex(path) {
      return requestJson("/api/index/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
    },
    getProjectBrief() {
      return requestJson("/api/project/brief");
    },
    getFileLens(path, depth) {
      return requestJson("/api/file-lens", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, depth: depth || 2 }),
      });
    },
  };
})();
