# app/nodes/_ANALYSIS.md — 工作流节点分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `app/nodes/` |
| 文件数 | 13（含 `__init__.py`） |
| 分析文件 | 12（排除空 `__init__.py`） |
| 目录职责 | LangGraph 工作流节点层：每个文件导出 `build_*_node()` 工厂函数，封装单步业务逻辑 |
| 设计模式 | 工厂闭包模式 — 外层注入 LLMClient/Settings 依赖，返回 `async def node(state) → dict` |

## §2 文件清单

| # | 文件 | 工厂函数 | 使用LLM | 流水线位置 | 核心输出字段 |
|---|------|----------|---------|-----------|-------------|
| 1 | input_parser.py | build_input_parser_node | 否 | 主图·入口 | parsed_document |
| 2 | project_context_loader.py | build_project_context_loader_node | 否 | 主图·可选 | project_context |
| 3 | context_research.py | build_context_research_node | 是 | 主图 | research_facts, planned_scenarios |
| 4 | scenario_planner.py | build_scenario_planner_node | 否 | 子图·入口 | planned_scenarios (pass-through) |
| 5 | checkpoint_generator.py | build_checkpoint_generator_node | 是 | 子图 | checkpoints |
| 6 | checkpoint_evaluator.py | build_checkpoint_evaluator_node | 是 | 子图 | checkpoints (filtered/revised) |
| 7 | checklist_optimizer.py | build_checklist_optimizer_node | 是 | ⚠️ 未启用 | optimized_tree |
| 8 | checkpoint_outline_planner.py | build_checkpoint_outline_planner_node | 是 | 子图 | optimized_tree |
| 9 | evidence_mapper.py | build_evidence_mapper_node | 是 | 子图 | evidence_map |
| 10 | draft_writer.py | build_draft_writer_node | 是 | 子图 | test_cases |
| 11 | evaluation.py | build_evaluation_node | 否 | 主图·反思 | evaluation_report |
| 12 | reflection.py | build_reflection_node | 否 | 主图·反思 | final response |
| - | structure_assembler.py | build_structure_assembler_node | 否 | 子图·出口 | optimized_tree (final) |

## §3 逐文件分析

### §3.1 input_parser.py
- **类型**: B-流程编排
- **职责**: 解析原始 PRD 文本，通过 DocumentParser 生成 ParsedDocument
- **签名**: `build_input_parser_node(parser: DocumentParser) → Callable`
- **输入**: `state["prd_content"]`
- **输出**: `{"parsed_document": ParsedDocument}`
- **设计**: 纯转换节点，无 LLM 调用，无副作用

### §3.2 project_context_loader.py
- **类型**: B-流程编排
- **职责**: 从 SQLite 加载项目上下文（历史测试用例、项目特定规则）
- **签名**: `build_project_context_loader_node(service: ProjectContextService) → Callable`
- **条件执行**: 仅当 `state["project_id"]` 非空时触发
- **输出**: `{"project_context": ProjectContext | None}`

### §3.3 context_research.py
- **类型**: A-核心算法 + C-LLM集成
- **职责**: LLM 驱动的上下文研究，从 PRD 章节提取 ResearchFact 和 PlannedScenario
- **LLM 策略**: 使用 `generate_structured()` + `ResearchOutput` schema，逐章节调用
- **输入**: `parsed_document.sections`
- **输出**: `{"research_facts": list[ResearchFact], "planned_scenarios": list[PlannedScenario]}`
- **防御设计**: ResearchOutput 的 model_validator 处理 LLM 输出的 str→list 畸变

### §3.4 scenario_planner.py
- **类型**: B-流程编排
- **职责**: 分发 PlannedScenario，当前为直接透传
- **现状**: pass-through 实现，预留为未来场景拆分/优先级排序扩展点

### §3.5 checkpoint_generator.py
- **类型**: A-核心算法 + C-LLM集成
- **职责**: LLM 将 ResearchFact 转换为 Checkpoint
- **核心逻辑**:
  - 使用 CheckpointDraft 中间模型接收 LLM 输出
  - 前置条件 str→list 强制转换（应对 LLM 输出不一致）
  - SHA-256 稳定 ID 生成：`hash(title + description + test_objective)`
- **输出**: `{"checkpoints": list[Checkpoint]}`

