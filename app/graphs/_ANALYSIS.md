# app/graphs/ Directory Analysis

## §6.1 Directory Overview

The `app/graphs/` directory is the **core orchestration layer** of the AutoChecklist system. It defines the LangGraph-based workflow graphs that drive the entire test case generation pipeline. This directory contains three files that collectively implement:

1. **The main workflow graph** (`main_workflow.py`) -- the top-level pipeline that sequences all major processing phases from document parsing through reflection.
2. **The case generation sub-graph** (`case_generation.py`) -- a dedicated sub-pipeline for the multi-step test case generation process, invoked as a single composite node within the main workflow.
3. **The state bridge mechanism** (`state_bridge.py`) -- an automatic TypedDict-based field forwarding system that manages data flow between the main graph's `GlobalState` and the sub-graph's `CaseGenState`, enforcing strict input/output boundaries.

**Technology**: All graphs are built using LangGraph's `StateGraph` API, compiled into executable workflows via `builder.compile()`. The architecture is a strictly linear pipeline (no conditional branching or cycles in the current implementation), with optional nodes dynamically inserted based on runtime configuration.

**Criticality**: **CRITICAL**. Every aspect of checklist quality -- from document understanding through checkpoint generation to final test case assembly -- is determined by the node execution order and data flow defined in these files. Any modification to node sequencing, state bridging, or sub-graph boundaries directly affects output quality.

---

## §6.2 File Analysis

### §6.2.1 main_workflow.py

**Type**: Type A -- Core Orchestration  
**Criticality**: **CRITICAL**  
**Lines**: ~180 (active code) + ~60 (deprecated fallback)  
**Primary Export**: `build_workflow()` function

#### LangGraph StateGraph Definition

The main workflow operates on `GlobalState` (a TypedDict defined in `app.domain.state`). The `StateGraph(GlobalState)` builder accumulates nodes and edges, then `builder.compile()` produces an immutable executable graph.

Key design decision: the graph uses **incremental state updates** -- each node receives the full `GlobalState` and returns only the fields it modifies, which LangGraph merges back into the accumulated state.

#### Full Pipeline Definition

The complete node execution order is:

```
START
  → input_parser          (parse raw document into structured form)
  → template_loader       (load project template; always present, self-skips if no template)
  → [xmind_reference_loader]   (OPTIONAL: load reference XMind file for coverage comparison)
  → [project_context_loader]   (OPTIONAL: inject project-specific context/standards)
  → [knowledge_retrieval]      (OPTIONAL: GraphRAG-based knowledge base lookup)
  → context_research      (LLM-powered analysis of the parsed document + all gathered context)
  → case_generation        (SUB-GRAPH: the entire checkpoint/case generation pipeline)
  → reflection             (post-generation quality reflection)
  → END
```

#### Dynamic Node Insertion Pattern

The `build_workflow()` function accepts optional node callables as parameters:

| Parameter | Node Name | Condition |
|---|---|---|
| `xmind_reference_loader_node` | `xmind_reference_loader` | Inserted if not `None` |
| `project_context_loader` | `project_context_loader` | Inserted if not `None` |
| `knowledge_retrieval_node` | `knowledge_retrieval` | Inserted if not `None` |

The insertion uses a **`prev_node` chaining pattern**:

```python
prev_node = "template_loader"
if xmind_reference_loader_node is not None:
    builder.add_edge(prev_node, "xmind_reference_loader")
    prev_node = "xmind_reference_loader"
if project_context_loader is not None:
    builder.add_edge(prev_node, "project_context_loader")
    prev_node = "project_context_loader"
# ... etc
builder.add_edge(prev_node, "context_research")
```

This ensures the linear chain remains intact regardless of which optional nodes are enabled. The pattern is clean but means the pipeline is always linear -- there is no parallel execution of optional loaders.

#### Node Execution Order Impact on Checklist Quality

The ordering is deliberately designed so that **each node enriches the state for downstream nodes**:

1. `input_parser` produces `parsed_document` -- the foundation for everything.
2. `template_loader` produces `template_leaf_targets` and `project_template` -- structural constraints for case generation.
3. `xmind_reference_loader` produces `xmind_reference_summary` -- reference coverage targets.
4. `project_context_loader` produces `project_context_summary` -- domain-specific standards.
5. `knowledge_retrieval` injects retrieved knowledge context from the GraphRAG engine.
6. `context_research` synthesizes ALL of the above into `research_output` -- the primary input to case generation.
7. `case_generation` (sub-graph) produces test cases, checkpoints, coverage results.
8. `reflection` evaluates the generated output quality.

