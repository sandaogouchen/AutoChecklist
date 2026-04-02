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
| - | template_loader.py | build_template_loader_node | 否 | 主图·模版 | project_template, template_leaf_targets, mandatory_skeleton |
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
### §3.13 structure_assembler.py ⭐ (PR #23 大幅增强)
- **类型**: A-核心算法 + B-流程编排
- **职责**: 组装并标准化测试用例 + **强制约束最终防线** + source 标注
- **角色**: 从被动组装升级为主动约束执行者
**原有功能**（保留）:
- 遍历 draft 用例，补全 ID、列表字段、证据引用
- 从 checkpoint 继承模版绑定字段（兆底补全）
- 调用 `normalize_test_case()` 文本归一化
- 调用 `attach_expected_results_to_outline()` 挂载 expected_results
**PR #23 新增功能：**
| 新增函数 | 签名 | 说明 |
|----------|------|------|
| `_enforce_mandatory_constraints()` | `(tree, skeleton) → list[ChecklistNode]` | 强制约束最终防线 |
| `_restore_or_merge()` | `(sk_node, tree_lookup) → ChecklistNode` | 从树中查找或从骨架复原节点 |
| `_annotate_source()` | `(tree, skeleton) → None` | 为每个节点标注 source 字段 |
| `_set_source_recursive()` | `(node, skeleton_ids) → None` | 递归设置 source 标记 |
| `_collect_skeleton_ids()` | `(node) → set[str]` | 收集骨架所有节点 ID |
| `_index_tree()` | `(tree, lookup) → None` | 递归索引树节点 |
**`_enforce_mandatory_constraints()` — 最终防线策略：**
```
输入: optimized_tree (已挂载 expected_results) + mandatory_skeleton
│
├── 1. 收集骨架所有节点 ID → skeleton_ids
├── 2. 索引树所有节点 → tree_lookup
│
├── 3. 遍历骨架顶层子节点:
│ └── _restore_or_merge():
│ ├── 在 tree_lookup 中查找对应节点
│ ├── 递归处理子骨架节点 → merged_children
│ ├── 保留已有节点的非骨架子节点
│ └── 构建 ChecklistNode:
│ node_id = sk_node.id
│ title = sk_node.title
│ source = "template"
│ is_mandatory = sk_node.is_mandatory
│ priority = original_metadata["priority"]
│
├── 4. 收集非骨架的顶层节点 → overflow_cases
│ ├── 计算溢出比例 = overflow / total
│ ├── 比例 > 20%? → logger.warning 告警
│ └── 包装为 ChecklistNode:
│ node_id = "_overflow"
│ title = "待分配 (Overflow)"
│ source = "overflow"
│
└── 返回: 合并后的树
```
**`_annotate_source()` — 来源标注：**
- 骨架 ID 集合中的节点 → `source = "template"`, `is_mandatory = True`
- `_overflow` 节点 → `source = "overflow"`
- 其他节点 → 保留默认 `source = "generated"`
**溢出机制设计分析：**
- 阈值 20% 是经验值，含义是"如果超过 1/5 的节点无法匹配到模版骨架，说明模版与实际 PRD 的匹配度不足"
- 溢出节点不丢弃（收集到 `_overflow` 容器），确保信息不丢失
- `_overflow` 容器在 Markdown 渲染时标记为 `[待分配]`，在 XMind 中标记为红色旗标，引导人工分配
**与 checkpoint_outline_planner._enforce_mandatory_skeleton() 的关系：**
- `checkpoint_outline_planner` 是第一道防线（在 outline 规划阶段修复）
- `structure_assembler` 是最终防线（在用例组装阶段再次修复）
- 两道防线的逻辑相似但独立：即使 planner 的修复遗漏了某些情况，assembler 会兆底
- 设计意图：关键约束的"防御性深度"——宁可重复检查也不遗漏
### §3.14 template_loader.py（节点）(PR #23 增强)
- **类型**: B-流程编排
- **职责**: 从工作流状态中读取模版文件路径或名称，加载模版，构建强制骨架
- **签名**: `build_template_loader_node() → Callable`
- **条件执行**: 当 `template_file_path` 和 `template_name` 均为空时跳过
- **输出**: `{"project_template": ..., "template_leaf_targets": [...], "mandatory_skeleton": ...}`
**PR #23 变更：**
| 变更 | 说明 |
|------|------|
| 支持 `template_name` | 除了 `template_file_path`，新增从 `request.template_name` 读取模版名称 |
| 优先级 | `template_name` 优先于 `template_file_path`（通过 `loader.load_by_name()` 加载） |
| 骨架构建 | 加载模版后调用 `loader.build_mandatory_skeleton(template)` 构建强制骨架 |
| 条件输出 | `mandatory_skeleton` 仅在非 None 时写入状态（避免下游错误消费 None 值） |
**模版加载优先级链：**
```
1. state["template_name"] 非空? → loader.load_by_name(template_name)
2. state["template_file_path"] 非空? → loader.load(template_file_path)
3. 均为空 → 跳过（返回空 dict）
```
**骨架输出逻辑：**
```python
mandatory_skeleton = loader.build_mandatory_skeleton(template)
result = {"project_template": template, "template_leaf_targets": leaf_targets}
if mandatory_skeleton is not None:
    result["mandatory_skeleton"] = mandatory_skeleton
return result
```
**设计说明：**
- `mandatory_skeleton` 的条件写入是刻意的——`None` 值不写入状态，确保下游 `state.get("mandatory_skeleton")` 在无约束时返回 `None` 而非被显式设置为 `None`（两者在 LangGraph 的状态合并语义中可能有差异）
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
         ↓                         ↓                  ↓
