> **Auto-generated analysis** — PR #17 (Checklist 前置条件分组优化 V2)
> Replaces PR #15 version
> Generated: 2026-03-19

# `markdown_renderer.py` — 统一 Markdown 渲染器

---

## §1 File Overview

| Attribute | Value |
|-----------|-------|
| **Path** | `app/services/markdown_renderer.py` |
| **Lines** | 142 |
| **Role** | Unified Markdown renderer for test cases — DRY fix replacing duplicate functions in `platform_dispatcher` and `workflow_service` |
| **PR** | #17 (V2 — enhanced with tree rendering mode) |
| **Key property** | Two modes: flat (backward compatible) and tree (grouped by preconditions) |

---

## §2 Core Content

### 2.1 Public API

```python
def render_test_cases_markdown(
    test_cases: list[TestCase],
    optimized_tree: list[ChecklistNode] | None = None,
) -> str:
```

**Mode selection**:
- If `optimized_tree` is truthy (non-empty list) → tree mode (`_render_tree`)
- Otherwise → flat mode (`_flat_render`)

### 2.2 Flat Mode — `_flat_render(test_cases)`

Identical to the original `_render_test_cases_markdown` that previously lived in both `platform_dispatcher.py` and `workflow_service.py`.

| Element | Format |
|---------|--------|
| Empty input | `"# 生成的测试用例\n\n暂无测试用例。\n"` |
| Case heading | `## {tc.id} {tc.title}` |
| Checkpoint | `**Checkpoint:** {tc.checkpoint_id}` (only if non-empty) |
| Preconditions | `### 前置条件` + `- {item}` list (or `- 无` if empty) |
| Steps | `### 步骤` + `{i}. {step}` numbered list |
| Expected results | `### 预期结果` + `- {item}` list |

### 2.3 Tree Mode — `_render_tree(tree)` + Recursive Helpers

#### Functions

| Function | Purpose |
|----------|--------|
| `_render_tree(tree)` | Entry point: header + iterate root-level nodes |
| `_render_node(node, lines)` | Dispatcher: routes by `node_type` |
| `_render_group_node(node, lines)` | Renders `precondition_group` nodes |
| `_render_case_node(node, lines, heading_level)` | Renders `case` leaf nodes |

#### Tree Mode Output Format

| Element | Format |
|---------|--------|
| Document title | `# 生成的测试用例（优化分组）` |
| Group heading | `## 前置条件: {node.title}` |
| Group preconditions | `- {pc}` list |
| Case heading (in group) | `### {ref_label} {node.title}` (heading_level=3) |
| Case heading (standalone) | `## {ref_label} {node.title}` (heading_level=2) |
| Additional preconditions | `####  附加前置条件` + `- {item}` (level = heading_level + 1) |
| Steps | `#### 步骤` + `{i}. {step}` |
| Expected results | `#### 预期结果` + `- {item}` |
| Checkpoint | `**Checkpoint:** {node.checkpoint_id}` |

**Dynamic heading levels**: `_render_case_node` receives `heading_level` parameter. Inside a group it is 3, standalone it is 2. Sub-sections use `heading_level + 1`.

#### Root Node Transparency

When `node_type == "root"`, the renderer skips the node itself and only renders its children — the root is transparent/virtual.

---

## §3 Dependencies

### Internal
| Import | Purpose |
|--------|---------|
| `app.domain.case_models.TestCase` | Flat mode input type |
| `app.domain.checklist_models.ChecklistNode` | Tree mode input type |

### External
None — pure string manipulation.

---

## §4 Key Logic / Data Flow

### DRY Fix

**Before PR #17**:
- `platform_dispatcher.py` had its own `_render_test_cases_markdown()`
- `workflow_service.py` had an identical copy

**After PR #17**:
- Both modules import and call `render_test_cases_markdown()` from this shared module
- `platform_dispatcher.py` passes `optimized_tree` from `workflow_result`
- `workflow_service.py` removes its copy entirely

### Rendering Pipeline

```
render_test_cases_markdown(test_cases, optimized_tree)
  │
  ├─ optimized_tree is truthy?
  │   ├─ YES → _render_tree(optimized_tree)
  │   │         → _render_node() for each root-level node
  │   │           → _render_group_node() or _render_case_node()
  │   │
  │   └─ NO → _flat_render(test_cases)
  │           → identical to original _render_test_cases_markdown
  │
  └─ return Markdown string
```

---

## §5 Design Patterns

| Pattern | Application |
|---------|------------|
| **Strategy** | Two rendering strategies (flat/tree) behind one entry point |
| **Composite visitor** | Recursive `_render_node` dispatches by `node_type` |
| **DRY** | Single shared module replaces duplicated code in 2 files |
| **Backward compatibility** | Empty/None `optimized_tree` → flat mode, identical to pre-V2 output |
| **Parameterized heading** | `heading_level` enables context-sensitive nesting depth |

---

## §6 Potential Concerns

| # | Concern | Severity | Notes |
|---|---------|----------|-------|
| 1 | No escaping of Markdown special characters in titles | Low | TestCase titles are LLM-generated, unlikely to contain `#` or `*` |
| 2 | `ref_label` falls back to `node_id` if `test_case_ref` empty | Low | Defensive; should not happen in normal flow |
| 3 | Deeply nested groups would produce `#####+` headings | Low | `_MAX_TREE_DEPTH=3` in grouper prevents this structurally |
| 4 | Flat mode `or ["- 无"]` uses list-level fallback | Low | Works correctly for rendering but is a non-obvious pattern |
