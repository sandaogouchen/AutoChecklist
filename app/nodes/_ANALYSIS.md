# app/nodes/ Directory Analysis

> Auto-generated analysis for the LangGraph pipeline nodes of AutoChecklist

## §7.1 Directory Overview

| Property | Value |
|----------|-------|
| Path | `app/nodes/` |
| Total Files | 18 |
| Total Lines | 4,178 |
| Main Purpose | LangGraph workflow node implementations |

All 18 files implement pipeline steps for AutoChecklist's LangGraph-based test case generation workflow. Nodes follow a consistent pattern: a factory function (`build_*_node()`) captures dependencies (typically `LLMClient`) via closure and returns a callable with signature `(state: dict) -> dict` that reads from and writes incremental updates to a shared `CaseGenState` or `GlobalState`.

**Line counts by file:**

| File | Lines | Category |
|------|-------|----------|
| `mr_analyzer.py` | 763 | MR analysis (largest) |
| `draft_writer.py` | 518 | Draft generation |
| `checkpoint_generator.py` | 514 | Checkpoint generation |
| `coco_consistency_validator.py` | 393 | Code consistency |
| `evaluation.py` | 351 | Quality evaluation |
| `structure_assembler.py` | 321 | Structure assembly (CRITICAL) |
| `mr_checkpoint_injector.py` | 308 | MR checkpoint injection |
| `reflection.py` | 203 | Quality reflection |
| `scenario_planner.py` | 124 | Scenario planning |
| `knowledge_retrieval.py` | 99 | Knowledge retrieval |
| `context_research.py` | 92 | Context research |
| `project_context_loader.py` | 89 | Project context |
| `xmind_reference_loader.py` | 85 | XMind reference loading |
| `evidence_mapper.py` | 79 | Evidence mapping |
| `template_loader.py` | 73 | Template loading |
| `checklist_optimizer.py` | 60 | Checklist optimization (CRITICAL/ORPHANED) |
| `input_parser.py` | 54 | Input parsing |
| `checkpoint_evaluator.py` | 52 | Checkpoint evaluation |

---

## §7.2 Pipeline Execution Order

The pipeline is split into a **main workflow** (defined in `graphs/main_workflow.py`) and a **case generation subgraph** (defined in `graphs/case_generation.py`).

### §7.2.1 Main Workflow (GlobalState)

```
START
  → input_parser                    # Parse PRD document
  → template_loader                 # Load project checklist template
  → [xmind_reference_loader]       # Optional: load XMind reference
  → [project_context_loader]       # Optional: load project context
  → [knowledge_retrieval]          # Optional: GraphRAG knowledge retrieval
  → context_research               # LLM-based PRD context extraction
  → case_generation (subgraph)     # ← Entire subgraph invoked as one node
  → reflection                     # Quality check and deduplication
  → END
```

Nodes in brackets `[]` are optional -- added to the graph only when their factory dependencies are provided.

### §7.2.2 Case Generation Subgraph (CaseGenState)

```
START
  → mr_analyzer                    # MR diff analysis + agentic code search
  → mr_checkpoint_injector         # Convert MR code facts → checkpoints
  → scenario_planner               # Plan test scenarios from research output
  → checkpoint_generator           # Convert facts → explicit checkpoints (LLM)
  → checkpoint_evaluator           # Deduplicate checkpoints, init coverage
  → coverage_detector              # Detect checkpoint/XMind leaf coverage
  → checkpoint_outline_planner     # Build shared hierarchy (optimized_tree) ← SERVICE, not in nodes/
  → evidence_mapper                # Map scenarios to PRD evidence
  → draft_writer                   # Generate test case drafts (LLM)
  → coco_consistency_validator     # Optional: Coco Agent code consistency check
  → structure_assembler            # Standardize, assemble, enforce constraints
  → END
```

**Critical observation:** `checklist_optimizer.py` is **NOT registered** in either graph. It is an orphaned file. The `optimized_tree` is now produced by `checkpoint_outline_planner` (a service in `services/`) and then rewritten by `structure_assembler`. See §7.3.1 for detailed analysis.

### §7.2.3 State Bridge

The subgraph is connected to the main graph via `state_bridge.build_bridge()`, which:
- **Inbound (main → sub):** Auto-forwards shared keys from `GlobalState` to `CaseGenState`
- **Outbound (sub → main):** Explicit allowlist: `{planned_scenarios, checkpoints, checkpoint_coverage, draft_cases, test_cases, optimized_tree, coverage_result}`

---

## §7.3 File Analysis

### §7.3.1 checklist_optimizer.py -- CRITICAL / ORPHANED

| Property | Value |
|----------|-------|
| Lines | 60 |
| Type | A -- core pipeline node (ORPHANED) |
| State | `CaseGenState` |
| Input | `test_cases` |
| Output | `test_cases`, `optimized_tree` |
| Dependencies | `SemanticPathNormalizer`, `ChecklistMerger`, `LLMClient` |
| Registered in graph | **NO -- not registered in any graph** |

#### Detailed Analysis

This file is **the most critical finding in the entire nodes layer**. Despite being documented as a core pipeline node that "runs after structure_assembler," it is **completely orphaned** -- not imported or registered in `case_generation.py` or `main_workflow.py`.

**The file contains only ~2 lines of real logic:**

```python
normalized_paths = SemanticPathNormalizer(llm_client).normalize(test_cases)
optimized_tree = ChecklistMerger().merge(normalized_paths)
```

All meaningful work is delegated to:
1. `SemanticPathNormalizer` -- LLM-based semantic path normalization
2. `ChecklistMerger` -- Prefix tree merging

**Timing Conflict (Docstring vs. Reality):**

The module docstring states:
```python
"""Checklist 共享逻辑树优化节点。
在 ``structure_assembler`` 之后执行：
1. 使用 LLM 将 ``test_cases`` 归一化为共享语义路径
2. 将语义路径合并为共享前缀树 ``optimized_tree``
```

But `structure_assembler` already **produces** `optimized_tree` as its output. If `checklist_optimizer` ran after `structure_assembler`, it would **overwrite** the carefully assembled tree with a freshly generated one from raw test cases, discarding:
- Template field inheritance
- Mandatory skeleton enforcement
- Consistency TODO annotations
- Source annotations

This means the docstring describes an **impossible** execution order. The node was likely designed for an earlier architecture where `optimized_tree` was built post-assembly, but was superseded by `checkpoint_outline_planner` (which builds the tree pre-draft-writing) and never removed.

**Dual entry points -- legacy compatibility risk:**

```python
def build_checklist_optimizer_node(llm_client: LLMClient):
    """构建使用 LLM 语义归一化的 checklist optimizer 节点。"""
    def checklist_optimizer_node(state: CaseGenState) -> dict[str, Any]:
        # ... actual logic with LLM ...
    return checklist_optimizer_node

def checklist_optimizer_node(state: CaseGenState) -> dict[str, Any]:
    """兼容旧调用入口。未注入 LLM 客户端时不执行语义优化，直接回退为扁平渲染。"""
    test_cases = state.get("test_cases", [])
    return {"test_cases": test_cases, "optimized_tree": []}
```

The module-level `checklist_optimizer_node` function (without LLM) is a no-op fallback that returns an empty tree. This creates a confusing dual-API where the function name is identical but behavior differs depending on which reference is used.

**Exception handling -- all-or-nothing:**

```python
try:
    normalized_paths = SemanticPathNormalizer(llm_client).normalize(test_cases)
    optimized_tree = ChecklistMerger().merge(normalized_paths)
except Exception:
    logger.warning(
        "Checklist semantic optimization failed; returning empty tree",
        exc_info=True,
    )
    optimized_tree = []
```

Issues:
- Catch-all `Exception` with no step-level degradation. If normalization succeeds but merging fails, the normalized paths are silently discarded.
- No logging of what was normalized or merged -- impossible to debug partial failures.
- Returns empty tree `[]` on any error, forcing downstream to "flat rendering" with no intermediate recovery.

**Feature flag guard without telemetry:**

```python
settings = get_settings()
if not settings.enable_checklist_optimization:
    return {"test_cases": test_cases, "optimized_tree": []}
```

The feature flag check happens at runtime with no logging when disabled. In production troubleshooting, it would be unclear whether the node was skipped due to the flag or due to being unregistered.

#### Improvement Recommendations

1. **Delete or archive this file.** It is dead code that will confuse future maintainers. The `checkpoint_outline_planner` service has fully replaced its functionality.
2. If the semantic normalization + merging logic is still desired as a post-assembly pass, it should be integrated as an optional step within `structure_assembler` rather than a separate node.
3. Remove the module-level `checklist_optimizer_node` function to eliminate the confusing dual-API.
4. If retained for any reason, add step-level try/except between normalize and merge.

---

### §7.3.2 structure_assembler.py -- CRITICAL

| Property | Value |
|----------|-------|
| Lines | 321 |
| Type | A -- core pipeline node |
| State | `CaseGenState` |
| Input | `draft_cases`, `mapped_evidence`, `checkpoints`, `optimized_tree`, `checkpoint_paths`, `canonical_outline_nodes`, `mandatory_skeleton` |
| Output | `test_cases`, `optimized_tree` |
| Dependencies | `TestCase`, `ChecklistNode`, `Checkpoint`, `MandatorySkeletonNode`, `attach_expected_results_to_outline`, `normalize_test_case` |
| Registered in graph | Yes -- final node in case_generation subgraph |

#### Detailed Analysis

`structure_assembler` is the **terminal node** of the case generation subgraph and the last node to touch `optimized_tree` before it exits to the main graph. It performs a **6-step assembly process** that is critical to checklist integration quality.

**Step-by-step breakdown of `structure_assembler_node()`:**

**Step 1 -- Field completion (lines 37-72):** For each `draft_case`, fills in missing fields:
- Auto-generates IDs (`TC-001`, `TC-002`, ...)
- Sets defaults for `preconditions`, `steps`, `expected_results`, `priority`, `category`
- Backfills `evidence_refs` from `mapped_evidence`
- Preserves `checkpoint_id`

**Step 2 -- Template inheritance (lines 54-72):** If a case lacks `template_leaf_id` but has a `checkpoint_id`, it inherits template binding fields from the checkpoint:

```python
if not case.template_leaf_id and case.checkpoint_id:
    cp = cp_lookup.get(case.checkpoint_id)
    if cp and cp.template_leaf_id:
        update_fields.update({
            "template_leaf_id": cp.template_leaf_id,
            "template_path_ids": cp.template_path_ids,
            "template_path_titles": cp.template_path_titles,
            "template_match_confidence": cp.template_match_confidence,
            "template_match_low_confidence": cp.template_match_low_confidence,
        })
```

**Step 3 -- Text normalization (line 74):** Each assembled case passes through `normalize_test_case()` for Chinese-English mixed text formatting.

**Step 4 -- Code consistency TODO application (line 77):** The `_apply_consistency_todos()` function iterates over cases and their associated checkpoints, appending `[TODO-CODE-MISMATCH]` or `[TODO-CODE-UNVERIFIED]` strings to `expected_results`.

**Step 5 -- Mount to optimized_tree (lines 88-92):** This is the **first rewrite** of `optimized_tree`:

```python
optimized_tree = attach_expected_results_to_outline(
    state.get("optimized_tree", []),
    assembled_cases,
    state.get("checkpoint_paths", []),
    state.get("canonical_outline_nodes", []),
)
```

The `optimized_tree` produced by `checkpoint_outline_planner` is taken and enriched with expected results from the assembled test cases.

