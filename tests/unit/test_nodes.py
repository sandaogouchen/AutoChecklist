from app.domain.case_models import TestCase
from app.domain.research_models import ResearchOutput
from app.nodes.reflection import deduplicate_cases
from app.nodes.scenario_planner import scenario_planner_node


def test_deduplicate_cases_removes_identical_titles() -> None:
    case_a = TestCase(
        id="TC-1",
        title="Login succeeds",
        preconditions=[],
        steps=["Open login page"],
        expected_results=["Dashboard is visible"],
        priority="P1",
        category="functional",
        evidence_refs=[],
    )
    case_b = TestCase(
        id="TC-2",
        title="Login succeeds",
        preconditions=[],
        steps=["Open login page"],
        expected_results=["Dashboard is visible"],
        priority="P1",
        category="functional",
        evidence_refs=[],
    )

    deduped, report = deduplicate_cases([case_a, case_b])

    assert len(deduped) == 1
    assert report.duplicate_groups == [["TC-1", "TC-2"]]


def test_scenario_planner_uses_research_scenarios() -> None:
    state = {
        "research_output": ResearchOutput(
            feature_topics=["Login"],
            user_scenarios=["User logs in with SMS code"],
            constraints=["SMS code expires in 5 minutes"],
            ambiguities=[],
            test_signals=["success path"],
        )
    }

    result = scenario_planner_node(state)

    assert result["planned_scenarios"]
    assert result["planned_scenarios"][0].title == "User logs in with SMS code"


def test_deduplicate_preserves_checkpoint_id() -> None:
    """去重后的用例应保留 checkpoint_id。"""
    case = TestCase(
        id="TC-1",
        title="Login succeeds",
        steps=["Open login page"],
        expected_results=["Dashboard is visible"],
        checkpoint_id="CP-abc123",
    )

    deduped, _ = deduplicate_cases([case])

    assert len(deduped) == 1
    assert deduped[0].checkpoint_id == "CP-abc123"
