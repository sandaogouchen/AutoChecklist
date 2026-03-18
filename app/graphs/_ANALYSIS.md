# app/graphs/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 3 | 分析策略: 业务逻辑 (business logic)

## §1 目录职责

`app/graphs/` 是 AutoChecklist 系统的**工作流编排层**，负责使用 LangGraph 框架定义、组装和编译整个测试用例生成的有向无环图（DAG）。该目录包含两级图结构：

1. **主工作流图** (`main_workflow.py`)：定义端到端的顶层处理流水线，从文档输入到最终用例输出。
2. **用例生成子图** (`case_generation.py`)：定义 case_generation 阶段内部的 6 节点线性流水线，专注于从研究结果到结构化测试用例的转化。

两级图通过**桥接节点模式** (`_build_case_generation_bridge`) 实现 `GlobalState` 与 `CaseGenState` 之间的状态映射与解耦。

## §2 文件清单

| 文件名 | 行数 | 主要职责 | 分析策略 |
|---|---|---|---|
| `__init__.py` | 1 | 包声明，标识 `app.graphs` 为 Python 子包 | — |
| `case_generation.py` | 66 | 构建 6 节点用例生成子图 (`CaseGenState`) | 业务逻辑 |
| `main_workflow.py` | 94 | 构建主工作流图 (`GlobalState`)，含条件节点和状态桥接 | 业务逻辑 |

## §3 文件详细分析

### §3.1 `__init__.py`

- **路径**: `app/graphs/__init__.py`
- **行数**: 1
- **职责**: 包初始化声明，文档字符串为 `"""LangGraph 工作流图子包。"""`

#### §3.1.1 核心内容

仅包含模块级文档字符串，无导出符号。作为 Python 包标识文件存在。

#### §3.1.2 依赖关系

无依赖。

#### §3.1.3 关键逻辑 / 数据流

无运行时逻辑。

---

### §3.2 `case_generation.py`

- **路径**: `app/graphs/case_generation.py`
- **行数**: 66
- **职责**: 构建并编译用例生成子图，将 6 个处理节点串联为线性流水线

#### §3.2.1 核心内容

**唯一公开函数**: `build_case_generation_subgraph(llm_client: LLMClient)`

构建基于 `CaseGenState` 的 `StateGraph`，包含以下 6 个节点的线性链：

```
START → scenario_planner → checkpoint_generator → checkpoint_evaluator
      → evidence_mapper → draft_writer → structure_assembler → END
```

各节点职责：

| 节点名 | 来源模块 | 是否需要 LLM | 职责 |
|---|---|---|---|
| `scenario_planner` | `app.nodes.scenario_planner` | 否（直接引用） | 从研究输出中规划测试场景 |
| `checkpoint_generator` | `app.nodes.checkpoint_generator` | 是（`build_*` 工厂） | 将 facts 转化为显式 checkpoints |
| `checkpoint_evaluator` | `app.nodes.checkpoint_evaluator` | 否（直接引用） | 对 checkpoints 去重、归一化 |
| `evidence_mapper` | `app.nodes.evidence_mapper` | 否（直接引用） | 为场景匹配 PRD 文档证据 |
| `draft_writer` | `app.nodes.draft_writer` | 是（`build_*` 工厂） | 调用 LLM 生成测试用例草稿 |
| `structure_assembler` | `app.nodes.structure_assembler` | 否（直接引用） | 标准化用例结构，补全缺失字段 |

**节点注入模式**：需要 LLM 的节点通过 `build_*_node(llm_client)` 工厂闭包注入依赖，不需要 LLM 的节点直接使用函数引用。

#### §3.2.2 依赖关系

**内部依赖**:
- `app.clients.llm.LLMClient` — LLM 客户端抽象
- `app.domain.state.CaseGenState` — 子图状态类型定义
- `app.nodes.*` — 6 个节点的实现模块（scenario_planner, checkpoint_generator, checkpoint_evaluator, evidence_mapper, draft_writer, structure_assembler）

**外部依赖**:
- `langgraph.graph.StateGraph` — 图构建器
- `langgraph.graph.START`, `END` — 特殊节点标识

#### §3.2.3 关键逻辑 / 数据流

