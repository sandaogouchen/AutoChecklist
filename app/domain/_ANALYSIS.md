# app/domain/ Directory Analysis

> Auto-generated analysis for the domain layer of AutoChecklist

## §5.1 Directory Overview

| Property | Value |
|----------|-------|
| Path | `app/domain/` |
| Total Files | 14 |
| Total Lines | 1,694 |
| Total Classes | 57 |
| Main Purpose | Domain models and data structures for the AutoChecklist pipeline: PRD parsing, research, checkpoint generation, test-case generation, checklist tree construction, template binding, MR analysis, XMind delivery, and LangGraph workflow state |

### Layer Responsibilities

The domain layer serves as the **single source of truth** for all data shapes flowing through the AutoChecklist pipeline. It encompasses:

1. **Input models** -- PRD document parsing (`document_models`), API request/response contracts (`api_models`), MR diff inputs (`mr_models`), XMind reference inputs (`xmind_reference_models`).
2. **Intermediate models** -- Research facts and evidence (`research_models`), checkpoints (`checkpoint_models`), precondition groupings (`precondition_models`), template bindings (`template_models`).
3. **Output models** -- Test cases and quality reports (`case_models`), checklist tree (`checklist_models`), XMind delivery nodes (`xmind_models`).
4. **Orchestration models** -- LangGraph workflow state (`state.py`), run-state tracking and evaluation loop (`run_state`), project context (`project_models`).

---

## §5.2 File Analysis

---

### §5.2.1 checklist_models.py

| Property | Value |
|----------|-------|
| Lines | 132 |
| Classes | 5 (`ChecklistNode`, `CanonicalOutlineNode`, `CanonicalOutlineNodeCollection`, `CheckpointPathMapping`, `CheckpointPathCollection`) |
| Imports from domain | `research_models.EvidenceRef` |
| Role | **CRITICAL** -- Core checklist tree structure and outline planning models |

#### Type Classification: C -- Core Model

#### Class: `ChecklistNode` (lines 12-73)

The central recursive tree node that represents the final checklist output. Every test case, precondition group, and structural heading is expressed as a `ChecklistNode`.

**Fields (18 total):**

| Field | Type | Default | Purpose |
|-------|------|---------|----------|
| `node_id` | `str` | `""` | Unique identifier; aliased from `"id"` |
| `title` | `str` | `""` | Display text; aliased from `"display_text"` |
| `node_type` | `Literal["root","group","expected_result","precondition_group","case"]` | `"group"` | Semantic classification of the node |
| `children` | `list[ChecklistNode]` | `[]` | Recursive child nodes |
| `hidden` | `bool` | `False` | Visibility toggle |
| `source` | `Literal["template","generated","overflow","reference"]` | `"generated"` | Origin marker |
| `is_mandatory` | `bool` | `False` | Whether node is mandatory (from template) |
| `test_case_ref` | `str` | `""` | Reference to a TestCase ID |
| `source_test_case_refs` | `list[str]` | `[]` | Source test case references |
| `preconditions` | `list[str]` | `[]` | Precondition text list |
| `steps` | `list[str]` | `[]` | Operation steps |
| `expected_results` | `list[str]` | `[]` | Expected outcomes |
| `priority` | `str` | `"P2"` | Priority level |
| `category` | `str` | `"functional"` | Category tag |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | PRD evidence chain |
| `checkpoint_id` | `str` | `""` | Back-reference to Checkpoint |

**Recursive self-reference:** The `children` field creates a tree. `model_rebuild()` is called at module level to support Pydantic v2 self-referencing.

**Alias handling:** Uses `AliasChoices` for backward compatibility (`id`/`node_id`, `title`/`display_text`). `ConfigDict(populate_by_name=True)` enables both alias and field name population.

**Property accessors:** `id` and `display_text` properties with getters/setters provide legacy API compatibility.

**Issues identified:**

1. **Missing conditional validation linking `node_type` to required fields.** When `node_type == "case"`, fields like `steps`, `expected_results`, `test_case_ref`, and `checkpoint_id` are semantically required, but no Pydantic validator enforces this. A `"case"` node with empty `steps` and `expected_results` is silently accepted. Similarly, `"root"` nodes should never have `steps`/`expected_results` populated, but nothing prevents it.

2. **`priority` and `category` are plain `str`, not `Literal` constrained.** The `Checkpoint` model has the same issue. Valid values (`P0`-`P3`, `functional`/`edge_case`/etc.) are undocumented at the type level, making it impossible for Pydantic to reject invalid values.

3. **`node_id` defaults to empty string.** This means multiple nodes can exist with `node_id == ""`, creating ambiguity in ID-based lookups. A factory default (e.g., `uuid4().hex`) would be safer.

4. **`checkpoint_id` is a plain `str` back-reference.** There is no validation that the referenced checkpoint actually exists, and no foreign-key-like constraint.

5. **Field completeness gap:** The `expected_result` node_type is listed but has no dedicated fields -- it reuses the same flat field set as `case` nodes. The semantic distinction between `"expected_result"` and `"case"` is unclear from the model alone.

#### Class: `CanonicalOutlineNode` (lines 76-85)

Planning-phase node representing a canonical outline position in the checklist hierarchy.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `node_id` | `str` | required | Unlike `ChecklistNode`, this is required |
| `semantic_key` | `str` | `""` | Deduplication key |
| `display_text` | `str` | required | |
| `kind` | `Literal["business_object","context","page","action"]` | `"context"` | Well-constrained |
| `visibility` | `Literal["visible","required","hidden"]` | `"visible"` | Well-constrained |
| `aliases` | `list[str]` | `[]` | Alternative names |

