# tests/ Directory Analysis

## §14.1 Directory Overview

The `tests/` directory contains a comprehensive but unevenly distributed test suite for the AutoChecklist project. The suite is organized into three tiers: root-level specialty tests, a `unit/` subdirectory with 37 test files, and an `integration/` subdirectory with 6 test files. A shared `conftest.py` provides two fake LLM client fixtures (`FakeLLMClient` for high-quality responses and `FakeLLMClientLowQuality` for low-quality/retry scenarios). A `fixtures/` directory holds a single `sample_prd.md` used by integration tests.

**Framework**: pytest (with `conftest.py` fixtures, class-based and function-based test organization)
**Total test files**: 45 (37 unit + 6 integration + 2 root-level)
**Key fixture**: `tests/conftest.py` -- provides `FakeLLMClient` and `FakeLLMClientLowQuality` that return deterministic structured responses for `ResearchOutput`, `CheckpointDraftCollection`, `DraftCaseCollection`, `CanonicalOutlineNodeCollection`, `CheckpointPathCollection`, `SemanticNodeCollection`, and `SemanticPathCollection`.

### Directory Tree

```
tests/
├── __init__.py
├── conftest.py                          (21 KB - shared fixtures)
├── test_draft_writer_concurrency.py     (10.8 KB)
├── test_timing.py                       (10.7 KB)
├── fixtures/
│   └── sample_prd.md                    (229 B)
├── unit/
│   ├── test_app_logging.py              (1.4 KB)
│   ├── test_attach_expected_results.py  (13.5 KB)
│   ├── test_checklist_logging.py        (4.8 KB)
│   ├── test_checklist_merger.py         (3.5 KB)
│   ├── test_checklist_optimizer.py      (5.7 KB)
│   ├── test_checkpoint.py              (4.8 KB)
│   ├── test_checkpoint_batch_planning.py (14.8 KB)
│   ├── test_checkpoint_outline_planner.py (7.3 KB)
│   ├── test_checkpoint_outline_planner_compile.py (0.4 KB)
│   ├── test_checkpoint_outline_planner_import.py  (0.6 KB)
│   ├── test_coverage_detector.py        (4.0 KB)
│   ├── test_draft_writer.py             (4.1 KB)
│   ├── test_evaluation.py              (10.8 KB)
│   ├── test_graphrag_engine.py          (5.1 KB)
│   ├── test_health.py                  (0.2 KB)
│   ├── test_knowledge_ingestion.py      (5.4 KB)
│   ├── test_knowledge_retrieval.py      (5.9 KB)
│   ├── test_llm_client.py              (8.1 KB)
│   ├── test_llm_retry.py              (19.5 KB)
│   ├── test_markdown_parser.py          (0.3 KB)
│   ├── test_markdown_renderer.py        (6.4 KB)
│   ├── test_models.py                  (0.2 KB)
│   ├── test_nodes.py                   (3.5 KB)
│   ├── test_precondition_grouper.py    (20.0 KB)
│   ├── test_project_context_loader.py   (5.2 KB)
│   ├── test_project_context_service.py  (1.4 KB)
│   ├── test_project_models.py          (1.4 KB)
│   ├── test_project_repository.py       (1.8 KB)
│   ├── test_project_routes.py          (2.7 KB)
│   ├── test_run_id.py                  (5.4 KB)
│   ├── test_run_repository.py          (0.3 KB)
│   ├── test_run_state.py               (6.9 KB)
│   ├── test_semantic_path_normalizer.py (4.1 KB)
│   ├── test_state_annotations.py        (2.6 KB)
│   ├── test_state_bridge.py            (8.2 KB)
│   ├── test_structure_assembler.py      (5.9 KB)
│   ├── test_text_normalizer.py         (9.9 KB)
│   ├── test_xmind_delivery.py          (23.4 KB)
│   ├── test_xmind_parser.py            (6.5 KB)
│   ├── test_xmind_reference_analyzer.py (7.7 KB)
│   ├── test_xmind_reference_loader.py   (7.3 KB)
│   ├── test_xmind_reference_tree_converter.py (5.1 KB)
│   └── test_xmind_steps_rendering.py   (10.3 KB)
└── integration/
    ├── test_api.py                      (3.5 KB)
    ├── test_iteration_loop.py           (6.4 KB)
    ├── test_knowledge_workflow.py        (3.6 KB)
    ├── test_project_workflow.py          (4.4 KB)
    ├── test_workflow.py                 (2.0 KB)
    └── test_xmind_reference_e2e.py      (9.6 KB)
```

