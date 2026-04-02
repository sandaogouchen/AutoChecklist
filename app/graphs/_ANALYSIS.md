# app/graphs/_ANALYSIS.md — 工作流图定义分析
> 分析分支自动生成 · 源分支 `main`
---
## §1 目录概述
| 维度 | 值 |
|------|-----|
| 路径 | `app/graphs/` |
| 文件数 | 3（含 `__init__.py`） |
| 分析文件 | 2 |
| 目录职责 | LangGraph 状态图定义：主工作流与用例生成子图的编排 |
## §2 文件清单
| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | `__init__.py` | - | 0 | 空 |
| 2 | `case_generation.py` | B-流程编排 | ~60 | 用例生成子图：7 节点线性流水线 |
| 3 | `main_workflow.py` | B-流程编排 | ~80 | 主工作流：4 节点 + 子图桥接 |
## §3 逐文件分析
### §3.1 case_generation.py
- **职责**: 构建 `StateGraph[CaseGenState]` 子图
- **拓扑**: `scenario_planner → checkpoint_generator → checkpoint_evaluator → checkpoint_outline_planner → evidence_mapper → draft_writer → structure_assembler`
- **设计选择 — 线性流水线（无条件分支）**:
- 优势：执行路径可预测，调试友好，LangGraph checkpoint 完全兼容
- 局限：`checkpoint_evaluator` 发现质量不足时无法回环到 `checkpoint_generator` 重试
- 权衡：当前通过外层迭代循环（IterationController）补偿，而非子图内回环
- **节点注册**: 通过 `add_node()` 注册节点，`add_edge()` 顺序连接
- **状态类型**: `CaseGenState`（TypedDict），包含 `checkpoints`、`optimized_tree`、`test_cases` 等字段
- **编译**: 调用 `.compile()` 生成可执行图，入口为 `scenario_planner`，出口为 `structure_assembler`
### §3.2 main_workflow.py
- **职责**: 构建 `StateGraph[GlobalState]` 主图
- **拓扑**: `input_parser → template_loader → [project_context_loader] → context_research → case_generation_bridge`
- **PR #23 变更**: 桥接节点新增 `mandatory_skeleton` 字段的传入与传出映射
- **关键机制 — `_build_case_generation_bridge()`**:
- 功能：将 `GlobalState` 字段映射到 `CaseGenState`，执行子图，回写结果
- 映射字段：`research_facts`, `planned_scenarios`, `checkpoints`, `optimized_tree`, `test_cases`, `evidence_map`, `template_leaf_targets`, `project_template`, **`mandatory_skeleton`** (PR #23)
- 回写重点：`optimized_tree` 需要从 `CaseGenState` 显式回写到 `GlobalState`
- 桥接原因：
1. 两个 TypedDict 类型域不同，LangGraph 不自动映射
2. `CaseGenState` 是子图的隔离执行空间
3. `optimized_tree` 在子图内生成，需要回传给主图的 `reflection` 节点
4. 显式桥接提高了可测试性（可独立测试子图）
- **PR #23 mandatory_skeleton 桥接**:
- 传入逻辑：`"mandatory_skeleton": state.get("mandatory_skeleton")` — 从 `GlobalState` 提取强制骨架树
- None 安全：桥接映射后执行 `{k: v for k, v in subgraph_input.items() if v is not None}` 清理，若模版无强制约束则字段自动省略
- 传出逻辑：骨架本身在子图内仅为只读输入，不回写（骨架在 template_loader 一次性构建后不变）
- 消费方：子图内 `checkpoint_outline_planner` 和 `structure_assembler` 通过 `state.get("mandatory_skeleton")` 各自读取
- 维护成本注意：每次 `CaseGenState` 新增字段，需同步更新此处桥接映射（观察 §4.1 仍然成立）
- **project_context_loader 条件执行**: 通过 `should_load_context()` 条件函数判断，仅当 `project_id` 存在时执行
- **编译**: 主图编译后通过 `WorkflowService` 的迭代循环执行
## §4 补充观察
1. **状态桥接的维护成本**: 每次 `CaseGenState` 新增字段都需同步更新桥接映射，遗漏将导致数据丢失。PR #23 新增 `mandatory_skeleton` 字段时已同步更新桥接，但手工维护仍有风险。建议考虑自动化映射或类型检查
2. **线性管道的扩展瓶颈**: 当前无法实现并行节点执行（如同时运行 evidence_mapper 和 outline_planner）。LangGraph 支持 fan-out/fan-in，但需要重构拓扑
3. **错误恢复缺失**: 子图内任一节点抛出异常将导致整个子图终止，无 fallback 路径。建议为关键节点添加 try-except 降级逻辑
4. **迭代循环位置**: 迭代评估（evaluate → retry）在主图外部通过 `IterationController` 实现，而非图内条件边。这简化了图结构但增加了编排复杂度
5. **未来优化方向**:
- Map-reduce 并行化：按 PlannedScenario 分组，每组独立执行子图，最后合并结果
- 子图内回环：为 `checkpoint_evaluator` → `checkpoint_generator` 添加条件回边
- 动态节点跳过：根据配置跳过可选节点（如 `checklist_optimizer`）
6. **PR #23 影响评估**:
- `_build_case_generation_bridge()` 新增 1 个传入字段（`mandatory_skeleton`），无传出字段变更
- 骨架为只读数据流：`GlobalState.mandatory_skeleton → 桥接传入 → CaseGenState.mandatory_skeleton → checkpoint_outline_planner / structure_assembler 读取`
- 与 template_leaf_targets / project_template 字段的桥接模式一致（单向传入，无回写），降低了桥接维护复杂度
- 未来若骨架需要在子图内变异（如动态增删强制节点），需增加传出映射
## §5 PR #24 变更 — 知识检索节点接入

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

PR #24 修改了 `main_workflow.py`，将知识检索节点动态插入工作流拓扑。

### build_workflow 签名变更

```
# 修改前
build_workflow(llm_client, project_context_loader=None)

# 修改后
build_workflow(llm_client, project_context_loader=None, knowledge_retrieval_node=None)
```

新增可选参数 `knowledge_retrieval_node`：当不为 `None` 时，以名称 `"knowledge_retrieval"` 注册到工作流图中。

### 拓扑变更 — 动态 `prev_node` 链式连接

```python
prev_node = "template_loader"

if project_context_loader is not None:
    builder.add_edge(prev_node, "project_context_loader")
    prev_node = "project_context_loader"

if knowledge_retrieval_node is not None:
    builder.add_edge(prev_node, "knowledge_retrieval")
    prev_node = "knowledge_retrieval"

builder.add_edge(prev_node, "context_research")
```

通过 `prev_node` 变量实现灵活的节点链式连接，支持以下拓扑组合：

| project_context_loader | knowledge_retrieval | 实际拓扑 |
|------------------------|---------------------|--------|
| None | None | template_loader → context_research |
| 有 | None | template_loader → project_context_loader → context_research |
| None | 有 | template_loader → knowledge_retrieval → context_research |
| 有 | 有 | template_loader → project_context_loader → knowledge_retrieval → context_research |

### 状态桥接

桥接函数中新增知识检索字段映射（GlobalState → CaseGenState 方向暂不涉及，知识上下文在主图消费）。

### 设计评价

1. **零侵入**: 当 `knowledge_retrieval_node=None` 时，工作流拓扑与 PR #24 前完全一致
2. **`prev_node` 模式优雅**: 相比硬编码 if/else 组合拓扑，链式变量追踪更具扩展性——后续新增节点只需追加同样的三行代码
3. **维护成本**: 与 `project_context_loader` 共享同一模式，维护一致性好

## §6 PR #36 变更 — MR 分析节点接入工作流

> 同步自 PR #36 `feat/mr-code-analysis-integration`

PR #36 修改了 `case_generation.py` 和 `main_workflow.py`，将 MR 分析的 3 个新节点接入工作流拓扑。

### §6.1 修改文件：case_generation.py

**变更：** 子图拓扑新增 3 个条件节点。

**更新后的拓扑：**

```
scenario_planner → checkpoint_generator → checkpoint_evaluator →
  [mr_analyzer] → [mr_checkpoint_injector] →
  checkpoint_outline_planner → evidence_mapper → draft_writer →
  structure_assembler → [coco_consistency_validator]
```

**条件节点接入方式：**

```python
# mr_analyzer 和 mr_checkpoint_injector 插入在 checkpoint_evaluator 之后
if mr_analyzer_node is not None:
    builder.add_edge("checkpoint_evaluator", "mr_analyzer")
    builder.add_edge("mr_analyzer", "mr_checkpoint_injector")
    builder.add_edge("mr_checkpoint_injector", "checkpoint_outline_planner")
else:
    builder.add_edge("checkpoint_evaluator", "checkpoint_outline_planner")

# coco_consistency_validator 追加在 structure_assembler 之后
if coco_validator_node is not None:
    builder.add_edge("structure_assembler", "coco_consistency_validator")
    # coco_consistency_validator 成为新的子图出口
```

**拓扑组合矩阵：**

| MR 节点 | Coco 节点 | 实际拓扑 |
|---------|-----------|---------|
| 无 | 无 | 原有 7 节点线性流水线（完全向后兼容） |
| 有 | 无 | checkpoint_evaluator → mr_analyzer → mr_checkpoint_injector → checkpoint_outline_planner ... |
| 无 | 有 | ... → structure_assembler → coco_consistency_validator |
| 有 | 有 | 完整 10 节点流水线 |

**设计说明：**
- 采用与 PR #24 `knowledge_retrieval_node` 相同的可选节点注入模式
- `mr_analyzer` 和 `mr_checkpoint_injector` 作为一组插入（MR 分析必然伴随 checkpoint 注入）
- `coco_consistency_validator` 独立插入，支持无 MR 场景下的独立一致性验证（理论可扩展）
- 子图出口动态调整：有 coco 节点时出口为 `coco_consistency_validator`，否则为 `structure_assembler`

### §6.2 修改文件：main_workflow.py

**变更：** 桥接函数新增 MR 分析字段的传入与传出映射。

**新增桥接字段：**

| 字段 | 方向 | 说明 |
|------|------|------|
| `mr_analysis_result` | GlobalState → CaseGenState | MR 分析结果传入子图 |
| `mr_code_facts` | GlobalState ↔ CaseGenState | 双向：初始传入 + 子图内补充后回写 |
| `code_consistency_checks` | CaseGenState → GlobalState | 一致性校验结果回传主图 |

**`_build_case_generation_bridge()` 更新：**
- 传入映射：增加 `mr_analysis_result`、`mr_code_facts` 两个字段的 `state.get()` 提取
- 传出映射：增加 `mr_code_facts`（可能在子图内被 agentic search 补充）和 `code_consistency_checks` 的回写
- None 安全：与 `mandatory_skeleton` 字段一致，使用 `{k: v for k, v in ... if v is not None}` 清理

**`build_workflow()` 签名变更：**

```python
# 修改前
build_workflow(llm_client, project_context_loader=None, knowledge_retrieval_node=None)

# 修改后
build_workflow(llm_client, project_context_loader=None, knowledge_retrieval_node=None,
               mr_analyzer_node=None, mr_checkpoint_injector_node=None,
               coco_validator_node=None)
```

**设计评价：**
1. **参数膨胀**：`build_workflow` 已有 6 个参数（含 self），可选节点参数持续增长。建议后续重构为 `WorkflowConfig` 配置对象
2. **桥接维护成本**：新增 3 个字段映射，手动维护成本进一步增加。技术债务 #8（状态桥接手动维护）的影响加深
3. **双向映射**：`mr_code_facts` 是首个需要双向映射的字段（传入 + 回写），增加了桥接的复杂度。此前 `mandatory_skeleton` 为单向传入，`optimized_tree` 和 `test_cases` 为单向传出