# app/services/ Directory Analysis

> Auto-generated analysis for the service layer of AutoChecklist
> **Special Focus**: Checklist integration/consolidation implementation analysis and improvement exploration

---

## §10.1 Directory Overview

| Property | Value |
|----------|-------|
| Path | `app/services/` |
| Total Files | 9 |
| Total Lines | 2,968 |
| Main Purpose | Core business logic: checklist merge algorithms, semantic normalization, coverage detection, outline planning, workflow orchestration, and iteration control |

**Architectural Role**: This directory contains the algorithmic heart of AutoChecklist. Every service here participates in one or more stages of the pipeline that transforms raw test cases and PRD checkpoints into a consolidated, deduplicated checklist tree. The three most critical files for checklist integration quality — `checklist_merger.py`, `semantic_path_normalizer.py`, and `coverage_detector.py` — are all located here.

---

## §10.2 File Analysis

---

### §10.2.1 `checklist_merger.py` — CRITICAL — CHECKLIST INTEGRATION CORE

| Property | Value |
|----------|-------|
| Lines | 191 |
| Type | Core algorithm (Type A) |
| Role | Merges normalized semantic paths into a shared prefix tree (Trie) |
| Key Classes | `ChecklistMerger`, `_TrieNode`, `_ExpectedResultBucket` |
| Inputs | `list[NormalizedChecklistPath]` from `SemanticPathNormalizer` |
| Outputs | `list[ChecklistNode]` — the merged checklist tree |

#### Algorithm: Trie-Based Merge — Step by Step

The `ChecklistMerger` implements a classic prefix-tree (Trie) merge strategy:

**Step 1 — Insertion (`_insert`)**:
For each `NormalizedChecklistPath`, iterate over its `path_segments`. Each segment is inserted into the Trie using a key derived from either `segment.node_id` or the normalized `display_text`:

```python
segment_key = segment.node_id or _normalize_text(segment.display_text)
```

If a child node with that key already exists, the traversal continues down that branch (sharing the prefix). Otherwise, a new `_TrieNode` is created. Expected results are attached as leaves at the terminal node.

**Step 2 — Tree Construction (`_build_children`)**:
Recursively converts `_TrieNode` children into `ChecklistNode` objects. For each child:
- If the segment is `hidden`, its children are "flattened" (promoted to the parent level) via `_build_node_or_flatten`.
- If visible, a `group` node is created with its children recursively built.
- Expected results become `expected_result` leaf nodes.

**Step 3 — Sibling Merge (`_merge_siblings`)**:
After flattening hidden anchors, siblings may become duplicated. `_merge_siblings` deduplicates using a merge key:

```python
def _node_merge_key(self, node: ChecklistNode) -> tuple[str, str]:
    if node.node_type == "group":
        return ("group", node.node_id or _normalize_text(node.title))
    if node.node_type == "expected_result":
        return ("expected_result", _normalize_text(node.title))
    return (node.node_type, node.node_id or _normalize_text(node.title))
```

When two nodes share the same merge key, `_merge_node_pair` combines their `source_test_case_refs` and recursively merges their children.

#### Critical Weakness Analysis

**1. Merge Key Relies on Exact Normalized Text Match**

The merge key for sibling deduplication is based on `_normalize_text()` which only performs whitespace compression and `casefold()`:

```python
def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()
```

This means two semantically identical nodes with even slightly different wording (e.g., "进入广告组页面" vs "导航到广告组创建页面") will **never** be merged. For Chinese text, `casefold()` is a no-op, so the normalization is effectively just whitespace collapsing.

**2. No Similarity-Based Deduplication**

Unlike `mr_checkpoint_injector.py` (which uses bigram Jaccard at threshold 0.75) or `coverage_detector.py` (which uses character-level Jaccard at threshold 0.4), the merger uses **exact match only**. This is the strictest dedup strategy in the entire codebase and the primary reason near-duplicate subtrees survive merging.

**3. No Priority Awareness**

The merger treats all paths equally. When merging two `group` nodes, it simply unions the `source_test_case_refs`. There is no mechanism to:
- Prefer a higher-priority test case's path structure
- Weight merge decisions by checkpoint risk level
- Preserve ordering based on priority

**4. Chinese Text Handling Weakness**

The `_normalize_text` function's `casefold()` is meaningless for Chinese characters. More critically, Chinese text variations that are semantically equivalent but lexically different (synonyms, different verb forms, abbreviated vs full names) are treated as completely distinct.

**5. Metadata Loss During Merge**

When two nodes merge via `_merge_node_pair`, only `children` and `source_test_case_refs` are combined. The following information is silently lost:
- Which source originally contributed the node's `title` (first-wins)
- Priority and category information from the original test cases
- Any ordering preference from the original paths
- The `checkpoint_id` from the contributing paths

**6. Field Name Assumptions**

The merger constructs `ChecklistNode` objects using `node_id` and `title`, which aligns with the domain model. However, the upstream `NormalizedChecklistPath` carries `priority`, `category`, and `checkpoint_id` fields that are **completely ignored** by the merger — these fields are never propagated into the output tree.

**7. Duplicate Trie Implementation**

A separate `_OutlineTrieNode` Trie exists in `checkpoint_outline_planner.py` (see §10.2.5). These two Trie implementations serve similar purposes but are completely independent, with different node structures and no shared code.

#### Improvement Recommendations

1. **Replace exact-match merge keys with embedding-based or Jaccard similarity** — even a bigram Jaccard at 0.6 would catch many near-duplicates that currently escape.
2. **Propagate priority and category through the merge** — the `NormalizedChecklistPath` already carries this data; use it to break ties and influence merge decisions.
3. **Add a post-merge validation step** — verify that the output tree has reasonable fan-out and depth, flagging subtrees that look like failed merges (many siblings with similar titles).
4. **Extract a shared Trie utility** — unify with `checkpoint_outline_planner.py`'s Trie.

---

### §10.2.2 `semantic_path_normalizer.py` — CRITICAL — CHECKLIST INTEGRATION

| Property | Value |
|----------|-------|
| Lines | 262 |
| Type | Core algorithm (Type A) |
| Role | LLM-driven 2-stage normalization of test cases into shared semantic paths |
| Key Classes | `SemanticPathNormalizer`, `SemanticNode`, `NormalizedChecklistPath` |
| Dependencies | `LLMClient` (structured generation) |

#### Two-Stage Normalization Pipeline

**Stage 1 — Vocabulary Extraction**: All test cases are submitted to the LLM together with a detailed system prompt (`_VOCAB_SYSTEM_PROMPT`). The LLM identifies canonical reusable nodes — business objects, contexts, and actions — that can be shared across multiple test cases. Output: `SemanticNodeCollection`.

**Stage 2 — Path Mapping**: Each test case is mapped to an ordered sequence of canonical node IDs, plus terminal expected results. Output: `SemanticPathCollection`.

**Resolution**: The normalizer then resolves `path_node_ids` into `NormalizedPathSegment` objects using the vocabulary lookup. If the LLM fails to return valid paths for a test case, a **fallback** path is created from raw preconditions + steps.

#### Impact on Merge Quality

This is the **upstream bottleneck** for the entire checklist integration pipeline. If the LLM produces inconsistent canonical nodes (e.g., creating two nodes for the same concept), or maps similar test cases to different path prefixes, the downstream merger **cannot recover** because it relies on exact key matching.

#### Critical Issues

1. **LLM Non-Determinism**: The same set of test cases can produce different canonical vocabularies across runs, leading to non-reproducible merge results.

2. **No Validation Between Stages**: After Stage 1, there is no check that the canonical nodes are truly deduplicated or that their `node_id` values are unique. If the LLM produces duplicate nodes with different IDs, downstream paths will diverge unnecessarily.

3. **Fallback Path Quality**: The fallback (`_fallback_path_segments`) concatenates raw preconditions and steps as individual path segments. These fallback paths use `{case.id}-fallback-{index}` as node IDs, which are **guaranteed to never merge** with any other path, creating isolated subtrees.

4. **No Cross-Batch Consistency**: When used in conjunction with the batched outline planner, different batches may produce different canonical vocabularies, leading to fragmented merge results.

5. **Priority and Category Propagation**: The normalizer correctly carries `priority`, `category`, and `checkpoint_id` into `NormalizedChecklistPath`, but the downstream `ChecklistMerger` ignores all of them (see §10.2.1).

---

### §10.2.3 `text_normalizer.py` — CRITICAL — CHECKLIST INTEGRATION

| Property | Value |
|----------|-------|
| Lines | 193 |
| Type | Core algorithm (Type A) |
| Role | Rule-based English-to-Chinese text normalization for mixed-language test cases |
| Key Functions | `normalize_text()`, `normalize_test_case()` |

#### One of THREE Independent Text Normalization Implementations

The codebase contains **three separate, inconsistent** text normalization approaches:

| Location | Method | Scope |
|----------|--------|-------|
| `text_normalizer.py` | Rule-based EN→CN action word replacement with protected patterns | Test case fields |
| `checklist_merger.py::_normalize_text()` | Whitespace compression + `casefold()` | Merge keys |
| `mr_checkpoint_injector.py::_normalize_text()` | NFKC + lowercase + punctuation removal | Dedup comparison |

#### How `text_normalizer.py` Works

1. **Protection Phase**: Regex patterns identify content that should NOT be translated — backtick-wrapped code, URLs, snake_case/camelCase/PascalCase identifiers, ALL_CAPS acronyms, and dot-path references.
2. **Action Word Replacement**: A mapping table of 30 English action verbs (Click, Navigate, Select, etc.) is replaced with Chinese equivalents.
3. **Structural Term Replacement**: Terms like "Preconditions", "Steps", "Expected Results" are translated.
4. **Restoration**: Protected content is restored from placeholders.

#### Inconsistency Impact

The problem is not `text_normalizer.py` itself — its protection-and-replace logic is well-designed. The problem is that it operates **independently** from the normalization used in the merge pipeline:

- `text_normalizer.py` may convert "Click" to "点击" in a test case title
- But `checklist_merger.py`'s `_normalize_text()` only does casefold, so "Click the button" and "点击 the button" remain different merge keys
- Meanwhile, `mr_checkpoint_injector.py` strips all punctuation before comparing, producing yet another normalization variant

This fragmentation means the **same text** can have **three different normalized forms** depending on which component processes it, leading to failed deduplication.

---

### §10.2.4 `coverage_detector.py` — CRITICAL — CHECKLIST INTEGRATION

| Property | Value |
|----------|-------|
| Lines | 144 |
| Type | Core algorithm (Type A) |
| Role | Detects which PRD checkpoints are already covered by reference XMind leaf titles |
| Key Classes | `CoverageDetector`, `CoverageResult` |
| Threshold | 0.4 (character-level Jaccard) |

#### P0 BUG: Field Name Mismatch (`id` vs `checkpoint_id`)

The `CoverageDetector._get_id()` method retrieves the `id` attribute:

```python
@staticmethod
def _get_id(checkpoint) -> str:
    """兼容 dict 和 Pydantic model 获取 id。"""
    if isinstance(checkpoint, dict):
        return checkpoint.get("id", "")
    return getattr(checkpoint, "id", "")
```

However, the `Checkpoint` model (from `checkpoint_models.py`) uses `checkpoint_id` as its primary identifier field:

```python
class Checkpoint(BaseModel):
    checkpoint_id: str = ""
    title: str
    ...
```

The `ChecklistNode` model does have an `id` property that aliases `node_id`:
```python
@property
def id(self) -> str:
    return self.node_id
```

But `Checkpoint` does **NOT** have this alias. The `Checkpoint.checkpoint_id` field is a plain string field with no `id` alias or property.

**Impact**: When `CoverageDetector.detect()` is called with `Checkpoint` objects (which is the primary use case, as seen in `_coverage_detector_node` in `case_generation.py`), `_get_id()` calls `getattr(checkpoint, "id", "")` which returns `""` for every checkpoint. This means **all checkpoint IDs in the result are empty strings**, making the `covered_checkpoint_ids` and `uncovered_checkpoint_ids` lists contain only empty strings.

**Compounding Issue in `case_generation.py`**:

```python
uncovered = [
    cp for cp in checkpoints
    if getattr(cp, "id", "") not in set(result.covered_checkpoint_ids)
]
```

This comparison also uses `getattr(cp, "id", "")` which returns `""`. Since `""` IS in `result.covered_checkpoint_ids` (because all IDs are empty), **all checkpoints may be falsely classified as covered**, potentially causing the outline planner to skip generating outlines for them.

#### Character-Level Jaccard: Unsuitable for Chinese Semantic Matching

The similarity metric decomposes strings into **individual characters** and computes Jaccard:

```python
title_chars = set(title)
cand_chars = set(candidate)
score = len(title_chars & cand_chars) / len(union)
```

For Chinese text, this has severe limitations:

| Scenario | Title A | Title B | Char Jaccard | Semantic |
|----------|---------|---------|-------------|----------|
| Same meaning, different words | "验证广告组创建功能" | "测试广告组新建能力" | ~0.44 | High |
| Different meaning, shared chars | "验证广告组删除功能" | "验证广告组创建功能" | ~0.78 | Low |
| English mixed | "Check CTA button" | "验证 CTA 按钮" | ~0.18 | High |

Character-level Jaccard creates **false positives** (high score for semantically different items sharing common Chinese characters like 验证/功能/广告组) and **false negatives** (low score for semantically equivalent items using different Chinese words).

#### Improvement Recommendations

1. **Fix the P0 bug**: Change `_get_id` to use `checkpoint_id`:
   ```python
   return checkpoint.get("checkpoint_id", checkpoint.get("id", ""))
   # and
   return getattr(checkpoint, "checkpoint_id", getattr(checkpoint, "id", ""))
   ```
2. **Replace character Jaccard with bigram or embedding-based similarity** for Chinese text.
3. **Add a unit test** that validates coverage detection with real `Checkpoint` objects.

---

### §10.2.5 `checkpoint_outline_planner.py`

| Property | Value |
|----------|-------|
| Lines | 743 |
| Type | Core algorithm (Type A) |
| Role | 4-stage checkpoint planning with batch support, LLM-driven outline generation |
| Key Classes | `CheckpointOutlinePlanner`, `CheckpointOutlinePlan`, `_OutlineTrieNode`, `_BatchGroup` |

#### 4-Stage Planning Flow

| Stage | Description |
|-------|-------------|
| Stage 0 | Build reference tree from existing test cases (`_build_reference_tree`) |
| Stage 1 | Coverage filtering — identify uncovered checkpoints using `CoverageResult` |
| Stage 2 | LLM generates canonical outline nodes (Stage A) + path mappings (Stage B) |
| Stage 3 | Merge reference tree + LLM tree into `optimized_tree` |

#### Batch Mechanism (for 30+ Checkpoints)

When `active_checkpoints > batch_threshold`, the planner:
1. Groups checkpoints by PRD `source_section` (with equal-split fallback)
2. Executes Stage A + Stage B serially per batch
3. Injects prior batch node summaries into each subsequent batch's prompt for naming consistency
4. Performs cross-batch deduplication of outline nodes via `_deduplicate_outline_nodes` (based on normalized `display_text`)
5. Remaps path node IDs to canonical IDs

#### Duplicate Trie Implementation

The file contains its own `_OutlineTrieNode` class:

```python
@dataclass
class _OutlineTrieNode:
    label: str
    children: dict[str, "_OutlineTrieNode"] = field(default_factory=dict)
```

Compared with `checklist_merger.py`'s `_TrieNode`:

```python
@dataclass
class _TrieNode:
    segment: NormalizedPathSegment | None = None
    children: dict[str, _TrieNode] = field(default_factory=dict)
    expected_results: dict[str, _ExpectedResultBucket] = field(default_factory=dict)
    source_test_case_refs: set[str] = field(default_factory=set)
```

These serve overlapping purposes (building a shared prefix tree from paths) but use different node shapes and normalization strategies. The `_OutlineTrieNode` version uses `_normalize_text` (which strips ALL whitespace for Chinese, lowercases, and strips), while the merger's `_normalize_text` only compresses whitespace and casefolds. This means the **same text** normalizes to **different keys** in these two Tries.

#### Cross-Batch Deduplication Issue

The `_deduplicate_outline_nodes` method uses the planner's `_normalize_text`:

```python
def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().lower()
```

Note: this removes **all** whitespace (not just compresses it) and uses `.lower()` (not `.casefold()`). This is yet another normalization variant, incompatible with both the merger's and `text_normalizer.py`'s approaches.

#### `_merge_reference_and_llm_trees` — Label-Based Merge

The merge of reference and LLM trees uses `node.label` as the key:

```python
merged = {node.label: node for node in reference_tree}
for node in llm_tree:
    if node.label not in merged:
        merged[node.label] = node
    else:
        merged[node.label].children = self._merge_reference_and_llm_trees(...)
```

This is an **exact label match** — no fuzzy matching, no normalization applied. Two nodes with labels "广告组设置" and "广告组 设置" would not merge.

---

### §10.2.6 `workflow_service.py`

| Property | Value |
|----------|-------|
| Lines | 515 |
| Type | Orchestrator (Type A) |
| Role | Top-level workflow execution with iteration evaluation loop |
| Key Classes | `WorkflowService` |
| Dependencies | `LLMClient`, `IterationController`, `PlatformDispatcher`, `FileRunRepository`, `RunStateRepository` |

#### Responsibilities

1. **Run Lifecycle Management**: Creates run IDs, saves request/result artifacts, manages `CaseGenerationRun` objects.
2. **Iteration Loop**: Invokes `_execute_with_iteration` which:
   - Builds a timed workflow for each iteration
   - Invokes the LangGraph workflow
   - Runs evaluation (`evaluate()`)
   - Delegates decision to `IterationController`
   - On `retry`, prepares modified workflow input with previous results
   - On `pass` or `fail`, exits the loop
3. **Timing Infrastructure**: `NodeTimer` wraps every workflow node and evaluation, persists `timing_report.json`.
4. **XMind Delivery**: Factory for `XMindDeliveryAgent` to export results.
5. **Retry Input Preparation**: `_prepare_retry_input` selectively carries forward results depending on the target retry stage.

#### Notable Design Patterns

- **No caching of workflow between iterations**: Each iteration rebuilds the entire LangGraph (necessary because timer/iteration_index differ).
- **LLM client configuration**: Supports fallback model, retry with exponential backoff, configurable timeout.
- **Platform dispatch**: Abstracts artifact persistence through `PlatformDispatcher`.

---

### §10.2.7 `iteration_controller.py`

| Property | Value |
|----------|-------|
| Lines | 251 |
| Type | Controller (Type A) |
| Role | Decides whether to pass, retry, or fail after each evaluation |
| Key Classes | `IterationController`, `IterationDecision` |

#### Decision Logic

| Condition | Action | Details |
|-----------|--------|--------|
| `score >= pass_threshold` (default 0.7) | `pass` | Quality sufficient |
| `iteration_index >= max_iterations - 1` (default 3) | `fail` | Budget exhausted |
| Two consecutive rounds with improvement < `min_improvement` (default 0.03) | `fail` | No progress plateau |
| Otherwise | `retry` | Route to suggested stage |

#### Retry Stage Routing

The evaluation report's `suggested_retry_stage` determines which stage to re-enter:
- `context_research` — re-analyze the PRD
- `checkpoint_generation` — regenerate checkpoints (carries forward parsed document + research)
- `draft_generation` — regenerate test case drafts (carries forward everything up to checkpoints)

#### State Management

The controller maintains a `RunState` with:
- `iteration_history`: List of `IterationRecord` (score, summary, retry reason per round)
- `retry_decisions`: List of `RetryDecision` (target stage, trigger dimension, previous score)
- Timestamps for lifecycle events

---

### §10.2.8 `mandatory_skeleton_builder.py`

| Property | Value |
|----------|-------|
| Lines | 138 |
| Type | Builder (Type A) |
| Role | Extracts mandatory nodes from checklist templates to create a hard-constraint skeleton |
| Key Classes | `MandatorySkeletonBuilder` |

#### Mandatory Node Determination Rules

A node is included in the skeleton if **any** of:
1. Its depth is in the template's `mandatory_levels` set
2. Its `mandatory` flag is `True`
3. It has descendant nodes that are mandatory (included as a connecting path)

#### Output Structure

Returns a `MandatorySkeletonNode` tree (or `None` if no mandatory constraints exist). This skeleton is injected into:
- The outline planner's LLM prompts as hard constraints
- The post-processing enforcement step (`_enforce_mandatory_skeleton`)

The builder preserves original metadata (priority, note, status, description) from the template.

---

### §10.2.9 `precondition_grouper.py`

| Property | Value |
|----------|-------|
| Lines | 531 |
| Type | Grouper (Type A) |
| Role | Groups test cases by shared preconditions using keyword extraction + optional LLM semantic merge |
| Key Classes | `PreconditionGrouper` |

#### Algorithm

1. **Keyword Extraction**: For each test case's preconditions, extract English/code keywords from backtick-wrapped content and ASCII token patterns. Uses a blocklist of generic terms (`_GENERIC_ASCII_TERMS`).

2. **Keyword Bucketing**: Each test case is assigned to its **single best** keyword bucket (highest frequency + length score). Cases with no shared keywords go to the "其他" (Other) bucket. Buckets with fewer than `_MIN_GROUP_SIZE` (2) members are dissolved into "其他".

3. **Optional LLM Semantic Merge**: If `llm_client` is provided, all bucket keys + "其他" precondition texts are submitted to an LLM for semantic grouping. The LLM can merge keyword buckets and re-classify "其他" cases. Falls back to keyword-only on LLM failure.

4. **Tree Construction**: Each surviving bucket becomes a `precondition_group` ChecklistNode, with individual test cases as `case` children.

#### Normalization Details

Uses its **own** normalization: NFKC + Chinese punctuation-to-ASCII mapping. This is yet another normalization variant distinct from the three already identified in §10.2.3.

---

## §10.3 Checklist Integration Deep Dive — SPECIAL FOCUS

---

### §10.3.1 Current Integration Pipeline

The complete checklist integration flow proceeds as follows:

```
Raw Test Cases
     │
     ▼
[text_normalizer] ─── Rule-based EN→CN translation (optional preprocessing)
     │
     ▼
[SemanticPathNormalizer] ─── LLM Stage 1: Extract canonical vocabulary
     │                       LLM Stage 2: Map cases to canonical paths
     ▼
[ChecklistMerger] ─── Trie insertion → Tree construction → Sibling merge
     │
     ▼
Merged ChecklistNode Tree
```

In parallel, the outline planning pipeline handles checkpoints:

```
PRD Checkpoints + Reference XMind
     │
     ▼
[CoverageDetector] ─── Character Jaccard coverage check
     │
     ▼
[CheckpointOutlinePlanner] ─── LLM outline + path mapping → Trie → Tree merge
     │
     ▼
Optimized Outline Tree
```

These two trees are eventually combined (in the structure assembler or delivery stage), but the **merge quality** depends critically on:
1. The LLM's ability to produce consistent canonical nodes (SemanticPathNormalizer)
2. The Trie merger's ability to match semantically equivalent paths (ChecklistMerger)
3. The coverage detector's ability to correctly identify overlaps (CoverageDetector)

---

### §10.3.2 Root Cause Analysis of Poor Integration Quality

After thorough code analysis, the poor integration quality stems from **six interconnected root causes**:

#### Root Cause 1: Exact-Match Merge Strategy Cannot Handle Semantic Variation

The `ChecklistMerger._node_merge_key` uses exact normalized text for deduplication. In a domain where:
- LLM outputs are inherently non-deterministic
- Chinese text has rich synonymy ("创建" / "新建" / "添加" can mean the same thing)
- Mixed-language content varies in translation completeness

...exact match is fundamentally insufficient. The merger depends **entirely** on the upstream LLM normalization producing perfectly consistent `node_id` values. When the LLM assigns different IDs to semantically equivalent concepts (which is common), the merger produces fragmented subtrees instead of a coherent shared hierarchy.

#### Root Cause 2: Similarity Metrics Are Inappropriate for Chinese Text

Two components use Jaccard similarity but in ways that are poorly suited for Chinese:

- **`coverage_detector.py`**: Character-level Jaccard treats each Chinese character as an independent token. Since many Chinese test case titles share structural characters (验/证/功/能/广/告/组), semantically unrelated items score high, while semantically equivalent items using different vocabulary score low.

- **`mr_checkpoint_injector.py`**: Bigram Jaccard is better but still character-bigram-based. For Chinese text, character bigrams are less meaningful than word-level bigrams because Chinese words are typically 2-4 characters, and bigrams cut across word boundaries unpredictably.

Neither component uses word segmentation, embeddings, or any Chinese-aware NLP technique.

#### Root Cause 3: Loss of Semantic Information During Normalization

The normalization pipeline is lossy at multiple stages:

1. **`text_normalizer.py`** replaces English action words with Chinese equivalents, but the merger's `_normalize_text` doesn't account for this (it just casefolds, which is a no-op for Chinese). So pre-normalized and post-normalized text may not match.

2. **`SemanticPathNormalizer`** discards the original test case text after mapping to canonical node IDs. If the LLM mapping is incorrect, there is no fallback to surface-level text comparison.

3. **`ChecklistMerger`** discards `priority`, `category`, and `checkpoint_id` from `NormalizedChecklistPath`, losing the ability to make priority-aware merge decisions.

#### Root Cause 4: Merge Conflicts Have No Resolution Strategy

When the merger encounters two `group` nodes with different titles but overlapping semantics, it has **no conflict resolution mechanism**:
- No similarity threshold to decide "close enough to merge"
- No priority system to decide which title wins
- No ability to flag ambiguous merges for human review
- No logging of merge decisions for debugging

The result is that near-duplicate subtrees silently coexist in the output, inflating the checklist with redundant items.

#### Root Cause 5: Error Propagation Through the Pipeline

Errors compound across stages:
1. If the LLM in `SemanticPathNormalizer` produces an inconsistent vocabulary → paths diverge
2. The merger cannot fix divergent paths → fragmented tree
3. The `CoverageDetector` (with its P0 bug) may misclassify coverage → the outline planner either skips needed checkpoints or regenerates already-covered ones
4. The outline planner's own merge (`_merge_reference_and_llm_trees`) uses yet another exact-match strategy → further fragmentation
5. No stage validates the output of the previous stage

#### Root Cause 6: Lack of Validation Between Pipeline Steps

There are **zero validation gates** between the normalization, merge, coverage, and outline stages:
- No check that the canonical vocabulary is consistent (no duplicate node IDs, no overlapping display_text)
- No check that all test cases were successfully mapped to paths (fallback paths are created silently)
- No check that the merged tree has reasonable properties (depth, fan-out, leaf count)
- No check that coverage detection results use valid checkpoint IDs

---

### §10.3.3 Deduplication Strategy Fragmentation

The codebase employs **four distinct deduplication mechanisms** with inconsistent approaches:

| # | Location | Method | Threshold | Normalization | Target |
|---|----------|--------|-----------|---------------|--------|
| 1 | `checkpoint_evaluator.py` | Exact title match | N/A (exact) | `casefold()` only | Checkpoint titles |
| 2 | `mr_checkpoint_injector.py` | Bigram Jaccard | 0.75 | NFKC + lowercase + punct removal | MR checkpoint vs existing |
| 3 | `coverage_detector.py` | Character Jaccard | 0.4 | None (raw text) | Checkpoint title vs XMind leaf |
| 4 | `checklist_merger.py` | Exact match | N/A (exact) | Whitespace compress + casefold | Sibling node titles |

Additionally, `checkpoint_outline_planner.py` has its own dedup for cross-batch outline nodes:

| 5 | `checkpoint_outline_planner.py` | Exact normalized label | N/A (exact) | Strip all whitespace + lowercase | Outline node display_text |

#### Conflicts and Inconsistencies

1. **Threshold Gap**: The jump from 0.4 (coverage) to 0.75 (MR dedup) to exact match (merger) creates a zone where items are "similar enough to be considered covered" but "not similar enough to be merged" — or vice versa.

2. **Normalization Divergence**: The same string processed by different normalizers produces different results:
   - `text_normalizer.py`: "Click the `save` button" → "点击 the `save` button"
   - `checklist_merger.py`: "Click the `save` button" → "click the `save` button"
   - `mr_checkpoint_injector.py`: "Click the `save` button" → "click the save button"
   - `checkpoint_outline_planner.py`: "Click the `save` button" → "clickthe`save`button"

3. **No Unified Dedup Contract**: Each component reinvents deduplication independently. There is no shared interface, no common normalization, and no consistent threshold framework.

---

### §10.3.4 Proposed Improvement Approaches

#### Approach 1: Embedding-Based Similarity Replacing Jaccard

**Problem**: Character/bigram Jaccard is semantically blind, especially for Chinese text.

**Solution**: Use a multilingual sentence embedding model (e.g., `text-embedding-ada-002`, `bge-base-zh-v1.5`, or `m3e-base`) to compute semantic similarity.

```python
# Conceptual implementation
from numpy import dot
from numpy.linalg import norm

def semantic_similarity(embedding_a, embedding_b) -> float:
    return dot(embedding_a, embedding_b) / (norm(embedding_a) * norm(embedding_b))
```

**Where to apply**:
- Replace character Jaccard in `CoverageDetector` (threshold ~0.80 for cosine)
- Replace bigram Jaccard in `mr_checkpoint_injector` (threshold ~0.85)
- Add as a secondary check in `ChecklistMerger._merge_siblings` (threshold ~0.88)

**Trade-off**: Adds latency for embedding computation. Mitigate by:
- Batch embedding calls
- Caching embeddings per run
- Using a local model for low-latency inference

#### Approach 2: Hierarchical Merge with Priority Awareness

**Problem**: The merger treats all paths equally, ignoring priority and risk.

**Solution**: Introduce a priority-aware merge strategy:

```python
@dataclass
class _TrieNode:
    segment: NormalizedPathSegment | None = None
    children: dict[str, _TrieNode] = field(default_factory=dict)
    expected_results: dict[str, _ExpectedResultBucket] = field(default_factory=dict)
    source_test_case_refs: set[str] = field(default_factory=set)
    max_priority: str = "P3"  # NEW: track highest priority in this subtree
    checkpoint_ids: set[str] = field(default_factory=set)  # NEW: track checkpoint origin
```

During merge, prefer the structure of higher-priority paths:
- When two subtrees could be merged, but the merge is ambiguous, prefer the subtree containing P0/P1 test cases.
- When choosing which title to display for a merged node, prefer the title from the higher-priority source.

#### Approach 3: LLM-Guided Merge Arbitration

**Problem**: Exact-match merge misses semantic equivalence; statistical similarity introduces false positives.

**Solution**: After the initial Trie merge, identify candidate merge pairs (sibling nodes with similar but not identical titles) and submit them to an LLM for arbitration:

```python
# Post-merge arbitration
candidate_pairs = find_similar_siblings(merged_tree, threshold=0.5)
for pair in candidate_pairs:
    decision = llm_client.generate_structured(
        system_prompt="Should these two checklist nodes be merged?",
        user_prompt=f"Node A: {pair.a.title}\nNode B: {pair.b.title}\n"
                    f"Children A: {[c.title for c in pair.a.children]}\n"
                    f"Children B: {[c.title for c in pair.b.children]}",
        response_model=MergeDecision,  # {should_merge: bool, merged_title: str}
    )
    if decision.should_merge:
        merge_nodes(pair.a, pair.b, decision.merged_title)
```

**Trade-off**: Additional LLM calls. Mitigate by only invoking for ambiguous pairs (similarity between 0.5 and 0.9).

#### Approach 4: Unified Deduplication Strategy

**Problem**: Four independent dedup mechanisms with inconsistent behavior.

**Solution**: Create a shared `TextSimilarity` service:

```python
class TextSimilarity:
    """Unified text similarity service for all dedup operations."""

    def __init__(self, embedding_client=None):
        self._embedding_client = embedding_client
        self._cache: dict[str, list[float]] = {}

    def normalize(self, text: str) -> str:
        """Single normalization strategy for all components."""
        text = unicodedata.normalize("NFKC", text.strip())
        text = self._normalize_punctuation(text)
        text = re.sub(r"\s+", " ", text).lower()
        return text

    def similarity(self, a: str, b: str, method: str = "auto") -> float:
        """Compute similarity with consistent method selection."""
        if method == "auto":
            method = "embedding" if self._embedding_client else "bigram_jaccard"
        ...

    def is_duplicate(self, a: str, b: str, context: str = "default") -> bool:
        """Context-aware dedup thresholds."""
        thresholds = {
            "checkpoint_dedup": 0.80,
            "coverage_check": 0.70,
            "merge_sibling": 0.85,
            "mr_dedup": 0.80,
        }
        return self.similarity(a, b) >= thresholds.get(context, 0.80)
```

All four dedup sites would use this shared service, ensuring consistent normalization and thresholds.

#### Approach 5: Validation Gates Between Pipeline Steps

**Problem**: Errors propagate silently across the pipeline.

**Solution**: Add explicit validation at each stage boundary:

| Gate | Location | Validates |
|------|----------|-----------|
| V1 | After SemanticPathNormalizer | No duplicate node IDs; all test cases mapped; no empty paths |
| V2 | After ChecklistMerger | Tree depth ≤ 6; no sibling group with >20 children; no orphan leaves |
| V3 | After CoverageDetector | All checkpoint IDs are non-empty; covered + uncovered = total |
| V4 | After CheckpointOutlinePlanner | All checkpoints have paths; optimized_tree is non-empty |

Each gate logs warnings and can optionally trigger a retry via the iteration controller.

#### Approach 6: Better Chinese Text Handling

**Problem**: All normalization and comparison methods are character-level, ignoring Chinese word boundaries.

**Solution**:
1. **Integrate jieba or pkuseg** for Chinese word segmentation before comparison
2. **Use word-level bigrams** instead of character-level bigrams for Jaccard
3. **Build a domain-specific synonym dictionary** for common QA terms:
   ```python
   SYNONYMS = {
       "创建": ["新建", "添加", "建立"],
       "验证": ["检查", "确认", "检验", "校验"],
       "页面": ["界面", "视图", "窗口"],
       "点击": ["单击", "按下", "触发"],
   }
   ```
4. **Apply synonym normalization before comparison** in all dedup paths

---

## §10.4 Key Findings

1. **P0 Bug — CoverageDetector Field Mismatch**: `_get_id()` uses `"id"` but `Checkpoint` uses `checkpoint_id`. All coverage results contain empty-string IDs, potentially causing all checkpoints to be falsely classified as covered. (§10.2.4)

2. **Exact-Match Merge is Fundamentally Insufficient**: The `ChecklistMerger` relies entirely on exact normalized text for deduplication. Given LLM non-determinism and Chinese text synonymy, this guarantees fragmented output trees. (§10.2.1, §10.3.2)

3. **Four Inconsistent Deduplication Mechanisms**: Character Jaccard (0.4), bigram Jaccard (0.75), exact casefold match, and exact whitespace-stripped match — all used for semantically similar purposes but producing different results. (§10.3.3)

4. **Four Inconsistent Text Normalization Implementations**: `text_normalizer.py`, `checklist_merger.py::_normalize_text`, `mr_checkpoint_injector.py::_normalize_text`, and `checkpoint_outline_planner.py::_normalize_text` — all different, all used in the merge/dedup pipeline. (§10.2.3, §10.3.3)

5. **Chinese Text Handling Is Character-Level Only**: No word segmentation, no synonym awareness, no semantic embeddings. Character-level Jaccard produces both false positives and false negatives for Chinese. (§10.3.2)