---

## §14.2 Test Coverage Analysis

### §14.2.1 Unit Test Coverage Matrix

| Source Module | Test File | Coverage Grade | Notes |
|---|---|---|---|
| `services/checklist_merger.py` | `test_checklist_merger.py` | **C** | Only 2 tests: shared-prefix merge and hidden-anchor filtering. No tests for 3+ way merge, conflict resolution, empty input, or deep nesting. |
| `nodes/structure_assembler.py` | `test_structure_assembler.py` | **C+** | 2 tests covering actionable path attachment and node merging. No tests for missing checkpoint_paths, empty draft_cases, or partial canonical_outline_nodes. |
| `services/semantic_path_normalizer.py` | `test_semantic_path_normalizer.py` | **B-** | 2 tests: happy path with fake LLM + fallback when LLM returns empty. Missing: multi-case normalization, duplicate node_id handling, error propagation from LLM. |
| `services/text_normalizer.py` | `test_text_normalizer.py` | **A-** | Comprehensive: 9 test classes covering action words, identifier preservation (snake_case, camelCase, ALL_CAPS), backtick protection, URL protection, structural terms, Chinese text passthrough, and TestCase object normalization. |
| `nodes/checklist_optimizer.py` | `test_checklist_optimizer.py` | **B** | 6 tests: empty input, missing key, config disabled, normal grouping (mocked), graceful degradation, immutability. All mock SemanticPathNormalizer and ChecklistMerger -- no real integration. |
| `nodes/evaluation.py` | `test_evaluation.py` | **A-** | 8+ tests covering structured report generation, uncovered facts/checkpoints, missing evidence, duplicates, incomplete cases, retry stage suggestion, score comparison. Also tests IterationController (pass/retry/fail/no-improvement-streak). |
| `nodes/draft_writer.py` | `test_draft_writer.py` | **B-** | 1 test verifying prompt injection of fixed hierarchy path context. Uses spy LLM to validate prompt content. No tests for multi-checkpoint batching or error handling. |
| `clients/llm.py` | `test_llm_client.py` | **B+** | Tests URL construction, timeout configuration, fenced JSON parsing, wrapper object unwrapping, top-level list coercion, string evidence_ref coercion. Good protocol coverage. |
| `clients/llm.py` (retry) | `test_llm_retry.py` | **A-** | 19.5 KB -- extensive retry logic coverage including backoff, max retries, specific error types. |
| `services/precondition_grouper.py` | `test_precondition_grouper.py` | **A-** | 20 KB -- thorough test of grouping logic. |
| `nodes/context_research.py` | `test_nodes.py` (partial) | **B-** | Tests prompt structure requirements and scenario planner. No dedicated test file. |
| `nodes/reflection.py` | `test_nodes.py` (partial) | **B** | Tests deduplication logic and checkpoint_id preservation. |
| `parsers/xmind_parser.py` | `test_xmind_parser.py` | **B+** | 6.5 KB of tests for XMind file parsing. |
| `services/xmind_delivery_agent.py` | `test_xmind_delivery.py` | **A-** | 23.4 KB -- most comprehensive single test file. |
| `services/xmind_reference_analyzer.py` | `test_xmind_reference_analyzer.py` | **B+** | 7.7 KB. |
| `services/xmind_reference_tree_converter.py` | `test_xmind_reference_tree_converter.py` | **B** | 5.1 KB. |
| `services/markdown_renderer.py` | `test_markdown_renderer.py` | **B+** | 6.4 KB. |
| `services/coverage_detector.py` | `test_coverage_detector.py` | **B** | 4.0 KB. |
| `domain/run_state.py` | `test_run_state.py` | **B+** | 6.9 KB. |
| `graphs/state_bridge.py` | `test_state_bridge.py` | **B+** | 8.2 KB. |
| `services/checkpoint_outline_planner.py` | `test_checkpoint_outline_planner.py` + `_compile.py` + `_import.py` + `test_checkpoint_batch_planning.py` | **B+** | 22.5 KB combined across 4 files. |
| `nodes/checkpoint_generator.py` | `test_checkpoint.py` | **B** | 4.8 KB. |
| `services/project_context_service.py` | `test_project_context_service.py` | **B-** | 1.4 KB -- light coverage. |
| `repositories/project_repository.py` | `test_project_repository.py` | **B-** | 1.8 KB. |
| `api/project_routes.py` | `test_project_routes.py` | **B-** | 2.7 KB. |
| `services/workflow_service.py` | (no dedicated test) | **D** | Only tested indirectly via integration tests. |
| `nodes/mr_analyzer.py` | (no test) | **F** | 26.7 KB source with zero test coverage. |
| `nodes/mr_checkpoint_injector.py` | (no test) | **F** | 9.9 KB source with zero test coverage. |
| `nodes/coco_consistency_validator.py` | (no test) | **F** | 13.4 KB source with zero test coverage. |
| `services/coco_client.py` | (no test) | **F** | 17.3 KB source with zero test coverage. |
| `services/coco_response_validator.py` | (no test) | **F** | 13.6 KB source with zero test coverage. |
| `services/codebase_tools.py` | (no test) | **F** | 23.1 KB source with zero test coverage. |
| `services/platform_dispatcher.py` | (no test) | **F** | 6.5 KB source with zero test coverage. |
| `services/mandatory_skeleton_builder.py` | (no test) | **F** | 4.7 KB source with zero test coverage. |
| `services/template_loader.py` | (no test) | **D** | 9.6 KB source; only indirectly exercised via node tests. |
| `services/xmind_connector.py` | (no test) | **F** | 6.7 KB source with zero test coverage. |
| `services/xmind_payload_builder.py` | (no test) | **D** | 11.2 KB source; partially tested via xmind_delivery tests. |
| `nodes/template_loader.py` | (no test) | **F** | 2.5 KB. |
| `nodes/input_parser.py` | (no test) | **D** | 1.7 KB; indirectly tested via workflow integration. |
| `nodes/knowledge_retrieval.py` | (no test) | **D** | 3.2 KB; indirectly tested via integration. |
| `nodes/evidence_mapper.py` | (no test) | **F** | 2.9 KB with zero test coverage. |

