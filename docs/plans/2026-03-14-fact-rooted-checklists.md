# Fact-Rooted Checklists Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate checklist output from explicit PRD facts instead of broad scenarios, and persist a fact-rooted doubly linked checklist graph in `test_cases.json`.

**Architecture:** The workflow keeps the same top-level graph, but upgrades the case-generation subgraph to operate on `ResearchFact -> PlannedChecklist -> ChecklistNode` instead of `ResearchOutput.user_scenarios -> TestCase`. `structure_assembler` becomes the normalization point that repairs links, assigns ids, and emits graph-safe root nodes for rendering and persistence.

**Tech Stack:** Python 3.11, LangGraph, Pydantic v2, pytest

---

### Task 1: Add Fact And Checklist Models

**Files:**
- Modify: `app/domain/research_models.py`
- Modify: `app/domain/case_models.py`
- Modify: `app/domain/state.py`
- Test: `tests/unit/test_nodes.py`

**Step 1: Write the failing test**

```python
def test_scenario_planner_creates_planned_checklists_from_research_facts() -> None:
    state = {
        "research_output": ResearchOutput(
            feature_topics=[],
            user_scenarios=[],
            constraints=[],
            ambiguities=[],
            test_signals=[],
            facts=[
                ResearchFact(
                    id="FACT-001",
                    summary="Advertiser can select optimize goal during ad group creation",
                    change_type="behavior",
                    requirement="Optimize Goal must be selectable in creation flow",
                    branch_hint="choice",
                    evidence_refs=[],
                )
            ],
        )
    }

    result = scenario_planner_node(state)

    assert result["planned_scenarios"][0].fact_id == "FACT-001"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_nodes.py::test_scenario_planner_creates_planned_checklists_from_research_facts -v`
Expected: FAIL because `ResearchFact` and `fact_id` do not exist.

**Step 3: Write minimal implementation**

Add `ResearchFact`, `PlannedChecklist`, and `ChecklistNode` models. Extend workflow state so planned and drafted outputs can carry fact ids and graph nodes end to end.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_nodes.py::test_scenario_planner_creates_planned_checklists_from_research_facts -v`
Expected: PASS

### Task 2: Extract And Plan From Facts

**Files:**
- Modify: `app/nodes/context_research.py`
- Modify: `app/nodes/scenario_planner.py`
- Modify: `tests/conftest.py`
- Test: `tests/unit/test_nodes.py`

**Step 1: Write the failing test**

```python
def test_scenario_planner_falls_back_to_feature_topics_when_no_facts_exist() -> None:
    result = scenario_planner_node(
        {
            "research_output": ResearchOutput(
                feature_topics=["Login"],
                user_scenarios=[],
                constraints=[],
                ambiguities=[],
                test_signals=[],
                facts=[],
            )
        }
    )

    assert result["planned_scenarios"][0].title == "Validate Login"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_nodes.py::test_scenario_planner_falls_back_to_feature_topics_when_no_facts_exist -v`
Expected: FAIL if planner assumes facts always exist or returns wrong shape.

**Step 3: Write minimal implementation**

Update research prompting to request structured facts. Plan from facts first, then fall back to scenarios or feature topics only when facts are absent.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_nodes.py -v`
Expected: PASS

### Task 3: Draft Checklist Nodes Instead Of Flat Cases

**Files:**
- Modify: `app/nodes/draft_writer.py`
- Modify: `tests/unit/test_nodes.py`
- Test: `tests/unit/test_llm_client.py`

**Step 1: Write the failing test**

```python
def test_draft_writer_prompt_requires_graph_fields() -> None:
    ...
    assert '"branch"' in system_prompt
    assert '"parent"' in system_prompt
    assert '"root"' in system_prompt
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_nodes.py::test_draft_writer_prompt_requires_graph_fields -v`
Expected: FAIL because the prompt only asks for flat test cases.

**Step 3: Write minimal implementation**

Change the draft response model to checklist nodes and require graph linkage fields in the system prompt. Keep evidence refs as object arrays.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_nodes.py::test_draft_writer_prompt_requires_graph_fields -v`
Expected: PASS

### Task 4: Assemble Doubly Linked Fact Trees

**Files:**
- Modify: `app/nodes/structure_assembler.py`
- Modify: `app/nodes/reflection.py`
- Test: `tests/unit/test_nodes.py`

**Step 1: Write the failing test**

```python
def test_structure_assembler_builds_doubly_linked_fact_tree() -> None:
    result = structure_assembler_node({...})
    root = result["test_cases"][0]
    assert root.root == root.id
    assert root.children[0].parent == root.id
    assert root.children[0].next == root.children[1].id
    assert root.children[1].prev == root.children[0].id
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_nodes.py::test_structure_assembler_builds_doubly_linked_fact_tree -v`
Expected: FAIL because the assembler only normalizes flat cases.

**Step 3: Write minimal implementation**

Normalize ids, backfill root and parent ids, sort siblings deterministically, and wire `prev/next` per sibling list. Reflection should report missing facts and broken links as warnings.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_nodes.py::test_structure_assembler_builds_doubly_linked_fact_tree -v`
Expected: PASS

### Task 5: Persist And Render The New Output Shape

**Files:**
- Modify: `app/domain/output_models.py`
- Modify: `tests/unit/test_output_nodes.py`
- Modify: `tests/integration/test_workflow.py`

**Step 1: Write the failing test**

```python
def test_output_bundle_writes_fact_rooted_checklists(tmp_path) -> None:
    payload = read_json(tmp_path / "run-1" / "test_cases.json")
    assert payload[0]["children"]
    assert payload[0]["root"] == payload[0]["id"]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_output_nodes.py tests/integration/test_workflow.py -v`
Expected: FAIL because serialization still assumes flat cases.

**Step 3: Write minimal implementation**

Render markdown grouped by fact root, serialize checklist trees to JSON, and keep `run_result.json` as the existing lightweight summary.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_output_nodes.py tests/integration/test_workflow.py -v`
Expected: PASS