CanonicalOutlineNode树       路径上下文注入(prompt)   挂载expected_results
         ↓                         ↓                  ↓
   optimized_tree            TestCase生成         最终ChecklistNode树
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
### §5.5 structure_assembler 的角色升级 (PR #23)
**PR #23 前**:
- 仅执行 `attach_expected_results_to_outline()` → 字符串匹配挂载
- 不做任何智能整合（不合并相似 expected_results，不检测遗漏）
- 是质量损失链中的"透明管道"
**PR #23 后**:
- 新增 `_enforce_mandatory_constraints()` — 强制约束最终防线
- 新增 `_annotate_source()` — 来源标注
- 新增溢出机制 — 未匹配节点收集到 `_overflow` 容器
- 从"透明管道"升级为"主动约束执行者"，是 Checklist 质量保证链的关键一环
### §5.6 端到端质量损失链
```
checkpoint_outline_planner → evidence_mapper → draft_writer → structure_assembler
  [中风险 ↓]                    [中风险]         [中风险]        [低风险]
  · 层级不合理                  · 证据错配       · 路径注入失效   · 挂载遗漏
  · 同义节点重复                · 遗漏映射       · 前置条件不一致 · 顺序混乱
  · 单子链过深                                   · 生成质量波动
                                                               PR #23 缓解:
  PR #23 缓解:                                                 · 最终防线修复
  · 强制骨架 prompt 注入                                        · source 标注
  · 后处理修复                                                  · 溢出告警
  · ↓ 风险从高降为中
```
### §5.7 改进建议
> **PR #23 进展**: 短期改进中的"建议 1: PRD 章节锚定"已通过强制模版骨架方式实现（变体）。详见 [services §5.6](../services/_ANALYSIS.md)。
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
## §6 PR #24 变更 — 知识检索节点

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

PR #24 新增 `knowledge_retrieval.py` 节点文件，并修改 `context_research.py` 以注入知识上下文。

### §6.1 新增文件：knowledge_retrieval.py

- **类型**: N-工作流节点
- **行数**: ~95
- **职责**: 工厂闭包模式构建知识检索节点，执行检索并将结果写入 GlobalState

#### 工厂函数

```python
def build_knowledge_retrieval_node(engine: GraphRAGEngine, settings: Settings):
    async def knowledge_retrieval(state: GlobalState) -> dict:
        ...
    return knowledge_retrieval
```

- 与项目中 `project_context_loader` 的工厂模式完全一致
- 闭包捕获 `engine` 和 `settings`，节点函数签名为 `(GlobalState) → dict`

#### 执行流程

1. 从 `state["parsed_document"]` 提取已解析的 PRD
2. 调用 `retrieve_knowledge(engine, parsed_document, mode=settings.knowledge_retrieval_mode)`
3. 返回 `{"knowledge_context": ..., "knowledge_sources": ..., "knowledge_retrieval_success": ...}`

#### 降级策略

- **核心原则**: 知识检索失败永远不阻塞主工作流
- `try/except Exception` 包裹全部检索逻辑
- 异常时返回 `{"knowledge_context": "", "knowledge_sources": [], "knowledge_retrieval_success": False}`
- 日志记录异常但不中断

### §6.2 修改文件：context_research.py

- **变更范围**: 知识上下文注入
- **注入方式**: 当 `state.get("knowledge_context")` 非空时，在 LLM prompt 中追加一段 `[Domain Knowledge Reference]` 段落

```python
knowledge_context = state.get("knowledge_context", "")
if knowledge_context:
    prompt += f"\n\n[Domain Knowledge Reference]\n{knowledge_context}"
```