1. 实例化 `StateGraph(CaseGenState)` 构建器
2. 按顺序添加 6 个节点（`add_node`）
3. 按顺序添加 7 条边（`add_edge`）形成 `START → ... → END` 线性链
4. 调用 `builder.compile()` 返回可执行子图

**状态流转** (`CaseGenState` 字段在各节点间的传递):

```
CaseGenState 输入:
  language, parsed_document, research_output, project_context_summary
       │
  scenario_planner → 写入 planned_scenarios
       │
  checkpoint_generator → 写入 checkpoints
       │
  checkpoint_evaluator → 更新 checkpoints, 写入 checkpoint_coverage
       │
  evidence_mapper → 写入 mapped_evidence
       │
  draft_writer → 写入 draft_cases
       │
  structure_assembler → 写入 test_cases
```

---

### §3.3 `main_workflow.py`

- **路径**: `app/graphs/main_workflow.py`
- **行数**: 94
- **职责**: 构建主工作流图，编排端到端处理流程，桥接主图与子图的状态转换

#### §3.3.1 核心内容

**公开函数**: `build_workflow(llm_client: LLMClient, project_context_loader=None)`

构建基于 `GlobalState` 的主工作流图：

```
START → input_parser → [project_context_loader] → context_research → case_generation → reflection → END
```

其中 `[project_context_loader]` 为**条件节点**——仅当参数 `project_context_loader is not None` 时才插入图中。

**条件边逻辑**:
- 当 `project_context_loader` 存在时: `input_parser → project_context_loader → context_research`
- 当 `project_context_loader` 为 None 时: `input_parser → context_research`（跳过上下文加载）

**内部函数**: `_build_case_generation_bridge(case_generation_subgraph)`

这是一个**桥接工厂函数**，返回闭包 `case_generation_node(state: GlobalState) -> GlobalState`。桥接逻辑：

| 步骤 | 操作 | 说明 |
|---|---|---|
| 1 | GlobalState → CaseGenState 提取 | 从全局状态提取 `language`, `parsed_document`, `research_output`, `project_context_summary` 四个字段 |
| 2 | 子图调用 | `case_generation_subgraph.invoke(subgraph_input)` |
| 3 | CaseGenState → GlobalState 映射 | 将子图输出的 `planned_scenarios`, `checkpoints`, `checkpoint_coverage`, `mapped_evidence`, `draft_cases`, `test_cases` 映射回全局状态 |

**状态桥接字段映射**:

```
GlobalState (输入侧)              CaseGenState (子图内部)           GlobalState (输出侧)
─────────────────────             ───────────────────────           ─────────────────────
language                ──────►   language                          
parsed_document         ──────►   parsed_document                   
research_output         ──────►   research_output                   
project_context_summary ──────►   project_context_summary           
                                  planned_scenarios        ──────►  planned_scenarios
                                  checkpoints              ──────►  checkpoints
                                  checkpoint_coverage      ──────►  checkpoint_coverage
                                  mapped_evidence          ──────►  mapped_evidence
                                  draft_cases              ──────►  draft_cases
                                  test_cases               ──────►  test_cases
```

#### §3.3.2 依赖关系

**内部依赖**:
- `app.clients.llm.LLMClient` — LLM 客户端
- `app.domain.state.GlobalState` — 主图状态类型
- `app.graphs.case_generation.build_case_generation_subgraph` — 子图构建
- `app.nodes.input_parser.input_parser_node` — 输入解析节点
- `app.nodes.context_research.build_context_research_node` — 上下文研究节点（工厂）
- `app.nodes.reflection.reflection_node` — 反思/回顾节点

**外部依赖**:
- `langgraph.graph.StateGraph`, `START`, `END`

#### §3.3.3 关键逻辑 / 数据流

**完整图拓扑（含条件分支）**:

```
                          ┌─────────────────────────┐
                          │       GlobalState        │
                          └─────────────────────────┘
                                      │
                                   START
                                      │
                                      ▼
                              ┌───────────────┐
                              │  input_parser  │
                              └───────────────┘
                                      │
                          ┌───────────┴───────────┐
                          │                       │
              (loader存在时)▼           (loader为None)▼
        ┌──────────────────────┐              │
        │project_context_loader│              │
        └──────────────────────┘              │
                          │                   │
                          ▼                   ▼
                        ┌───────────────────────┐
                        │   context_research    │
                        └───────────────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │   case_generation     │  ← 桥接节点，内部调用子图
                        │  (bridge → subgraph)  │
                        └───────────────────────┘
                                    │
                                    ▼
                          ┌───────────────┐
                          │   reflection  │
                          └───────────────┘
                                    │
                                   END
```

**端到端 GlobalState 演进**:

1. `input_parser`: 读取原始输入 → 写入 `parsed_document`
2. `project_context_loader`（可选）: 加载项目上下文 → 写入 `project_context_summary`
3. `context_research`: 基于文档进行研究 → 写入 `research_output`
4. `case_generation`（桥接）: GlobalState ↔ CaseGenState 转换 → 写入 6 个用例相关字段
5. `reflection`: 对生成结果进行反思和改进 → 更新 `test_cases`

## §4 目录级依赖关系

```
app/graphs/
    │
    ├──► app/domain/state         (GlobalState, CaseGenState — 状态定义)
    ├──► app/clients/llm          (LLMClient — LLM 抽象层)
    ├──► app/nodes/*              (所有图节点的具体实现)
    │       ├── input_parser
    │       ├── context_research
    │       ├── scenario_planner
    │       ├── checkpoint_generator
    │       ├── checkpoint_evaluator
    │       ├── evidence_mapper
    │       ├── draft_writer
    │       ├── structure_assembler
    │       └── reflection
    └──► langgraph                (图构建与编排框架)
```

**依赖方向**: `graphs/` 是纯编排层，依赖 `domain/`（状态）、`nodes/`（逻辑）、`clients/`（基础设施），自身不被其他 `app/` 子包直接导入（由服务层或入口点调用）。

## §5 设计模式与架构特征

| 模式 | 应用位置 | 说明 |
|---|---|---|
| **子图嵌套** (Subgraph Composition) | `case_generation.py` + `main_workflow.py` | 将 6 节点用例生成逻辑封装为独立子图，通过桥接节点嵌入主图 |
| **状态桥接** (State Bridge) | `_build_case_generation_bridge()` | 闭包工厂实现 GlobalState ↔ CaseGenState 的双向映射，解耦两级状态结构 |
| **工厂闭包注入** (Factory Closure DI) | `build_*_node(llm_client)` | 需要 LLM 的节点通过工厂函数接收依赖，返回闭包作为节点函数 |
| **条件图构建** (Conditional Graph Assembly) | `build_workflow()` 中 `project_context_loader` 参数 | 构建时（非运行时）根据参数决定是否插入可选节点，属于静态条件编排 |
| **增量状态更新** (Incremental State Update) | 所有节点返回值 | 节点仅返回需要更新的字段字典，LangGraph 自动合并到全局状态 |
| **线性流水线** (Linear Pipeline) | 子图和主图均为线性 DAG | 无循环、无分支合并（除条件节点外），简化调试和推理 |

## §6 潜在关注点

1. **桥接字段硬编码**: `_build_case_generation_bridge` 中 GlobalState → CaseGenState 和反向映射的字段列表是硬编码的。若 `CaseGenState` 新增字段，必须同步更新桥接逻辑，否则数据会丢失。建议考虑基于状态 schema 的自动映射机制。

2. **条件节点的静态性**: `project_context_loader` 的存在与否在图构建时确定，而非运行时。这意味着同一编译后的图实例无法动态切换是否加载项目上下文，需要为不同配置构建不同的图实例。

3. **子图错误传播**: 桥接节点直接调用 `case_generation_subgraph.invoke()`，若子图内部某节点异常，错误将通过桥接函数冒泡到主图。当前缺少子图级别的错误处理或重试逻辑。

4. **状态字段默认值**: 桥接输入使用 `state.get("language", "zh-CN")` 和 `state.get("project_context_summary", "")` 提供默认值，而 `parsed_document` 和 `research_output` 则直接用 `state["key"]` 访问（无默认值）。若上游节点未正确设置这些字段，将在桥接处抛出 `KeyError`。

5. **子图编译时机**: `build_workflow()` 每次调用都会调用 `build_case_generation_subgraph(llm_client)` 创建并编译新的子图实例。在高频调用场景下可考虑子图实例的缓存复用。