**Critical insight**: The quality of `context_research` output is the single most important factor for downstream case generation quality, because it is the synthesis point where all gathered context merges. If any upstream loader fails silently (returns empty data), `context_research` proceeds with degraded input, and the entire downstream pipeline produces lower-quality output without explicit error signals.

#### State Bridge for Sub-graph Integration

The `case_generation` node is not a simple function -- it is a compiled LangGraph sub-graph wrapped in an automatic state bridge:

```python
case_gen_bridge = build_bridge(
    subgraph=case_generation_subgraph,
    parent_type=GlobalState,
    child_type=CaseGenState,
    override_in={"language": "zh-CN", "project_context_summary": "", "template_leaf_targets": []},
    include_out={"planned_scenarios", "checkpoints", "checkpoint_coverage",
                 "draft_cases", "test_cases", "optimized_tree", "coverage_result"},
)
```

The `include_out` allowlist is the **critical security boundary** -- only these 7 fields propagate from the sub-graph back to the main graph. This prevents sub-graph internal intermediate state (e.g., `uncovered_checkpoints`, `evidence_mapper` scratch data) from leaking into the main graph's state.

#### Timer Integration

Every node is wrapped with `maybe_wrap(name, fn, timer, iteration_index)` which, when a `NodeTimer` is provided, records execution time per node. This enables performance profiling without code changes to individual nodes.

#### Deprecated Fallback

The file retains `_build_case_generation_bridge()` (marked `pragma: no cover`) as a manual bridge implementation for emergency rollback. This deprecated function explicitly maps ~15 fields in each direction, including MR-related fields (`mr_input`, `mr_code_facts`, `mr_consistency_issues`, etc.).

---

### §6.2.2 case_generation.py

**Type**: Type A -- Core Sub-pipeline  
**Criticality**: **HIGH**  
**Lines**: ~130  
**Primary Export**: `build_case_generation_subgraph()` function

#### Sub-graph Pipeline Definition

The case generation sub-graph operates on `CaseGenState` and implements an 11-node linear pipeline:

```
START
  → mr_analyzer                  (analyze MR code changes, extract code facts)
  → mr_checkpoint_injector       (convert MR code facts into checkpoints)
  → scenario_planner             (plan test scenarios from research output)
  → checkpoint_generator         (LLM: convert facts into explicit checkpoints)
  → checkpoint_evaluator         (deduplicate and normalize checkpoints)
  → coverage_detector            (compare checkpoints against XMind reference leaves)
  → checkpoint_outline_planner   (LLM: plan shared hierarchy, produce optimized_tree)
  → evidence_mapper              (match PRD document evidence to each scenario)
  → draft_writer                 (LLM: generate leaf-level test case drafts)
  → coco_consistency_validator   (validate checkpoint-code consistency via Coco Agent)
  → structure_assembler          (standardize case structure, fill missing fields)
  → END
```

#### Node Responsibilities and Quality Impact

| Node | LLM? | Quality Impact |
|---|---|---|
| `mr_analyzer` | Yes (via llm_client) | Determines code-aware testing coverage |
| `mr_checkpoint_injector` | No | Merges code-derived checkpoints |
| `scenario_planner` | No (rule-based) | Determines scenario breadth |
| `checkpoint_generator` | **Yes** | Core quality driver -- generates the checkpoints |
| `checkpoint_evaluator` | No | Dedup quality gate |
| `coverage_detector` | No | Reference coverage measurement |
| `checkpoint_outline_planner` | **Yes** | Determines hierarchical organization |
| `evidence_mapper` | No | PRD traceability |
| `draft_writer` | **Yes** | Core quality driver -- generates actual test case text |
| `coco_consistency_validator` | External | Code consistency validation |
| `structure_assembler` | No | Output normalization |

The three **LLM-critical nodes** (`checkpoint_generator`, `checkpoint_outline_planner`, `draft_writer`) are the primary determinants of checklist quality. Their prompts, temperature settings, and output parsing directly control:
- Whether all relevant test scenarios are captured
- Whether the hierarchical structure is logical and navigable
- Whether individual test cases are actionable and specific

#### Coverage Detector Implementation

The file includes an inline `_coverage_detector_node()` function (not imported from a separate module) that:
1. Checks if `xmind_reference_summary` exists and has `all_leaf_titles`
2. Instantiates `CoverageDetector` from `app.services.coverage_detector`
3. Produces `coverage_result` and `uncovered_checkpoints`
4. Returns `None` for `coverage_result` if no reference is available

This is notable because it is the only node defined inline within the graph module rather than imported from a dedicated node module.