**Step 6 -- Mandatory constraint enforcement (lines 95-101):** This is the **second rewrite** of `optimized_tree`:

```python
if mandatory_skeleton:
    optimized_tree = _enforce_mandatory_constraints(
        optimized_tree, mandatory_skeleton
    )
    _annotate_source(optimized_tree, mandatory_skeleton)
```

The tree is restructured to ensure all mandatory template nodes exist, with an overflow bucket for unmatched nodes.

#### Critical Issue: Double-Write of `optimized_tree`

The `optimized_tree` undergoes **two sequential rewrites** in a single node:

1. `attach_expected_results_to_outline()` -- Enriches the tree with test case expected results
2. `_enforce_mandatory_constraints()` -- Restructures the tree to match mandatory skeleton

The second rewrite can **discard or relocate** nodes that were just enriched in the first step. Specifically:
- `_enforce_mandatory_constraints()` rebuilds the tree from scratch based on skeleton children
- Nodes not matching skeleton IDs go into an `_overflow` bucket
- The `_restore_or_merge()` function creates new `ChecklistNode` objects, potentially losing metadata attached by `attach_expected_results_to_outline()`

**Evidence of potential data loss in `_restore_or_merge()`:**

```python
def _restore_or_merge(sk_node, tree_lookup):
    existing = tree_lookup.get(sk_node.id)
    merged_children = []
    # ... merge skeleton children ...
    # Preserves existing non-skeleton children, BUT:
    priority = sk_node.original_metadata.get("priority", "P2")
    return ChecklistNode(
        node_id=sk_node.id,
        title=sk_node.title,        # ← Uses skeleton title, not enriched title
        node_type="group",
        hidden=False,
        source="template",
        is_mandatory=sk_node.is_mandatory,
        priority=priority,
        children=merged_children,
    )
```

A **new** `ChecklistNode` is created with the skeleton's title and metadata, discarding any enrichment that `attach_expected_results_to_outline()` may have applied to the existing node's direct properties.

#### Overflow Bucket Warning Logic

```python
if overflow_cases:
    overflow_ratio = len(overflow_cases) / max(len(tree), 1)
    if overflow_ratio > 0.2:
        logger.warning(
            "大量节点进入溢出区 (%d/%d = %.0f%%)，建议检查模版与 PRD 的匹配度",
            ...
        )
```

The 20% threshold is arbitrary with no configuration option. When triggered, it only logs a warning but does not adjust behavior or signal the issue to downstream consumers.

#### `_apply_consistency_todos()` -- Mutation concerns

```python
def _apply_consistency_todos(cases, checkpoints):
    for case in cases:
        # ...
        if todo_text not in case.expected_results:
            case.expected_results.append(todo_text)  # ← Mutates in place
        if not case.code_consistency:
            case.code_consistency = consistency        # ← Mutates in place
        if hasattr(case, "tags") and tag not in case.tags:
            case.tags.append(tag)                      # ← Mutates in place
    return cases
```

This function mutates `TestCase` objects in place despite claiming to return a new list. If any upstream code retains references to the original `draft_cases`, they will see the mutations.

#### Error Handling Analysis

The node has **no try/except** at the top level. Any exception in the 6-step process crashes the entire pipeline. This is particularly risky because:
- `attach_expected_results_to_outline()` is an external service call
- `_enforce_mandatory_constraints()` does recursive tree manipulation
- Missing or malformed state keys (e.g., `mandatory_skeleton` with unexpected structure) will cause `AttributeError`

#### Improvement Recommendations

1. **Add top-level try/except** with graceful degradation: if constraint enforcement fails, return the pre-enforcement tree.
2. **Eliminate the double-write pattern**: Either merge the two tree transformations into a single pass, or make `_enforce_mandatory_constraints()` operate on enriched nodes rather than creating new ones.
3. **Preserve enrichment during skeleton merge**: In `_restore_or_merge()`, copy enrichment data from the existing node when available.
4. **Make overflow threshold configurable** via settings.
5. **Add intermediate validation** between Steps 5 and 6 to verify tree integrity.
6. **Avoid in-place mutation** in `_apply_consistency_todos()`: use `model_copy(update=...)` consistently.

---

### §7.3.3 checkpoint_generator.py

| Property | Value |
|----------|-------|
| Lines | 514 |
| Type | A -- core pipeline node |
| State | `CaseGenState` |
| Input | `research_output`, `template_leaf_targets`, `xmind_reference_summary`, `mr_code_facts` |
| Output | `checkpoints` |
| Dependencies | `LLMClient`, `Checkpoint`, `ResearchFact`, `TemplateLeafTarget` |

#### Detailed Analysis

This node is the central LLM-driven checkpoint generation step. It converts `ResearchFact` objects into explicit `Checkpoint` objects through a carefully orchestrated prompt assembly process.

**Prompt assembly injects 4 context types:**

1. **Base facts** -- Formatted list of research facts with IDs, categories, and source sections.
2. **Template binding instructions** -- When `template_leaf_targets` exist, injects a list of valid leaf IDs and instructs the LLM to assign each checkpoint to a leaf with a confidence score.
3. **XMind reference structure** -- When `xmind_reference_summary` exists, injects the reference checklist's coverage dimensions to guide structural alignment.
4. **MR code facts** -- When `mr_code_facts` exist, appends code-level facts from MR analysis to ensure checkpoints cover code changes.

**Post-processing includes invalid leaf_id clearing:**

```python
if template_leaf_id not in valid_leaf_ids:
    original_leaf_id = template_leaf_id
    template_leaf_id = ""
    template_match_confidence = 0.0
    # ...
    invalid_cleared_count += 1
```

When the LLM returns a `template_leaf_id` not in the valid set, the binding is silently cleared. This is logged but has no recovery mechanism (e.g., fuzzy matching to the closest valid leaf).

