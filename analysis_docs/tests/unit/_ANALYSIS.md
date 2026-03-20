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
| 23 | `test_attach_expected_results.py` | `services/checkpoint_outline_planner.attach_expected_results_to_outline` | ✅ |
| 24 | `test_xmind_steps_rendering.py` | `services/xmind_payload_builder` (steps 渲染) | ✅ |
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

### §3.7 test_attach_expected_results.py（新增）
- **测试范围**: `checkpoint_outline_planner.attach_expected_results_to_outline()` 函数的完整行为
- **测试文件**: `tests/unit/test_attach_expected_results.py`（368 行）
- **关键测试类与用例**:

| 测试类 | 场景 | 关键断言 |
|--------|------|----------|
| `TestSingleMatch` | 单 checkpoint 映射单 TestCase | steps/preconditions/expected_results/priority/category/test_case_ref/evidence_refs 全部正确填充；返回节点是原始对象（in-place 修改） |
| `TestEmptyTree` | 空 `optimized_tree` | 返回空列表；返回值为同一引用 |
| `TestEmptyTestCases` | 空 `test_cases` 列表 | 树原样返回；case 节点字段保持默认值（空字符串） |
| `TestNoMatchingCheckpoint` | checkpoint_id 无匹配 TestCase | 节点字段保持默认值，不抛异常 |
| `TestMultipleTestCasesSameCheckpoint` | 多 TestCase 映射同一 checkpoint_id | 第一个 TC 合并到原始节点；后续 TC 创建 sibling case 节点；sibling ID 格式为 `{node.id}__tc__{tc.id}`；各 sibling 独立持有正确的 steps/priority/test_case_ref |
| `TestNestedTree` | 深层嵌套树（group → group → case） | 叶节点被正确 enrich；不同深度的 case 节点各自独立填充；嵌套 group 内的多 TC 正确创建 sibling |
| `TestLegacyExpectedResultNodes` | group 节点持有 checkpoint_id | 创建 `expected_result` 类型的子节点（Legacy 兼容路径） |
| `TestGracefulDegradation` | 异常输入（非标准 TestCase 对象） | 不抛异常，返回非 None 的树（graceful degradation） |

- **测试设计特点**:
  - 使用工厂函数 `_make_case_node()` / `_make_group_node()` / `_make_test_case()` 构建测试数据
  - 覆盖了正常路径、边界条件（空输入）、多对一映射、深层嵌套、Legacy 兼容和异常容错 6 个维度
  - 验证了 in-place 修改语义（`result[0] is case_node`）
- **Checklist 关联**: 直接验证了 `attach_expected_results_to_outline()` 重构后的完整 TestCase 数据挂载逻辑，包括 sibling 节点创建和 graceful degradation

### §3.8 test_xmind_steps_rendering.py（新增）
- **测试范围**: `XMindPayloadBuilder` 对 `ChecklistNode.steps` 字段的渲染行为
- **测试文件**: `tests/unit/test_xmind_steps_rendering.py`（311 行）
- **关键测试类与用例**:

| 测试类 | 场景 | 关键断言 |
|--------|------|----------|
| `TestCaseNodeWithSteps` | case 节点有非空 steps | XMindNode 包含"步骤"子节点；子节点数量与 steps 行数一致；各行文本正确；单行 steps 也生成子节点；空行被过滤 |
| `TestCaseNodeWithoutSteps` | case 节点 steps 为空/纯空白 | 无"步骤"子节点；空字符串、纯空白、默认值三种情况均验证 |
| `TestTreeModeRendering` | group → case 完整层级渲染 | XMind 树结构镜像 ChecklistNode 层级；case 子节点包含"步骤"/"预期结果"/"优先级: P0"/"类型: 功能测试"等；深层嵌套（group → group → case）正确渲染；同一 group 下有/无 steps 的 case 共存 |

- **辅助函数**:
  - `_child_titles(xnode)` — 返回所有直接子节点的标题列表
  - `_find_child(xnode, title)` — 按标题查找直接子节点
- **测试设计特点**:
  - 覆盖了 steps 渲染的正向（有 steps）和反向（无 steps）两个方向
  - 验证了空行过滤逻辑（`"步骤A\n\n\n步骤B\n"` → 2 个子节点）
  - 验证了完整的 XMind 树层级结构：group 标题 → case 标题 → 步骤/预期结果/优先级/类型
  - 深层嵌套测试确保递归渲染的正确性
- **Checklist 关联**: 验证了 `ChecklistNode.steps` 字段在 XMind 输出中的正确渲染，确保 `attach_expected_results_to_outline()` 挂载的 steps 数据能在最终 XMind 文件中正确呈现

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
2. **Checklist 测试比重高**: 8/24 (33%) 的测试文件直接涉及 checklist 整合，反映了这是开发重点和痛点
3. **⚠️ 缺失测试**:
| 组件 | 当前状态 | 影响 |
|------|----------|------|
| `PreconditionGrouper` | **无单元测试** | 前置条件分组逻辑未验证 |
| `structure_assembler` 节点 | **部分覆盖**（`test_attach_expected_results.py` 覆盖了核心挂载函数） | expected_results 挂载逻辑已有验证；节点级集成行为仍未覆盖 |
| `text_normalizer` | **无单元测试** | 中英文归一化边界情况未验证 |
| `workflow_service` | **无单元测试** | 编排逻辑仅通过集成测试覆盖 |
4. **Checklist 端到端质量断言缺失**: 单元测试各自验证组件正确性，但缺少跨组件的质量断言（如：给定特定 checkpoints，outline + 用例的整体质量是否达标）
5. **新增测试填补关键空白**: `test_attach_expected_results.py` 和 `test_xmind_steps_rendering.py` 的加入填补了 `attach_expected_results_to_outline()` 重构后的测试空白，并验证了 steps 数据从挂载到 XMind 渲染的端到端正确性
6. **建议**:
- 优先为 `PreconditionGrouper` 添加单元测试
- 为 `structure_assembler` 节点添加完整的节点级集成测试（超出 `attach_expected_results_to_outline` 函数本身）
- 添加 checklist 整合的"快照测试"：固定输入 → 验证输出结构稳定性
- 为 `checkpoint_outline_planner` 添加大规模输入（30+ checkpoints）的压力测试