#### Optional Node Pattern

Unlike the main workflow's dynamic insertion, the sub-graph **always includes all 11 nodes**. The `mr_analyzer` and `coco_consistency_validator` are built with factory functions that accept optional configuration (`codebase_root`, `coco_settings`), and internally short-circuit (return empty results) when their configuration is absent. This means the sub-graph topology is static, but node behavior is conditional.

---

### §6.2.3 state_bridge.py

**Type**: Type A -- Infrastructure  
**Criticality**: **HIGH**  
**Lines**: ~160  
**Primary Exports**: `build_bridge()`, `compute_shared_keys()`

#### Automatic State Bridge Mechanism

The state bridge solves the problem of manually maintaining field mappings between `GlobalState` (main graph) and `CaseGenState` (sub-graph). It uses Python's `typing.get_type_hints()` to introspect both TypedDict types at build time and compute their intersection.

#### `compute_shared_keys(parent_type, child_type)`

- Uses `get_type_hints()` to extract field names from both TypedDict types
- Computes `frozenset(parent_keys & child_keys)` -- the intersection
- Results cached via `@lru_cache(maxsize=16)` since TypedDict fields are static
- Logs the shared key count and names at INFO level

#### `build_bridge()` -- Design Principles

**Inbound mapping (main graph -> sub-graph)**:
- **Default: auto-forward all shared keys** present in the parent state
- `override_in` provides defaults for missing keys (NOT for None-valued keys)
- The `None` vs. missing distinction is intentional: explicit `None` preserves business semantics (e.g., "feature disabled"), while missing keys use the override default

**Outbound mapping (sub-graph -> main graph)**:
- **Strict allowlist via `include_out`** -- ONLY explicitly listed fields propagate back
- This is the most important security boundary in the architecture
- Prevents sub-graph intermediate state from leaking to the main graph

#### Validation at Build Time

The bridge constructor validates:
- `override_in` keys that are NOT in the shared set (stale configuration warning)
- `include_out` keys that are NOT in the shared set (stale configuration warning)

This catches configuration drift when TypedDict fields are renamed or removed.

#### Runtime Behavior

For each invocation:
1. **IN**: Iterate shared keys, forward from parent state or use override default
2. **EXECUTE**: `subgraph.invoke(subgraph_input)`
3. **OUT**: Iterate shared keys, only forward those in `include_out` that exist in subgraph result
4. Debug logging tracks forwarded/missing/skipped counts in both directions

---

## §6.3 Workflow Architecture

### Complete Workflow Graph (Expanded)

```
[Main Workflow - GlobalState]
START
  ├─ input_parser                    (sync, rule-based)
  ├─ template_loader                 (sync, file I/O)
  ├─ [xmind_reference_loader]        (optional, file I/O)
  ├─ [project_context_loader]        (optional, DB lookup)
  ├─ [knowledge_retrieval]           (optional, async GraphRAG)
  ├─ context_research                (LLM call)
  ├─ case_generation ───────────────── [Sub-graph - CaseGenState]
  │     ├─ mr_analyzer               (optional LLM, code analysis)
  │     ├─ mr_checkpoint_injector    (sync, merge)
  │     ├─ scenario_planner          (sync, rule-based)
  │     ├─ checkpoint_generator      (LLM call -- CRITICAL)
  │     ├─ checkpoint_evaluator      (sync, dedup)
  │     ├─ coverage_detector         (sync, comparison)
  │     ├─ checkpoint_outline_planner (LLM call -- CRITICAL)
  │     ├─ evidence_mapper           (sync, matching)
  │     ├─ draft_writer              (LLM call -- CRITICAL)
  │     ├─ coco_consistency_validator (optional, external agent)
  │     └─ structure_assembler       (sync, normalization)
  ├─ reflection                      (sync, evaluation)
  └─ END
```

### Critical Path for Checklist Quality

The quality-critical path is:

```
input_parser → context_research → checkpoint_generator → checkpoint_outline_planner → draft_writer
```

These 5 nodes (4 in the pipeline, with `context_research` feeding into the sub-graph) determine:
1. **Completeness**: Whether all PRD requirements are captured as checkpoints
2. **Organization**: Whether checkpoints are logically grouped into a navigable tree
3. **Specificity**: Whether each test case is concrete and actionable

### Data Flow Boundaries

| Boundary | Mechanism | Direction | Policy |
|---|---|---|---|
| Main → Sub-graph | `build_bridge` inbound | auto-forward shared keys | Permissive (all shared) |
| Sub-graph → Main | `build_bridge` outbound | `include_out` allowlist | Restrictive (7 fields) |
| Nodes → State | LangGraph merge | incremental dict return | Additive only |

### Iteration Support

The workflow supports multi-iteration refinement via the `iteration_index` parameter passed to `build_workflow()`. The outer orchestration layer (not in this directory) can invoke `build_workflow()` multiple times with incrementing `iteration_index`, using the `reflection` node's output to decide whether another iteration is needed. The `timer` parameter tracks per-iteration timing independently.

---

## §6.4 Key Findings

1. **Linear-only topology**: Both the main workflow and sub-graph are strictly linear pipelines. There are no conditional edges, parallel branches, or cycles within the graph definitions themselves. Iteration is handled externally. This simplifies debugging but limits parallelism opportunities (e.g., `project_context_loader` and `knowledge_retrieval` could theoretically run in parallel).

2. **Asymmetric bridge policy**: The inbound auto-forward / outbound allowlist design is a deliberate security choice. The comment in `state_bridge.py` explicitly states that adding a new main-graph-visible output requires updating `include_out` AND adding a corresponding test. This is well-documented but relies on developer discipline.

3. **Silent degradation risk**: Optional nodes (`xmind_reference_loader`, `project_context_loader`, `knowledge_retrieval`) return empty data when unconfigured, and `context_research` proceeds without error. This means a misconfiguration that disables a critical context source produces no error -- only degraded quality.

4. **Inline node definition**: `_coverage_detector_node()` is defined inline in `case_generation.py` rather than in a dedicated `app/nodes/` module. This breaks the pattern established by all other nodes and may cause confusion during maintenance.

5. **Sub-graph nodes are always present**: The sub-graph's MR analysis and Coco validation nodes are always in the graph topology but internally short-circuit. This adds minor overhead but keeps the graph structure deterministic.

6. **Deprecated code retained**: The manual bridge function `_build_case_generation_bridge()` is kept for rollback capability. It contains explicit MR field mappings that are NOT present in the `include_out` set of the current automatic bridge, suggesting the automatic bridge may have intentionally narrowed the output boundary for MR fields.

7. **Three LLM-critical bottleneck nodes**: `checkpoint_generator`, `checkpoint_outline_planner`, and `draft_writer` are the three nodes where LLM quality most directly impacts output. Any prompt engineering, model selection, or temperature tuning effort should prioritize these nodes.

---

## §6.5 Cross-References

| Reference | Target | Relationship |
|---|---|---|
| `GlobalState` | `app/domain/state.py` | Main graph state type |
| `CaseGenState` | `app/domain/state.py` | Sub-graph state type |
| `LLMClient` | `app/clients/llm.py` (§4) | Injected into LLM-calling nodes |
| `input_parser_node` | `app/nodes/input_parser.py` | First pipeline node |
| `build_context_research_node` | `app/nodes/context_research.py` | LLM synthesis node |
| `reflection_node` | `app/nodes/reflection.py` | Post-generation evaluation |
| `build_template_loader_node` | `app/nodes/template_loader.py` | Template loading |
| `scenario_planner_node` | `app/nodes/scenario_planner.py` | Scenario planning |
| `build_checkpoint_generator_node` | `app/nodes/checkpoint_generator.py` | Checkpoint generation (LLM) |
| `checkpoint_evaluator_node` | `app/nodes/checkpoint_evaluator.py` | Checkpoint dedup |
| `CoverageDetector` | `app/services/coverage_detector.py` | Coverage comparison |
| `build_checkpoint_outline_planner_node` | `app/services/checkpoint_outline_planner.py` | Hierarchy planning (LLM) |
| `evidence_mapper_node` | `app/nodes/evidence_mapper.py` | PRD evidence matching |
| `DraftWriterNode` | `app/nodes/draft_writer.py` | Test case draft generation (LLM) |
| `build_mr_analyzer_node` | `app/nodes/mr_analyzer.py` | MR code analysis |
| `build_mr_checkpoint_injector_node` | `app/nodes/mr_checkpoint_injector.py` | MR checkpoint injection |
| `build_coco_consistency_validator_node` | `app/nodes/coco_consistency_validator.py` | Code consistency validation |
| `structure_assembler_node` | `app/nodes/structure_assembler.py` | Output normalization |
| `maybe_wrap` / `NodeTimer` | `app/utils/timing.py` (§12) | Node-level timing infrastructure |
| `WorkflowService` | `app/services/workflow_service.py` | Invokes `build_workflow()` |
| API route `create_case_generation_run` | `app/api/routes.py` (§3) | HTTP entry point |