**Legacy compatibility via `_synthesize_facts_from_legacy()`:** When `research_output.facts` is empty, synthesizes facts from `user_scenarios`, `feature_topics`, and `constraints`. This backward-compat path ensures the node works even with older research outputs.

**`CheckpointDraft` model with auto-repair:**

```python
@model_validator(mode="before")
@classmethod
def coerce_and_strip_extra_fields(cls, values):
    _EXTRA_FIELDS = {"steps", "expected_result", "expected_results", "checkpoint_id"}
    for key in _EXTRA_FIELDS:
        values.pop(key, None)
    # Also: splits preconditions string → list
```

Proactively strips fields that the LLM should not produce but often does. This is a pragmatic defense against LLM hallucination.

**Low confidence threshold:** `_LOW_CONFIDENCE_THRESHOLD = 0.6`. Matches below this are flagged as `template_match_low_confidence = True` but are still used -- no escalation or re-prompting.

#### Issues

- No retry logic for LLM failures; a single `generate_structured` call with no fallback.
- `effective_fact_ids` has a subtle bug: `draft.fact_ids or [facts[0].fact_id] if facts else []` -- due to Python operator precedence, this evaluates as `(draft.fact_ids or [facts[0].fact_id]) if facts else []` when `facts` is truthy but `draft.fact_ids` is empty, which is correct but fragile.
- Template binding summary logging is excellent but only at INFO level; production environments may miss it.

---

### §7.3.4 draft_writer.py

| Property | Value |
|----------|-------|
| Lines | 518 |
| Type | A -- core pipeline node |
| State | `CaseGenState` |
| Input | `checkpoints`, `checkpoint_paths`, `canonical_outline_nodes`, `planned_scenarios`, `mapped_evidence`, `xmind_reference_summary`, `project_context_summary` |
| Output | `draft_cases`, `draft_writer_timing` |
| Dependencies | `LLMClient`, `TestCase`, `Checkpoint`, `ChecklistNode`, `ThreadPoolExecutor` |

#### Detailed Analysis

**Dual-path design:** The node has two generation paths:

1. **Checkpoint path (primary):** When `checkpoints` exist, generates test cases from checkpoints with fixed hierarchy path context resolved from `checkpoint_paths` and `canonical_outline_nodes`.
2. **Scenario path (fallback):** When no checkpoints exist, falls back to generating from `planned_scenarios` with evidence. However, scenario-path test cases **lack `checkpoint_id`**, breaking downstream coverage tracking in `evaluation.py` and `reflection.py`.

**ThreadPoolExecutor concurrent reference leaf generation:**

```python
_REF_LEAF_BATCH_SIZE: int = 40
_MAX_WORKERS: int = 5
```

When an XMind reference tree exists, the node collects reference leaves (source='reference') and generates details for them concurrently using `ThreadPoolExecutor`. Batches of 40 leaves are processed with 5 concurrent threads.

**Title preservation concern:** After LLM generates cases for reference leaves, the code overwrites titles:

```python
for i in range(paired):
    returned_cases[i].title = batch[i].title
```

If the LLM returns fewer cases than leaves, only `min(returned, expected)` get title alignment, and a warning is logged. Excess LLM-generated cases retain LLM-chosen titles that may not match reference leaves.

**Code consistency annotation helper:** `_apply_code_consistency_to_xmind_node()` adds child annotation nodes to the tree with visual markers (✓, ⚠, ?) but is defined in this file rather than in a shared utility, coupling tree annotation to the draft writer.

**Missing error handling at the main generation call:** The primary `llm_client.generate_structured()` call for the main checkpoint/scenario prompt has no try/except wrapping.

---

### §7.3.5 evaluation.py

| Property | Value |
|----------|-------|
| Lines | 351 |
| Type | A -- core pipeline node |
| State | `CaseGenState` (via function params) |
| Input | `test_cases`, `checkpoints`, `research_output`, `previous_score` |
| Output | `EvaluationReport` |
| Dependencies | `TestCase`, `Checkpoint`, `ResearchOutput`, `EvaluationReport` |

#### Detailed Analysis

This node performs **6-dimension evaluation** of the generated test case quality:

| Dimension | What it measures | Threshold |
|-----------|-----------------|------------|
| `fact_coverage` | % of facts referenced by at least one checkpoint | < 0.6 → retry context_research |
| `checkpoint_coverage` | % of checkpoints covered by at least one test case | < 0.6 → retry checkpoint_generation |
| `evidence_completeness` | % of test cases with evidence_refs | < 0.6 → retry draft_generation |
| `duplicate_rate` | Uniqueness of test case titles (casefold) | < 0.6 → retry draft_generation |
| `case_completeness` | % of cases with non-empty steps and expected_results | < 0.6 → retry draft_generation |
| `branch_coverage` | Coverage of non-functional checkpoints (edge_case, boundary) | Scored 0.5 if all cases are functional |

**Retry stage determination (`_determine_retry_stage()`):** Returns one of `context_research`, `checkpoint_generation`, `draft_generation`, or `None` based on which dimension scores lowest. Priority: fact > checkpoint > testcase quality. However, the returned `suggested_retry_stage` is **not consumed by any graph routing logic** -- the pipeline is linear with no conditional edges.

**Note:** This file defines a pure function `evaluate()` rather than a LangGraph node function. It is called by the iteration/reflection layer rather than being directly registered as a graph node. The evaluation results influence iteration decisions but the pipeline itself has no conditional branching.

---

### §7.3.6 input_parser.py

| Property | Value |
|----------|-------|
| Lines | 54 |
| Type | Entry point node |
| State | `GlobalState` |
| Input | `file_path` or `request.file_path` |
| Output | `parsed_document` |

