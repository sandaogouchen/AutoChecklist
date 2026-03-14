from __future__ import annotations

from app.domain.research_models import PlannedScenario, ResearchOutput
from app.domain.state import GlobalState


def scenario_planner_node(state: GlobalState) -> GlobalState:
    research_output = state["research_output"]
    planned_scenarios = _collect_planned_scenarios(research_output)
    return {"planned_scenarios": planned_scenarios}


def _collect_planned_scenarios(research_output: ResearchOutput) -> list[PlannedScenario]:
    constraints = "; ".join(research_output.constraints[:2])
    if research_output.facts:
        return [
            PlannedScenario(
                title=fact.summary.strip(),
                fact_id=fact.id.strip(),
                category="functional",
                risk="high" if fact.branch_hint.strip() and fact.branch_hint.strip() != "main" else "medium",
                rationale=fact.requirement.strip() or constraints or "Derived from document research output.",
                branch_hint=fact.branch_hint.strip() or "main",
            )
            for fact in research_output.facts
            if fact.summary.strip()
        ]

    scenario_titles = _collect_scenario_titles(research_output)
    return [
        PlannedScenario(
            title=title,
            category="functional",
            risk="medium",
            rationale=constraints or "Derived from document research output.",
        )
        for title in scenario_titles
    ]


def _collect_scenario_titles(research_output: ResearchOutput) -> list[str]:
    titles = [title.strip() for title in research_output.user_scenarios if title.strip()]
    if titles:
        return _dedupe_preserving_order(titles)

    derived = [f"Validate {topic}" for topic in research_output.feature_topics if topic.strip()]
    return _dedupe_preserving_order(derived) or ["Validate core workflow"]


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped
