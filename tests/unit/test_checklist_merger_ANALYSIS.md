# test_checklist_merger.py 分析

## 概述

`tests/unit/test_checklist_merger.py` 是 `ChecklistMerger` Trie 合并逻辑的单元测试文件。使用 `FakeTestCase` 轻量替身模拟 `TestCase` 对象，覆盖归一化、空/单/多用例合并、单子链剪枝和深度限制等核心场景。

该文件位于 `tests/unit/` 测试目录，为 F1（前置操作合并）功能提供测试保障。

## 依赖关系

- 上游依赖:
  - `pytest`
  - `app.domain.checklist_models.ChecklistNode`
  - `app.services.checklist_merger.ChecklistMerger`
  - `app.services.checklist_merger._normalize_for_comparison`（内部函数，白盒测试）
- 下游消费者: 无（测试文件）

## 核心实现

### FakeTestCase 替身

轻量级 TestCase 模拟类，具有 `__test__ = False` 标记避免 pytest 误收集。提供与真实 `TestCase` 相同的字段接口：`id`, `title`, `preconditions`, `steps`, `expected_results`, `priority`, `category`, `evidence_refs`, `checkpoint_id`。

### 辅助函数

- **`_collect_leaves(nodes)`**: 递归收集所有 case 叶子节点，用于验证合并结果中叶子数量和内容
- **`_assert_no_single_child_groups(nodes)`**: 递归断言不存在单子节点 group 链，用于验证剪枝逻辑

### TestNormalization 测试类

测试 `_normalize_for_comparison` 归一化逻辑：
- `test_strip_numbering`: 验证序号前缀（`1. `, `Step 2: `）被正确移除
- `test_casefold`: 验证大小写统一
- `test_chinese_punctuation`: 验证中文标点被替换为英文标点

### TestChecklistMerger 测试类

测试核心合并功能：
- `test_empty_input`: 空列表返回空列表
- `test_single_case`: 单用例合并后叶子数为 1
- `test_shared_prefix_creates_group`: 共享前缀的用例创建 group 节点
- `test_no_shared_prefix`: 无共享前缀时不创建 group
- `test_pruning_removes_single_child_chains`: 验证单子链剪枝
- `test_max_depth_respected`: 超长步骤列表（20 步）不崩溃，叶子有 remaining_steps

## 关联需求

- PRD: Checklist 同前置操作整合与表达精炼优化
- 功能编号: F1（前置操作合并 — 测试覆盖）

## 变更历史

- PR #15: 初始创建
