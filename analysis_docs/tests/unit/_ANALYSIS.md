# tests/unit/_ANALYSIS.md — 单元测试分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `tests/unit/` |
| 文件数 | 25（含 `__init__.py`） |
| 分析文件 | 24 |
| 目录职责 | 组件级单元测试：覆盖 domain models、nodes、services 三层 |
| Checklist 相关 | 8/24 文件直接涉及 checklist 整合 |

## §2 文件清单

| # | 文件 | 测试目标 | Checklist相关 |
|---|------|----------|---------------|
| 1 | `test_api_models.py` | `domain/api_models` | 否 |
| 2 | `test_case_models.py` | `domain/case_models` | 否 |
| 3 | `test_checklist_models.py` | `domain/checklist_models` | ✅ |
| 4 | `test_checkpoint_models.py` | `domain/checkpoint_models` | 部分 |
| 5 | `test_document_models.py` | `domain/document_models` | 否 |
| 6 | `test_research_models.py` | `domain/research_models` | 否 |
| 7 | `test_run_state.py` | `domain/run_state` | 否 |
| 8 | `test_state.py` | `domain/state` | 否 |
| 9 | `test_checklist_merger.py` | `services/checklist_merger` | ✅ |
| 10 | `test_checklist_optimizer.py` | `nodes/checklist_optimizer` | ✅ |
| 11 | `test_checkpoint_outline_planner.py` | `services/checkpoint_outline_planner` | ✅ |
| 12 | `test_context_research.py` | `nodes/context_research` | 否 |
| 13 | `test_draft_writer.py` | `nodes/draft_writer` | ✅ |
| 14 | `test_evaluation.py` | `nodes/evaluation` | 否 |
| 15 | `test_input_parser.py` | `nodes/input_parser` | 否 |
| 16 | `test_iteration_controller.py` | `services/iteration_controller` | 否 |
| 17 | `test_llm_client.py` | `clients/llm` | 否 |
| 18 | `test_markdown_parser.py` | `parsers/markdown` | 否 |
| 19 | `test_markdown_renderer.py` | `services/markdown_renderer` | 否 |
| 20 | `test_platform_dispatcher.py` | `services/platform_dispatcher` | 否 |
| 21 | `test_reflection.py` | `nodes/reflection` | 否 |
| 22 | `test_semantic_path_normalizer.py` | `services/semantic_path_normalizer` | ✅ |
| 23 | `test_attach_expected_results.py` | `services/checkpoint_outline_planner` (attach logic) | ✅ |
| 24 | `test_xmind_steps_rendering.py` | `services/xmind_payload_builder` (steps rendering) | ✅ |

## §3 Checklist 相关测试深度分析

### §3.1 test_checklist_models.py
- **测试范围**: `ChecklistNode` 树结构的构建与属性
- **关键用例**:
  - 构建多层 `ChecklistNode` 树（root → group → expected_result）
  - 验证 `node_type` 枚举的 5 种类型均可正确实例化
  - 验证 `children` 嵌套结构
  - `CanonicalOutlineNode` 路径管理
  - `CheckpointPathMapping` 和 `CheckpointPathCollection` 的关联关系
- **覆盖度**: 模型层覆盖完整

### §3.2 test_checklist_merger.py
- **测试范围**: `ChecklistMerger` 的 Trie 树合并逻辑
- **关键用例**:
  - 空输入 → 空输出
  - 单路径 → 单链树
  - 多路径公共前缀合并 → 正确的分支结构
  - 重复路径 → 不产生重复节点
  - 深层嵌套路径 → 层级正确性
- **注意**: 测试的是已弃用方案 A 的组件，但测试本身仍有价值（验证确定性算法的正确性）

### §3.3 test_checklist_optimizer.py
- **测试范围**: 已弃用的 `checklist_optimizer` 节点
- **关键用例**:
  - 正常流程：`SemanticPathNormalizer.normalize()` → `ChecklistMerger.merge()` → `optimized_tree`
  - 异常降级：normalize 或 merge 抛异常 → 返回空 `optimized_tree`（不阻断流水线）
- **价值**: 验证了异常容错机制，即使节点已弃用，其降级逻辑设计值得参考

### §3.4 test_checkpoint_outline_planner.py
- **测试范围**: `CheckpointOutlinePlanner` 服务的 outline 规划
- **关键用例**:
  - LLM 输出 → `CanonicalOutlineNode` 树的解析
  - `attach_expected_results_to_outline()` 的 checkpoint 匹配挂载
  - 空 checkpoint 列表处理
  - 多 checkpoint 共享同一 outline 节点
- **不足**: 缺少大规模 checkpoint（30+）场景的测试，无法暴露 LLM 规模瓶颈

### §3.5 test_draft_writer.py
- **测试范围**: `draft_writer` 节点的用例生成
- **关键用例**:
  - `_resolve_path_context()` 路径解析：验证从 `optimized_tree` 提取层级路径
  - LLM prompt 构建：验证系统提示包含 5 条前置条件规则
  - `TestCase` 生成：验证输出格式和字段完整性
  - 路径查找失败时的降级处理
- **Checklist 关联**: 验证了 outline 结构如何影响用例生成上下文

### §3.6 test_semantic_path_normalizer.py
- **测试范围**: `SemanticPathNormalizer` 的两阶段归一化
- **关键用例**:
  - Phase 1：从 checkpoint 提取原始路径
  - Phase 2：LLM 归一化路径格式
  - 输出格式验证：`NormalizedChecklistPath` 结构
- **注意**: 测试的是已弃用方案 A 的组件