### §14.2.2 Integration Test Analysis

| Test File | Scope | Quality | Notes |
|---|---|---|---|
| `test_api.py` | API endpoint round-trip | **B+** | Tests POST create, GET retrieve, checkpoint count, artifact persistence. Uses `FakeLLMClient` + `FastAPI TestClient`. |
| `test_iteration_loop.py` | Evaluation retry loop | **A-** | Tests retry-on-low-quality, failed-state persistence, successful-run artifacts. End-to-end through `WorkflowService` with `FakeLLMClientLowQuality`. Strong persistence verification. |
| `test_workflow.py` | LangGraph workflow | **B** | 4 tests: basic invocation, checkpoint generation, coverage records, checkpoint_id on cases. All use `FakeLLMClient` -- no real LLM. |
| `test_knowledge_workflow.py` | Knowledge retrieval integration | **B-** | Tests workflow building with/without knowledge nodes. No actual retrieval execution. |
| `test_project_workflow.py` | Project context flow | **B+** | End-to-end: create project, build loader, invoke, verify summary. Tests graceful degradation and shared service instances. |
| `test_xmind_reference_e2e.py` | XMind reference pipeline | **A** | Full pipeline: .xmind file creation, parse, analyze, loader node, state update. Deterministic sampling verification. Coverage detector integration. Best integration test in the suite. |

### §14.2.3 Critical Missing Tests

**1. No end-to-end unmocked test for the Normalizer -> Merger -> Assembler chain** (CRITICAL GAP)

The three core checklist pipeline components -- `SemanticPathNormalizer`, `ChecklistMerger`, and `structure_assembler_node` -- are each tested in isolation with their own synthetic inputs, but **no test exercises the full chain** where:
- Real `TestCase` objects flow into `SemanticPathNormalizer`
- `NormalizedChecklistPath` objects flow from normalizer into `ChecklistMerger`
- `ChecklistNode` tree from merger flows into `structure_assembler_node`
- Final `optimized_tree` is validated end-to-end

