# Actionable Checklist Path Phase 1 Design

**Date:** 2026-03-19
**Status:** Approved
**Scope:** Phase 1 only

## Goal

将现有 `optimized_tree` 从“共享语义树”升级为“可执行路径树”，同时保持 Markdown / XMind 继续消费同一份 `optimized_tree`。

本期只覆盖：

1. 在树中保留 testcase 的关键 `preconditions` 和 `steps`
2. 让中下层节点尽量变成中文可执行动作短句
3. 继续兼容当前工作流、Markdown、XMind 输出契约

本期不覆盖：

1. 完整的项目级 ontology CRUD
2. 质量报告与告警面板
3. Phase 2 的显式父子合法性自动修正器

## Current State

当前子图已经改为：

`checkpoint_outline_planner -> draft_writer -> structure_assembler`

其中：

1. `checkpoint_outline_planner` 在 testcase 生成前规划稳定骨架并直接产出 `optimized_tree`
2. `draft_writer` 只在既定路径下生成叶子级 testcase 内容
3. `structure_assembler` 目前只会把 `expected_results` 挂回 outline tree

这意味着 Phase 1 的最小正确实现路径不是重做 renderer，也不是回到旧的 `checklist_optimizer`，而是扩展“先骨架、后回填”的主链路。

## Chosen Approach

采用“稳定骨架 + testcase 内容注入”的方案：

1. `checkpoint_outline_planner` 继续负责上层稳定结构
2. `draft_writer` 继续被固定路径约束，不生成父级摘要层
3. `structure_assembler` 在 testcase 标准化后，把 `preconditions + steps + expected_results` 按 checkpoint 路径回填进 `optimized_tree`
4. 渲染层继续直接消费 `optimized_tree`

这样做的原因：

1. 不破坏现有工作流拓扑
2. `optimized_tree` 的外部字段名和渲染入口保持稳定
3. 可在不引入完整 ontology 配置系统的情况下先得到“可执行路径树”

## Tree Shape

Phase 1 目标节点分层如下：

1. `business_object`: 允许保留名词，如 `Ad group`
2. `precondition` / `page_entry`: 用中文状态句或进入页面句承载前置上下文
3. `operation`: 用中文动作短句承载 testcase 步骤
4. `expected_result`: 继续作为叶子节点

在数据结构上，Phase 1 仍复用现有 `ChecklistNode`：

1. 非叶子统一继续使用 `group`
2. 预期结果继续使用 `expected_result`
3. 节点语义通过新增元数据区分，而不是改掉外部 `optimized_tree` 契约

## Data Flow

### 1. Outline Planning

`checkpoint_outline_planner` 继续生成：

1. `canonical_outline_nodes`
2. `checkpoint_paths`
3. 只包含结构骨架的 `optimized_tree`

同时增强 prompt，使其更偏向：

1. 顶层保留业务对象
2. 下层优先使用中文状态句、页面入口句、动作句
3. 避免纯英文抽象名词节点

### 2. Testcase Attachment

`structure_assembler` 在 testcase 标准化后执行路径注入：

1. 按 `checkpoint_id` 找到 testcase 对应的 outline path
2. 在已存在的可见骨架路径下，依序追加 testcase 的 `preconditions`
3. 追加 testcase 的 `steps`
4. 将 `expected_results` 挂到最贴近的操作节点下

归并规则：

1. 文本完全一致或规范化后等价的节点合并
2. 不把不同动作抽象压缩成一个名词节点
3. 当 testcase 没有步骤时，结果仍挂到当前最深节点

## Project Context Handling

Phase 1 不新增 ontology CRUD，但会让现有项目上下文先能承载结构提示：

1. 项目 `metadata` 中允许写入 checklist path hints / ontology hints
2. `project_context_summary` 会把这些结构提示串接进注入文本
3. `checkpoint_outline_planner` 与 `draft_writer` 都通过已有 `project_context_summary` 获得项目层级约束

这是一种兼容式过渡，后续可以无缝升级为独立 ontology 数据模型。

## Compatibility

保持以下契约不变：

1. `optimized_tree` 字段名不变
2. `test_cases.md` 产物名不变
3. Markdown 继续从 `optimized_tree` 渲染树模式
4. XMind 继续从 `optimized_tree` 渲染树模式

## Testing Strategy

Phase 1 重点覆盖：

1. outline planner 生成的节点更接近可执行路径
2. testcase 的 `preconditions + steps + expected_results` 会回填到 `optimized_tree`
3. 相同操作前缀会在树中归并
4. Markdown / XMind 不需要改接口即可正确展示新树
