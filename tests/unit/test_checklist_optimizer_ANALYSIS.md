# test_checklist_optimizer.py 分析

## 概述

`tests/unit/test_checklist_optimizer.py` 是 `checklist_optimizer_node` LangGraph 节点函数的单元测试文件。使用 `unittest.mock.patch` 对 `refine_test_case` 和 `ChecklistMerger` 进行 mock，覆盖正常流、空输入、单步降级和全局降级等场景。

该文件位于 `tests/unit/` 测试目录，为 F5（工作流集成）和优雅降级策略提供测试保障。

## 依赖关系

- 上游依赖:
  - `pytest`
  - `unittest.mock` (`patch`, `MagicMock`)
  - `app.domain.checklist_models.ChecklistNode`
  - `app.nodes.checklist_optimizer.checklist_optimizer_node`
- 下游消费者: 无（测试文件）

## 核心实现

### FakeTestCase 替身

与 `test_checklist_merger.py` 类似的轻量 TestCase 模拟类，带 `__test__ = False` 标记。

### TestChecklistOptimizerNode 测试类

- **`test_empty_test_cases`**: 空 test_cases 输入返回空列表和空树
- **`test_missing_test_cases_key`**: state 中无 test_cases 键时安全返回空结果
- **`test_normal_flow`**: 正常流测试
  - mock `refine_test_case` 返回精炼后的用例
  - mock `ChecklistMerger` 返回预设的 ChecklistNode 树
  - 验证 `test_cases` 为精炼后结果，`optimized_tree` 为 mock 树
  - 验证调用参数正确（language 传递等）
- **`test_refine_failure_keeps_original`**: refine_test_case 抛出 ValueError 时，保留原始用例继续处理
- **`test_merger_failure_returns_empty_tree`**: ChecklistMerger.merge 抛出 RuntimeError 时，test_cases 正常返回，optimized_tree 为空列表

### Mock 策略

- `@patch("app.nodes.checklist_optimizer.refine_test_case")`: 在节点模块的命名空间中 mock，确保 patch 正确
- `@patch("app.nodes.checklist_optimizer.ChecklistMerger")`: mock 整个类，通过 `MockMerger.return_value` 控制实例行为

## 关联需求

- PRD: Checklist 同前置操作整合与表达精炼优化
- 功能编号: F5（工作流集成 — 节点测试）、F1/F2（降级策略测试）

## 变更历史

- PR #15: 初始创建
