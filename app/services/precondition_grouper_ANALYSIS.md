> **Auto-generated analysis** — PR #17 (Checklist 前置条件分组优化 V2)
> NEW file — replaces `checklist_merger_ANALYSIS.md` (Trie approach reverted in PR #16)
> Generated: 2026-03-19

# `precondition_grouper.py` — 前置条件分组引擎

---

## §1 File Overview

| Attribute | Value |
|-----------|-------|
| **Path** | `app/services/precondition_grouper.py` |
| **Lines** | 201 |
| **Role** | Core grouping engine: transforms a flat `list[TestCase]` into a grouped `list[ChecklistNode]` tree |
| **PR** | #17 (V2 — replaces PR #15 `checklist_merger.py` Trie-based approach) |
| **Key property** | Pure function, no LLM calls, deterministic output (except UUID-based group IDs) |

---

## §2 Core Content

### 2.1 Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_MAX_TREE_DEPTH` | `3` | Enforces root → group → case (≤3 layers) |
| `_MIN_GROUP_SIZE` | `2` | Single-case buckets produce standalone `case` nodes, not groups |
| `_PUNCT_MAP` | `str.maketrans({...})` | 9 Chinese → English punctuation mappings |

### 2.2 Punctuation Mapping Table (`_PUNCT_MAP`)

| Chinese | English | Unicode |
|---------|---------|--------|
| ， | , | `\uff0c` |
| 。 | . | `\u3002` |
| ； | ; | `\uff1b` |
| ： | : | `\uff1a` |
| （ | ( | `\uff08` |
| ） | ) | `\uff09` |
| 、 | , | `\u3001` |
| ！ | ! | `\uff01` |
| ？ | ? | `\uff1f` |

### 2.3 Module-Level Functions

#### `_normalize_precondition(text: str) -> str`
Normalization pipeline:
1. `strip()` — remove leading/trailing whitespace
2. `unicodedata.normalize("NFKC", ...)` — unify Unicode representations (e.g., fullwidth → ASCII)
3. `.translate(_PUNCT_MAP)` — Chinese punctuation → English equivalents

**Important**: NO `casefold()` (Chinese has no case), NO number/bullet removal.

#### `_normalize_precondition_list(preconditions: Sequence[str]) -> tuple[str, ...]`
Applies `_normalize_precondition` to each item, then `sorted()`, returns as `tuple` (hashable for dict key).

#### `_longest_common_prefix(strings: Sequence[str]) -> str`
Computes LCP of multiple strings. **Defined but NOT used** in the main grouping flow — reserved for future title generation.

### 2.4 `PreconditionGrouper` Class

#### Public API

```python
class PreconditionGrouper:
    def group(self, test_cases: list[TestCase]) -> list[ChecklistNode]: ...
```

Returns root-level children (not wrapped in a root node).

#### Internal Methods

| Method | Signature | Purpose |
|--------|-----------|--------|
| `_bucket_by_preconditions` | `(test_cases) -> OrderedDict[tuple[str,...], list[TestCase]]` | Groups cases by normalized precondition tuple; preserves insertion order |
| `_build_grouped_tree` | `(buckets) -> list[ChecklistNode]` | Converts buckets to tree nodes |
| `_build_precondition_group` | `(key, cases) -> ChecklistNode` | Creates a `precondition_group` node |
| `_build_case_node` | `(tc, shared_preconditions) -> ChecklistNode` | Creates a `case` leaf node |

---

## §3 Dependencies

### Internal
| Import | Purpose |
|--------|---------|
| `app.domain.case_models.TestCase` | Input data type |
| `app.domain.checklist_models.ChecklistNode` | Output data type |

### External
| Package | Usage |
|---------|-------|
| `unicodedata` | NFKC normalization |
| `uuid` | `uuid4().hex[:8]` for group IDs |
| `collections.OrderedDict` | Insertion-order-preserving buckets |
| `typing.Sequence` | Type hints for function parameters |
| `logging` | Logger instance |

---

## §4 Key Logic / Data Flow

### 4.1 Grouping Algorithm

```
Input: list[TestCase]
  │
  ▼
_bucket_by_preconditions()
  │  For each TestCase:
  │    key = tuple(sorted(normalize(pc) for pc in tc.preconditions))
  │    OrderedDict[key] → append tc
  │
  ▼
_build_grouped_tree()
  │  For each (key, cases) in buckets:
  │    if key is empty OR len(cases) < 2:
  │      → standalone case nodes (no group wrapper)
  │    else:
  │      → precondition_group node with case children
  │
  ▼
Output: list[ChecklistNode]  (root-level children)
```

### 4.2 "Additional Preconditions" Logic

When a case belongs to a group, its `preconditions` field is rewritten to contain only conditions **not** in the shared set:

```python
def _build_case_node(self, tc, shared_preconditions=()):
    shared_set = set(shared_preconditions)
    additional = []
    for p in tc.preconditions:
        normalized = _normalize_precondition(p)
        if normalized not in shared_set:
            additional.append(p)  # preserves original text
    # node.preconditions = additional
```

This enables the renderer to show only "extra" conditions under each case.

### 4.3 Group ID Format

```python
group_id = f"GRP-{uuid.uuid4().hex[:8]}"  # e.g., "GRP-a1b2c3d4"
```

Case IDs: `f"CASE-{tc.id}"` (e.g., `"CASE-TC-001"`).

### 4.4 Group Title

```python
group_title = " → ".join(precondition_key)
```

Joins the normalized precondition tuple with ` → ` (Unicode arrow).

---

## §5 Design Patterns

| Pattern | Application |
|---------|------------|
| **Pure function** | No side effects, no LLM, no I/O — only data transformation |
| **Strategy** | Bucketing strategy isolated in `_bucket_by_preconditions`; tree building in `_build_grouped_tree` |
| **Normalization pipeline** | 3-step: strip → NFKC → punctuation mapping |
| **OrderedDict** | Guarantees output order matches input encounter order |
| **Threshold-based grouping** | `_MIN_GROUP_SIZE=2` prevents trivial single-case groups |

---

## §6 Potential Concerns

| # | Concern | Severity | Notes |
|---|---------|----------|-------|
| 1 | `_longest_common_prefix` is dead code | Low | Intentionally reserved for future use; no impact on current flow |
| 2 | No casefold means "Login" and "login" are different buckets | Medium | Design choice: Chinese text has no case. English-heavy inputs may under-group. |
| 3 | UUID-based group IDs make output non-reproducible | Low | Acceptable for display purposes; tests check format (`GRP-` prefix) not exact values |
| 4 | No deduplication within a bucket | Low | If two cases have identical preconditions but are duplicates, both appear in the group |
| 5 | `_MAX_TREE_DEPTH=3` constant defined but not dynamically checked | Low | The algorithm structurally guarantees ≤3 layers (root→group→case), no deeper nesting possible |