Simple node that resolves a file path from state and delegates to `parsers.factory.get_parser()`. Supports relative paths (resolved against cwd). Raises `ValueError` if no path is provided and `FileNotFoundError` if the file doesn't exist. No try/except wrapping -- errors propagate to the graph runner.

---

### §7.3.7 context_research.py

| Property | Value |
|----------|-------|
| Lines | 92 |
| Type | A -- core pipeline node |
| State | `GlobalState` |
| Input | `parsed_document`, `model_config`, `project_context_summary`, `knowledge_context`, `language` |
| Output | `research_output` (ResearchOutput) |

LLM-driven extraction of testing-relevant context from PRD documents. The system prompt is detailed and prescriptive, requiring structured JSON output with `facts`, `feature_topics`, `user_scenarios`, `constraints`, `ambiguities`, and `test_signals`.

**Context injection layers:**
1. Project context summary (if available)
2. Knowledge context from GraphRAG (if available)
3. Full document text

The prompt includes strict language requirements: Chinese for descriptions, English for proper nouns, with mixed formatting rules.

---

### §7.3.8 knowledge_retrieval.py

| Property | Value |
|----------|-------|
| Lines | 99 |
| Type | Optional enrichment node |
| State | `dict[str, Any]` |
| Input | `parsed_document` |
| Output | `knowledge_context`, `knowledge_sources`, `knowledge_retrieval_success` |

Retrieves domain knowledge from GraphRAG engine. Uses `asyncio.new_event_loop()` to run async retrieval in a sync node context -- this is a known anti-pattern that can cause issues if LangGraph itself runs in an async event loop (nested event loops).

**Graceful degradation:** Three-layer fallback:
1. Engine not ready → empty result
2. Missing parsed_document → empty result  
3. Any exception → empty result with logging

Never blocks the main workflow.

---

### §7.3.9 template_loader.py

| Property | Value |
|----------|-------|
| Lines | 73 |
| Type | Configuration node |
| State | `GlobalState` |
| Input | `template_file_path`, `template_name`, `request` |
| Output | `project_template`, `template_leaf_targets`, `mandatory_skeleton` |

Loads project-level checklist templates. Supports two loading modes: by file path or by name (from a `templates/` directory). After loading, flattens leaf targets and builds mandatory skeleton for downstream constraint enforcement.

**Auto-skip behavior:** Returns empty `{}` when neither path nor name is provided -- downstream nodes handle absence gracefully.

---

### §7.3.10 xmind_reference_loader.py

| Property | Value |
|----------|-------|
| Lines | 85 |
| Type | Optional enrichment node |
| State | `GlobalState` |
| Input | `reference_xmind_path` |
| Output | `xmind_reference_summary` |

Parses XMind reference files and generates both a summary analysis and a deterministic reference tree. The tree converter is optional -- if it fails, the node degrades to summary-only mode.

**Exception handling is thorough** -- separate handlers for `FileNotFoundError`, `XMindParseError`, and generic `Exception`, each returning empty `{}` to avoid blocking the workflow.

---

### §7.3.11 mr_analyzer.py

| Property | Value |
|----------|-------|
| Lines | 763 (largest node) |
| Type | A -- MR analysis pipeline node |
| State | `CaseGenState` |
| Input | `frontend_mr_config`, `backend_mr_config`, `mr_input` |
| Output | `mr_code_facts`, `mr_consistency_issues`, `mr_combined_summary`, `frontend_mr_result`, `backend_mr_result` |

The most complex node in the system. Implements a 3-phase MR analysis pipeline:

**Phase 1 -- Diff Summary:** Parses MR diff files and generates a change summary via LLM.

**Phase 2 -- Agentic Search:** An LLM-driven tool-calling loop (max 10 rounds, 60s timeout) that searches the codebase for related code context. Uses `CODEBASE_TOOLS` (grep, find_references, get_file_content) with the LLM deciding which tool to call each round.

**Phase 3 -- Fact Extraction + Consistency Check:** Extracts code-level facts and checks PRD-vs-code consistency with a confidence threshold of 0.7.

**Dual path support:**
- **Local analysis:** Uses direct file access and agentic search
- **Coco delegation:** Sends the entire task to a Coco Agent for remote analysis

The node is **async** (`async def mr_analyzer_node`), one of only two async nodes (along with `coco_consistency_validator`). The `_run_agentic_search()` function is also async but calls `await llm_client.chat()` which may not be universally async-compatible.

**Issue:** The `_safe_parse_json()` function imports from `app.services.coco_response_validator` at call time, creating a hidden dependency.

---

### §7.3.12 mr_checkpoint_injector.py

| Property | Value |
|----------|-------|
| Lines | 308 |
| Type | MR pipeline node |
| State | `CaseGenState` |
| Input | `mr_code_facts`, `checkpoints` |
| Output | `checkpoints` (merged), `mr_injected_checkpoint_ids` |

Converts `MRCodeFact` objects into checkpoint dictionaries and merges them with existing checkpoints. Uses character-level bigram similarity (`_text_similarity()`) with a threshold of 0.75 for deduplication.

**Design note:** Produces checkpoint **dictionaries** rather than `Checkpoint` model instances to avoid hard dependency on `checkpoint_models`. This is a pragmatic but inconsistent choice -- downstream consumers must handle both dict and Pydantic model checkpoints.

**`_link_consistency_issues()`** mutates `ConsistencyIssue` objects in place by appending to `affected_checkpoint_ids`, which could cause issues if the same issue list is referenced elsewhere.

---

### §7.3.13 project_context_loader.py

| Property | Value |
|----------|-------|
| Lines | 89 |
| Type | Optional enrichment node |
| State | `dict[str, Any]` |
| Input | `project_id` |
| Output | `project_context_summary` |

Loads project context and generates a summary string. Factory pattern captures `ProjectContextService`. Graceful degradation: returns empty string on missing project, lookup failure, or summary generation failure. Well-documented with English docstrings.

---

