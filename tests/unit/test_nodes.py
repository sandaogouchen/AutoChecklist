from app.domain.case_models import TestCase
from app.domain.document_models import DocumentSource, ParsedDocument
from app.domain.research_models import EvidenceRef, PlannedScenario, ResearchOutput
from app.domain.state import GlobalState
from app.nodes.context_research import build_context_research_node
from app.nodes.draft_writer import DraftCaseCollection, build_draft_writer_node
from app.nodes.reflection import deduplicate_cases
from app.nodes.scenario_planner import scenario_planner_node
from app.nodes.structure_assembler import structure_assembler_node


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


def test_scenario_planner_prioritizes_research_facts() -> None:
    state = {
        "research_output": ResearchOutput.model_validate(
            {
                "feature_topics": ["Campaign"],
                "user_scenarios": ["Create ad group"],
                "constraints": ["Optimize Goal must be editable during creation"],
                "ambiguities": [],
                "test_signals": ["selection path"],
                "facts": [
                    {
                        "id": "FACT-001",
                        "summary": "Advertiser can select Optimize Goal during ad group creation",
                        "change_type": "behavior",
                        "requirement": "Optimize Goal is independently selectable in ad group creation flow",
                        "branch_hint": "choice",
                        "evidence_refs": [],
                    }
                ],
            }
        )
    }

    result = scenario_planner_node(state)

    assert result["planned_scenarios"]
    planned = result["planned_scenarios"][0]
    assert hasattr(planned, "fact_id")
    assert planned.fact_id == "FACT-001"
    assert planned.title == "Advertiser can select Optimize Goal during ad group creation"


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


class _RecordingResearchLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return ResearchOutput()


def test_context_research_prompt_requires_canonical_evidence_ref_shape() -> None:
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
    assert '"section_title"' in system_prompt
    assert '"excerpt"' in system_prompt
    assert '"line_start"' in system_prompt
    assert '"line_end"' in system_prompt
    assert '"confidence"' in system_prompt
    assert '"section"' in system_prompt
    assert '"quote"' in system_prompt
    assert "`requirement`" in system_prompt
    assert "string, not an object" in system_prompt


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
    assert '"evidence_refs"' in system_prompt
    assert "array of objects" in system_prompt
    assert '"branch"' in system_prompt
    assert '"parent"' in system_prompt
    assert '"root"' in system_prompt
    assert '"prev"' in system_prompt
    assert '"next"' in system_prompt


def test_draft_writer_batches_large_scenario_sets() -> None:
    llm_client = _RecordingLLMClient()
    node = build_draft_writer_node(llm_client, batch_size=2)
    state = {
        "planned_scenarios": [
            PlannedScenario(
                title=f"Scenario {index}",
                fact_id=f"FACT-{index:03d}",
                category="functional",
                risk="medium",
                rationale=f"Rationale {index}",
            )
            for index in range(1, 6)
        ],
        "mapped_evidence": {},
    }

    result = node(state)

    assert len(llm_client.calls) == 3
    assert len(result["draft_cases"]) == 3
    assert llm_client.calls[0]["user_prompt"].count("Fact ID:") == 2
    assert llm_client.calls[1]["user_prompt"].count("Fact ID:") == 2
    assert llm_client.calls[2]["user_prompt"].count("Fact ID:") == 1


def test_structure_assembler_builds_bidirectional_fact_tree() -> None:
    result = structure_assembler_node(
        {
            "draft_cases": [
                TestCase.model_validate(
                    {
                        "id": "",
                        "fact_id": "FACT-001",
                        "node_type": "root",
                        "title": "Optimize Goal selection checklist",
                        "branch": "main",
                        "parent": None,
                        "root": None,
                        "prev": None,
                        "next": None,
                        "preconditions": ["Advertiser has access to campaign creation"],
                        "steps": ["Open ad group creation"],
                        "expected_results": ["Optimize Goal field is visible"],
                        "priority": "P1",
                        "category": "functional",
                        "evidence_refs": [],
                    }
                ),
                TestCase.model_validate(
                    {
                        "id": "",
                        "fact_id": "FACT-001",
                        "node_type": "check",
                        "title": "Select an Optimize Goal value",
                        "branch": "main",
                        "parent": "FACT-001-ROOT",
                        "root": "FACT-001-ROOT",
                        "prev": None,
                        "next": None,
                        "preconditions": [],
                        "steps": ["Choose an Optimize Goal option"],
                        "expected_results": ["The chosen Optimize Goal is selected"],
                        "priority": "P1",
                        "category": "functional",
                        "evidence_refs": [],
                    }
                ),
                TestCase.model_validate(
                    {
                        "id": "",
                        "fact_id": "FACT-001",
                        "node_type": "check",
                        "title": "Persist the selected Optimize Goal",
                        "branch": "main",
                        "parent": "FACT-001-ROOT",
                        "root": "FACT-001-ROOT",
                        "prev": None,
                        "next": None,
                        "preconditions": [],
                        "steps": ["Save the ad group"],
                        "expected_results": ["The selected Optimize Goal persists on details page"],
                        "priority": "P1",
                        "category": "functional",
                        "evidence_refs": [],
                    }
                ),
            ],
            "mapped_evidence": {},
        }
    )

    root = result["test_cases"][0]

    assert hasattr(root, "children")
    assert root.root == root.id
    assert len(root.children) == 2
    assert root.children[0].parent == root.id
    assert root.children[0].next == root.children[1].id
    assert root.children[1].prev == root.children[0].id