The `test_checklist_optimizer.py` tests this chain but with **all three components mocked** (`@patch` on both `SemanticPathNormalizer` and `ChecklistMerger`), making it a wiring test, not a functional one.

**2. `ChecklistMerger` lacks edge-case tests** (HIGH)

Only 2 test cases exist:
- No test for merging 3+ paths with divergent branches
- No test for empty input list
- No test for single-path input (degenerate case)
- No test for conflicting `expected_results` on same path
- No test for deeply nested trees (depth > 3)
- No test for performance with large input sets

**3. `StructureAssembler` lacks robustness tests** (HIGH)

Only 2 test cases exist:
- No test for missing/empty `checkpoint_paths`
- No test for `canonical_outline_nodes` that don't match `checkpoint_paths` node IDs
- No test for empty `draft_cases`
- No test for cases where precondition text doesn't semantically match any path node
- No test for tree flattening when all steps collapse to a single chain

**4. MR (Merge Request) pipeline is entirely untested** (CRITICAL)

- `mr_analyzer.py` (26.7 KB) -- zero tests
- `mr_checkpoint_injector.py` (9.9 KB) -- zero tests
- These represent a substantial feature area with no coverage

**5. CoCo (Consistency Validation) pipeline is entirely untested** (HIGH)

- `coco_consistency_validator.py` (13.4 KB) -- zero tests
- `coco_client.py` (17.3 KB) -- zero tests
- `coco_response_validator.py` (13.6 KB) -- zero tests

**6. Template loading service has no dedicated test** (MEDIUM)

- `services/template_loader.py` (9.6 KB) -- no test
- `nodes/template_loader.py` (2.5 KB) -- no test
- The YAML template format used by `templates/brand_spp_consideration.yaml` is not validated by any test

---

## §14.3 File Analysis

### §14.3.1 `tests/conftest.py` (21 KB)

**Purpose**: Shared pytest fixtures providing deterministic fake LLM clients.

**Key Fixtures**:
- `FakeLLMClient` -- Routes `generate_structured()` calls by `response_model.__name__`, returning well-formed responses for 7 different model types: `ResearchOutput`, `CheckpointDraftCollection`, `DraftCaseCollection`, `CanonicalOutlineNodeCollection`, `CheckpointPathCollection`, `SemanticNodeCollection`, `SemanticPathCollection`.
- `FakeLLMClientLowQuality` -- Returns intentionally deficient responses: empty `expected_results`, missing `checkpoint_id`, no `evidence_refs`, incomplete checkpoint coverage. Used to test evaluation retry loops.

**Pattern**: Both clients use a dispatch-on-class-name pattern (`if response_model.__name__ == "..."`) which is fragile to class renames but effective for deterministic testing without real LLM calls.

**Quality Assessment**: **B+** -- Well-structured and provides realistic fake data, but the dispatch pattern creates a maintenance burden when new response models are added.

### §14.3.2 `tests/unit/test_checklist_merger.py` (3.5 KB)

**Purpose**: Unit tests for `ChecklistMerger.merge()`.

**Tests** (2 total):
1. `test_merges_shared_visible_prefix_and_deduplicates_expected_results` -- Verifies two paths sharing a visible prefix are merged into a single tree with deduplicated expected results and correct `source_test_case_refs`.
2. `test_hidden_anchor_is_not_rendered_but_still_merges_paths` -- Verifies hidden nodes (precondition anchors) are excluded from rendered output while still enabling path merging.

**Mock Usage**: None -- tests use real `ChecklistMerger` with synthetic `NormalizedChecklistPath` inputs built via helpers.

**Quality Assessment**: **C** -- Correctly tests the core happy paths but critically lacks edge-case and error-condition coverage. The helper functions `_segment()` and `_path()` are well-designed for readability.

### §14.3.3 `tests/unit/test_structure_assembler.py` (5.9 KB)

**Purpose**: Unit tests for `structure_assembler_node`.

**Tests** (2 total):
1. `test_structure_assembler_attaches_actionable_path_to_outline_tree` -- Verifies that draft case preconditions, steps, and expected results are correctly woven into the `optimized_tree` at the right nesting depth based on `checkpoint_paths` and `canonical_outline_nodes`.
2. `test_structure_assembler_merges_equivalent_page_and_operation_nodes` -- Verifies semantic deduplication of similar preconditions/steps from two draft cases.

