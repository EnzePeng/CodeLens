"""
TaskRouter — 任务分类路由。

把用户 query 路由到三种执行模式之一：
  simple      — 单轮或少量工具调用即可完成的查询/读取
  multi_step  — 需要规划 + 多步骤串行执行（如添加功能、重构）
  map_reduce  — 批量操作，可拆成多个并行子任务（如"分析 N 个文件"）

设计原则
--------
1. 启发式优先。绝大多数常见任务靠关键词即可准确分类，不调 LLM。
2. LLM 仅作为二次确认（对模糊查询），不阻塞快速路径。
3. 显式识别 batch 模式（所有/每个/全部/every/each/all/**/*）→ 直判 map_reduce。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from logger import logger


RouteKind = Literal["simple", "multi_step", "map_reduce"]


@dataclass
class TaskRoute:
    kind: RouteKind
    subtask_count_hint: int = 1
    estimated_cost: Literal["low", "medium", "high"] = "low"
    reasoning: str = ""
    # 对 map_reduce 模式，可能包含显式列出的目标文件/目录
    explicit_targets: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "subtask_count_hint": self.subtask_count_hint,
            "estimated_cost": self.estimated_cost,
            "reasoning": self.reasoning,
            "explicit_targets": self.explicit_targets,
        }


# ---- 关键词集合 ----

# 批量指示词：出现即强烈暗示 map_reduce
_BATCH_ZH = [
    "所有", "每个", "全部", "每一个", "各个", "整批", "遍历",
    "都分析", "都汇报", "都说明", "都解释", "都读取",
    "逐一", "逐个", "一份一份",
]
_BATCH_EN = ["all ", "every ", "each ", "every single", "each of"]
_GLOB_PATTERNS = [r"\*\*/\*\.\w+", r"\*\.\w+", r"[\w/]+\*/\*\.\w+"]

# 多步指示词：需要规划 + 串行执行
_MULTI_STEP_ZH = ["实现", "添加", "新增", "修改", "重构", "重写", "迁移", "删除",
                  "拆分", "合并", "创建", "构建", "设计", "优化", "修复", "测试",
                  "重命名", "改名", "替换", "改造", "增强"]
_MULTI_STEP_EN = ["implement", "add feature", "refactor", "rewrite", "migrate",
                  "build", "design", "optimize", "fix", "test and", "rename", "replace"]

# 简单任务指示词
_SIMPLE_ZH = ["读取", "查看", "解释", "说明", "列出", "显示", "描述", "分析",
              "搜索", "查找", "定位", "统计"]
_SIMPLE_EN = ["read", "explain", "show", "list", "describe", "analyze",
              "search", "find", "locate", "count"]

# 数字 + 量词模式："N 个文件"/"N files"
_N_ITEMS_RE = re.compile(r"(\d+)\s*(?:个|份|只|个文件|files|modules|functions)", re.IGNORECASE)


@dataclass
class _BatchHint:
    count: int
    reasoning: str
    targets: list[str] | None = None


class TaskRouter:
    """任务路由器。主入口：route() 异步方法。"""

    def __init__(self, use_llm: bool = False) -> None:
        self.use_llm = use_llm

    async def route(self, query: str, context: str = "") -> TaskRoute:
        """
        对 query 做分类。先走启发式；若启发式置信度低且 use_llm=True，再让 LLM 复核。
        """
        route = self._heuristic_route(query)
        if self.use_llm and route.estimated_cost != "low":
            try:
                llm_route = await self._llm_route(query)
                if llm_route:
                    # 启发式判 map_reduce 时优先（批量检测更可靠）
                    if route.kind == "map_reduce":
                        return route
                    return llm_route
            except Exception as e:
                logger.warning(f"[Router] LLM 复核失败，使用启发式结果: {e}")
        return route

    def route_sync(self, query: str) -> TaskRoute:
        """同步版本，仅启发式。用于不需要 await 的场景。"""
        return self._heuristic_route(query)

    # ---- 启发式分类 ----

    def _heuristic_route(self, query: str) -> TaskRoute:
        q = query.strip()
        q_lower = q.lower()

        batch = self._looks_batch(q, q_lower)
        multi_step = self._looks_multi_step(q_lower)

        # 优先级：当两者同时命中时，需要区分两种情况：
        #   (a) "搜索所有引用并重命名" — 真正的串行写工作流 → multi_step
        #   (b) "分析所有 py 文件...修复[出现的问题]" — 批量读为主，
        #       "修复"只是任务的元描述/收尾，不是对每个目标的写动作 → map_reduce
        # 区分依据：query 里是否同时出现「写意图动词 + 写目标词」
        # （如 修改/重构/实现/添加 + 功能/文件/模块/接口）。
        # 注意 "修复/fix/test/验证" 单独出现时不构成写意图，因为它们常作为
        # 测试任务的收尾语出现（"分析问题并修复"）。
        if batch and multi_step:
            if self._has_explicit_write_intent(q_lower):
                return TaskRoute(
                    kind="multi_step",
                    subtask_count_hint=3,
                    estimated_cost="medium",
                    reasoning="同时检测到批量词和显式写意图（写动词+写目标），按多步串行处理",
                )
            # 批量读为主，写信号弱 → 走 map_reduce 并行批量
            hint = self._extract_batch_hint(q)
            return TaskRoute(
                kind="map_reduce",
                subtask_count_hint=hint.count,
                estimated_cost="high" if hint.count > 10 else "medium",
                reasoning=hint.reasoning + "（多步指示词未伴随显式写目标，按批量并行处理）",
                explicit_targets=hint.targets,
            )

        # 1. 批量模式检测（map_reduce）
        if batch:
            hint = self._extract_batch_hint(q)
            return TaskRoute(
                kind="map_reduce",
                subtask_count_hint=hint.count,
                estimated_cost="high" if hint.count > 10 else "medium",
                reasoning=hint.reasoning,
                explicit_targets=hint.targets,
            )

        # 2. 多步模式检测
        if multi_step:
            return TaskRoute(
                kind="multi_step",
                subtask_count_hint=3,
                estimated_cost="medium",
                reasoning="检测到多步指示词（实现/重构/修改等），需要规划后串行执行",
            )

        # 3. 简单任务
        return TaskRoute(
            kind="simple",
            subtask_count_hint=1,
            estimated_cost="low",
            reasoning="未检测到批量或多步指示词，按简单任务处理",
        )

    def _looks_batch(self, query: str, q_lower: str) -> bool:
        """是否呈现批量模式。"""
        # 中文批量词
        for kw in _BATCH_ZH:
            if kw in query:
                return True
        # 英文批量词（需词边界）
        for kw in _BATCH_EN:
            if kw in q_lower:
                # 进一步确认后面跟的是可数名词
                idx = q_lower.find(kw)
                tail = q_lower[idx + len(kw): idx + len(kw) + 30]
                if any(noun in tail for noun in ["file", "module", "class", "function", "folder", "directory"]):
                    return True

        # glob 通配符
        for pat in _GLOB_PATTERNS:
            if re.search(pat, query):
                return True

        # "N 个文件/模块/类" — N 较大时
        m = _N_ITEMS_RE.search(query)
        if m and int(m.group(1)) >= 3:
            return True

        return False

    def _looks_multi_step(self, q_lower: str) -> bool:
        for kw in _MULTI_STEP_ZH:
            if kw in q_lower:
                return True
        for kw in _MULTI_STEP_EN:
            if kw in q_lower:
                return True

        # "加/添加/新增 + 功能/特性/模块/接口" — 隐式添加功能
        if re.search(r"(?:加|添加|新增|补充)\s*\S{0,20}\s*(?:功能|特性|模块|接口|按钮|页面|字段|配置)", q_lower):
            return True
        # "给 X 加 Y" 模式
        if re.search(r"给\s+\S+\s+加\s+", q_lower):
            return True

        # 长 query（> 80 字符）且含多个动词
        if len(q_lower) > 80:
            verbs = sum(1 for kw in (_MULTI_STEP_ZH + _MULTI_STEP_EN) if kw in q_lower)
            if verbs >= 2:
                return True
        return False

    # 真正的写意图动词（修改/重构/添加等），不含 修复/fix/test/验证/优化
    # 这些词在「分析类任务」里常作为收尾语出现，不构成对每个目标的写动作。
    _WRITE_ACTION_ZH = [
        "修改", "重构", "重写", "迁移", "删除", "拆分", "合并", "创建",
        "构建", "设计", "重命名", "改名", "替换", "改造", "增强",
    ]
    _WRITE_ACTION_EN = [
        "modify", "refactor", "rewrite", "migrate", "delete", "remove",
        "rename", "replace", "restructure", "overhaul",
    ]
    # 写目标词：写动作必须作用于这些目标才算真写意图
    _WRITE_TARGET_RE = re.compile(
        r"(功能|特性|模块|接口|按钮|页面|字段|配置|文件|代码|函数|类|逻辑"
        r"|feature|module|interface|button|page|field|config|file|code|function|class|logic)",
        re.IGNORECASE,
    )

    def _has_explicit_write_intent(self, q_lower: str) -> bool:
        """判断 query 是否包含「写动作 + 写目标」的显式写意图。

        用于在 batch + multi_step 同时命中时区分：
          - "搜索所有引用并重命名" → 重命名(写) + 引用(目标) → True
          - "分析所有 py 文件...修复问题" → 修复不算写动作 → False
        """
        has_action = any(kw in q_lower for kw in self._WRITE_ACTION_ZH) \
            or any(kw in q_lower for kw in self._WRITE_ACTION_EN)
        if not has_action:
            return False
        return bool(self._WRITE_TARGET_RE.search(q_lower))

    # ---- 批量 hint 抽取 ----

    def _extract_batch_hint(self, query: str) -> _BatchHint:
        # 数字
        m = _N_ITEMS_RE.search(query)
        if m:
            return _BatchHint(
                count=int(m.group(1)),
                reasoning=f"检测到 'N 项' 模式 ({m.group(0)})",
            )

        # 显式路径/目录
        path_re = re.compile(r"[`'\"]?([a-zA-Z0-9_./\\-]+\.[a-zA-Z0-9]{1,5})[`'\"]?")
        paths = path_re.findall(query)
        dir_re = re.compile(r"(?:目录|文件夹|folder|directory)\s*[`'\"]?([a-zA-Z0-9_./\\-]+)")
        dirs = dir_re.findall(query)
        targets = list(dict.fromkeys(paths + dirs)) or None

        # glob 模式
        glob_match = re.search(r"(\*\*/?\*\.\w+)", query)
        if glob_match:
            targets = (targets or []) + [glob_match.group(1)]

        count = len(targets) if targets else 8  # 默认 8 个占位，decomposer 会算准
        return _BatchHint(
            count=count,
            reasoning=f"检测到批量模式，目标数估计为 {count}",
            targets=targets,
        )

    # ---- LLM 复核 ----

    async def _llm_route(self, query: str) -> TaskRoute | None:
        from core.llm_client import llm_client

        prompt = f"""把以下用户任务分类到三类之一:

类别:
- "simple": 直接问答、单文件读取、简单搜索
- "multi_step": 需要规划和多步骤串行执行（如添加功能、重构）
- "map_reduce": 批量操作，可拆成多个并行子任务（如"分析 N 个文件"、"为每个模块生成报告"）

任务: {query}

只输出一个 JSON 对象，格式:
{{"kind": "simple|multi_step|map_reduce", "reasoning": "简短理由", "subtask_count_hint": 数字}}
"""
        try:
            resp = await llm_client.call(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.1,
                task_type="quick_reflection",
            )
            content = (resp.content or "").strip()
            # 抽取 JSON
            import json as _json
            m = re.search(r"\{[\s\S]*\}", content)
            if not m:
                return None
            data = _json.loads(m.group(0))
            kind = data.get("kind", "simple")
            if kind not in ("simple", "multi_step", "map_reduce"):
                return None
            return TaskRoute(
                kind=kind,
                subtask_count_hint=int(data.get("subtask_count_hint", 1)),
                estimated_cost="medium" if kind != "simple" else "low",
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            logger.warning(f"[Router] LLM 路由失败: {e}")
            return None


# 全局实例（默认不开 LLM，更可靠）
task_router = TaskRouter(use_llm=False)


def get_router() -> TaskRouter:
    return task_router