### §7.3.14 reflection.py

| Property | Value |
|----------|-------|
| Lines | 203 |
| Type | A -- terminal quality node |
| State | `GlobalState` |
| Input | `test_cases`, `planned_scenarios`, `checkpoints`, `research_output`, `project_context_summary` |
| Output | `test_cases` (deduped), `quality_report`, `checkpoint_coverage` |

Performs final quality checks:
1. **Title deduplication** -- casefold-based, preserves first occurrence
2. **Field completeness** -- checks for missing expected_results and evidence_refs
3. **Coverage assessment** -- compares generated case count vs. planned scenario count
4. **Checkpoint quality** -- uncovered facts, uncovered checkpoints, evidence gaps, title overlap detection
5. **Checkpoint coverage computation** -- builds `CheckpointCoverage` records

**Overlap detection uses substring containment** rather than similarity scoring:
```python
if title_i in titles[j] or titles[j] in title_i:
```
This is simplistic -- "验证登录" would match "验证登录功能的边界条件" even though they test different things.

---

### §7.3.15 scenario_planner.py

| Property | Value |
|----------|-------|
| Lines | 124 |
| Type | Planning node |
| State | `GlobalState` |
| Input | `research_output`, `mr_combined_summary` |
| Output | `planned_scenarios` |

Deterministic scenario planning (no LLM call). Priority: `user_scenarios` > `feature_topics` derivation > fallback. MR summary lines starting with `"- "` are converted to `"验证 ..."` scenarios.

**All scenarios get `category="functional"` and `risk="medium"`** regardless of content. The MR-derived scenarios get a distinct rationale but the same flat categorization.

---

### §7.3.16 checkpoint_evaluator.py

| Property | Value |
|----------|-------|
| Lines | 52 |
| Type | Post-processing node |
| State | `CaseGenState` |
| Input | `checkpoints` |
| Output | `checkpoints` (deduped), `checkpoint_coverage` (initialized) |

Simple deduplication by `title.casefold()` and initialization of `CheckpointCoverage` records with `coverage_status="uncovered"`. No LLM calls, no complex logic. Acts as a data normalization step between `checkpoint_generator` and `coverage_detector`.

---

### §7.3.17 coco_consistency_validator.py

| Property | Value |
|----------|-------|
| Lines | 393 |
| Type | Optional MR pipeline node (async) |
| State | `CaseGenState` |
| Input | `checkpoints`, `frontend_mr_config`, `backend_mr_config` |
| Output | `checkpoints` (annotated), `coco_validation_summary` |

Async node that validates each checkpoint against code implementation via Coco Agent. Features:
- Concurrency control: `asyncio.Semaphore(5)`, per-case timeout 120s, total timeout 600s
- Graceful degradation: failed validations marked as `"unverified"`, never block other cases
- Annotates checkpoints with `code_consistency` field and tags (`code_confirmed`, `code_mismatch`, `code_unverified`)

**Concern:** High-confidence mismatches append TODO text directly to `expected_result`:
```python
todo_text = (
    f"\n\n**TODO: 代码实现与预期不一致** — "
    f"预期「{expected[:50]}」，"
    f"但代码实现为「{result.actual_implementation[:80]}」"
)
new_expected = (expected or "") + todo_text
_set_attr_safe(cp, "expected_result", new_expected)
```

This mutates checkpoint `expected_result` strings, which are then inherited by test cases in `structure_assembler`. The mutation is **permanent** and cannot be distinguished from original content without parsing the `**TODO:` prefix.

---

### §7.3.18 evidence_mapper.py

| Property | Value |
|----------|-------|
| Lines | 79 |
| Type | Enrichment node |
| State | `CaseGenState` |
| Input | `parsed_document`, `planned_scenarios` |
| Output | `mapped_evidence` |

Keyword-intersection based evidence mapping. Tokenizes scenario titles and section headings/content, then checks for set intersection. Falls back to first document section with `confidence=0.4` when no match is found.

**Tokenization is basic:** `re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", ...)` -- splits on every non-alphanumeric/CJK character, treating each Chinese character as a separate token. This makes matching very aggressive (any single shared character triggers a match).

---

## §7.4 Data Flow Analysis

### §7.4.1 Checklist Tree (`optimized_tree`) Lifecycle

The `optimized_tree` is the central data structure representing the hierarchical checklist output. It undergoes the following transformations:

```
checkpoint_outline_planner (service)
  ├── Stage A: LLM generates canonical outline nodes
  ├── Stage B: LLM maps checkpoints to paths
  └── Stage C: Deterministic tree construction
        ↓
    optimized_tree v1 (skeleton with checkpoint mappings)
        ↓
draft_writer
  └── No modification to optimized_tree (reads checkpoint_paths + canonical_outline_nodes)
        ↓
structure_assembler
  ├── Step 5: attach_expected_results_to_outline()
  │     → optimized_tree v2 (enriched with test case results)
  ├── Step 6: _enforce_mandatory_constraints()
  │     → optimized_tree v3 (restructured to match skeleton)
  └── _annotate_source()
        → optimized_tree v3+ (source annotations added)
        ↓
    Final optimized_tree exits subgraph via state bridge
        ↓
reflection
  └── No modification to optimized_tree (reads test_cases only)
```

### §7.4.2 Checkpoint Data Flow

```
context_research → research_output.facts
        ↓
checkpoint_generator → checkpoints (with template bindings)
        ↓
checkpoint_evaluator → checkpoints (deduped)
        ↓
mr_checkpoint_injector → checkpoints (merged with MR checkpoints)
        ↓                     ↓
coverage_detector    checkpoint_outline_planner
        ↓                     ↓
    coverage_result     checkpoint_paths + canonical_outline_nodes + optimized_tree
        ↓                     ↓
draft_writer → draft_cases (with checkpoint_id links)
        ↓
coco_consistency_validator → checkpoints (annotated with code_consistency)
        ↓
structure_assembler → test_cases (final) + optimized_tree (final)
```