No issues. This model is well-typed with proper `Literal` constraints.

#### Class: `CanonicalOutlineNodeCollection` (lines 87-99)

Wrapper around a list of `CanonicalOutlineNode`. Uses `AliasChoices` for `canonical_nodes`/`nodes`. Provides a `nodes` property for legacy access.

#### Class: `CheckpointPathMapping` (lines 102-113)

Maps a checkpoint to its position in the canonical outline tree via an ordered list of node IDs. Alias support: `path_node_ids`/`path`.

#### Class: `CheckpointPathCollection` (lines 116-128)

Collection wrapper for `CheckpointPathMapping`. Alias support: `checkpoint_paths`/`mappings`.

---

### §5.2.2 checkpoint_models.py

| Property | Value |
|----------|-------|
| Lines | 99 |
| Classes | 2 (`Checkpoint`, `CheckpointCoverage`) |
| Functions | 1 (`generate_checkpoint_id`) |
| Imports from domain | `research_models.EvidenceRef` |
| Role | **CRITICAL** -- Intermediate anchor between facts and test cases |

#### Type Classification: C -- Core Model

#### Class: `Checkpoint` (lines 21-68)

The central domain entity bridging research facts to test cases. Every fact produces one or more checkpoints; every test case traces back to exactly one checkpoint.

**Fields (18 total):**

| Field | Type | Default | Critical Notes |
|-------|------|---------|----------------|
| `checkpoint_id` | `str` | `""` | Generated via `generate_checkpoint_id()` |
| `title` | `str` | required | Only required field besides inherited BaseModel |
| `objective` | `str` | `""` | |
| `category` | `str` | `"functional"` | **Not Literal-constrained** -- should be `Literal["functional","edge_case","performance","security"]` per docstring |
| `risk` | `str` | `"medium"` | **Not Literal-constrained** -- should be `Literal["low","medium","high"]` per docstring |
| `branch_hint` | `str` | `""` | |
| `fact_ids` | `list[str]` | `[]` | Upstream provenance |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | PRD evidence chain |
| `preconditions` | `list[str]` | `[]` | |
| `coverage_status` | `str` | `"uncovered"` | **Not Literal-constrained** -- should be `Literal["uncovered","partial","covered"]` per docstring |
| `template_leaf_id` | `str` | `""` | Template binding |
| `template_path_ids` | `list[str]` | `[]` | Template binding |
| `template_path_titles` | `list[str]` | `[]` | Template binding |
| `template_match_confidence` | `float` | `0.0` | 0.0-1.0 range **not validated** |
| `template_match_reason` | `str` | `""` | |
| `template_match_low_confidence` | `bool` | `False` | |
| `code_consistency` | `dict[str, Any] \| None` | `None` | **Untyped dict** -- should use `CodeConsistencyResult` from `mr_models` |

**Issues identified:**

1. **`coverage_status` is a plain `str`**, not `Literal["uncovered","partial","covered"]`. Any arbitrary string is accepted without validation. The same issue exists on `CheckpointCoverage.coverage_status`. This is a type-safety gap that can cause silent bugs in coverage logic.

2. **`category` and `risk` lack `Literal` constraints** despite the docstring enumerating exact valid values. This is inconsistent with `ChecklistNode.node_type` and `ChecklistNode.source` which do use `Literal`.

3. **`code_consistency` is typed as `dict[str, Any] | None`** instead of using the dedicated `CodeConsistencyResult` model defined in `mr_models.py`. This defeats the purpose of having a typed model and forces downstream consumers to do untyped dict access. The same issue appears on `TestCase.code_consistency`.

4. **`template_match_confidence` has no `Field(ge=0.0, le=1.0)` constraint**, so values outside 0-1 are silently accepted.

5. **`checkpoint_id` defaults to `""`** -- the `generate_checkpoint_id()` function exists but is not called automatically; the caller must invoke it manually and assign the result. There is no validator ensuring a non-empty ID after construction.

#### Class: `CheckpointCoverage` (lines 70-82)

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `checkpoint_id` | `str` | required | |
| `covered_by_test_ids` | `list[str]` | `[]` | |
| `coverage_status` | `str` | `"uncovered"` | Same `Literal` constraint gap as `Checkpoint` |

#### Function: `generate_checkpoint_id()` (lines 84-99)

Deterministic ID generation via SHA-256 hash of sorted `fact_ids` + case-folded `title`. Returns `"CP-<8-hex-chars>"`. The algorithm is sound for deduplication; however, the 8-character hex window yields ~4.3 billion unique values, which is sufficient for this use case but could theoretically collide in extreme scenarios.

---

### §5.2.3 state.py

| Property | Value |
|----------|-------|
| Lines | 188 |
| Classes | 2 (`GlobalState`, `CaseGenState`) |
| Imports from domain | 10 domain modules + 1 service module |
| Role | **CRITICAL** -- LangGraph workflow state definition |

#### Type Classification: C -- Core State

#### Architecture Note

Both `GlobalState` and `CaseGenState` are `TypedDict(total=False)`, meaning **all fields are optional**. This is intentional for LangGraph's incremental update pattern where each node returns only the fields it modifies. However, it means the type system provides no compile-time guarantees about which fields are populated at any given pipeline stage.

#### Class: `GlobalState` (lines 43-128)