### §3.6 checkpoint_evaluator.py
- **类型**: A-核心算法 + C-LLM集成
- **职责**: LLM 评估 checkpoint 质量，可请求重新生成
- **评估维度**: 完整性、可测试性、非冗余性
- **输出**: 过滤/修订后的 checkpoints

### §3.7 checklist_optimizer.py ⚠️
- **类型**: A-核心算法 + C-LLM集成
- **状态**: **已弃用 — 未纳入当前子图流水线**
- **原始设计**: `SemanticPathNormalizer.normalize()` → `ChecklistMerger.merge()`
  - Phase 1: LLM 两阶段路径归一化
  - Phase 2: Trie 树合并为 ChecklistNode 层级
- **被替代原因**: 路径归一化质量不稳定，trie 合并产生不合理层级
- **容错设计**: 异常时返回空 `optimized_tree`，不阻断流水线
- **保留价值**: 两阶段归一化思路值得在改进方案中复用

### §3.8 checkpoint_outline_planner.py（节点）
- **类型**: A-核心算法 + C-LLM集成
- **职责**: 调用 CheckpointOutlinePlanner 服务，从 checkpoints 创建 CanonicalOutlineNode 树
- **核心流程**:
  1. 收集所有 checkpoint 标题 → 输入 LLM
  2. LLM 生成层级 outline JSON
  3. 解析为 CanonicalOutlineNode 树
- **输出**: `{"optimized_tree": list[ChecklistNode]}`（通过 attach 转换）

### §3.9 evidence_mapper.py
- **类型**: A-核心算法 + C-LLM集成
- **职责**: LLM 将 research_facts 中的证据映射到对应 checkpoint
- **输出**: `{"evidence_map": list[EvidenceRef]}`

### §3.10 draft_writer.py ⭐
- **类型**: A-核心算法 + C-LLM集成
- **职责**: LLM 基于 checkpoint + evidence 生成 TestCase
- **关键特性**:
  - **_SYSTEM_PROMPT** 包含 5 条前置条件编写规则：
    1. 归一化：统一措辞格式
    2. 层级性：体现测试场景的层级关系
    3. 原子性：每条前置条件只描述一个状态
    4. 充分性：覆盖测试执行所需全部前提
    5. 复用感知：相似前置条件使用一致表述
  - **_resolve_path_context()**: 从 optimized_tree 提取层级路径注入 prompt
- **Checklist 整合关键点**: 此处是 outline 结构影响测试用例生成的核心节点

### §3.11 evaluation.py
- **类型**: A-核心算法
- **职责**: 6 维度评估测试用例集质量
- **评估维度**:
  | 维度 | 权重 | 说明 |
  |------|------|------|
  | fact_coverage | 高 | 研究事实覆盖率 |
  | checkpoint_coverage | 高 | 检查点覆盖率 |
  | evidence_completeness | 中 | 证据引用完整度 |
  | duplicate_rate | 中 | 重复率（越低越好） |
  | case_completeness | 中 | 用例字段完整度 |
  | branch_coverage | 低 | 分支覆盖率 |
- **输出**: `EvaluationReport(overall_score, pass_)`

### §3.12 reflection.py
- **类型**: A-核心算法
- **职责**: 最终反思节点 — 去重、质量检查、构建最终响应
- **去重策略**: 基于 `checkpoint_id` 去重，保留首条
- **覆盖计算**: `covered_checkpoints / total_checkpoints`
- **输出**: 构建 `CaseGenerationResponse` 返回给 API 层

### §3.13 structure_assembler.py
- **类型**: B-流程编排
- **职责**: 调用 `attach_expected_results_to_outline()` 将 expected_results 挂载到 outline 叶节点
- **角色**: 被动组装，不做智能整合

## §4 节点流水线

### 主图流水线
```
START → input_parser → [project_context_loader] → context_research → case_generation_subgraph → reflection → END
```

### 子图流水线（case_generation）
```
scenario_planner → checkpoint_generator → checkpoint_evaluator → checkpoint_outline_planner → evidence_mapper → draft_writer → structure_assembler
```

### 数据流关键路径
```
PRD文本 → ParsedDocument → ResearchFact[] → Checkpoint[] → CanonicalOutlineNode[] → ChecklistNode[] → TestCase[] → CaseGenerationResponse
```

## §5 补充观察 — Checklist 整合深度分析

> **用户重点关注**: 此部分是分析的核心焦点。

### §5.1 当前 Checklist 整合架构全景

Checklist 整合涉及 4 个节点的协作链：