### §3.7 test_attach_expected_results.py (NEW — PR #21)

> 新增于 PR #21 `feat/checklist-action-verbs-and-steps-passthrough`

- **测试范围**: `attach_expected_results_to_outline()` 重构后的新签名 `(optimized_tree, test_cases)` 及相关辅助逻辑
- **测试规模**: 8 个测试类，约 14 个测试用例
- **关键用例**:

| 测试场景 | 说明 |
|----------|------|
| 单匹配 | 单个 test_case 正确匹配到对应 outline 节点并填充字段 |
| 空树 | `optimized_tree` 为空列表时不抛异常，返回空结果 |
| 空 test_cases | `test_cases` 为空列表时，树结构保持不变（无填充） |
| 无匹配 checkpoint | outline 节点与 test_cases 无匹配时的优雅降级 |
| 多 TC 兄弟创建 | 多个 test_case 匹配同一 outline 节点时，正确创建兄弟子节点 |
| 嵌套树 | 多层嵌套树结构的递归充实正确性 |
| 遗留 expected_result 节点 | 处理树中已存在的 `expected_result` 类型旧节点 |
| 优雅降级 | 各种边界/异常情况下不崩溃，返回合理默认值 |

- **覆盖度**: 全面覆盖了重构后 `attach_expected_results_to_outline` 的核心逻辑，包括正常路径、边界条件和错误降级
- **Checklist 关联**: 直接验证了 PR #21 中签名简化后的挂载正确性，是 `_fill_node_from_testcase` 和 `_enrich_children` 的集成测试

### §3.8 test_xmind_steps_rendering.py (NEW — PR #21)

> 新增于 PR #21 `feat/checklist-action-verbs-and-steps-passthrough`

- **测试范围**: XMind 输出中 test case steps 的渲染逻辑（`XMindPayloadBuilder` 对 steps 字段的处理）
- **测试规模**: 3 个测试类，约 11 个测试用例
- **关键用例**:

| 测试场景 | 说明 |
|----------|------|
| 带 steps 的用例 | 验证 steps 字段正确渲染为 XMind topic 子节点 |
| 无 steps 的用例 | 验证 steps 为空时不产生多余的子节点 |
| 树模式 + 分组 | 树渲染模式下，group 节点包含的用例 steps 正确嵌套 |
| 深层嵌套 | 多层嵌套 group → case → steps 的渲染层级正确性 |
| 混合用例 | 同一组内部分有 steps、部分无 steps 的混合场景 |

- **覆盖度**: 覆盖了 steps 字段从 `ChecklistNode` 树到 XMind topic 树的完整渲染路径
- **Checklist 关联**: 验证了 PR #21 新增的 steps passthrough 功能在 XMind 输出端的正确性

## §4 非 Checklist 测试概览

### §4.1 模型层测试（6 文件）
- `test_api_models.py` — 请求/响应模型序列化
- `test_case_models.py` — TestCase 字段验证
- `test_checkpoint_models.py` — Checkpoint SHA-256 ID 生成幂等性
- `test_document_models.py` — ParsedDocument 结构
- `test_research_models.py` — ResearchFact 的 model_validator（str→list 转换）
- `test_run_state.py` / `test_state.py` — 状态模型

### §4.2 节点/服务层测试（8 文件）
- `test_context_research.py` — 上下文研究节点
- `test_evaluation.py` — 6 维度评估逻辑
- `test_input_parser.py` — PRD 解析
- `test_iteration_controller.py` — 迭代决策（pass/retry/abort）
- `test_llm_client.py` — JSON 三层防御解析
- `test_markdown_parser.py` — Markdown 章节分割
- `test_markdown_renderer.py` — 测试用例 Markdown 渲染
- `test_platform_dispatcher.py` — 平台分发逻辑
- `test_reflection.py` — 去重与质量检查

## §5 补充观察

1. **测试覆盖广度优秀**: 24 个测试文件覆盖了大部分核心组件，测试金字塔底层（单元测试）厚实
2. **Checklist 测试比重高**: 8/24 (33%) 的测试文件直接涉及 checklist 整合，反映了这是开发重点和痛点（PR #21 新增 2 个测试文件进一步加强了此覆盖）
3. **缺失测试**:
   | 组件 | 当前状态 | 影响 |
   |------|----------|------|
   | `PreconditionGrouper` | **无单元测试** | 前置条件分组逻辑未验证 |
   | `structure_assembler` 节点 | **无单元测试** | expected_results 挂载逻辑未验证 |
   | `text_normalizer` | **无单元测试** | 中英文归一化边界情况未验证 |
   | `workflow_service` | **无单元测试** | 编排逻辑仅通过集成测试覆盖 |
4. **Checklist 端到端质量断言缺失**: 单元测试各自验证组件正确性，但缺少跨组件的质量断言（如：给定特定 checkpoints，outline + 用例的整体质量是否达标）
5. **PR #21 测试改进**: 新增的 `test_attach_expected_results.py`（14 用例）和 `test_xmind_steps_rendering.py`（11 用例）显著增强了 checklist 挂载逻辑和 XMind steps 渲染的测试覆盖，部分缓解了上述 §5.3 中 `structure_assembler` 挂载逻辑未验证的问题
6. **建议**:
   - 优先为 `PreconditionGrouper` 和 `structure_assembler` 添加单元测试
   - 添加 checklist 整合的"快照测试"：固定输入 → 验证输出结构稳定性
   - 为 `checkpoint_outline_planner` 添加大规模输入（30+ checkpoints）的压力测试