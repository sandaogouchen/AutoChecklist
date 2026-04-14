# Actionable Checklist Path Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade `optimized_tree` into an actionable checklist path tree while preserving Markdown/XMind compatibility.

**Architecture:** Keep `checkpoint_outline_planner` as the stable skeleton builder, then inject testcase `preconditions + steps + expected_results` back into the planned tree during `structure_assembler`. Reuse existing `optimized_tree` rendering entrypoints and use project-context metadata as lightweight ontology hints for Phase 1.

**Tech Stack:** Python, Pydantic, FastAPI, LangGraph, pytest

---

### Task 1: Lock Phase 1 Behavior With Tests

**Files:**
- Modify: `tests/unit/test_checkpoint_outline_planner.py`
- Modify: `tests/unit/test_draft_writer.py`
- Modify: `tests/unit/test_markdown_renderer.py`
- Create or Modify: `tests/unit/test_structure_assembler.py`

**Step 1: Write the failing tests**

Cover:

1. outline planner prompt and fallback behavior prefer actionable Chinese path nodes
2. `structure_assembler` injects `preconditions + steps + expected_results` into `optimized_tree`
3. identical preconditions / steps deduplicate under the same branch
4. markdown tree rendering still works on the new actionable tree

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_checkpoint_outline_planner.py tests/unit/test_draft_writer.py tests/unit/test_markdown_renderer.py tests/unit/test_structure_assembler.py -q`

Expected: FAIL because actionable path injection is not implemented yet.

### Task 2: Extend Project Context For Lightweight Ontology Hints

**Files:**
- Modify: `app/domain/project_models.py`
- Modify: `app/services/project_context_service.py`
- Modify: `tests/unit/test_project_context_service.py`
- Modify: `tests/unit/test_project_routes.py`

**Step 1: Add summary support for checklist path metadata**

Allow `ProjectContext.summary_text()` to surface structured hints stored in `metadata`, such as:

- `checklist_path_hints`
- `ontology_hints`
- alias/canonical examples

**Step 2: Keep API compatibility**

Do not introduce new top-level API fields in Phase 1; reuse existing `metadata`.

**Step 3: Run focused tests**

Run: `uv run pytest tests/unit/test_project_context_service.py tests/unit/test_project_routes.py -q`

Expected: PASS after implementation.

### Task 3: Make Outline Planning More Actionable

**Files:**
- Modify: `app/services/checkpoint_outline_planner.py`
- Modify: `app/nodes/draft_writer.py`
- Modify: `tests/unit/test_checkpoint_outline_planner.py`
- Modify: `tests/unit/test_draft_writer.py`

**Step 1: Tighten planner prompts**

Update prompt rules so visible nodes prefer:

1. business object noun at top level
2. Chinese precondition/page-entry sentences
3. Chinese actionable operation phrases

**Step 2: Improve fallback path generation**

When LLM mapping is incomplete, fallback path should preserve checkpoint preconditions and title in actionable order rather than emitting generic abstractions.

**Step 3: Include project-context structure hints in outline planning if available**

Pass `project_context_summary` into outline planning prompts so project-specific hierarchy hints influence skeleton generation.

### Task 4: Attach Actionable Testcase Paths Into `optimized_tree`

**Files:**
- Modify: `app/services/checkpoint_outline_planner.py`
- Modify: `app/nodes/structure_assembler.py`
- Modify: `app/domain/checklist_models.py`
- Create or Modify: `tests/unit/test_structure_assembler.py`

**Step 1: Add optional node metadata**

Support lightweight internal metadata on `ChecklistNode` for path role / normalized merge key if needed, while keeping existing external fields stable.

**Step 2: Replace leaf-only attachment with full actionable attachment**

Implement attachment logic that:

1. finds the visible outline path for a testcase
2. appends normalized testcase preconditions under that path
3. appends normalized testcase steps under the deepest matching node
4. attaches expected results under the final action node

**Step 3: Merge repeated actionable nodes**

Deduplicate equivalent siblings by normalized text so shared prefixes remain shared.

### Task 5: Verify End-to-End Compatibility

**Files:**
- No new files required unless a regression fix is needed

**Step 1: Run focused workflow tests**

Run: `uv run pytest tests/unit/test_checkpoint_outline_planner.py tests/unit/test_draft_writer.py tests/unit/test_structure_assembler.py tests/unit/test_markdown_renderer.py tests/unit/test_xmind_delivery.py tests/unit/test_project_context_service.py tests/unit/test_project_routes.py -q`

**Step 2: Run workflow integration tests**

Run: `uv run pytest tests/integration/test_workflow.py tests/integration/test_project_workflow.py tests/integration/test_api.py -q`

**Step 3: Review outputs**

Confirm:

1. `optimized_tree` still exists
2. Markdown tree mode renders actionable nodes
3. XMind tree mode renders actionable nodes
4. flat mode fallback still works
