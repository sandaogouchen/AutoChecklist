from app.domain.case_models import TestCase
from app.domain.research_models import EvidenceRef, PlannedScenario, ResearchOutput
from app.nodes.draft_writer import DraftCaseCollection, build_draft_writer_node
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


class _RecordingLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return DraftCaseCollection(
            test_cases=[
                TestCase(
                    id="TC-001",
                    title="User logs in with SMS code",
                    preconditions=[],
                    steps=["Open login page"],
                    expected_results=["Dashboard is visible"],
                    priority="P1",
                    category="functional",
                    evidence_refs=[],
                )
            ]
        )


def test_draft_writer_prompt_requires_test_cases_wrapper() -> None:
    llm_client = _RecordingLLMClient()
    node = build_draft_writer_node(llm_client)
    state = {
        "planned_scenarios": [
            PlannedScenario(
                title="User logs in with SMS code",
                category="functional",
                risk="high",
                rationale="Core login flow",
            )
        ],
        "mapped_evidence": {
            "User logs in with SMS code": [
                EvidenceRef(
                    section_title="Acceptance Criteria",
                    excerpt="Successful login redirects to the dashboard.",
                    line_start=7,
                    line_end=10,
                    confidence=0.9,
                )
            ]
        },
    }

    result = node(state)

    assert result["draft_cases"][0].id == "TC-001"
    system_prompt = llm_client.calls[0]["system_prompt"]
    assert '{"test_cases": [...]}' in system_prompt
