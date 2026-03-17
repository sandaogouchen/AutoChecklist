"""场景规划节点。

基于上下文研究输出（``ResearchOutput``），规划出需要测试的场景列表。
优先使用 LLM 提取的用户场景，若为空则从功能主题派生。
"""

from __future__ import annotations

from app.domain.research_models import PlannedScenario, ResearchOutput
from app.domain.state import GlobalState

# 当研究输出中既无用户场景也无功能主题时的兆底场景
_FALLBACK_SCENARIO_TITLE = "Validate core workflow"


def scenario_planner_node(state: GlobalState) -> GlobalState:
    """根据研究输出规划测试场景。

    规划逻辑：
    1. 优先使用 ``user_scenarios`` 作为场景标题
    2. 若为空，从 ``feature_topics`` 派生（添加 "Validate" 前缀）
    3. 都为空时使用兆底场景

    所有场景标题会进行大小写不敏感的去重处理。
    """
    research_output = state["research_output"]
    scenario_titles = _collect_scenario_titles(research_output)

    # 取前两个约束条件作为场景的理由说明
    constraints_summary = "; ".join(research_output.constraints[:2])

    planned_scenarios = [
        PlannedScenario(
            title=title,
            category="functional",
            risk="medium",
            rationale=constraints_summary or "Derived from document research output.",
        )
        for title in scenario_titles
    ]
    return {"planned_scenarios": planned_scenarios}


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