**Mock Usage**: None -- tests use real `structure_assembler_node` with synthetic state dicts.

**Quality Assessment**: **C+** -- Both tests validate important behavior but only cover the happy path. The test for node merging is especially valuable since semantic deduplication is subtle. Missing: error handling, empty inputs, mismatched IDs.

### §14.3.4 `tests/unit/test_text_normalizer.py` (9.9 KB)

**Purpose**: Unit tests for `normalize_text()` and `normalize_test_case()`.

**Tests** (9 test classes, ~40+ individual tests):
- `TestNormalizeCommonEnglishActions` (23 action words)
- `TestPreserveSnakeCase`, `TestPreserveCamelCase`, `TestPreserveAllCaps`
- `TestPreserveBacktickContent`, `TestPreserveURL`, `TestPreserveJSONFieldNames`
- `TestMixedChineseEnglish` (including empty/whitespace edge cases)
- `TestNormalizeStructuralTerms`, `TestNormalizeTestCase`

**Quality Assessment**: **A-** -- Best-structured unit test file in the suite. Comprehensive coverage of the text normalization rules with clear organization. Each test class maps to a specific feature.

### §14.3.5 `tests/unit/test_evaluation.py` (10.8 KB)

**Purpose**: Tests for `evaluate()` function and `IterationController`.

**Tests** (~12+ tests):
- Evaluation: structured report, uncovered facts, uncovered checkpoints, missing evidence, duplicates, incomplete cases, retry stage suggestion, score comparison
- IterationController: pass on high score, retry on low score, fail on max iterations, fail on no-improvement streak

**Quality Assessment**: **A-** -- Thorough coverage of evaluation dimensions and controller state machine. Tests are clear and well-isolated.

### §14.3.6 `tests/unit/test_checklist_optimizer.py` (5.7 KB)

**Purpose**: Tests for the LangGraph optimizer node wrapper.

**Tests** (6 total): Empty input, missing key, config disabled, normal grouping, graceful degradation, immutability.

**Mock Usage**: Heavy -- `@patch` on `get_settings`, `ChecklistMerger`, and `SemanticPathNormalizer`. This means the test verifies wiring, not actual merge/normalize behavior.

**Quality Assessment**: **B** -- Good node-level contract testing but the heavy mocking means the actual Normalizer -> Merger pipeline is never exercised.

### §14.3.7 `tests/integration/test_iteration_loop.py` (6.4 KB)

**Purpose**: Integration tests for the evaluation retry loop.

**Tests** (3 total):
1. `test_evaluation_triggers_retry_on_low_quality` -- Uses `FakeLLMClientLowQuality` to trigger multi-iteration runs
2. `test_failed_run_state_persists_after_max_iterations` -- Verifies run_state.json, evaluation_report.json, iteration_log.json all persist after failure
3. `test_successful_run_persists_all_iteration_artifacts` -- Verifies artifacts for successful runs

**Quality Assessment**: **A-** -- Exercises the full workflow through `WorkflowService` and verifies persistence. Uses `FastAPI TestClient` for realistic API interaction.

### §14.3.8 `tests/integration/test_xmind_reference_e2e.py` (9.6 KB)

**Purpose**: End-to-end test for the XMind reference pipeline.

**Tests** (7 total): Full pipeline, deterministic sampling, routing hints, graceful degradation (missing file, no reference), reference tree conversion, coverage detector integration.

**Quality Assessment**: **A** -- The best integration test in the suite. Creates realistic .xmind files, exercises the full pipeline without mocks, and verifies deterministic behavior. Includes proper error handling tests.

---

## §14.4 Key Findings

1. **The checklist assembly pipeline has the weakest test-to-complexity ratio.** `ChecklistMerger` (6.6 KB source, 3.5 KB test) and `structure_assembler.py` (11.4 KB source, 5.9 KB test) perform complex tree operations but have only 2 tests each. By contrast, `text_normalizer.py` (7.6 KB source, 9.9 KB test) has a test-to-source ratio > 1.3x.

2. **Mocking strategy creates a coverage blind spot.** The `test_checklist_optimizer.py` mocks both `SemanticPathNormalizer` and `ChecklistMerger`, meaning the node-level test for the full optimizer pipeline never exercises actual normalization or merging. No other test fills this gap.

