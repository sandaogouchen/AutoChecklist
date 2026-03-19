> **Auto-generated analysis** — PR #17 (Checklist 前置条件分组优化 V2)
> NEW file — no PR #15 equivalent (markdown_renderer.py is new in V2)
> Generated: 2026-03-19

# `test_markdown_renderer.py` — Markdown 渲染器单元测试

---

## §1 File Overview

| Attribute | Value |
|-----------|-------|
| **Path** | `tests/unit/test_markdown_renderer.py` |
| **Lines** | 203 |
| **Role** | Unit tests for `render_test_cases_markdown()` — covers both flat and tree rendering modes |
| **PR** | #17 (new file, no PR #15 equivalent) |
| **Test count** | 14 tests across 2 test classes |
| **Test data** | Uses real `TestCase` and `ChecklistNode` objects via helper functions |

---

## §2 Core Content

### 2.1 Helper Functions

#### `_tc(tc_id, title, preconditions, steps, expected_results, checkpoint_id) -> TestCase`
Builds minimal `TestCase` objects for flat mode tests.

#### `_group_node(title, preconditions, case_children) -> ChecklistNode`
Builds `precondition_group` nodes for tree mode tests.

```python
def _group_node(title, preconditions, case_children) -> ChecklistNode:
    return ChecklistNode(
        node_id="GRP-test",
        title=title,
        node_type="precondition_group",
        children=case_children,
        preconditions=preconditions,
    )
```

#### `_case_node(tc_id, title, preconditions, steps, expected_results, checkpoint_id) -> ChecklistNode`
Builds `case` leaf nodes for tree mode tests.

### 2.2 Test Classes and Cases

#### `TestFlatRender` (7 tests)

Tests for flat mode (`optimized_tree` is `None` or empty).

| Test | Key Assertion |
|------|---------------|
| `test_empty_input` | `"暂无测试用例"` in output |
| `test_single_case` | `"## TC-001 验证登录"` in output |
| `test_with_preconditions` | `"- 用户已注册"` and `"- 网络正常"` in output |
| `test_with_checkpoint_id` | `"**Checkpoint:** CP-abc123"` in output |
| `test_no_preconditions_shows_none` | `"- 无"` in output when preconditions empty |
| `test_fallback_when_tree_empty` | `optimized_tree=[]` → flat mode (`"## TC-001"` in output) |
| `test_fallback_when_tree_none` | `optimized_tree=None` → flat mode |

#### `TestTreeRender` (7 tests)

Tests for tree mode (`optimized_tree` has nodes).

| Test | Key Assertion |
|------|---------------|
| `test_single_group` | `"## 前置条件: 用户已登录"` in output, both `TC-001` and `TC-002` present |
| `test_group_preconditions_rendered` | `"- 登录"` and `"- 网络正常"` in group section |
| `test_additional_preconditions` | `"附加前置条件"` heading and `"- VPN连接"` in output |
| `test_multiple_groups` | Both `"## 前置条件: 条件A"` and `"## 前置条件: 条件B"` present |
| `test_steps_and_expected_results` | Numbered steps (`"1. 打开页面"`) and bullet results (`"- 页面跳转"`) |
| `test_root_node_renders_children_only` | Root node transparent — child `"子用例"` appears, no root heading |
| `test_case_with_checkpoint_id` | `"**Checkpoint:** CP-xyz"` in tree-mode output |

---

## §3 Dependencies

### Internal
| Import | Purpose |
|--------|---------|
| `app.domain.case_models.TestCase` | Flat mode test data |
| `app.domain.checklist_models.ChecklistNode` | Tree mode test data |
| `app.services.markdown_renderer.render_test_cases_markdown` | SUT |

### External
| Package | Usage |
|---------|-------|
| `pytest` | Test framework |

---

## §4 Key Logic / Data Flow

### Coverage Matrix

| Feature | Flat Tests | Tree Tests |
|---------|------------|------------|
| Empty/None fallback | `test_empty_input`, `test_fallback_when_tree_empty`, `test_fallback_when_tree_none` | — |
| Case heading | `test_single_case` | `test_single_group` |
| Preconditions | `test_with_preconditions`, `test_no_preconditions_shows_none` | `test_group_preconditions_rendered`, `test_additional_preconditions` |
| Checkpoint ID | `test_with_checkpoint_id` | `test_case_with_checkpoint_id` |
| Steps & results | (implicit in all cases) | `test_steps_and_expected_results` |
| Multiple groups | — | `test_multiple_groups` |
| Root transparency | — | `test_root_node_renders_children_only` |

### Mode Selection Testing

The flat tests explicitly verify that:
- `optimized_tree=[]` → flat mode
- `optimized_tree=None` → flat mode

This ensures backward compatibility when the optimizer is disabled or produces no output.

---

## §5 Design Patterns

| Pattern | Application |
|---------|------------|
| **Helper factories** | `_tc()`, `_group_node()`, `_case_node()` reduce test boilerplate |
| **Substring assertion** | `assert "..." in md` — tests content presence without brittle full-string matching |
| **Dual mode coverage** | Separate test classes for flat vs tree modes |
| **Boundary testing** | Empty input, None tree, empty tree |

---

## §6 Potential Concerns

| # | Concern | Severity | Notes |
|---|---------|----------|-------|
| 1 | No negative test for malformed `ChecklistNode` | Low | Pydantic validation would catch this at model level |
| 2 | Tests use substring matching, not exact output | Low | Intentional — avoids brittleness from whitespace/ordering changes |
| 3 | `_group_node` always uses `node_id="GRP-test"` | Low | Sufficient for rendering tests; ID format tested in `test_precondition_grouper.py` |
