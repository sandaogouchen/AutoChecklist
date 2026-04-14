# Checkpoint Outline Planner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move checklist hierarchy planning from post-testcase optimization to a pre-draft checkpoint-outline planning stage so the generated checklist is business-object-first and structurally stable.

**Architecture:** Insert a new `checkpoint_outline_planner` node after `checkpoint_evaluator` and before `draft_writer`. This node uses LLM prompts to build canonical visible business-object nodes and map each checkpoint onto a fixed path, then deterministically builds `optimized_tree` before testcase drafting. `draft_writer` becomes path-constrained: it writes leaf-level steps and expected results under an already planned hierarchy instead of inventing grouping phrases.

**Tech Stack:** Python, Pydantic, LangGraph, existing `LLMClient`, pytest

---

### Task 1: Lock The New Hierarchy Contract With Tests

**Files:**
- Create: `tests/unit/test_checkpoint_outline_planner.py`
- Modify: `tests/unit/test_markdown_renderer.py`
- Modify: `tests/unit/test_xmind_delivery.py`
- Modify: `tests/conftest.py`

**Step 1: Write failing tests for pre-draft outline planning**

Cover:
- outline planner outputs a visible `Ad group` parent node for both `CBO` and `launch 前/后` contexts
- context nodes are attached under the nearest business object instead of becoming top-level siblings
- `optimized_tree` can be rendered before testcase drafting is complete

**Step 2: Write failing tests for constrained draft writing expectations**

Cover:
- when path context already includes `Ad group` and `launch 前`, draft output must not restate them as a merged parent phrase
- tree-mode markdown does not emit testcase summary layers in the new flow

**Step 3: Add fake LLM fixture responses**

Extend `tests/conftest.py` to support:
- canonical outline node planning response
- checkpoint-to-path mapping response
- draft writer response that respects supplied path context

**Step 4: Run targeted tests to verify failure**

Run: `uv run pytest tests/unit/test_checkpoint_outline_planner.py tests/unit/test_markdown_renderer.py tests/unit/test_xmind_delivery.py -q`

**Step 5: Commit after tests are green later**

Commit message: `test: lock pre-draft checklist hierarchy`

### Task 2: Add Checkpoint Outline Planning Models And Service

**Files:**
- Create: `app/services/checkpoint_outline_planner.py`
- Modify: `app/domain/state.py`
- Modify: `app/domain/checklist_models.py`

**Step 1: Add structured planning models**

Define models for:
- canonical outline nodes
- checkpoint path mappings
- optional visibility enum such as `visible`, `required`, `hidden`

Keep them near the planner service unless reuse pressure justifies a new domain module.

**Step 2: Implement the two-stage planner**

Stage A: canonical node planning
- input: `research_output.facts` + `checkpoints`
- output: reusable nodes centered on business objects such as `Campaign`, `Ad group`, `Creative`, `Reporting`, `TTMS account`

Stage B: checkpoint path mapping
- input: canonical nodes + checkpoints
- output: ordered path for each checkpoint

**Step 3: Deterministically build `optimized_tree` from checkpoint paths**

Rules:
- visible business objects must remain visible parents
- context/page/action nodes are merged by shared prefix
- expected results are not generated here
- keep `optimized_tree` as the external field name to minimize downstream churn

**Step 4: Add state fields needed by downstream nodes**

Add internal fields to `CaseGenState` and `GlobalState`:
- `checkpoint_paths`
- optional `canonical_outline_nodes`

Retain existing `optimized_tree` field as the rendered/shared hierarchy artifact.

**Step 5: Commit after tests are green later**

Commit message: `feat: add checkpoint outline planner`

### Task 3: Rewire The Case Generation Graph

**Files:**
- Modify: `app/graphs/case_generation.py`
- Modify: `app/graphs/main_workflow.py`
- Modify: `app/nodes/checklist_optimizer.py`

**Step 1: Insert the new node before draft generation**

New order:
`scenario_planner -> checkpoint_generator -> checkpoint_evaluator -> checkpoint_outline_planner -> evidence_mapper -> draft_writer -> structure_assembler`

**Step 2: Preserve compatibility for `optimized_tree` consumers**

Do not change:
- markdown renderer input contract
- XMind payload builder input contract
- platform dispatcher artifact names

`optimized_tree` should now come from `checkpoint_outline_planner`, not from post-hoc testcase optimization.

**Step 3: Decide the fate of `checklist_optimizer`**

Recommended phase 1:
- remove it from the default graph
- keep the module as a compatibility fallback or feature-flagged experiment until the new path is stable

Avoid running both planners in sequence by default, because that reintroduces post-hoc shape drift.

**Step 4: Commit after tests are green later**

Commit message: `refactor: move checklist planning before draft generation`

### Task 4: Constrain Draft Writer To The Planned Hierarchy

**Files:**
- Modify: `app/nodes/draft_writer.py`
- Modify: `tests/unit/test_draft_writer.py`

**Step 1: Change draft writer input shape**

For each checkpoint, pass:
- checkpoint metadata
- checkpoint-specific path context
- brief sibling context only if needed

Do not ask the LLM to invent grouping layers.

**Step 2: Rewrite prompt responsibilities**

The prompt must clearly separate:
- fixed path context provided by the system
- leaf work the model is allowed to generate

Allowed output:
- testcase title
- concrete steps
- expected results