```
checkpoint_outline_planner → evidence_mapper → draft_writer → structure_assembler
         ↓                                          ↓                    ↓
  CanonicalOutlineNode树              路径上下文注入(prompt)        挂载expected_results
         ↓                                          ↓                    ↓
   optimized_tree                          TestCase生成            最终ChecklistNode树
```

### §5.2 checklist_optimizer 被架空的影响分析

`build_checklist_optimizer_node()` 虽然代码完整但未接入子图，这意味着：

1. **SemanticPathNormalizer 的两阶段归一化能力被闲置**
   - Phase 1（路径提取）和 Phase 2（LLM 归一化）的设计思路正确
   - 问题在于执行层面：LLM 输出格式不稳定，缺乏 few-shot 约束
   
2. **ChecklistMerger 的 Trie 树合并被放弃**
   - Trie 合并是确定性算法，可重复性好
   - 问题在于路径归一化质量不足导致树结构不合理（过深/过浅/同义重复）

3. **被 checkpoint_outline_planner 替代的权衡**
   - 优势：LLM 一次性规划更灵活，可理解语义关系
   - 劣势：丧失了确定性，输出不可重复，大量 checkpoint 时质量下降

### §5.3 checkpoint_outline_planner 的局限性

1. **单次 LLM 调用的规模瓶颈**
   - 输入：所有 checkpoint 标题（约 20-50 个，每个 50-100 字）
   - Token 估算：输入 2000-5000 tokens + 系统提示 ~1000 tokens
   - 当 checkpoint 超过 30 个时，LLM 层级规划质量显著下降
   
2. **缺乏 PRD 结构锚定**
   - 当前仅输入 checkpoint 标题，不包含 PRD 原文章节结构
   - LLM 需要"凭空"创建层级，缺乏领域锚点
   
3. **结构化输出脆弱性**
   - 依赖 LLM 生成合法 JSON 树结构
   - 嵌套深度不可控，可能产生单子节点长链

4. **无质量验证环节**
   - outline 生成后直接进入下游，没有类似 checkpoint_evaluator 的验证节点

### §5.4 draft_writer 路径注入机制分析

`_resolve_path_context()` 将 `optimized_tree` 层级路径注入 LLM prompt：

- **优势**: 为 LLM 提供结构化上下文，指导前置条件和用例组织
- **风险 1**: 路径上下文过长 → prompt 膨胀 → 挤压生成空间
- **风险 2**: 固定路径 → 限制 LLM 对边界场景的创造性组织
- **风险 3**: 路径查找失败时（checkpoint 未匹配到 outline 节点）→ 降级为无上下文生成，质量断崖

### §5.5 structure_assembler 的被动角色

- 仅执行 `attach_expected_results_to_outline()` → 字符串匹配挂载
- 不做任何智能整合（不合并相似 expected_results，不检测遗漏）
- 是质量损失链中的"透明管道"

### §5.6 端到端质量损失链

```
checkpoint_outline_planner  →  evidence_mapper  →  draft_writer  →  structure_assembler
       [高风险]                   [中风险]            [中风险]           [低风险]
  · 层级不合理                · 证据错配           · 路径注入失效        · 挂载遗漏
  · 同义节点重复              · 遗漏映射           · 前置条件不一致      · 顺序混乱
  · 单子链过深                                     · 生成质量波动
```

### §5.7 改进建议

#### 短期（1-2 周）
1. **PRD 章节锚定**: 将 PRD 一级/二级标题作为 outline 顶层骨架，LLM 仅规划叶级分组
2. **分批规划**: 按 PlannedScenario 分组 checkpoint，每组独立 LLM 规划，最后合并
3. **增加 outline 验证**: 复用 checkpoint_evaluator 模式，对 outline 做完整性/合理性检查

#### 中期（2-4 周）
4. **混合方案**: 恢复 SemanticPathNormalizer 做预处理 + CheckpointOutlinePlanner 做精调
5. **PreconditionGrouper 语义升级**: 用 embedding 相似度替代关键词匹配
6. **双向验证**: outline 生成后反向验证每个 checkpoint 的归属正确性

#### 长期（1-2 月）
7. **多轮迭代 outline**: 参照 case generation 迭代循环，outline 也做多轮评估优化
8. **结构化模板库**: 构建常见测试场景的标准分类模板，作为 LLM 规划参考
9. **用户反馈闭环**: 记录人工对 outline 的修改历史，作为未来规划的微调信号