### §7.4.3 State Key Inventory

| State Key | Produced By | Consumed By |
|-----------|-------------|-------------|
| `parsed_document` | input_parser | context_research, evidence_mapper, knowledge_retrieval |
| `research_output` | context_research | checkpoint_generator, scenario_planner, evaluation, reflection |
| `project_template` | template_loader | (bridge to subgraph) |
| `template_leaf_targets` | template_loader | checkpoint_generator |
| `mandatory_skeleton` | template_loader | structure_assembler |
| `xmind_reference_summary` | xmind_reference_loader | checkpoint_generator, draft_writer, coverage_detector |
| `project_context_summary` | project_context_loader | context_research, draft_writer |
| `knowledge_context` | knowledge_retrieval | context_research |
| `planned_scenarios` | scenario_planner | evidence_mapper, reflection |
| `checkpoints` | checkpoint_generator → evaluator → mr_injector → coco_validator | draft_writer, structure_assembler, evaluation, reflection |
| `checkpoint_paths` | checkpoint_outline_planner | draft_writer, structure_assembler |
| `canonical_outline_nodes` | checkpoint_outline_planner | draft_writer, structure_assembler |
| `optimized_tree` | checkpoint_outline_planner → structure_assembler | (output) |
| `mapped_evidence` | evidence_mapper | structure_assembler |
| `draft_cases` | draft_writer | structure_assembler |
| `test_cases` | structure_assembler | reflection, evaluation |
| `mr_code_facts` | mr_analyzer | checkpoint_generator, mr_checkpoint_injector |
| `mr_consistency_issues` | mr_analyzer | mr_checkpoint_injector |

---

## §7.5 Key Findings

### §7.5.1 CRITICAL: `checklist_optimizer.py` is Orphaned Dead Code

The file is not registered in any graph definition. Its docstring claims execution after `structure_assembler`, but this would produce a timing conflict where the carefully assembled `optimized_tree` would be overwritten. The `checkpoint_outline_planner` service (in `services/`) has fully replaced this node's functionality. **This file should be deleted.**

### §7.5.2 CRITICAL: Double-Write of `optimized_tree` in `structure_assembler`

The `optimized_tree` is rewritten twice in `structure_assembler_node()`:
1. `attach_expected_results_to_outline()` enriches the tree
2. `_enforce_mandatory_constraints()` restructures it, potentially losing enrichment

The second pass creates **new** `ChecklistNode` objects from skeleton metadata, discarding properties that may have been set during enrichment. This is a data integrity risk.

### §7.5.3 HIGH: No Top-Level Error Handling in Critical Nodes

Neither `structure_assembler` nor `checkpoint_generator` have top-level exception handling. A failure in any step crashes the entire pipeline with no partial output recovery.

### §7.5.4 HIGH: Async/Sync Mismatch in knowledge_retrieval

`knowledge_retrieval.py` creates a new event loop via `asyncio.new_event_loop()` inside a synchronous node. If LangGraph's executor is already running an event loop, this will fail or cause undefined behavior.

### §7.5.5 MEDIUM: Inconsistent Checkpoint Types

`mr_checkpoint_injector` outputs checkpoint **dictionaries** while all other nodes produce `Checkpoint` Pydantic model instances. Downstream consumers must handle both types, as evidenced by the `_get_attr_safe()` / `_set_attr_safe()` dual-mode helpers in `coco_consistency_validator.py`.

### §7.5.6 MEDIUM: In-Place Mutations of Shared State

Multiple nodes mutate objects in place:
- `structure_assembler._apply_consistency_todos()` mutates `TestCase.expected_results`
- `coco_consistency_validator._annotate_checkpoints()` mutates checkpoint objects
- `mr_checkpoint_injector._link_consistency_issues()` mutates `ConsistencyIssue` objects

This violates the immutable-state-update pattern that LangGraph encourages and can cause subtle bugs when state snapshots are compared or when nodes are retried.

### §7.5.7 MEDIUM: Aggressive Token-Level Evidence Matching

`evidence_mapper` treats each Chinese character as a separate token. A single shared character (e.g., "的") would create a match. This likely produces many false-positive evidence associations.

### §7.5.8 LOW: Evaluation Results Not Consumed by Graph Routing

`evaluation.py` computes `suggested_retry_stage` but the pipeline is strictly linear. The retry suggestion is never used for conditional routing, making the evaluation purely informational.

---

## §7.6 Checklist Integration Impact Analysis

This section traces how each node contributes to or degrades the quality of the final checklist output (`optimized_tree` + `test_cases`).

| Node | Impact on Checklist | Risk Level |
|------|-------------------|------------|
| `input_parser` | **Foundation** -- incorrect parsing propagates to all downstream | Low (well-tested) |
| `template_loader` | **Structural anchor** -- defines mandatory skeleton | Medium |
| `xmind_reference_loader` | **Reference quality** -- guides structural alignment | Low |
| `project_context_loader` | **Context enrichment** -- indirect quality improvement | Low |
| `knowledge_retrieval` | **Domain coverage** -- enriches fact extraction | Low |
| `context_research` | **Fact quality** -- determines checkpoint completeness | High |
| `mr_analyzer` | **Code coverage** -- adds code-level testing dimensions | Medium |
| `mr_checkpoint_injector` | **Checkpoint completeness** -- but dict/model inconsistency risk | Medium |
| `scenario_planner` | **Coverage breadth** -- flat categorization limits differentiation | Low |
| `checkpoint_generator` | **CRITICAL** -- template binding quality directly affects tree structure | High |
| `checkpoint_evaluator` | **Dedup quality** -- prevents redundant tree nodes | Low |
| `checkpoint_outline_planner` | **CRITICAL** -- produces the initial `optimized_tree` | Highest |
| `evidence_mapper` | **Traceability** -- aggressive matching dilutes evidence quality | Medium |
| `draft_writer` | **Content quality** -- test case detail generation | High |
| `coco_consistency_validator` | **Code alignment** -- mutates checkpoint expected_result permanently | Medium |
| `structure_assembler` | **CRITICAL** -- final assembly with double-write risk | Highest |
| `reflection` | **Quality gate** -- but no enforcement mechanism | Low |
| `checklist_optimizer` | **DEAD CODE** -- no impact (orphaned) | N/A |

