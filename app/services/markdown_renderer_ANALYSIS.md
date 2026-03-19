# markdown_renderer.py 分析

## 概述

`app/services/markdown_renderer.py` 提供统一的 Markdown 渲染入口，支持扁平模式（flat）和树形模式（tree）两种渲染策略。该模块消除了原先在 `platform_dispatcher.py` 和 `workflow_service.py` 中重复定义的 `_render_test_cases_markdown` 函数，实现了 DRY（Don't Repeat Yourself）修复。

该文件位于 `app/services/` 业务服务层，是 F4（Markdown 输出适配）功能的核心实现。

## 依赖关系

- 上游依赖:
  - `app.domain.case_models.TestCase` — 扁平模式渲染消费（TYPE_CHECKING 导入）
  - `app.domain.checklist_models.ChecklistNode` — 树形模式渲染消费（TYPE_CHECKING 导入）
- 下游消费者:
  - `app.services.platform_dispatcher` — 在 `_persist_local_artifacts` 中调用 `render_test_cases_markdown()`

## 核心实现

### 常量

- `_MAX_HEADING_DEPTH = 6`: Markdown 标题最大深度限制（HTML 标准 h1-h6）

### 公开 API

- **`render_test_cases_markdown(test_cases, optimized_tree=None) -> str`**: 统一入口。当 `optimized_tree` 非空时使用树形渲染，否则回退到扁平渲染。保证向后兼容。

- **`flat_render(test_cases) -> str`**: 扁平模式渲染，与原 `_render_test_cases_markdown` 实现完全一致。中文标题。空列表时返回「暂无测试用例」占位文本。

### 树形渲染

- **`_render_tree(tree) -> str`**: 将 ChecklistNode 树渲染为层级 Markdown，根标题为「生成的测试用例（树形视图）」

- **`_render_node(node, depth, lines)`**: 递归渲染分发器，根据 `node_type` 分发到 group 或 case 渲染函数

- **`_render_group_node(node, depth, lines)`**: 渲染 group 节点为 Markdown 标题，深度受 `_MAX_HEADING_DEPTH` 限制，递归渲染子节点

- **`_render_case_node(node, depth, lines)`**: 渲染 case 叶子节点，包含标题、Checkpoint 标注、remaining_steps（有序列表）、expected_results（无序列表）

### DRY 修复说明

原先 `platform_dispatcher.py` 和 `workflow_service.py` 各自定义了完全相同的 `_render_test_cases_markdown` 函数。PR #15 将该逻辑提取到本模块：
- `platform_dispatcher.py` 改为导入 `render_test_cases_markdown`（-38 行）
- `workflow_service.py` 移除重复函数（-37 行）

## 关联需求

- PRD: Checklist 同前置操作整合与表达精炼优化
- 功能编号: F4（Markdown 输出适配 — 共享渲染 + DRY 修复）

## 变更历史

- PR #15: 初始创建