**Fields (40+ total, grouped by concern):**

| Group | Fields | Types |
|-------|--------|-------|
| Run identity | `run_id`, `file_path`, `language` | `str` |
| Request | `request`, `model_config` | `CaseGenerationRequest`, `ModelConfigOverride` |
| Document | `parsed_document` | `ParsedDocument` |
| Research | `research_output`, `planned_scenarios`, `mapped_evidence` | `ResearchOutput`, `list[PlannedScenario]`, `dict[str, list[EvidenceRef]]` |
| Checkpoints | `checkpoints`, `checkpoint_coverage`, `checkpoint_paths`, `canonical_outline_nodes` | Typed lists |
| Cases | `draft_cases`, `test_cases` | `list[TestCase]` |
| Checklist | `optimized_tree` | `list[ChecklistNode]` |
| Quality | `quality_report` | `QualityReport` |
| Artifacts | `artifacts`, `error` | `dict[str, str]`, `ErrorInfo` |
| Iteration | `run_state`, `evaluation_report`, `iteration_index` | `RunState`, `EvaluationReport`, `int` |
| Project | `project_id`, `project_context_summary` | `str` |
| Template | `template_file_path`, `project_template`, `template_leaf_targets`, `mandatory_skeleton` | `str`, `ProjectChecklistTemplateFile`, `list[TemplateLeafTarget]`, `MandatorySkeletonNode` |
| Knowledge | `knowledge_context`, `knowledge_sources`, `knowledge_retrieval_success` | `str`, `list[str]`, `bool` |
| XMind ref | `reference_xmind_path`, `xmind_reference_summary` | `str`, `XMindReferenceSummary` |
| Timing | `draft_writer_timing` | `dict` (untyped) |
| Coverage | `coverage_result` | `CoverageResult \| None` |
| **MR fields** | `frontend_mr_config`, `backend_mr_config`, `mr_input`, `mr_analysis_result`, `frontend_mr_result`, `backend_mr_result` | **`Any`** |
| **MR data** | `mr_code_facts`, `mr_consistency_issues`, `mr_combined_summary` | **`list`** (untyped), **`list`** (untyped), `str` |

**Issues identified:**

1. **CRITICAL: Reverse dependency on service layer.** Line 40 imports `from app.services.coverage_detector import CoverageResult`. This violates the standard layered architecture principle where the domain layer should never depend on the service layer. `CoverageResult` is a simple Pydantic `BaseModel` with 3 fields (`covered_checkpoint_ids`, `uncovered_checkpoint_ids`, `coverage_map`) and should be relocated to the domain layer (e.g., `checkpoint_models.py` or a new `coverage_models.py`).

2. **CRITICAL: 6 MR-related fields typed as `Any`.** `frontend_mr_config`, `backend_mr_config`, `mr_input`, `mr_analysis_result`, `frontend_mr_result`, `backend_mr_result` are all `Any`. The domain layer already defines proper typed models (`MRSourceConfig`, `MRInput`, `MRAnalysisResult` in `mr_models.py`) that should be used instead. This completely bypasses type checking for MR-related state.

3. **`mr_code_facts` and `mr_consistency_issues` are typed as bare `list`** (equivalent to `list[Any]`). They should be `list[MRCodeFact]` and `list[ConsistencyIssue]` respectively, using models from `mr_models.py`.

4. **`draft_writer_timing` is typed as bare `dict`** without key/value types. Should be at minimum `dict[str, Any]` or ideally a dedicated timing model.

5. **Field name collision risk:** `model_config` as a field name on `GlobalState` shadows `pydantic.BaseModel.model_config`. Since `GlobalState` is a `TypedDict` (not `BaseModel`), this does not cause a runtime error, but it creates confusion and makes migration to BaseModel impossible.

#### Class: `CaseGenState` (lines 130-188)

Sub-graph state for the case generation phase. Mirrors a subset of `GlobalState` with the same issues:

- Same 6 `Any`-typed MR fields (lines 180-185).
- Same bare `list` for `mr_code_facts`, `mr_consistency_issues`, `uncovered_checkpoints` (lines 175, 186-187).
- No structural difference from `GlobalState` that would justify the duplication -- this is a partial copy with 30+ overlapping fields. A `Protocol` or shared base could reduce drift.

---

### §5.2.4 api_models.py

| Property | Value |
|----------|-------|
| Lines | 117 |
| Classes | 7 (`ModelConfigOverride`, `RunOptions`, `ErrorInfo`, `IterationSummary`, `MRRequestConfig`, `CaseGenerationRequest`, `CaseGenerationRun`) |
| Imports from domain | `case_models`, `document_models`, `research_models` |
| Role | API request/response contracts |

#### Type Classification: B -- Boundary Model

#### Class: `CaseGenerationRequest` (lines 68-96)

Primary API input model.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `file_path` | `str` | required | PRD file path |
| `language` | `str` | `"zh-CN"` | |
| `llm_config` | `ModelConfigOverride` | factory | Aliased from `"model_config"` |
| `options` | `RunOptions` | factory | |
| `project_id` | `str \| None` | `None` | |
| `template_file_path` | `str \| None` | `None` | |
| `template_name` | `str \| None` | `None` | |
| `reference_xmind_path` | `str \| None` | `None` | |
| `frontend_mr` | `MRRequestConfig \| None` | `None` | |
| `backend_mr` | `MRRequestConfig \| None` | `None` | |

