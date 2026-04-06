# AutoChecklist — Global Analysis Index

> **Repository**: [sandaogouchen/AutoChecklist](https://github.com/sandaogouchen/AutoChecklist)
> **Branch Analyzed**: `main`
> **Analysis Date**: 2026-04-06
> **Analysis Branch**: `analysis`
> **Total Source Files**: 68 | **Total Lines**: ~11,680 | **Total Size**: ~405 KB

---

## 1. Project Overview

**AutoChecklist** is a FastAPI-based service that automates the generation of structured test checklists from Product Requirement Documents (PRDs). It leverages a LangGraph multi-node workflow to orchestrate an LLM-powered pipeline that:

1. Parses PRD input (Markdown or XMind)
2. Retrieves contextual knowledge via GraphRAG
3. Generates checkpoints from requirements
4. Writes draft test cases
5. Assembles a hierarchical checklist structure
6. Evaluates and iterates on quality
7. Outputs structured JSON and Markdown checklists

The system also supports MR (Merge Request) code analysis for code-aware checkpoint generation, XMind reference integration for existing checklist structures, and project-level persistence for incremental workflow management.

### ⚠️ Special Focus: Checklist Integration Quality

The checklist consolidation/integration implementation is identified as underperforming. This analysis dedicates significant attention to diagnosing root causes and exploring improvement approaches. See:
- **§10.3** — Checklist Integration Deep Dive (Root Cause Analysis + Improvement Proposals)
- **§7.3.1** — `checklist_optimizer.py` is orphaned dead code
- **§7.3.2** — `structure_assembler.py` double-write issue
- **§10.2.1** — `checklist_merger.py` algorithm analysis
- **§10.2.4** — `coverage_detector.py` P0 bug

---

## 2. Technology Stack

| Category | Technology | Version | Notes |
|----------|-----------|---------|-------|
| **Runtime** | Python | 3.11+ | No upper bound specified |
| **Web Framework** | FastAPI | ≥0.115.12 | With lifespan management |
| **ASGI Server** | Uvicorn | ≥0.34.2 | |
| **Workflow Orchestration** | LangGraph | ≥0.3.34 | StateGraph with dynamic node insertion |
| **LLM Client** | OpenAI SDK | ≥1.68.2 | OpenAI-compatible API (configurable endpoint) |
| **Knowledge Graph** | LightRAG | ≥1.1.0 | GraphRAG retrieval engine |
| **Data Validation** | Pydantic | ≥2.11.1 | 42 BaseModel subclasses, 4 Enums |
| **Configuration** | pydantic-settings | ≥2.11.0 | Environment-based configuration |
| **HTTP Client** | httpx | ≥0.28.1 | Async HTTP for LightRAG |
| **YAML** | PyYAML | ≥6.0.1 | Template loading |
| **Testing** | pytest | ≥8.3.5 | With pytest-asyncio ≥0.26.0 |
| **Database** | SQLite | Built-in | Schemaless JSON-in-payload pattern |
| **File Storage** | Filesystem | N/A | Per-run artifact storage |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Layer                             │
│  routes.py  │  project_routes.py  │  knowledge_routes.py        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Workflow    │
                    │  Service     │ ← Orchestrator
                    └──────┬──────┘
                           │
          ┌────────────────▼────────────────┐
          │         LangGraph Pipeline       │
          │                                  │
          │  input_parser                    │
          │       ↓                          │
          │  [project_context_loader]        │ ← Optional
          │       ↓                          │
          │  [template_loader]               │ ← Optional
          │       ↓                          │
          │  [xmind_reference_loader]        │ ← Optional
          │       ↓                          │
          │  [mr_analyzer]                   │ ← Optional
          │       ↓                          │
          │  context_research                │
          │       ↓                          │
          │  [knowledge_retrieval]           │ ← Optional
          │       ↓                          │
          │  checkpoint_generator            │
          │       ↓                          │
          │  [mr_checkpoint_injector]        │ ← Optional
          │       ↓                          │
          │  [checkpoint_evaluator]          │ ← Optional
          │       ↓                          │
          │  checkpoint_outline_planner*     │ ← Service, not node
          │       ↓                          │
          │  [scenario_planner]              │ ← Optional
          │       ↓                          │
          │  draft_writer                    │
          │       ↓                          │
          │  structure_assembler             │ ← CRITICAL
          │       ↓                          │
          │  [coco_consistency_validator]    │ ← Optional
          │       ↓                          │
          │  [evidence_mapper]               │ ← Optional
          │       ↓                          │
          │  evaluation                      │
          │       ↓                          │
          │  [reflection → iteration loop]   │ ← Conditional
          └──────────────────────────────────┘
                           │
     ┌─────────────────────┼─────────────────────┐
     ▼                     ▼                     ▼
┌─────────┐        ┌──────────┐          ┌───────────┐
│ Services │        │  Domain  │          │  Clients  │
│          │        │  Models  │          │  (LLM)    │
└─────────┘        └──────────┘          └───────────┘
     │
     ├── checklist_merger.py       ← Core merge algorithm
     ├── semantic_path_normalizer  ← Path normalization
     ├── text_normalizer           ← Text normalization
     ├── coverage_detector         ← Coverage analysis
     ├── checkpoint_outline_planner ← Outline planning
     ├── precondition_grouper      ← Checkpoint grouping
     ├── mandatory_skeleton_builder ← Template skeletons
     └── iteration_controller      ← Eval/iteration loop
```

**Note**: `checklist_optimizer.py` (in nodes/) is **orphaned dead code** — not registered in any graph. See §7.3.1.

---

## 4. Analysis File Index

| § | Directory | Analysis File | Lines | Key Topics |
|---|-----------|--------------|-------|------------|
| §1 | `/` (root) | [`_ANALYSIS.md`](./_ANALYSIS.md) | 188 | README, pyproject.toml, .env.example, prd.md |
| §2 | `app/` | [`app/_ANALYSIS.md`](./app/_ANALYSIS.md) | 304 | main.py, logging.py, config/settings.py, architecture overview |
| §3 | `app/api/` | [`app/api/_ANALYSIS.md`](./app/api/_ANALYSIS.md) | 226 | FastAPI routes, API design, endpoint inventory |
| §4 | `app/clients/` | [`app/clients/_ANALYSIS.md`](./app/clients/_ANALYSIS.md) | 168 | LLM client, retry/fallback, exponential backoff |
| §5 | `app/domain/` | [`app/domain/_ANALYSIS.md`](./app/domain/_ANALYSIS.md) | 832 | 14 model files, 57 classes, field analysis, dependency graph |
| §6 | `app/graphs/` | [`app/graphs/_ANALYSIS.md`](./app/graphs/_ANALYSIS.md) | 327 | LangGraph workflow, pipeline definition, state bridge |
| §7 | `app/nodes/` | [`app/nodes/_ANALYSIS.md`](./app/nodes/_ANALYSIS.md) | 937 | 18 pipeline nodes, ⚠️ checklist optimizer orphaned, double-write issue |
| §8 | `app/parsers/` | [`app/parsers/_ANALYSIS.md`](./app/parsers/_ANALYSIS.md) | 294 | PRD parsing, XMind parsing, factory pattern |
| §9 | `app/repositories/` | [`app/repositories/_ANALYSIS.md`](./app/repositories/_ANALYSIS.md) | 274 | SQLite persistence, filesystem artifacts, run state |
| §10 | `app/services/` | [`app/services/_ANALYSIS.md`](./app/services/_ANALYSIS.md) | 834 | ⚠️ Checklist integration deep dive, P0 bug, merger algorithm |
| §11 | `app/templates/` | [`app/templates/_ANALYSIS.md`](./app/templates/_ANALYSIS.md) | 112 | YAML checklist templates, mandatory skeleton |
| §12 | `app/utils/` | [`app/utils/_ANALYSIS.md`](./app/utils/_ANALYSIS.md) | 281 | Filesystem, run ID, timing utilities |
| §13 | `app/knowledge/` | [`app/knowledge/_ANALYSIS.md`](./app/knowledge/_ANALYSIS.md) | 314 | GraphRAG engine, LightRAG, ingestion, retrieval |
| §14 | `tests/` | [`tests/_ANALYSIS.md`](./tests/_ANALYSIS.md) | 357 | 45 test files, coverage matrix, critical testing gaps |

**Total**: 14 analysis files, 5,448 lines

---

## 5. Module Dependency Panorama

### 5.1 Core Data Flow

```
PRD Input → input_parser → DocumentChunks
     ↓
context_research → ContextualFacts
     ↓
checkpoint_generator → List[Checkpoint]
     ↓
checkpoint_outline_planner → ChecklistNode (optimized_tree)
     ↓
draft_writer → List[TestCase] (draft_cases)
     ↓
structure_assembler → ChecklistNode (final tree)
     ↓
evaluation → EvaluationResult → [reflection → iteration]
```

### 5.2 Service Dependencies

| Service | Depends On | Depended By |
|---------|-----------|-------------|
| `workflow_service` | All nodes, all services | `routes.py` |
| `checklist_merger` | `checklist_models` | `checkpoint_outline_planner` |
| `semantic_path_normalizer` | `checklist_models`, LLM client | `checkpoint_outline_planner` |
| `coverage_detector` | `checkpoint_models`, `checklist_models` | `checkpoint_outline_planner` |
| `text_normalizer` | (standalone) | `checklist_merger`, `precondition_grouper` |
| `checkpoint_outline_planner` | merger, normalizer, detector, grouper, skeleton builder | `main_workflow` (inline call) |
| `precondition_grouper` | `precondition_models`, LLM client | `checkpoint_outline_planner` |
| `mandatory_skeleton_builder` | `checklist_models`, `template_models` | `checkpoint_outline_planner` |
| `iteration_controller` | `state`, evaluation results | `main_workflow` |

### 5.3 Architecture Violation

**Domain → Service reverse dependency** (§5.4): `app/domain/state.py` imports `CoverageResult` from `app.services.coverage_detector`, violating the layered architecture principle that domain should not depend on services.

---

## 6. External Dependencies

| Package | Purpose | Risk Notes |
|---------|---------|------------|
| `fastapi` | Web framework | Stable, well-maintained |
| `langgraph` | Workflow orchestration | Core dependency, API may evolve |
| `lightrag-hku` | GraphRAG knowledge retrieval | Academic project, bypasses LLM retry (§13) |
| `openai` | LLM API client | Used in OpenAI-compatible mode |
| `pydantic` | Data validation | v2 migration complete |
| `httpx` | Async HTTP | Used by LightRAG directly |
| `pyyaml` | YAML template loading | |
| `uvicorn` | ASGI server | |

**All dependency versions are unbounded** (only lower bounds specified) — risk of breaking changes from major version bumps. See §1.2.2.

---

## 7. Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|----------|
| `LLM_API_BASE` | Yes | — | OpenAI-compatible API base URL |
| `LLM_API_KEY` | Yes | — | API authentication key |
| `LLM_MODEL` | No | (settings default) | Primary LLM model name |
| `LLM_FALLBACK_MODEL` | No | — | Fallback model on primary failure |
| `LLM_MAX_TOKENS` | No | 1600 (.env) / 50000 (settings) | ⚠️ Mismatch between .env.example and settings.py |
| `LLM_TEMPERATURE` | No | (settings default) | LLM temperature |
| `LIGHTRAG_*` | No | — | GraphRAG configuration variables |
| `DATA_DIR` | No | `./data` | Data storage directory |
| `LOG_LEVEL` | No | `INFO` | Logging level (note: hard-coded in logging.py) |

---

## 8. Critical Issues Summary

### P0 — Must Fix

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| P0-1 | **CoverageDetector field name mismatch** — `_get_id()` reads `id` attribute but `Checkpoint` uses `checkpoint_id` | §10.2.4 | All checkpoints falsely classified as covered; outline planner skips needed checkpoints or regenerates covered ones |
| P0-2 | **`checklist_optimizer.py` is orphaned dead code** — not registered in any graph definition | §7.3.1 | Dead code confusion; developers may modify it thinking it affects output |

### P1 — High Priority

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| P1-1 | **Exact-match merge strategy** cannot handle semantic variation from LLM non-determinism | §10.2.1, §10.3.2 | Fragmented, duplicate-laden output trees |
| P1-2 | **`optimized_tree` double-write** in `structure_assembler` — enrichment then constraint rewrite | §7.3.2 | Enrichment data potentially discarded |
| P1-3 | **4 inconsistent dedup mechanisms** with different thresholds (0.4, 0.75, exact casefold, exact whitespace-stripped) | §10.3.3 | Same text treated differently depending on code path |
| P1-4 | **4 independent text normalization implementations** producing different results | §10.2.3, §10.3.3 | Merge/dedup inconsistency |
| P1-5 | **Chinese text handling is character-level only** — no word segmentation, no synonym awareness | §10.3.2 | False positives and false negatives in Chinese text matching |
| P1-6 | **Domain → Service architecture violation** — `state.py` imports from `coverage_detector` | §5.4 | Circular dependency risk, testability degradation |

### P2 — Medium Priority

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| P2-1 | 12 MR fields in `GlobalState` typed as `Any`/bare `list` despite proper models existing | §5.4 | Type safety gaps, runtime errors |
| P2-2 | Async/sync mismatch in `knowledge_retrieval.py` using `asyncio.new_event_loop()` | §7.3 | Event loop conflicts |
| P2-3 | `mr_checkpoint_injector` outputs dicts while all other nodes produce Pydantic models | §7.5 | Dual-mode access patterns downstream |
| P2-4 | GraphRAG engine bypasses `LLMClient` retry/fallback | §13 | No resilience for knowledge retrieval |
| P2-5 | Duplicate Trie implementation in `checklist_merger` and `checkpoint_outline_planner` | §10.2.1, §10.2.5 | Maintenance burden, divergence risk |
| P2-6 | `LLM_MAX_TOKENS` default mismatch: 1600 in .env.example vs 50000 in settings.py | §1.2 | Confusion, unexpected behavior |

---

## 9. Checklist Integration Improvement Roadmap

> Based on the deep dive analysis in §10.3 and cross-referenced findings from §7, §5, and §14.

### Phase 1: Foundation Fixes (Immediate)

1. **Fix P0-1**: Change `_get_id()` in `coverage_detector.py` to use `checkpoint_id`
2. **Remove P0-2**: Delete or archive `checklist_optimizer.py`
3. **Unify text normalization**: Consolidate 4 implementations into a single `TextNormalizer` service
4. **Unify deduplication**: Create a single `DeduplicationService` with configurable thresholds

### Phase 2: Algorithm Upgrade (Short-term)

5. **Replace character-level Jaccard with embedding-based similarity** for Chinese text
   - Use sentence embeddings (e.g., `text2vec-chinese` or OpenAI embeddings)
   - Set cosine similarity threshold empirically (start ~0.85)
6. **Add priority-aware merge strategy** to `ChecklistMerger`
   - Higher-priority nodes take precedence in conflicts
   - Preserve source tracking through merge operations
7. **Add validation gates** between pipeline steps
   - Post-normalization validation
   - Post-merge structural integrity check
   - Pre-assembly completeness check

### Phase 3: Architecture Enhancement (Medium-term)

8. **Resolve `optimized_tree` double-write** in `structure_assembler`
   - Option A: Single-pass assembly with combined enrichment + constraint
   - Option B: Immutable tree with copy-on-write semantics
9. **Implement LLM-guided merge arbitration** for ambiguous merge cases
   - When similarity is in the uncertain zone (0.6–0.85), use LLM to decide
   - Cache decisions for consistent behavior
10. **Add Chinese word segmentation** (jieba or similar) to normalization pipeline
11. **Build end-to-end integration test** for Normalizer → Merger → Assembler chain

### Phase 4: Quality Assurance (Ongoing)

12. **Expand test coverage** for `ChecklistMerger` (currently grade C) and `StructureAssembler` (grade C+)
13. **Add regression test suite** with known-good checklist outputs
14. **Implement merge quality metrics** tracked per run

---

## 10. Analysis Methodology

- **Scan**: Recursive directory traversal of `main` branch via GitHub API
- **Read**: All 68 source files downloaded and cached locally (405 KB)
- **Analyze**: 6 parallel analysis agents covering root/config, domain, nodes, services, graphs/misc, and tests
- **Format**: `§N.M.K` cross-reference numbering system
- **Focus**: Special emphasis on checklist integration pipeline per user request
- **File Types**: 11 categories (A–K) with type-specific analysis strategies applied

---

*Generated by analysis-branch-builder on 2026-04-06*