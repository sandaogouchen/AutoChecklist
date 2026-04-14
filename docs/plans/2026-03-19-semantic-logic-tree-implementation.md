# Semantic Logic Tree Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace keyword grouping with an LLM-normalized semantic logic tree that merges shared preconditions/actions and renders only expected-result leaves.

**Architecture:** Add a two-stage LLM semantic path normalizer that first builds shared canonical logic nodes and then maps each test case into an ordered semantic path. Feed those normalized paths into a trie merger that emits a `ChecklistNode` tree containing only shared operation groups and expected-result leaves. Update markdown and XMind tree rendering to remove case summary nodes.

**Tech Stack:** Python, Pydantic, LangGraph, existing `LLMClient`, pytest

---

### Task 1: Lock New Tree Shape With Tests

**Files:**
- Modify: `tests/unit/test_markdown_renderer.py`
- Modify: `tests/unit/test_xmind_delivery.py`
- Create: `tests/unit/test_semantic_path_normalizer.py`

**Step 1: Write failing tests for tree rendering**

Cover:
- optimized tree renders only shared path nodes plus expected-result leaves
- markdown output does not contain `[TC-xxx]` or case titles
- xmind tree mode does not emit case summary nodes

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_markdown_renderer.py tests/unit/test_xmind_delivery.py tests/unit/test_semantic_path_normalizer.py -q`

**Step 3: Commit after tests are green later**

Commit message: `test: lock semantic logic tree rendering`

### Task 2: Add LLM Semantic Path Normalizer

**Files:**
- Create: `app/services/semantic_path_normalizer.py`
- Modify: `tests/conftest.py`

**Step 1: Add structured models for canonical nodes and semantic paths**

Need:
- `SemanticNode`
- `SemanticNodeCollection`
- `SemanticPathItem`
- `SemanticPathCollection`

**Step 2: Implement two-stage normalization**

Stage A:
- ask LLM for shared canonical nodes, aliases, hidden anchors

Stage B:
- ask LLM to map each test case into ordered canonical path node ids

**Step 3: Add deterministic fake responses in test fixtures**

Support new response models in `FakeLLMClient` and `FakeLLMClientLowQuality`.

**Step 4: Commit after tests are green later**

Commit message: `feat: add semantic path normalizer`

### Task 3: Replace Optimizer Output Builder

**Files:**
- Modify: `app/nodes/checklist_optimizer.py`
- Modify: `app/graphs/case_generation.py`
- Modify: `app/domain/checklist_models.py`
- Modify: `app/services/checklist_merger.py`
- Modify: `tests/unit/test_checklist_optimizer.py`

**Step 1: Update checklist models**

Support at least:
- `root`
- `group`
- `expected_result`

Keep compatibility fields if helpful for existing code paths.

**Step 2: Convert optimizer to factory**

Implement `build_checklist_optimizer_node(llm_client)` and inject it from the graph builder.

**Step 3: Make merger consume normalized semantic paths**

Output tree should contain:
- shared group nodes
- expected-result leaves only

No case summary nodes in optimized tree.

**Step 4: Commit after tests are green later**

Commit message: `feat: build semantic logic tree`

### Task 4: Update Markdown and XMind Rendering

**Files:**
- Modify: `app/services/markdown_renderer.py`
- Modify: `app/services/xmind_payload_builder.py`

**Step 1: Render recursive group nodes**

Group nodes should render as shared path hierarchy.

**Step 2: Render expected-result leaves only**

Do not show case titles in tree mode.

**Step 3: Commit after tests are green later**

Commit message: `feat: render semantic logic tree outputs`

### Task 5: Verify With Unit Tests and Real Sample Preview

**Files:**
- No code changes required unless verification reveals defects

**Step 1: Run focused unit tests**

Run: `uv run pytest tests/unit/test_semantic_path_normalizer.py tests/unit/test_checklist_optimizer.py tests/unit/test_markdown_renderer.py tests/unit/test_xmind_delivery.py -q`

**Step 2: Run workflow-facing verification**

Run: `uv run pytest tests/integration/test_workflow.py tests/integration/test_api.py -q`

**Step 3: Generate a preview XMind from the real sample**

Use the current sample `output/runs/2026-03-19_16-38-43/test_cases.json` to build a preview file and inspect the resulting top-level tree.

**Step 4: Commit**

Commit message: `feat: merge checklist into semantic logic tree`