- **设计评价**:
  1. 条件注入：知识上下文为空时无任何 prompt 变更，不影响 LLM 推理质量
  2. 标签明确：`[Domain Knowledge Reference]` 标签让 LLM 清楚区分知识上下文与 PRD 正文
  3. 注入位置合理：context_research 是检索阶段入口，知识上下文在此注入可影响后续所有场景规划


## §7 PR #36 变更 — MR 代码分析节点

> 同步自 PR #36 `feat/mr-code-analysis-integration`

PR #36 新增 3 个工作流节点文件，修改 4 个现有节点，为 MR 代码分析引入完整的节点层实现。

### §7.1 新增文件：mr_analyzer.py

| 属性 | 值 |
|---|---|
| **类型** | A-核心算法 + C-LLM集成 |
| **行数** | ~763 |
| **工厂函数** | `build_mr_analyzer_node(llm_client, settings, codebase_tools)` |
| **职责** | MR 代码分析核心节点——解析 MR diff、提取代码事实、执行 agentic search 补充上下文 |

**核心执行流程：**

```
MR URL/配置 → 获取 MR diff → 结构化解析 → LLM 代码事实提取 → Agentic Search 补充 → MRAnalysisResult
```

1. **diff 获取与解析**：从 MR URL 获取变更文件列表和 diff 内容，结构化为 `MRFileDiff[]`
2. **LLM 代码事实提取**：按文件分批调用 LLM，使用 `generate_structured()` + `MRCodeFact` schema 提取行为变更、API 变更等五类事实
3. **Agentic Search 循环**：对每个代码事实，通过 `codebase_tools` 执行多轮搜索（最多 3 轮），补充关联上下文（调用方、依赖链、配置影响）
4. **结果聚合**：合并所有代码事实和搜索补充，构建 `MRAnalysisResult`

**Agentic Search 机制：**

```
for code_fact in extracted_facts:
    search_context = ""
    for round in range(max_search_rounds=3):
        query = LLM.generate_search_query(code_fact, search_context)
        if query.should_stop:
            break
        results = codebase_tools.search(query)
        search_context += format_results(results)
    code_fact.evidence += search_context
```

- 每轮搜索由 LLM 自主决定查询内容和是否继续
- 搜索工具包括：`grep_codebase`、`find_references`、`read_file_range`、`search_symbol`、`list_directory`
- LLM 输出 `MRSearchQuery` 模型，包含 `should_stop: bool` 终止信号
- 最多 3 轮搜索，防止无限循环

**依赖关系：**
- 输入：`state["mr_analysis_result"]`（初始 MR 配置）或 `state` 中的 MR 配置字段
- 输出：`{"mr_analysis_result": MRAnalysisResult, "mr_code_facts": list[MRCodeFact]}`
- 外部依赖：`codebase_tools`（代码库搜索工具集）、`llm_client`、`settings`

**设计模式：**
- **Agentic Tool Use**：LLM 不仅提取事实，还自主规划搜索策略，体现了 agent 式的工具调用范式
- **渐进式上下文积累**：每轮搜索结果累积到 `search_context`，LLM 基于已有上下文决定下一步搜索方向
- **降级安全**：搜索失败时记录日志但不中断，保留已提取的事实

### §7.2 新增文件：mr_checkpoint_injector.py

| 属性 | 值 |
|---|---|
| **类型** | A-核心算法 + C-LLM集成 |
| **行数** | ~308 |
| **工厂函数** | `build_mr_checkpoint_injector_node(llm_client)` |
| **职责** | 将 MR 代码事实转换为 Checkpoint，注入现有 checkpoint 流水线 |

**核心执行流程：**

1. **事实分组**：按 `fact_type` 对 `MRCodeFact[]` 分组（behavior_change、api_change 等）
2. **LLM 转换**：每组事实调用 LLM 生成对应的 Checkpoint（使用 `generate_structured()` + Checkpoint schema）
3. **去重合并**：与现有 `state["checkpoints"]` 基于 SHA-256 ID 去重，MR 来源的 checkpoint 追加 `source_fact_ids` 中的 MRCodeFact ID
4. **标签注入**：MR 来源的 checkpoint 在 metadata 中标记 `{"source": "mr_analysis"}`

**输出：** `{"checkpoints": list[Checkpoint]}` — 合并后的完整 checkpoint 列表

**依赖关系：**
- 输入：`state["mr_code_facts"]`、`state["checkpoints"]`（已有的 PRD 来源 checkpoints）
- 输出：合并后的 `checkpoints`
- 复用：`Checkpoint` 的 SHA-256 ID 生成策略，确保相同内容的 checkpoint 自动去重

