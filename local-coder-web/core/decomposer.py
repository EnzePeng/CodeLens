"""
TaskDecomposer — 把复杂任务拆成可执行的子任务序列。

设计原则
--------
1. 文件系统快照驱动。分解前先 glob 拿到真实文件列表，不让 LLM 瞎猜路径。
2. 模板优先。常见模式（"分析 N 个文件"、"搜索并重构 X"）有硬编码模板。
3. LLM 仅处理模板覆盖不了的复杂情况（作为 fallback）。
4. 并行性标记：纯读操作 parallelizable=True；写操作串行。

依赖
----
- core.router.TaskRoute（路由结果）
- core.tools.glob_tool（用于 fs 快照，但可选）
"""
from __future__ import annotations

import fnmatch
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from logger import logger


SubTaskKind = Literal["read", "analyze", "search", "modify", "run", "list", "report"]


@dataclass
class SubTask:
    """一个可独立执行的子任务。"""
    id: str
    description: str
    kind: SubTaskKind
    inputs: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    parallelizable: bool = True
    # 给子任务内 ReAct 循环的提示（更聚焦的 prompt）
    focus_prompt: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "kind": self.kind,
            "inputs": self.inputs,
            "depends_on": self.depends_on,
            "parallelizable": self.parallelizable,
            "focus_prompt": self.focus_prompt,
        }


