> **Auto-generated analysis** — PR #17 (Checklist 前置条件分组优化 V2)
> Replaces PR #15 version (Trie-based approach reverted in PR #16)
> Generated: 2026-03-19

# `checklist_models.py` — Checklist 优化树节点模型

---

## §1 File Overview

| Attribute | Value |
|-----------|-------|
| **Path** | `app/domain/checklist_models.py` |
| **Lines** | 42 |
| **Role** | Defines `ChecklistNode`, the Pydantic v2 data model for the ≤3-layer optimization tree |
| **PR** | #17 (V2 — replaces PR #15 Trie-based model) |
| **New in V2** | Simplified from V1: removed Trie-specific fields, added `model_rebuild()` for self-referencing |

---

## §2 Core Content

### 2.1 `ChecklistNode(BaseModel)`

A single Pydantic v2 `BaseModel` that represents every node type in the tree via `node_type` discrimination.

#### Field Table

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `node_id` | `str` | `""` | Unique identifier (`GRP-{hex}` for groups, `CASE-{tc.id}` for cases) |
| `title` | `str` | `""` | Human-readable title |
| `node_type` | `Literal["root", "precondition_group", "case"]` | `"precondition_group"` | Discriminator for node semantics |
| `children` | `list[ChecklistNode]` | `[]` (via `Field(default_factory=list)`) | Child nodes — enables ≤3-layer tree |
| `test_case_ref` | `str` | `""` | Original `TestCase.id` (case nodes only) |
| `preconditions` | `list[str]` | `[]` | Shared preconditions (group) or additional preconditions (case) |
| `steps` | `list[str]` | `[]` | Test steps (case nodes only) |
| `expected_results` | `list[str]` | `[]` | Expected results (case nodes only) |
| `priority` | `str` | `"P2"` | Priority label |
| `category` | `str` | `"functional"` | Test category |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | PRD evidence references |
| `checkpoint_id` | `str` | `""` | Linked checkpoint ID |

**Key design**: All fields have defaults — no required fields. This allows partial construction during tree building.

### 2.2 Self-Referencing Pattern

```python
class ChecklistNode(BaseModel):
    children: list[ChecklistNode] = Field(default_factory=list)

# Pydantic v2 requires explicit rebuild for self-referencing
ChecklistNode.model_rebuild()
```

The `model_rebuild()` call at module level is mandatory in Pydantic v2 when a model references itself in `children`. Without it, JSON schema generation and validation would fail.

---

## §3 Dependencies

### Internal
| Import | Purpose |
|--------|---------|
| `app.domain.research_models.EvidenceRef` | Type for `evidence_refs` field |

### External
| Package | Usage |
|---------|-------|
| `pydantic.BaseModel` | Model base class |
| `pydantic.Field` | `default_factory` for mutable defaults |
| `typing.Literal` | `node_type` discrimination |

---

## §4 Key Logic / Data Flow

### Tree Structure (≤3 layers)

```
root (virtual)
├── precondition_group (shared conditions)
│   ├── case (leaf — individual test case)
│   └── case
├── precondition_group
│   └── case
└── case (standalone — ungrouped)
```

- **root**: Virtual container, only used as children holder
- **precondition_group**: Groups cases sharing identical normalized preconditions; `preconditions` field holds the shared set
- **case**: Leaf node; `preconditions` field holds *additional* conditions not covered by the parent group

---

## §5 Design Patterns

| Pattern | Application |
|---------|------------|
| **Composite** | Single `ChecklistNode` class serves all node roles via `node_type` discriminator |
| **Self-referencing model** | `children: list[ChecklistNode]` + `model_rebuild()` |
| **All-defaults** | Every field has a default, enabling partial construction |
| **Literal discrimination** | `node_type` constrains to exactly 3 allowed values |

---

## §6 Potential Concerns

| # | Concern | Severity | Notes |
|---|---------|----------|-------|
| 1 | Case-specific fields exposed on group/root nodes | Low | Trade-off: simplicity vs type safety. Group nodes carry `steps=[]` etc. but they are never read. |
| 2 | Default `node_type="precondition_group"` | Low | Could be `"case"` to match leaf-heavy usage, but current default aligns with constructor usage in `PreconditionGrouper` |
| 3 | No depth validation | Low | `_MAX_TREE_DEPTH=3` is enforced in `PreconditionGrouper`, not in the model itself |