**设计模式：**
- **增量注入**：不替换现有 checkpoint，而是追加合并，保持 PRD 来源的 checkpoint 不变
- **fact_type 分组处理**：不同类型的代码事实使用不同的 prompt 策略（行为变更侧重功能测试，API 变更侧重接口契约测试）

### §7.3 新增文件：coco_consistency_validator.py

| 属性 | 值 |
|---|---|
| **类型** | A-核心算法 + C-外部服务集成 |
| **行数** | ~393 |
| **工厂函数** | `build_coco_consistency_validator_node(coco_client, llm_client)` |
| **职责** | Coco Task 2 代码一致性验证——将 checkpoint 与实际代码变更交叉验证 |

**核心执行流程：**

```
Checkpoint[] + MRCodeFact[] → Coco API 验证 → CodeConsistencyCheck[] → 回写到 Checkpoint/TestCase
```

1. **匹配对构建**：将每个 checkpoint 与其 `source_fact_ids` 关联的 `MRCodeFact` 配对
2. **Coco API 调用**：调用 `coco_client.validate_consistency()` 执行代码一致性校验
3. **三层验证**：Coco 响应经过 `coco_response_validator` 三层校验（schema 验证 → 业务规则验证 → 阈值验证）
4. **结果回写**：`CodeConsistencyCheck` 写入 `state["code_consistency_checks"]`

**输出：** `{"code_consistency_checks": list[CodeConsistencyCheck]}`

**依赖关系：**
- 输入：`state["checkpoints"]`、`state["mr_code_facts"]`
- 外部服务：`coco_client`（Coco API 客户端）
- 验证层：`coco_response_validator`（三层验证服务）

**设计模式：**
- **外部服务隔离**：Coco API 调用通过 `coco_client` 抽象，支持 mock 测试
- **三层验证防御**：schema → 业务规则 → 阈值，层层过滤，确保只有高置信度的一致性结果进入下游

### §7.4 修改文件：structure_assembler.py

**变更：** 新增 `# TODO: MR source annotation` 标记，预留 MR 来源节点的 source 标注扩展点。

**设计说明：**
- 当前 `_annotate_source()` 仅处理 `"template"` / `"generated"` / `"overflow"` 三种来源
- TODO 标记预示未来将增加 `"mr_derived"` 来源类型，标记由 MR 代码事实产生的检查清单节点

### §7.5 修改文件：scenario_planner.py

**变更：** 增强 MR 上下文注入——当 `state.get("mr_analysis_result")` 存在时，将 MR 摘要（受影响模块、风险评估）注入场景规划的上下文。

**设计说明：**
- 条件注入模式与 PR #24 的知识上下文注入一致
- MR 上下文帮助场景规划器理解代码变更范围，生成更有针对性的测试场景

### §7.6 修改文件：checkpoint_generator.py

**变更：** 当存在 `state["mr_code_facts"]` 时，将代码事实作为额外输入注入 LLM prompt，引导 checkpoint 生成覆盖代码变更相关的测试点。

**设计说明：**
- 与 `mr_checkpoint_injector` 形成互补：`checkpoint_generator` 在生成阶段感知 MR 上下文，`mr_checkpoint_injector` 在后处理阶段补充 MR 专属 checkpoint
- 双路径策略确保 MR 相关测试点既能通过 PRD+MR 联合推理产生，也能从纯代码事实独立推理产生

### §7.7 修改文件：draft_writer.py

**变更：** XMind 适配增强——当检测到 MR 来源的 checkpoint 时，在 `_resolve_path_context()` 中追加代码变更上下文，帮助 LLM 生成包含代码验证步骤的测试用例。

**设计说明：**
- 影响测试步骤的生成质量：MR 来源的 checkpoint 通常需要代码级验证步骤（如"验证 API 响应字段变更"），路径上下文中的代码变更信息帮助 LLM 生成更精确的步骤描述

### §7.8 节点流水线更新

**子图流水线（case_generation）新增 3 个节点：**

```
scenario_planner → checkpoint_generator → checkpoint_evaluator →
  [mr_analyzer] → [mr_checkpoint_injector] →
  checkpoint_outline_planner → evidence_mapper → draft_writer →
  structure_assembler → [coco_consistency_validator]
```

- `mr_analyzer`：在 checkpoint 生成后、outline 规划前执行 MR 分析
- `mr_checkpoint_injector`：紧随 mr_analyzer，将代码事实转换为 checkpoint 并合并
- `coco_consistency_validator`：在 structure_assembler 后执行一致性验证

**条件执行：** 三个新节点均为条件节点——仅当请求中包含 MR 配置时才执行，无 MR 配置时自动跳过，保持向后兼容。