### Key Checklist Quality Risks

1. **Template binding → tree structure chain:** If `checkpoint_generator` assigns wrong `template_leaf_id`, the tree structure in `checkpoint_outline_planner` will place checkpoints under wrong branches. The invalid-ID clearing logic catches non-existent IDs but not semantically wrong assignments.

2. **Double-write data loss:** `structure_assembler` enriches the tree then restructures it, potentially losing enrichment for nodes that get recreated from skeleton metadata.

3. **Permanent TODO mutation:** `coco_consistency_validator` appends TODO text to `expected_result` fields, which flows through to `structure_assembler` and into the final `test_cases`. These mutations are irreversible and mixed with actual expected results.

4. **Evidence quality dilution:** The aggressive token matching in `evidence_mapper` means most test cases get evidence refs, but many may be false positives, reducing the traceability value.

---

## §7.7 Improvement Recommendations

### Priority 1 (Critical)

| # | Recommendation | Affected Files |
|---|---------------|----------------|
| 1 | **Delete `checklist_optimizer.py`** -- it is dead code with a misleading docstring | `checklist_optimizer.py` |
| 2 | **Eliminate double-write in `structure_assembler`** -- merge enrichment and constraint enforcement into a single tree pass that preserves enriched properties | `structure_assembler.py` |
| 3 | **Add top-level error handling** to `structure_assembler` and `checkpoint_generator` with graceful degradation | `structure_assembler.py`, `checkpoint_generator.py` |

### Priority 2 (High)

| # | Recommendation | Affected Files |
|---|---------------|----------------|
| 4 | **Fix async/sync pattern** in `knowledge_retrieval` -- use `asyncio.get_event_loop()` with fallback or make the node async | `knowledge_retrieval.py` |
| 5 | **Standardize checkpoint types** -- `mr_checkpoint_injector` should produce `Checkpoint` model instances, not dicts | `mr_checkpoint_injector.py` |
| 6 | **Separate TODO annotations** from expected_result content in `coco_consistency_validator` -- use a dedicated field | `coco_consistency_validator.py` |
| 7 | **Add intermediate validation** between tree enrichment and constraint enforcement in `structure_assembler` | `structure_assembler.py` |

### Priority 3 (Medium)

| # | Recommendation | Affected Files |
|---|---------------|----------------|
| 8 | **Improve evidence matching** -- use TF-IDF or embedding similarity instead of raw token intersection, filter out stop words and single-character tokens | `evidence_mapper.py` |
| 9 | **Avoid in-place mutations** -- use `model_copy(update=...)` consistently throughout all nodes | Multiple files |
| 10 | **Add fuzzy matching** for invalid `template_leaf_id` in `checkpoint_generator` before clearing | `checkpoint_generator.py` |
| 11 | **Make overflow threshold configurable** in `structure_assembler._enforce_mandatory_constraints()` | `structure_assembler.py` |
| 12 | **Wire evaluation results to graph routing** -- add conditional edges based on `suggested_retry_stage` | `evaluation.py`, `case_generation.py` |

---

## §7.8 Cross-References

| Reference | Target | Relationship |
|-----------|--------|-------------|
| §7.3.1 `checklist_optimizer.py` | `services/semantic_path_normalizer.py` | Delegates normalization (orphaned) |
| §7.3.1 `checklist_optimizer.py` | `services/checklist_merger.py` | Delegates merging (orphaned) |
| §7.3.2 `structure_assembler.py` | `services/checkpoint_outline_planner.py` | Consumes `optimized_tree` produced by planner |
| §7.3.2 `structure_assembler.py` | `services/text_normalizer.py` | Uses `normalize_test_case()` |
| §7.3.2 `structure_assembler.py` | `domain/template_models.py` (`MandatorySkeletonNode`) | Constraint enforcement |
| §7.3.2 `structure_assembler.py` | `domain/checklist_models.py` (`ChecklistNode`) | Tree node type |
| §7.3.3 `checkpoint_generator.py` | `domain/checkpoint_models.py` (`Checkpoint`, `generate_checkpoint_id`) | Output model |
| §7.3.3 `checkpoint_generator.py` | `domain/template_models.py` (`TemplateLeafTarget`) | Template binding |
| §7.3.4 `draft_writer.py` | `domain/checklist_models.py` (`ChecklistNode`, `CanonicalOutlineNode`, `CheckpointPathMapping`) | Path resolution |
| §7.3.11 `mr_analyzer.py` | `services/codebase_tools.py` | Agentic search tools |
| §7.3.11 `mr_analyzer.py` | `services/coco_client.py` | Coco Agent delegation |
| §7.3.17 `coco_consistency_validator.py` | `services/coco_client.py` | Checkpoint validation |
| §7.3.2, §7.3.3, §7.3.4 | `graphs/case_generation.py` | Subgraph registration |
| §7.3.6, §7.3.7, §7.3.14 | `graphs/main_workflow.py` | Main graph registration |
| §7.2 Pipeline Order | `graphs/state_bridge.py` | State bridging between main/sub graphs |
| §7.5.1 Dead code finding | Entire `checklist_optimizer.py` | Should reference deletion in cleanup tasks |
| §7.5.2 Double-write finding | `services/checkpoint_outline_planner.py` | Produces the tree that gets double-written |