**Issue:** `template_name` and `template_file_path` are documented as mutually exclusive ("template_name 优先"), but no validator enforces this. Both can be provided simultaneously with undefined merge semantics.

#### Class: `CaseGenerationRun` (lines 99-117)

| Field | Type | Notes |
|-------|------|-------|
| `status` | `Literal["pending","running","evaluating","retrying","succeeded","failed"]` | **Well-constrained** -- good use of Literal |
| `checkpoint_count` | `int` | Summary stat, not a list |

**Issue:** `MRRequestConfig` defines `mr_url`, `git_url`, `local_path`, `use_coco` as simple fields, but the more comprehensive `MRSourceConfig` in `mr_models.py` has richer structure (`CodebaseSource` with `branch`, `commit_sha`). The two models represent the same concept at different abstraction levels with no mapping between them.

#### Other Classes

- `ModelConfigOverride`: All-optional LLM parameter overrides. Clean design.
- `RunOptions`: Single bool field. Minimal.
- `ErrorInfo`: Code + message + detail dict. Standard error envelope.
- `IterationSummary`: Evaluation loop summary. Clean.

---

### §5.2.5 case_models.py

| Property | Value |
|----------|-------|
| Lines | 80 |
| Classes | 2 (`TestCase`, `QualityReport`) |
| Imports from domain | `research_models.EvidenceRef` |
| Role | Final output test case model |

#### Type Classification: C -- Core Model

#### Class: `TestCase` (lines 14-65)

**Fields (16 total):**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `id` | `str` | required | e.g., `TC-001` |
| `title` | `str` | required | |
| `preconditions` | `list[str]` | `[]` | |
| `steps` | `list[str]` | `[]` | |
| `expected_results` | `list[str]` | `[]` | |
| `priority` | `str` | `"P2"` | **Not Literal-constrained** |
| `category` | `str` | `"functional"` | **Not Literal-constrained** |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | |
| `checkpoint_id` | `str` | `""` | Back-reference |
| `project_id` | `str` | `""` | |
| `template_leaf_id` | `str` | `""` | Inherited from checkpoint |
| `template_path_ids` | `list[str]` | `[]` | Inherited from checkpoint |
| `template_path_titles` | `list[str]` | `[]` | Inherited from checkpoint |
| `template_match_confidence` | `float` | `0.0` | **No range validation** |
| `template_match_low_confidence` | `bool` | `False` | |
| `tags` | `list[str]` | `[]` | e.g., `'mr_derived'` |
| `code_consistency` | `dict[str, Any] \| None` | `None` | **Untyped dict** -- same issue as Checkpoint |

**Issues:**

1. **Template binding fields are duplicated** across `Checkpoint` and `TestCase` (5 fields each). There is no shared mixin or embedded model, which means changes to the template schema must be replicated in two places.

2. **`code_consistency` uses `dict[str, Any]`** instead of `CodeConsistencyResult` -- identical issue as `checkpoint_models.py`.

3. **`__test__ = False`** is a pragmatic workaround for pytest collection, but it is a code smell indicating the class name pattern conflicts with testing conventions.

#### Class: `QualityReport` (lines 68-80)

Six `list[str]` fields for quality metrics. Clean, no issues.

---

### §5.2.6 document_models.py

| Property | Value |
|----------|-------|
| Lines | 58 |
| Classes | 3 (`DocumentSource`, `DocumentSection`, `ParsedDocument`) |
| Imports from domain | None |
| Role | PRD document parsing output |

#### Type Classification: A -- Leaf Model (no domain dependencies)

#### Class: `DocumentSource`

| Field | Type | Notes |
|-------|------|-------|
| `source_path` | `str` | required |
| `source_type` | `str` | **Should be Literal** (e.g., `"markdown"`, `"docx"`, `"pdf"`) |
| `title` | `str` | |
| `checksum` | `str` | SHA-256 for cache invalidation |

#### Class: `DocumentSection`

Well-structured with required fields for `heading`, `level`, `line_start`, `line_end`. Content is optional. No issues.

#### Class: `ParsedDocument`

| Field | Type | Notes |
|-------|------|-------|
| `raw_text` | `str` | required -- full document text |
| `sections` | `list[DocumentSection]` | |
| `references` | `list[str]` | External references |
| `metadata` | `dict[str, Any]` | Untyped catch-all |
| `source` | `DocumentSource \| None` | |

Minimal issues. `metadata` could benefit from typing.

---

### §5.2.7 mr_models.py

| Property | Value |
|----------|-------|
| Lines | 295 |
| Classes | 11 (`MRDiffFile`, `MRInput`, `RelatedCodeSnippet`, `MRCodeFact`, `ConsistencyIssue`, `CocoTaskConfig`, `CocoTaskStatus`, `CodeConsistencyResult`, `MRAnalysisResult`, `CodebaseSource`, `MRSourceConfig`) |
| Imports from domain | None |
| Role | MR/merge request analysis models |

#### Type Classification: A -- Leaf Model (no domain dependencies)

This is the **largest file** in the domain layer and defines the complete MR analysis data model hierarchy.

**Key models:**