3. **MR and CoCo features are entirely untested.** Approximately 80+ KB of source code across `mr_analyzer.py`, `mr_checkpoint_injector.py`, `coco_consistency_validator.py`, `coco_client.py`, and `coco_response_validator.py` has zero test coverage. These may be newer features not yet stabilized, but they represent significant risk.

4. **The `conftest.py` fake LLM pattern is well-designed but creates coupling.** Any change to response model field names or structures requires updating the fake client, and there is no mechanism to verify that the fake responses remain schema-compatible with real LLM outputs.

5. **Integration tests use `tmp_path` and `TestClient` consistently** -- good for isolation and reproducibility.

6. **No tests use real LLM calls.** All tests use fake/spy/mock LLM clients. This is appropriate for CI but means there are no smoke tests for actual LLM integration. The `test_timing.py` root-level test may relate to performance benchmarks but was not analyzed in detail.

---

## §14.5 Testing Improvement Recommendations

### Priority 1: Add End-to-End Checklist Pipeline Test (CRITICAL)

Create a new integration test `tests/integration/test_checklist_pipeline_e2e.py` that:
- Starts with realistic `TestCase` objects (using data from `conftest.py` fixtures)
- Runs `SemanticPathNormalizer` with `FakeLLMClient` (not mocked -- actual normalizer code with fake LLM)
- Feeds `NormalizedChecklistPath` results into `ChecklistMerger`
- Feeds merged tree into `structure_assembler_node`
- Validates the final `optimized_tree` structure end-to-end

This single test would close the most critical coverage gap in the project.

### Priority 2: Expand `ChecklistMerger` Edge Cases (HIGH)

Add tests for:
- Empty input list
- Single path (no merging needed)
- 3+ paths with divergent branches at different depths
- Paths with conflicting expected results for the same terminal node
- Deep nesting (depth 5+)
- Large input sets (performance regression guard)

### Priority 3: Expand `StructureAssembler` Robustness (HIGH)

Add tests for:
- Empty `draft_cases`
- Missing `checkpoint_paths` or `canonical_outline_nodes`
- Mismatched node IDs between paths and outline nodes
- Cases where precondition text does not match any existing tree node

### Priority 4: Add MR Pipeline Tests (HIGH)

Create `tests/unit/test_mr_analyzer.py` and `tests/unit/test_mr_checkpoint_injector.py` covering:
- MR diff parsing
- Checkpoint injection logic
- Error handling for malformed MR data

### Priority 5: Add CoCo Validation Tests (MEDIUM)

Create `tests/unit/test_coco_*.py` files covering:
- Client request construction
- Response validation logic
- Consistency check pass/fail scenarios

### Priority 6: Add Template Loading Tests (MEDIUM)

Create `tests/unit/test_template_loader.py` covering:
- YAML template parsing (validate `templates/brand_spp_consideration.yaml` format)
- Mandatory skeleton building from template
- Missing/malformed template handling

---

## §14.6 Cross-References

- **`conftest.py` fixtures** are consumed by: `tests/integration/test_api.py`, `tests/integration/test_iteration_loop.py`, `tests/integration/test_workflow.py`, `tests/integration/test_knowledge_workflow.py`
- **`ChecklistMerger` tests** relate to: `app/services/checklist_merger.py` (source) -> see also `app/nodes/checklist_optimizer.py` (consumer)
- **`StructureAssembler` tests** relate to: `app/nodes/structure_assembler.py` (source) -> see also `app/domain/checklist_models.py` (data models)
- **`SemanticPathNormalizer` tests** relate to: `app/services/semantic_path_normalizer.py` (source) -> feeds into `ChecklistMerger`
- **`TextNormalizer` tests** relate to: `app/services/text_normalizer.py` (source) -> called by multiple nodes
- **`Evaluation` tests** relate to: `app/nodes/evaluation.py` (source), `app/services/iteration_controller.py` (source) -> drives the retry loop in `app/services/workflow_service.py`
- **Template directory** (`templates/brand_spp_consideration.yaml`) is consumed by `app/services/template_loader.py` and `app/nodes/template_loader.py` but has **no test coverage** -> see `analysis_output/app/templates/_ANALYSIS.md` (§11)
- **XMind reference E2E test** is the closest model for what a checklist pipeline E2E test should look like
