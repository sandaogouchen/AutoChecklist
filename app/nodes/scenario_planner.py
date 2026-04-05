"""场景规划节点。

基于上下文研究输出（``ResearchOutput``），规划出需要测试的场景列表。
优先使用 LLM 提取的用户场景，若为空则从功能主题派生。

变更：当 state 中存在 mr_combined_summary 时，将 MR 代码分析摘要
注入场景规划上下文，使生成的场景覆盖代码变更维度。
"""

from __future__ import annotations

import logging

from app.domain.research_models import PlannedScenario, ResearchOutput
from app.domain.state import GlobalState

logger = logging.getLogger(__name__)

# 当研究输出中既无用户场景也无功能主题时的兆底场景
_FALLBACK_SCENARIO_TITLE = "Validate core workflow"


def scenario_planner_node(state: GlobalState) -> GlobalState:
    """根据研究输出规划测试场景。

    规划逻辑：
    1. 优先使用 ``user_scenarios`` 作为场景标题
    2. 若为空，从 ``feature_topics`` 派生（添加 "Validate" 前缀）
    3. 都为空时使用兆底场景
    4. 当 mr_combined_summary 存在时，追加 MR 代码变更派生的场景

    所有场景标题会进行大小写不敏感的去重处理。
    """
    research_output = state["research_output"]
    scenario_titles = _collect_scenario_titles(research_output)

    # ---- MR 代码分析摘要注入 ----
    mr_combined_summary: str = state.get("mr_combined_summary", "")
    mr_derived_scenarios: list[str] = []
    if mr_combined_summary:
        logger.info(
            "MR combined summary available (%d chars), deriving code-change scenarios",
            len(mr_combined_summary),
        )
        mr_derived_scenarios = _derive_scenarios_from_mr_summary(mr_combined_summary)
        if mr_derived_scenarios:
            scenario_titles.extend(mr_derived_scenarios)
            scenario_titles = _dedupe_preserving_order(scenario_titles)
            logger.info(
                "Added %d MR-derived scenarios, total after dedup: %d",
                len(mr_derived_scenarios),
                len(scenario_titles),
            )

    # 取前两个约束条件作为场景的理由说明
    constraints_summary = "; ".join(research_output.constraints[:2])

    planned_scenarios = [
        PlannedScenario(
            title=title,
            category="functional",
            risk="medium",
            rationale=(
                "Derived from MR code change analysis."
                if title in mr_derived_scenarios
                else constraints_summary or "Derived from document research output."
            ),
        )
        for title in scenario_titles
    ]
    return {"planned_scenarios": planned_scenarios}


def _derive_scenarios_from_mr_summary(summary: str) -> list[str]:
    """从 MR 代码分析摘要中提取场景标题。

    解析摘要文本中的关键变更描述，转化为可测试场景标题。
    采用简单的行解析策略：以 '- ' 开头的行视为变更条目。
    """
    scenarios: list[str] = []
    for line in summary.splitlines():
        line = line.strip()
        if line.startswith("- ") and len(line) > 4:
            # 去掉前缀 '- '，添加 'Validate' 前缀
            change_desc = line[2:].strip()
            if change_desc:
                scenarios.append(f"验证 {change_desc}")
    return scenarios


def _collect_scenario_titles(research_output: ResearchOutput) -> list[str]:
    """从研究输出中收集并去重场景标题。

    优先级：user_scenarios > feature_topics 派生 > 兆底值。
    """
    # 优先使用 LLM 提取的用户场景
    titles = [title.strip() for title in research_output.user_scenarios if title.strip()]
    if titles:
        return _dedupe_preserving_order(titles)

    # 次选：从功能主题派生测试场景
    derived = [
        f"Validate {topic}"
        for topic in research_output.feature_topics
        if topic.strip()
    ]
    return _dedupe_preserving_order(derived) or [_FALLBACK_SCENARIO_TITLE]


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    """去重并保持原始顺序（大小写不敏感）。

    使用 ``casefold()`` 进行标准化比较，确保 "Login" 和 "login"
    被视为同一项，但保留首次出现时的原始大小写。
    """
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped
