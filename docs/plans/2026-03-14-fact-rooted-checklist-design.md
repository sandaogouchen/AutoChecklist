# Fact-Rooted Checklist Design

**Date:** 2026-03-14

## Goal

Replace the current scenario-only case generation flow with a fact-rooted checklist graph so the system first extracts verifiable PRD change facts, then expands each fact into structured checklist nodes with branch and linkage metadata.

## Problem

The current pipeline only extracts broad `user_scenarios` and converts each scenario into one test case. That loses coverage when a single PRD section contains multiple independent validation points. The result is under-generated output like one case for an entire ad-group creation change.

## Approved Direction

### Option A: Strengthen Prompt Only

Keep the existing flat `TestCase[]` contract and ask the LLM to generate more cases from the same scenario list.

Trade-off:
- Smallest code change
- Unstable coverage because the missing fact layer still does not exist
- No place to model checklist hierarchy or branch metadata

### Option B: Fact-Rooted Checklist Graph

Extend research output with explicit `facts`, plan one checklist root per fact, and serialize linked checklist nodes with `branch`, `parent`, `root`, `prev`, and `next`.

Trade-off:
- Slightly larger schema change
- Matches the required mental model directly
- Gives stable intermediate structure for coverage checks and markdown rendering

### Option C: Hybrid Flat Cases Plus Sidecar Graph

Keep flat cases as the main output and add a separate checklist graph artifact.

Trade-off:
- Avoids breaking current `test_cases.json`
- Duplicates the source of truth and complicates downstream consumers

**Recommendation:** Option B. It creates the missing fact layer explicitly and keeps one authoritative output shape.

## Design

### Architecture

`context_research` will extract `facts` in addition to existing summary fields. Each fact carries a stable id, summary, change type, source evidence, and optional branch hints. `scenario_planner` will stop planning from broad scenario titles alone and instead create one planned checklist root per fact.

`draft_writer` will no longer ask the model for one flat test case list. It will request checklist nodes for each fact, including decision branches when the fact implies alternate flows. `structure_assembler` will normalize ids and connect every node into a doubly linked list within its fact tree while also backfilling `parent` and `root`.

### Data Model

Add `ResearchFact`, `PlannedChecklist`, and `ChecklistNode` models.

`ResearchFact` fields:
- `id`
- `summary`
- `change_type`
- `requirement`
- `branch_hint`
- `evidence_refs`

`ChecklistNode` fields:
- `id`
- `fact_id`
- `title`
- `node_type`
- `branch`
- `parent`
- `root`
- `prev`
- `next`
- `preconditions`
- `steps`
- `expected_results`
- `priority`
- `category`
- `evidence_refs`

`test_cases.json` becomes an array of root nodes, each containing its linked descendants through a `children` field while every node also exposes the back-links above for traversal.

### Flow

1. Parse document as today.
2. Extract research facts from PRD text.
3. Plan one checklist root per fact.
4. Map evidence by fact instead of only by scenario title.
5. Draft checklist nodes for each fact.
6. Assemble normalized ids and graph pointers.
7. Reflect on missing fact coverage and duplicate facts.
8. Render markdown grouped by fact root.

### Error Handling

If the LLM returns no facts, derive one fallback fact from the first feature topic so the workflow still produces output. If a checklist node arrives without a valid parent/root relationship, `structure_assembler` repairs it deterministically and records the repair in `quality_report`.

### Testing

Add unit tests for:
- research output accepting fact payloads
- scenario planner creating one planned checklist per fact
- structure assembler wiring `parent/root/prev/next`
- markdown rendering grouped by fact root

Add integration coverage for:
- workflow returning multiple checklist roots when research output includes multiple facts
- persisted `test_cases.json` containing the new graph shape while `run_result.json` remains lightweight