Disallowed output:
- merged parent phrases like `处于 CBO 的 Ad group 配置场景`
- restating already supplied business-object hierarchy
- creating case-summary headings

**Step 3: Keep preconditions lean**

Once hierarchy is planned earlier, `preconditions` should no longer be the main grouping carrier.
Use them only for execution prerequisites that truly belong inside the leaf testcase.

**Step 4: Commit after tests are green later**

Commit message: `feat: constrain draft writer by planned hierarchy`

### Task 5: Adjust Renderers Only Where Necessary

**Files:**
- Modify: `app/services/markdown_renderer.py`
- Modify: `app/services/xmind_payload_builder.py`
- Modify: `app/services/platform_dispatcher.py`

**Step 1: Keep tree rendering API stable**

Continue to render from `optimized_tree`.

**Step 2: Audit assumptions that tree nodes are post-testcase artifacts**

Check for any code that assumes:
- expected-result leaves already exist in `optimized_tree`
- tree generation happened after `test_cases`

If needed, allow `draft_writer` or `structure_assembler` to attach final expected-result leaves to the existing tree without changing top-level structure.

**Step 3: Keep artifact naming stable**

Do not rename:
- `test_cases.md`
- `optimized_tree`
- XMind tree mode entrypoint

This reduces rollout cost and avoids repository-wide renames.

**Step 4: Commit after tests are green later**

Commit message: `refactor: preserve renderer contracts for pre-draft tree`

### Task 6: Add Prompt Packs For The New Planner

**Files:**
- Modify: `app/services/checkpoint_outline_planner.py`
- Modify: `app/nodes/draft_writer.py`

**Step 1: Add canonical node planning prompt**

Prompt requirements:
- business-object-first hierarchy
- mandatory split for mixed object+state phrases
- visible parent requirement for core objects like `Campaign`, `Ad group`, `Creative`, `Reporting`
- no testcase summary nodes

**Step 2: Add checkpoint path mapping prompt**

Prompt requirements:
- every checkpoint path must include the nearest visible business object
- lifecycle/context/page nodes must sit under that object
- reuse only provided canonical node ids

**Step 3: Tighten draft writer prompt**

Prompt requirements:
- treat provided path as fixed hierarchy
- generate only leaf-level operations and expected results
- forbid regeneration of grouping phrases

**Step 4: Commit after tests are green later**

Commit message: `feat: add pre-draft hierarchy prompts`

### Task 7: Verification And Rollout

**Files:**
- No code changes required unless verification reveals defects

**Step 1: Run focused unit tests**

Run: `uv run pytest tests/unit/test_checkpoint_outline_planner.py tests/unit/test_draft_writer.py tests/unit/test_markdown_renderer.py tests/unit/test_xmind_delivery.py tests/unit/test_checklist_optimizer.py -q`

**Step 2: Run workflow-level verification**

Run: `uv run pytest tests/integration/test_workflow.py tests/integration/test_api.py -q`

**Step 3: Run a real PRD sample through the workflow**

Use the current CADS sample and inspect whether:
- `Ad group` becomes an explicit visible parent
- `CBO 场景` and `launch 前/后` become child contexts
- no new `[TC-xxx]` summary layer appears in tree output

**Step 4: Validate migration safety**

Check:
- markdown artifact still renders
- XMind delivery still works
- quality report still references the same `test_cases`

**Step 5: Commit**

Commit message: `feat: move checklist hierarchy planning ahead of drafting`

### Prompt Drafts To Use During Implementation

**Outline planner: canonical nodes**

```text
You are planning a shared QA checklist hierarchy before testcase generation.

Goal:
Create a stable, business-object-first hierarchy from product checkpoints.

Hard rules:
- Build visible business-object nodes first. Typical objects include Campaign, Ad group, Creative, Reporting, TTMS account, optimize goal, secondary goal, CTA, CBO.
- Do NOT create testcase summary nodes such as "[TC-001] ..." or "验证xxx".
- Do NOT hide core business objects like Campaign / Ad group / Creative / Reporting.
- If a phrase mixes object + state, split it into object node then context node.

Mandatory split examples:
- "处于 CBO 的 Ad group 配置场景" => "Ad group" -> "CBO 配置场景"
- "Ad group 处于 launch 前" => "Ad group" -> "launch 前"
- "进入 Create Ad Group 页面" => "Ad group" -> "Create Ad Group 页面"

Preferred order:
system/environment -> user state -> business object -> lifecycle/context/page -> focused operation
```

**Outline planner: checkpoint path mapping**

```text
Map each checkpoint to an ordered hierarchy path using ONLY the provided canonical nodes.

Hard rules:
- Every path must include its nearest visible business-object node.
- Context nodes such as "CBO 场景", "launch 前", "已 launch", "历史 campaign" must appear under that object node.
- Page nodes such as "Create Ad Group 页面", "详情/编辑页", "creative 页面" must not float above the object node.
- Do not create testcase titles.
- Do not create expected results.
- Do not invent new node ids.
```

**Draft writer: constrained leaf generation**

```text
You are writing testcase leaves for an already planned hierarchy.

You MUST treat the provided path as fixed.
You are NOT allowed to create new parent groups or restate parent groups as a merged phrase.

Allowed output:
- testcase title
- concrete steps
- expected results

Forbidden output:
- merged parent phrases like "处于 CBO 的 Ad group 配置场景"
- regenerating object/context hierarchy that already exists in the supplied path
- testcase summary headings
```