class TaskDecomposer:
    """
    任务分解器。

    用法：
        decomposer = TaskDecomposer()
        subtasks = await decomposer.decompose(query, route, project_root)
    """

    def __init__(self, use_llm_fallback: bool = True) -> None:
        self.use_llm_fallback = use_llm_fallback

    async def decompose(
        self,
        query: str,
        route,  # TaskRoute
        project_root: Path | None,
    ) -> list[SubTask]:
        """
        把 query 按 route 类型分解为子任务列表。

        project_root
            项目根目录；用于 glob 快照。可以为 None（此时跳过 fs 快照）。
        """
        if route.kind == "simple":
            return self._decompose_simple(query, route)

        if route.kind == "map_reduce":
            return await self._decompose_map_reduce(query, route, project_root)

        if route.kind == "multi_step":
            return await self._decompose_multi_step(query, route, project_root)

        # Fallback
        return self._decompose_simple(query, route)

    # ---- 简单任务 ----

    def _decompose_simple(self, query: str, route) -> list[SubTask]:
        """简单任务 = 单个子任务。"""
        return [
            SubTask(
                id=self._new_id(),
                description=query,
                kind=self._infer_simple_kind(query),
                inputs={"query": query},
                parallelizable=True,
            )
        ]

    def _infer_simple_kind(self, query: str) -> SubTaskKind:
        q = query.lower()
        if any(k in q for k in ["读取", "read", "查看", "查看文件", "view"]):
            return "read"
        if any(k in q for k in ["分析", "analyze", "说明", "explain", "描述", "describe"]):
            return "analyze"
        if any(k in q for k in ["搜索", "查找", "search", "find", "定位", "locate"]):
            return "search"
        if any(k in q for k in ["列出", "list", "浏览"]):
            return "list"
        return "read"

    # ---- map_reduce（批量） ----

    async def _decompose_map_reduce(
        self,
        query: str,
        route,
        project_root: Path | None,
    ) -> list[SubTask]:
        # 1. 解析批量目标
        targets = self._resolve_batch_targets(query, route, project_root)
        if not targets:
            logger.warning(f"[Decomposer] 无法解析批量目标，回退到单子任务: {query}")
            return self._decompose_simple(query, route)

        # 2. 判断每个目标的子任务类型
        op_kind = self._infer_batch_operation(query)

        # 3. 每个目标生成一个子任务
        subtasks: list[SubTask] = []
        for target in targets:
            subtask = SubTask(
                id=self._new_id(),
                description=self._describe_subtask(op_kind, target, query),
                kind=op_kind,
                inputs={"path": target} if op_kind in ("read", "analyze") else {"pattern": target},
                parallelizable=(op_kind in ("read", "analyze", "search")),
                focus_prompt=self._build_focus_prompt(query, op_kind, target),
            )
            subtasks.append(subtask)

        # 4. 可选：加一个"汇总"子任务（非并行，依赖前面所有）
        if len(subtasks) >= 2:
            summary_subtask = SubTask(
                id=self._new_id(),
                description=f"汇总所有 {op_kind} 结果并生成最终报告",
                kind="report",
                inputs={},
                depends_on=[s.id for s in subtasks],
                parallelizable=False,
                focus_prompt="基于所有子任务的结构化结果（在已完成的工作摘要中），生成一份综合报告。",
            )
            subtasks.append(summary_subtask)

        return subtasks

    def _resolve_batch_targets(
        self,
        query: str,
        route,
        project_root: Path | None,
    ) -> list[str]:
        """把批量查询解析成具体的目标列表（文件路径/模式）。"""
        # 优先用 route.explicit_targets（如果有 glob 模式则展开）
        if route.explicit_targets:
            expanded: list[str] = []
            for t in route.explicit_targets:
                if "*" in t or "?" in t or "[" in t:
                    if project_root:
                        expanded.extend(self._glob_expand(project_root, t))
                    else:
                        expanded.append(t)
                else:
                    expanded.append(t)
            if expanded:
                return expanded

        # 检测 Windows 绝对路径（如 E:\Project\...\core 或 E:/Project/.../core）
        # 把它们转成相对于 project_root 的路径，作为搜索根
        win_abs_re = re.compile(r"[A-Za-z]:[\\/][a-zA-Z0-9_./\\-]+")
        abs_match = win_abs_re.search(query)
        if abs_match and project_root:
            abs_path = Path(abs_match.group(0))
            # 推断文件扩展名过滤（*.py 或 *.ts 等）
            ext = None
            m_ext = re.search(r"\*\.(\w+)", query)
            if m_ext:
                ext = m_ext.group(1)
            else:
                m_ext_zh = re.search(r"\b([a-zA-Z0-9]{1,6})\s*(?:文件|files?)\b", query)
                if m_ext_zh:
                    ext = m_ext_zh.group(1).lower()
            pattern = f"**/*.{ext}" if ext else "**/*"
            # abs_path 可能是目录也可能是文件；作为目录处理
            if abs_path.is_dir():
                results = self._glob_expand(abs_path, pattern, root=project_root)
                if results:
                    return results
            # 否则尝试它的父目录（如果用户给的是文件路径）
            if abs_path.parent.is_dir():
                results = self._glob_expand(abs_path.parent, pattern, root=project_root)
                if results:
                    return results

        # 中文路径分隔模式："X里的Y里的Z"、"X下的Y"、"X中的Y"。
        # 把所有 「路径片段 + 里的/下的/中的」 串起来组成 search_dir。
        # 例: "分析local-coder-web里的core里的所有py" → "local-coder-web/core"
        # 例: "src下的utils下的js" → "src/utils"
        zh_sep_re = re.compile(
            r"([a-zA-Z0-9_./\\-]+)\s*(?:里的|下的|中的|里面|内部)",
        )
        zh_segs: list[str] = []
        for m in zh_sep_re.finditer(query):
            seg = m.group(1).strip().strip("./")
            if seg and seg not in zh_segs:
                zh_segs.append(seg)
        if zh_segs:
            # 合并多段路径；后续与 ext 配合使用
            zh_search_dir = "/".join(zh_segs)
            # 解析扩展名（含裸 "py"、".py"、"*.py"）
            zh_ext = self._extract_extension(query)
            if project_root:
                pattern = f"**/*.{zh_ext}" if zh_ext else "**/*"
                results = self._glob_expand(project_root / zh_search_dir, pattern, root=project_root)
                if results:
                    return results
                # 路径可能是文件而非目录；尝试其作为文件直接匹配
                direct = project_root / zh_search_dir
                if direct.is_file():
                    try:
                        return [direct.relative_to(project_root).as_posix()]
                    except ValueError:
                        return [zh_search_dir]

        # 从 query 里提取目录 + 扩展名。
        # 策略：先定位"目录/文件夹"类关键词，再在其附近找路径（处理 "X 下的 Y 文件夹"）。
        dir_match = None
        dir_keywords = ["文件夹", "目录", "folder", "directory"]
        path_pat = re.compile(r"[`'\"]?([a-zA-Z0-9_./\\-]+)[`'\"]?")

        # 找到最后一个目录关键词（通常修饰最近的目录）
        kw_positions: list[int] = []
        for kw in dir_keywords:
            idx = 0
            while True:
                j = query.find(kw, idx)
                if j < 0:
                    break
                kw_positions.append(j)
                idx = j + len(kw)
        kw_positions.sort()

        if kw_positions:
            # 取最后一个关键词，在其前后 40 字符窗口内找最近的路径
            kw_pos = kw_positions[-1]
            window_start = max(0, kw_pos - 40)
            window_end = min(len(query), kw_pos + 40)
            window = query[window_start:window_end]
            candidates: list[tuple[int, str]] = []  # (distance_to_kw, path)
            for m in path_pat.finditer(window):
                p = m.group(1)
                if len(p) >= 2 and ("/" in p or "." not in p or p.endswith("/")):
                    # 计算匹配起始位置到关键词的绝对距离
                    abs_start = window_start + m.start(1)
                    dist = abs(abs_start - kw_pos)
                    candidates.append((dist, p))
            if candidates:
                # 选距离最近的；距离相同时选较长的
                candidates.sort(key=lambda x: (x[0], -len(x[1])))
                best = candidates[0][1]
                class _M:
                    def group(self, _):
                        return best
                dir_match = _M()

        # Fallback for English "in <path>" pattern (e.g., "analyze every py file in core")
        if not dir_match:
            m_in = re.search(r"\bin\s+([a-zA-Z0-9_./\\-]{2,})(?:\s|$|[.,;])", query)
            if m_in:
                path_candidate = m_in.group(1)
                # 排除常见非目录词
                if path_candidate.lower() not in {"the", "this", "that", "these", "those", "which", "what"}:
                    class _M:
                        def group(self, _):
                            return path_candidate
                    dir_match = _M()

        ext = self._extract_extension(query)

        if project_root and dir_match:
            search_dir = dir_match.group(1)
            pattern = f"**/*.{ext}" if ext else "**/*"
            return self._glob_expand(project_root / search_dir, pattern, root=project_root)

        # Fallback: 如果只有 ext 没有 dir，从项目根目录搜索
        if project_root and ext:
            pattern = f"**/*.{ext}"
            return self._glob_expand(project_root, pattern, root=project_root)

        # Fallback: 从 route.subtask_count_hint 生成占位（让 agent 自己发现）
        return []

    def _glob_expand(
        self,
        base_dir: Path,
        pattern: str,
        root: Path | None = None,
    ) -> list[str]:
        """用 fnmatch 展开 glob 模式，返回相对路径列表。

        容错：如果 base_dir 不存在，尝试剥离「与 project_root 同名的前缀段」
        再重试。用户常在 query 里带上项目名（"分析 local-coder-web/core"），
        但 project_root 本身就是 local-coder-web，导致路径重复。
        """
        if not base_dir.exists() and root is not None and root != base_dir:
            base_dir = self._strip_redundant_prefix(base_dir, root)

        if not base_dir.exists():
            logger.warning(f"[Decomposer] 目录不存在: {base_dir}")
            return []

        # base_dir 可能被解析成绝对路径；统一解析 root 以保证 relative_to 正确
        root = (root or base_dir)
        try:
            root_resolved = root.resolve()
        except Exception:
            root_resolved = root
        results: list[str] = []
        # 跳过隐藏目录和常见构建/依赖目录
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv",
                     "dist", "build", ".idea", ".vscode", "site-packages"}
        try:
            for path in base_dir.rglob(pattern.lstrip("./")):
                if not path.is_file():
                    continue
                if any(part in skip_dirs for part in path.parts):
                    continue
                try:
                    rel = path.resolve().relative_to(root_resolved)
                    results.append(rel.as_posix())
                except ValueError:
                    results.append(path.as_posix())
        except Exception as e:
            logger.warning(f"[Decomposer] glob 失败: {e}")
            return []

        results.sort()
        return results

    @staticmethod
    def _strip_redundant_prefix(base_dir: Path, root: Path) -> Path:
        """剥离 path 中与 project_root 名字重复的前导段。

        场景：project_root = .../local-coder-web，用户 query 写
        "local-coder-web/core"，join 后变成 .../local-coder-web/local-coder-web/core。
        本方法把第一段（若与 root 的最后一段同名）剥掉，得到 .../local-coder-web/core。
        """
        try:
            root_resolved = root.resolve()
            base_resolved = base_dir.resolve()
        except Exception:
            return base_dir
        root_name = root_resolved.name
        if not root_name:
            return base_dir
        try:
            rel = base_resolved.relative_to(root_resolved)
        except ValueError:
            return base_dir
        if rel.parts and rel.parts[0] == root_name:
            stripped = root_resolved / Path(*rel.parts[1:])
            return stripped
        return base_dir

    # 常见编程语言扩展名白名单；裸扩展名匹配只认这些，避免误把
    # query 里的普通英文单词（如 "all"、"the"）当成扩展名。
    _KNOWN_EXTS = {
        "py", "js", "ts", "tsx", "jsx", "java", "kt", "go", "rs", "c", "h",
        "cpp", "cc", "cxx", "hpp", "cs", "rb", "php", "swift", "m", "mm",
        "scala", "clj", "ex", "exs", "erl", "hs", "ml", "fs", "vb",
        "html", "htm", "css", "scss", "sass", "less", "vue", "svelte",
        "json", "yaml", "yml", "toml", "xml", "ini", "cfg", "conf",
        "md", "rst", "txt", "sh", "bash", "zsh", "bat", "ps1", "sql",
        "proto", "thrift", "gradle", "sbt", "dart",
    }

    def _extract_extension(self, query: str) -> str | None:
        """从 query 中提取文件扩展名（不含点）。

        支持的写法（按优先级）：
          1. ``*.py`` / ``*.ts``   — glob 通配
          2. ``.py``               — 点开头
          3. ``py 文件`` / ``py files`` — 扩展名 + 量词
          4. 裸 ``py``             — 仅当出现在已知扩展名白名单中，
                                     且位于路径片段之后（如 "core 里的所有 py"）
        """
        # 1. *.ext
        m = re.search(r"\*\.([a-zA-Z][a-zA-Z0-9]{0,5})\b", query)
        if m:
            return m.group(1).lower()
        # 2. .ext （独立 token，前面不是字母/数字，避免误匹配域名/版本号）
        m = re.search(r"(?<![a-zA-Z0-9])\.([a-zA-Z][a-zA-Z0-9]{0,5})\b", query)
        if m:
            return m.group(1).lower()
        # 3. ext + 文件/files
        m = re.search(r"\b([a-zA-Z][a-zA-Z0-9]{0,5})\s*(?:文件|files?)\b", query, re.IGNORECASE)
        if m and m.group(1).lower() in self._KNOWN_EXTS:
            return m.group(1).lower()
        # 4. 裸 ext：必须在已知白名单内
        for m in re.finditer(r"\b([a-zA-Z][a-zA-Z0-9]{0,5})\b", query):
            cand = m.group(1).lower()
            if cand in self._KNOWN_EXTS:
                return cand
        return None

    def _infer_batch_operation(self, query: str) -> SubTaskKind:
        q = query.lower()
        if any(k in q for k in ["分析", "analyze", "报告", "report", "说明", "explain"]):
            return "analyze"
        if any(k in q for k in ["读取", "read", "查看", "view"]):
            return "read"
        if any(k in q for k in ["搜索", "search", "find", "查找"]):
            return "search"
        if any(k in q for k in ["修改", "重构", "重写", "实现", "modify", "refactor"]):
            return "modify"
        return "analyze"

    def _describe_subtask(self, op_kind: SubTaskKind, target: str, original_query: str) -> str:
        """为单个子任务生成简洁、聚焦的描述（不复述原始 query 的整段文本）。"""
        zh_verbs = {
            "analyze": "分析文件",
            "read": "读取并说明文件",
            "search": "在文件中搜索相关内容",
            "modify": "修改文件",
        }
        en_verbs = {
            "analyze": "Analyze",
            "read": "Read and explain",
            "search": "Search in",
            "modify": "Modify",
        }
        # 判断原始 query 的语言倾向
        is_zh = any("\u4e00" <= c <= "\u9fff" for c in original_query)
        if is_zh:
            return f"{zh_verbs.get(op_kind, '处理')} `{target}`"
        return f"{en_verbs.get(op_kind, 'Handle')} `{target}`"

    def _build_focus_prompt(self, original_query: str, kind: SubTaskKind, target: str) -> str:
        """为子任务的 ReAct 循环生成聚焦提示。"""
        if kind == "analyze":
            return (
                f"你的唯一目标是分析文件 `{target}`。\n"
                f"原始任务背景: {original_query[:200]}\n\n"
                f"要求:\n"
                f"1. 读取 `{target}` 的完整内容\n"
                f"2. 总结其核心功能（3-5 个要点）\n"
                f"3. 指出潜在问题（bug、设计缺陷、性能问题、安全隐患）\n"
                f"4. 完成后直接输出结构化结果，不要继续执行其他文件\n"
            )
        if kind == "read":
            return (
                f"读取文件 `{target}` 并说明其作用。\n"
                f"原始任务背景: {original_query[:200]}\n"
            )
        if kind == "search":
            return (
                f"在文件/目录 `{target}` 中搜索相关内容。\n"
                f"原始任务背景: {original_query[:200]}\n"
            )
        if kind == "modify":
            return (
                f"对文件 `{target}` 做指定的修改。\n"
                f"原始任务背景: {original_query[:200]}\n"
            )
        return f"处理目标: {target}"

    # ---- multi_step（多步串行） ----

    async def _decompose_multi_step(
        self,
        query: str,
        route,
        project_root: Path | None,
    ) -> list[SubTask]:
        """
        多步任务分解。
        - 先尝试模板匹配（如"搜索+重命名"、"读取+修改+测试"）
        - 失败则走 LLM fallback
        """
        # 模板 1: 搜索 + 重命名/替换
        if self._matches_search_and_modify(query):
            return self._template_search_and_modify(query)

        # 模板 2: 读取 → 修改 → 测试
        if self._matches_read_modify_test(query):
            return self._template_read_modify_test(query)

        # LLM fallback
        if self.use_llm_fallback:
            try:
                llm_subtasks = await self._llm_decompose(query, project_root)
                if llm_subtasks:
                    return llm_subtasks
            except Exception as e:
                logger.warning(f"[Decomposer] LLM 分解失败: {e}")

        # 兜底：单子任务
        return [
            SubTask(
                id=self._new_id(),
                description=query,
                kind="modify",
                inputs={"query": query},
                parallelizable=False,
            )
        ]

    def _matches_search_and_modify(self, query: str) -> bool:
        q = query.lower()
        return bool(
            re.search(r"(搜索|查找|search|find).{0,20}(重命名|替换|rename|replace|修改)", q)
        )

    def _template_search_and_modify(self, query: str) -> list[SubTask]:
        s1 = SubTask(
            id=self._new_id(),
            description="搜索所有相关引用位置",
            kind="search",
            inputs={"query": query},
            parallelizable=True,
            focus_prompt=f"搜索与以下任务相关的所有引用位置:\n{query}\n列出每个匹配的文件和行号。",
        )
        s2 = SubTask(
            id=self._new_id(),
            description="基于搜索结果执行修改",
            kind="modify",
            inputs={"query": query},
            depends_on=[s1.id],
            parallelizable=False,
            focus_prompt=f"基于上一步的搜索结果，对所有相关位置做修改。\n任务: {query}",
        )
        return [s1, s2]

    def _matches_read_modify_test(self, query: str) -> bool:
        q = query.lower()
        has_read = any(k in q for k in ["读", "查看", "分析"])
        has_modify = any(k in q for k in ["修改", "重构", "添加", "实现", "重写"])
        has_test = any(k in q for k in ["测试", "验证", "test", "verify"])
        return has_read and has_modify and has_test

    def _template_read_modify_test(self, query: str) -> list[SubTask]:
        s1 = SubTask(
            id=self._new_id(),
            description="读取相关文件并理解上下文",
            kind="read",
            inputs={"query": query},
            parallelizable=True,
        )
        s2 = SubTask(
            id=self._new_id(),
            description="基于上下文执行修改",
            kind="modify",
            inputs={"query": query},
            depends_on=[s1.id],
            parallelizable=False,
        )
        s3 = SubTask(
            id=self._new_id(),
            description="运行测试验证修改",
            kind="run",
            inputs={"query": query},
            depends_on=[s2.id],
            parallelizable=False,
        )
        return [s1, s2, s3]

    # ---- LLM fallback ----

    async def _llm_decompose(self, query: str, project_root: Path | None) -> list[SubTask]:
        from core.llm_client import llm_client

        # 提供 fs 快照摘要
        fs_hint = ""
        if project_root and project_root.exists():
            try:
                files = [p.relative_to(project_root).as_posix()
                         for p in project_root.rglob("*.py")
                         if not any(x in p.parts for x in [".git", "__pycache__", "node_modules", ".venv"])]
                if len(files) <= 40:
                    fs_hint = "\n".join(files)
                else:
                    fs_hint = f"({len(files)} 个 py 文件，前 40 个):\n" + "\n".join(files[:40])
            except Exception:
                pass

        prompt = f"""把以下任务分解为 2-6 个有序子任务。

任务: {query}

项目文件 (供参考):
{fs_hint[:3000]}

输出 JSON 数组，每个元素:
{{"description": "子任务描述", "kind": "read|analyze|search|modify|run", "parallelizable": true/false, "depends_on_index": [前序子任务的索引，0-based]}}

只输出 JSON，不要其他内容:"""

        try:
            resp = await llm_client.call(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
                task_type="agent",
            )
            content = (resp.content or "").strip()
            import json as _json
            m = re.search(r"\[[\s\S]*\]", content)
            if not m:
                return []
            items = _json.loads(m.group(0))
            if not isinstance(items, list) or not items:
                return []

            subtasks: list[SubTask] = []
            ids: list[str] = []
            for item in items:
                sid = self._new_id()
                ids.append(sid)
            for i, item in enumerate(items):
                depends_idx = item.get("depends_on_index", []) or []
                depends_on = [ids[j] for j in depends_idx if 0 <= j < i]
                kind = item.get("kind", "modify")
                if kind not in ("read", "analyze", "search", "modify", "run", "list", "report"):
                    kind = "modify"
                subtasks.append(SubTask(
                    id=ids[i],
                    description=str(item.get("description", f"子任务 {i+1}")),
                    kind=kind,  # type: ignore[arg-type]
                    inputs={"query": query},
                    depends_on=depends_on,
                    parallelizable=bool(item.get("parallelizable", False)),
                ))
            return subtasks
        except Exception as e:
            logger.warning(f"[Decomposer] LLM 分解失败: {e}")
            return []

    # ---- 工具 ----

    def _new_id(self) -> str:
        return str(uuid.uuid4())[:8]


# 全局实例
task_decomposer = TaskDecomposer(use_llm_fallback=True)


def get_decomposer() -> TaskDecomposer:
    return task_decomposer