6. **Priority and Metadata Dropped During Merge**: `NormalizedChecklistPath` carries `priority`, `category`, and `checkpoint_id`, but `ChecklistMerger` ignores all three. No priority-aware merge decisions are possible. (§10.2.1)

7. **Duplicate Trie Implementation**: `checklist_merger.py` and `checkpoint_outline_planner.py` each implement their own Trie with different node structures and normalization. (§10.2.5)

8. **No Validation Gates Between Pipeline Steps**: Errors propagate silently from normalization through merge to coverage to outline planning. (§10.3.2)

9. **LLM Fallback Creates Unmergeable Paths**: When `SemanticPathNormalizer` falls back to raw preconditions/steps, the generated node IDs (`{case_id}-fallback-{n}`) guarantee these paths can never share prefixes with any other path. (§10.2.2)

10. **Semantic Path Normalizer Is the Upstream Bottleneck**: The entire merge pipeline's quality depends on the LLM producing consistent canonical vocabularies. There is no validation, no retry, and no fallback quality check after the LLM normalization stages. (§10.2.2)

---

## §10.5 Improvement Recommendations Summary

| Priority | Recommendation | Effort | Impact |
|----------|---------------|--------|--------|
| **P0** | Fix `CoverageDetector._get_id()` to use `checkpoint_id` | Low | Fixes false coverage classification |
| **P0** | Unify text normalization into a shared `TextSimilarity` service | Medium | Eliminates inconsistent dedup across all components |
| **P1** | Replace exact-match merge key with similarity-based matching (embedding or improved Jaccard) | Medium | Dramatically improves merge quality for Chinese text |
| **P1** | Add validation gates between pipeline steps | Medium | Prevents silent error propagation |
| **P1** | Propagate priority/category through merge pipeline | Low | Enables priority-aware merge decisions |
| **P2** | Integrate Chinese word segmentation (jieba/pkuseg) for word-level comparison | Medium | Improves all Chinese text comparisons |
| **P2** | Extract shared Trie utility from merger + outline planner | Low | Eliminates code duplication, ensures consistent normalization |
| **P2** | Add LLM-guided merge arbitration for ambiguous sibling pairs | Medium | Catches semantic near-duplicates that statistical methods miss |
| **P3** | Add vocabulary validation after SemanticPathNormalizer Stage 1 | Low | Catches LLM inconsistencies before they propagate |
| **P3** | Build domain-specific synonym dictionary for QA terms | Low | Improves normalized form consistency |

---

## §10.6 Cross-References

| This File | References | Referenced By |
|-----------|-----------|---------------|
| `checklist_merger.py` | `checklist_models.ChecklistNode`, `semantic_path_normalizer.NormalizedChecklistPath` | Structure assembler, delivery agents |
| `semantic_path_normalizer.py` | `LLMClient`, `case_models.TestCase` | `checklist_merger.py` (via normalized paths) |
| `text_normalizer.py` | `case_models.TestCase` | Preprocessing nodes (optional) |
| `coverage_detector.py` | `checklist_models.Checkpoint` (intended) | `case_generation.py::_coverage_detector_node`, `checkpoint_outline_planner.py` |
| `checkpoint_outline_planner.py` | `LLMClient`, `coverage_detector.CoverageResult`, `checklist_models.*`, `checkpoint_models.Checkpoint`, `template_models.MandatorySkeletonNode`, `xmind_reference_models.XMindReferenceSummary` | `case_generation.py` (via `build_checkpoint_outline_planner_node`) |
| `workflow_service.py` | `LLMClient`, `IterationController`, `PlatformDispatcher`, `FileRunRepository`, `RunStateRepository`, `main_workflow.build_workflow` | API layer (`api_models.CaseGenerationRequest`) |
| `iteration_controller.py` | `run_state.*` | `workflow_service.py` |
| `mandatory_skeleton_builder.py` | `template_models.MandatorySkeletonNode`, `template_models.ProjectChecklistTemplateFile` | Template loading nodes, `checkpoint_outline_planner.py` |
| `precondition_grouper.py` | `LLMClient`, `case_models.TestCase`, `checklist_models.ChecklistNode`, `precondition_models.PreconditionGroupingResult` | Structure assembler |

### Key Dependency Chain for Checklist Integration

```
TestCase ──→ [text_normalizer] ──→ [SemanticPathNormalizer] ──→ NormalizedChecklistPath
                                                                        │
                                                                        ▼
                                                              [ChecklistMerger] ──→ ChecklistNode tree
                                                                        │
Checkpoint ──→ [CoverageDetector] ──→ CoverageResult ──→ [CheckpointOutlinePlanner] ──→ optimized_tree
                                                                        │
                                                        [MandatorySkeletonBuilder] ──→ MandatorySkeletonNode
```

### Related Analysis Files

- `§8` — Domain models (`checklist_models.py`, `checkpoint_models.py`) — field definitions and aliases
- `§9` — Nodes (`checkpoint_evaluator.py`, `mr_checkpoint_injector.py`, `reflection.py`) — additional dedup implementations
- `§11` — Graphs (`case_generation.py`, `main_workflow.py`) — pipeline wiring and data flow