- `MRDiffFile`: Individual file diff representation (path, change type, diff content, language, additions/deletions).
- `MRInput`: Complete MR input (ID, title, description, branches, diff files, URL).
- `MRCodeFact`: Code-level facts extracted from MR diffs. `fact_type` is `str` (not Literal-constrained for `"code_logic"`, `"error_handling"`, `"boundary"`, `"state_change"`, `"side_effect"`).
- `ConsistencyIssue`: PRD-vs-MR consistency findings. `severity` is `str` (not Literal-constrained for `"critical"`, `"warning"`, `"info"`).
- `CodeConsistencyResult`: Per-checkpoint/case code consistency result. `status` is `str` (not Literal for `"confirmed"`, `"mismatch"`, `"unverified"`).
- `MRAnalysisResult`: Complete MR analysis output aggregating all sub-results.
- `MRSourceConfig` / `CodebaseSource`: API-level MR configuration.

**Issues:**

1. **`CodeConsistencyResult` exists here but is not used by `Checkpoint.code_consistency` or `TestCase.code_consistency`**, which instead use `dict[str, Any] | None`. This is the most significant type-safety gap in the domain layer.

2. **Duplicate MR config models:** `MRRequestConfig` (in `api_models.py`) and `MRSourceConfig` (in `mr_models.py`) serve overlapping purposes with different field sets and no documented mapping.

3. **Multiple `str` fields should be Literal-constrained:** `MRDiffFile.change_type`, `MRCodeFact.fact_type`, `ConsistencyIssue.severity`, `CodeConsistencyResult.status`, `CocoTaskStatus.status`, `RelatedCodeSnippet.relation_type`.

---

### §5.2.8 precondition_models.py

| Property | Value |
|----------|-------|
| Lines | 28 |
| Classes | 2 (`SemanticGroup`, `PreconditionGroupingResult`) |
| Imports from domain | None |
| Role | LLM-driven precondition semantic grouping |

#### Type Classification: A -- Leaf Model

Minimal, well-focused models for LLM structured output. `SemanticGroup.member_indices` uses 1-based indexing (documented in `Field(description=...)`). No issues.

---

### §5.2.9 project_models.py

| Property | Value |
|----------|-------|
| Lines | 68 |
| Classes | 3 (`ProjectType`, `RegulatoryFramework`, `ProjectContext`) |
| Imports from domain | None |
| Role | Project-level context and persistence |

#### Type Classification: A -- Leaf Model

**Well-designed model** with proper `str Enum` types for `ProjectType` (7 values) and `RegulatoryFramework` (8 values). `ProjectContext` has `Field` constraints (`min_length`, `max_length`), `uuid4` default for ID, and a `summary_text()` helper for LLM prompt injection.

**Minor issue:** Uses `datetime.utcnow` which is deprecated in Python 3.12+. Should use `datetime.now(timezone.utc)`.

---

### §5.2.10 research_models.py

| Property | Value |
|----------|-------|
| Lines | 254 |
| Classes | 4 (`EvidenceRef`, `ResearchFact`, `PlannedScenario`, `ResearchOutput`) |
| Functions | 2 (`_value_to_str`, `_extract_text_from_dict`) |
| Imports from domain | None |
| Role | PRD research analysis output |

#### Type Classification: A -- Foundational Model (no domain dependencies, heavily imported)

This is the **most imported module** in the domain layer -- `EvidenceRef` alone is imported by `checklist_models`, `checkpoint_models`, `case_models`, and `state.py`.

#### Class: `EvidenceRef` (lines 21-59)

PRD evidence traceability anchor. Notable for its sophisticated `model_validator(mode="before")` that handles:
- Dict input with key aliasing (`section` -> `section_title`, `quote` -> `excerpt`)
- String input via regex parsing: `"Section Name (10-20): excerpt text"`
- Plain string fallback: `"section: excerpt"`
- Empty string fallback: creates `{"section_title": "generated_ref"}`

This resilience is well-designed for LLM output parsing.

#### Class: `ResearchFact` (lines 62-113)

Also has a `model_validator` for LLM output normalization: handles `id` -> `fact_id`, `summary` -> `description`, `section_title` -> `source_section`, `change_type` -> `category` aliasing, and nested `requirement` dict flattening.

**Issue:** `category` field accepts `str` but docstring specifies `"requirement"`, `"constraint"`, `"assumption"`, `"behavior"` -- should be Literal.

#### Class: `ResearchOutput` (lines 188-254)

Aggregator with a `model_validator` that coerces `list[dict]` items to `list[str]` using the `_PRIMARY_KEY_MAP` dictionary. Handles diverse LLM output formats gracefully.

**No critical issues.** This is one of the better-designed modules in the domain layer.

---

### §5.2.11 run_state.py

| Property | Value |
|----------|-------|
| Lines | 119 |
| Classes | 7 (`RunStatus`, `RunStage`, `EvaluationDimension`, `EvaluationReport`, `RetryDecision`, `IterationRecord`, `RunState`) |
| Imports from domain | None |
| Role | Iteration evaluation loop state tracking |

#### Type Classification: A -- Leaf Model

**Well-designed with proper enums:**
- `RunStatus` (6 values): `pending`, `running`, `evaluating`, `retrying`, `succeeded`, `failed`
- `RunStage` (6 values): `context_research`, `checkpoint_generation`, `draft_generation`, `evaluation`, `output_delivery`, `xmind_delivery`

Both are `str, Enum` subclasses, enabling string comparison while maintaining type safety.

**`EvaluationReport`** includes `pass_threshold: float = 0.7` as a field with a default -- this should arguably be configuration, not embedded in the model.

**`RunState`** is a comprehensive state object with proper typing. `max_iterations: int = 3` is another policy value embedded in the model.

**Minor issue:** `RunState.error` is `dict[str, Any] | None` while `api_models.ErrorInfo` exists as a proper typed model.

---

### §5.2.12 template_models.py

| Property | Value |
|----------|-------|
| Lines | 136 |
| Classes | 5 (`ProjectChecklistTemplateNode`, `ProjectChecklistTemplateMetadata`, `ProjectChecklistTemplateFile`, `TemplateLeafTarget`, `MandatorySkeletonNode`) |
| Imports from domain | None |
| Role | Project-level checklist template structure |

#### Type Classification: A -- Leaf Model

Two self-referencing recursive trees (`ProjectChecklistTemplateNode` and `MandatorySkeletonNode`), both with `model_rebuild()` calls.

**`ProjectChecklistTemplateMetadata`** has a proper `field_validator` for `mandatory_levels` that enforces positive integers and deduplicates/sorts. Good validation practice.

**`MandatorySkeletonNode`** properly uses `Literal["template"]` for its `source` field.

**Issue:** `MandatorySkeletonNode.original_metadata` is typed as bare `dict` without key/value types.

---

### §5.2.13 xmind_models.py

| Property | Value |
|----------|-------|
| Lines | 55 |
| Classes | 2 (`XMindNode`, `XMindDeliveryResult`) |
| Imports from domain | None |
| Role | XMind output generation |

#### Type Classification: A -- Leaf Model

**`XMindNode`** is a simple recursive tree (title, children, markers, notes, labels). No `model_rebuild()` call -- **this may cause issues with Pydantic v2 self-referencing** (though in practice it often works without explicit rebuild for simple cases).

**`XMindDeliveryResult`** tracks delivery status. Uses `datetime.now().isoformat()` in a `default_factory` lambda for `delivery_time` -- no timezone awareness.

---

### §5.2.14 xmind_reference_models.py

| Property | Value |
|----------|-------|
| Lines | 65 |
| Classes | 2 (`XMindReferenceNode`, `XMindReferenceSummary`) |
| Imports from domain | `TYPE_CHECKING`-guarded import of `checklist_models.ChecklistNode` |
| Role | XMind reference file parsing and analysis |

#### Type Classification: B -- Integration Model

**`XMindReferenceNode`** is a minimal recursive tree for XMind input parsing (title + children only). Unlike `XMindNode`, this is for **reading** existing XMind files, not generating new ones.

**`XMindReferenceSummary`** is a rich analysis result model:

| Field | Type | Notes |
|-------|------|-------|
| `source_file` | `str` | required |
| `total_nodes` | `int` | required |
| `total_leaf_nodes` | `int` | required |
| `max_depth` | `int` | required |
| `skeleton` | `str` | Text representation of top layers |
| `sampled_paths` | `list[str]` | |
| `depth_distribution` | `dict[int, int]` | Depth -> count |
| `top_prefixes` | `list[str]` | |
| `formatted_summary` | `str` | required -- prompt-injectable text |
| `reference_tree` | `list` | **Untyped** -- should be `list[ChecklistNode]` |
| `all_leaf_titles` | `list[str]` | For coverage detection |

**Issue:** `reference_tree` is typed as bare `list` instead of `list[ChecklistNode]`. The `TYPE_CHECKING` import of `ChecklistNode` exists but is not used at runtime, so Pydantic cannot validate the list contents. This creates a type hole at the integration boundary between XMind reference parsing and checklist tree construction.

---

## §5.3 Model Dependency Graph

```
                         ┌──────────────────────┐
                         │   research_models     │  (EvidenceRef, ResearchFact,
                         │   [FOUNDATION]        │   PlannedScenario, ResearchOutput)
                         └──────────┬───────────┘
                                    │ imported by
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
           ┌────────────┐  ┌───────────────┐  ┌──────────────┐
           │ checklist_  │  │ checkpoint_   │  │ case_models  │
           │ models      │  │ models        │  │              │
           └─────┬───────┘  └───────┬───────┘  └──────┬───────┘
                 │                  │                  │
                 └──────────┬───────┘──────────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │   api_models         │  (imports case_models, document_models,
                 │                      │   research_models)
                 └──────────┬───────────┘
                            │
                            ▼
┌────────────┐   ┌──────────────────────┐   ┌─────────────────────┐
│ run_state  │──▶│     state.py         │◀──│ template_models     │
└────────────┘   │  [ORCHESTRATION HUB] │   └─────────────────────┘
                 │                      │
┌────────────┐   │  Imports from ALL    │   ┌─────────────────────┐
│ document_  │──▶│  domain modules +    │◀──│ xmind_reference_    │
│ models     │   │  service layer (!)   │   │ models              │
└────────────┘   └──────────────────────┘   └─────────────────────┘

Isolated (no domain imports):
  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │ mr_models        │  │ precondition_    │  │ project_models   │
  │ (11 classes)     │  │ models           │  │                  │
  └──────────────────┘  └──────────────────┘  └──────────────────┘
  ┌──────────────────┐
  │ xmind_models     │
  └──────────────────┘
```

### Dependency Summary Table

| Module | Depends On (domain) | Depended On By |
|--------|-------------------|----------------|
| `research_models` | -- | `checklist_models`, `checkpoint_models`, `case_models`, `api_models`, `state` |
| `document_models` | -- | `api_models`, `state` |
| `case_models` | `research_models` | `api_models`, `state` |
| `checklist_models` | `research_models` | `state` |
| `checkpoint_models` | `research_models` | `state` |
| `api_models` | `case_models`, `document_models`, `research_models` | `state` |
| `template_models` | -- | `state` |
| `run_state` | -- | `state` |
| `xmind_reference_models` | (`checklist_models` TYPE_CHECKING only) | `state` |
| `mr_models` | -- | (not imported by any domain module!) |
| `precondition_models` | -- | -- |
| `project_models` | -- | -- |
| `xmind_models` | -- | -- |
| `state` | **10 domain modules + 1 service module** | -- |

### Circular Dependencies

**No circular import dependencies exist** at the module level. The `xmind_reference_models` -> `checklist_models` reference is guarded by `TYPE_CHECKING` and does not create a runtime cycle.

### Anomaly: `mr_models` is Orphaned in Domain

`mr_models.py` defines 11 classes (the most of any file) but is **not imported by any other domain module**, including `state.py`. Instead, `state.py` uses `Any` for all MR-related fields. This means the MR domain models exist but are not integrated into the type system of the workflow state.

---

## §5.4 Key Findings

### Finding 1: Service-Layer Dependency Violation in Domain (CRITICAL)

`state.py` line 40 imports `from app.services.coverage_detector import CoverageResult`. This creates a reverse dependency from the domain layer into the service layer, violating clean architecture. `CoverageResult` is a 3-field Pydantic model that should be relocated to `app/domain/checkpoint_models.py` or a new `app/domain/coverage_models.py`.

**Impact:** Prevents independent testing of the domain layer; creates a coupling path from domain to service internals.

### Finding 2: MR Fields in State Are Completely Untyped (CRITICAL)

12 MR-related fields across `GlobalState` and `CaseGenState` use `Any` or bare `list` types despite the existence of fully typed models in `mr_models.py`. This means:
- No IDE autocompletion or type checking for MR data flowing through the pipeline.
- Runtime `AttributeError` risks when accessing fields on `Any`-typed values.
- The 295 lines of careful MR model definitions are effectively dead code from a type-safety perspective.

**Affected fields (in both `GlobalState` and `CaseGenState`):**
- `frontend_mr_config: Any` -- should be `MRSourceConfig | None`
- `backend_mr_config: Any` -- should be `MRSourceConfig | None`
- `mr_input: Any` -- should be `MRInput | None`
- `mr_analysis_result: Any` -- should be `MRAnalysisResult | None`
- `frontend_mr_result: Any` -- should be `MRAnalysisResult | None`
- `backend_mr_result: Any` -- should be `MRAnalysisResult | None`
- `mr_code_facts: list` -- should be `list[MRCodeFact]`
- `mr_consistency_issues: list` -- should be `list[ConsistencyIssue]`

### Finding 3: `code_consistency` Field Type Mismatch (HIGH)

Both `Checkpoint.code_consistency` and `TestCase.code_consistency` are typed as `dict[str, Any] | None`, while `mr_models.py` defines a proper `CodeConsistencyResult` model with 7 typed fields. This creates a disconnect where:
- Producers must serialize `CodeConsistencyResult` to dict before assignment.
- Consumers must do untyped dict access instead of attribute access.
- No validation occurs on the structure of the dict.

### Finding 4: Missing Conditional Validation on `ChecklistNode` (HIGH)

`ChecklistNode.node_type` defines 5 possible values, each with different semantic requirements, but no validator enforces field completeness per type:
- `"case"` nodes should require non-empty `steps`, `expected_results`, and `checkpoint_id`.
- `"root"` nodes should disallow `steps`, `expected_results`, `test_case_ref`.
- `"group"` nodes should not have `test_case_ref` populated.

Without these validations, malformed nodes pass silently through the pipeline.

### Finding 5: Systematic Lack of `Literal` Constraints (MEDIUM)

Multiple fields document allowed values in docstrings but use plain `str` types:

| Model | Field | Documented Values |
|-------|-------|-------------------|
| `Checkpoint` | `category` | `functional`, `edge_case`, `performance`, `security` |
| `Checkpoint` | `risk` | `low`, `medium`, `high` |
| `Checkpoint` | `coverage_status` | `uncovered`, `partial`, `covered` |
| `CheckpointCoverage` | `coverage_status` | `uncovered`, `partial`, `covered` |
| `TestCase` | `priority` | `P0`-`P3` |
| `TestCase` | `category` | `functional`, `edge_case`, `performance`, etc. |
| `DocumentSource` | `source_type` | `markdown`, `docx`, etc. |
| `MRCodeFact` | `fact_type` | `code_logic`, `error_handling`, `boundary`, `state_change`, `side_effect` |
| `ConsistencyIssue` | `severity` | `critical`, `warning`, `info` |
| `CodeConsistencyResult` | `status` | `confirmed`, `mismatch`, `unverified` |

This is the most pervasive design issue in the domain layer and affects type safety across the entire pipeline.

### Finding 6: Template Binding Field Duplication (MEDIUM)

Five template-related fields (`template_leaf_id`, `template_path_ids`, `template_path_titles`, `template_match_confidence`, `template_match_low_confidence`) are duplicated verbatim across `Checkpoint` and `TestCase`. A shared `TemplateBinding` embedded model would:
- Eliminate duplication.
- Ensure consistent field naming and typing.
- Make the inheritance relationship explicit.

### Finding 7: `GlobalState` / `CaseGenState` Drift Risk (MEDIUM)

`CaseGenState` is a manual subset of `GlobalState` with 30+ overlapping fields. There is no mechanism to ensure they stay synchronized. When a new field is added to `GlobalState`, it may or may not be added to `CaseGenState`, leading to silent data loss at subgraph boundaries.

### Finding 8: `reference_tree` Type Hole (LOW)

`XMindReferenceSummary.reference_tree` is typed as `list` (bare) despite an existing `TYPE_CHECKING` import of `ChecklistNode`. The runtime type should be `list[ChecklistNode]` but Pydantic cannot validate this at the bare-list level.

---

## §5.5 Improvement Recommendations

### R1: Relocate `CoverageResult` to Domain Layer (Priority: P0)

Move `CoverageResult` from `app.services.coverage_detector` to `app.domain.checkpoint_models` (or a new `coverage_models.py`). Update the import in `state.py` and `coverage_detector.py`. This eliminates the architecture violation.

```python
# In checkpoint_models.py (or new coverage_models.py):
class CoverageResult(BaseModel):
    covered_checkpoint_ids: list[str] = Field(default_factory=list)
    uncovered_checkpoint_ids: list[str] = Field(default_factory=list)
    coverage_map: dict[str, str] = Field(default_factory=dict)
```

### R2: Type All MR Fields in State (Priority: P0)

Replace `Any` and bare `list` types in `GlobalState` and `CaseGenState` with proper imports from `mr_models.py`:

```python
from app.domain.mr_models import (
    MRSourceConfig, MRInput, MRAnalysisResult, MRCodeFact, ConsistencyIssue,
)

# In GlobalState:
frontend_mr_config: MRSourceConfig | None
backend_mr_config: MRSourceConfig | None
mr_input: MRInput | None
mr_analysis_result: MRAnalysisResult | None
frontend_mr_result: MRAnalysisResult | None
backend_mr_result: MRAnalysisResult | None
mr_code_facts: list[MRCodeFact]
mr_consistency_issues: list[ConsistencyIssue]
```

### R3: Use `CodeConsistencyResult` Instead of `dict[str, Any]` (Priority: P1)

Update `Checkpoint.code_consistency` and `TestCase.code_consistency` to:
```python
code_consistency: CodeConsistencyResult | None = None
```

### R4: Add Conditional Validation to `ChecklistNode` (Priority: P1)

Add a `model_validator(mode="after")` that enforces field requirements per `node_type`:

```python
@model_validator(mode="after")
def validate_node_type_fields(self) -> ChecklistNode:
    if self.node_type == "case":
        if not self.steps and not self.expected_results:
            raise ValueError("case nodes require steps or expected_results")
    elif self.node_type == "root":
        if self.test_case_ref:
            raise ValueError("root nodes should not have test_case_ref")
    return self
```

### R5: Introduce `Literal` Constraints for Enumerated String Fields (Priority: P1)

Replace `str` with `Literal[...]` for all fields documented with fixed value sets. At minimum:
- `Checkpoint.coverage_status` -> `Literal["uncovered", "partial", "covered"]`
- `Checkpoint.category` -> `Literal["functional", "edge_case", "performance", "security"]`
- `Checkpoint.risk` -> `Literal["low", "medium", "high"]`

### R6: Extract `TemplateBinding` Embedded Model (Priority: P2)

```python
class TemplateBinding(BaseModel):
    template_leaf_id: str = ""
    template_path_ids: list[str] = Field(default_factory=list)
    template_path_titles: list[str] = Field(default_factory=list)
    template_match_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    template_match_low_confidence: bool = False
    template_match_reason: str = ""

# Usage:
class Checkpoint(BaseModel):
    template_binding: TemplateBinding = Field(default_factory=TemplateBinding)
```

### R7: Consolidate MR Config Models (Priority: P2)

Merge `MRRequestConfig` (in `api_models.py`) and `MRSourceConfig` (in `mr_models.py`) into a single canonical model, or establish an explicit conversion function.

### R8: Type `reference_tree` and `draft_writer_timing` (Priority: P3)

- `XMindReferenceSummary.reference_tree` -> `list[ChecklistNode]` (requires moving import out of `TYPE_CHECKING`).
- `GlobalState.draft_writer_timing` -> `dict[str, float]` or a dedicated `TimingMetadata` model.

---

## §5.6 Cross-References

| Reference Target | Section | Relevance |
|-----------------|---------|------------|
| `app/services/coverage_detector.py` | §5.2.3, §5.4 F1 | Contains `CoverageResult` that should be in domain |
| Checklist rendering pipeline | §5.2.1 | `ChecklistNode` is the final tree consumed by renderers |
| LangGraph workflow nodes | §5.2.3 | `GlobalState`/`CaseGenState` are the workflow state contracts |
| Checkpoint generation prompts | §5.2.2 | `Checkpoint` fields must match LLM output parsing expectations |
| XMind delivery service | §5.2.13, §5.2.14 | `XMindNode` (output) vs `XMindReferenceNode` (input) |
| MR analysis pipeline | §5.2.7, §5.4 F2 | `mr_models` types not wired into `state.py` |
| Template YAML parser | §5.2.12 | `ProjectChecklistTemplateFile` is the parse target |
| Draft writer / case generation | §5.2.5 | `TestCase` is the primary generation output |
| PRD document parser | §5.2.6 | `ParsedDocument` feeds into research stage |
| Evaluation loop | §5.2.11 | `RunState`/`EvaluationReport` drive retry decisions |
| Project context DB | §5.2.9 | `ProjectContext` persisted for cross-run reuse |

---

*Analysis generated for the AutoChecklist domain layer. 14 files, 1,694 lines, 57 classes examined.*