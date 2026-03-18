from app.domain.case_models import TestCase
from app.domain.document_models import DocumentSource, ParsedDocument
from app.domain.research_models import ResearchOutput
from app.domain.state import GlobalState
from app.nodes.context_research import build_context_research_node
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


class _RecordingResearchLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return ResearchOutput()


def test_context_research_prompt_requires_compatibility_guidance() -> None:
    llm_client = _RecordingResearchLLMClient()
    node = build_context_research_node(llm_client)
    state: GlobalState = {
        "language": "zh-CN",
        "parsed_document": ParsedDocument(
            raw_text="# Title\ncontent",
            sections=[],
            references=[],
            metadata={},
            source=DocumentSource(
                source_path="/tmp/prd.md",
                source_type="markdown",
                title="Title",
                checksum="abc",
            ),
        ),
    }

    result = node(state)

    assert result["research_output"].facts == []
    system_prompt = llm_client.calls[0]["system_prompt"]
    assert "fact_id" in system_prompt
    assert "description" in system_prompt
    assert '"section_title"' in system_prompt
    assert '"excerpt"' in system_prompt
    assert '"line_start"' in system_prompt
    assert '"line_end"' in system_prompt
    assert '"confidence"' in system_prompt
    assert '"section"' in system_prompt
    assert '"quote"' in system_prompt
    assert "requirement must be a string" in system_prompt
