# app/domain/_ANALYSIS.md — 领域模型分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 属性 | 值 |
|---|---|
| **路径** | `app/domain/` |
| **文件数量** | 11（1 `__init__.py` + 10 模型文件） |
| **角色描述** | 项目核心领域模型层，定义从 PRD 解析到测试用例生成全流程中所有数据结构。全部采用 Pydantic v2 模型（少数使用 `TypedDict`），负责数据校验、序列化和跨层通信的类型契约。 |
| **设计风格** | 纯数据模型，无业务逻辑（除 `model_validator` 中的防御性归一化）；贫血模型 + 管道式数据流 |

---

## §2 文件清单

| # | 文件 | 类型 | 预估行数 | 摘要 |
|---|---|---|---|---|
| 1 | `__init__.py` | 包初始化 | ~0 | 空文件，标记 `domain` 为 Python 包 |
| 2 | `api_models.py` | A-model | ~60 | API 层请求/响应模型：`CaseGenerationRequest`、`CaseGenerationResponse`、`IterationSummary` |
| 3 | `case_models.py` | A-model | ~80 | 测试用例核心模型：`TestCase`（含 checkpoint 关联与 evidence 引用）、`QualityReport` |
| 4 | `checklist_models.py` | A-model | ~150 | **关键文件**：检查清单树结构 `ChecklistNode`（五种 node_type）、规范化大纲树 `CanonicalOutlineNode`、路径映射模型 |
| 5 | `checkpoint_models.py` | A-model | ~100 | 检查点模型 `Checkpoint`，使用 SHA-256 生成确定性 ID，关联 source facts |
| 6 | `document_models.py` | A-model | ~50 | 文档解析结果：`ParsedDocument`、`DocumentSection` |
| 7 | `project_models.py` | A-model | ~60 | 项目上下文 CRUD 模型：`ProjectContext`、`ProjectContextCreate`、`ProjectContextUpdate` |
| 8 | `research_models.py` | A-model | ~120 | 研究阶段产出：`EvidenceRef`、`ResearchFact`、`PlannedScenario`、`ResearchOutput`，含 LLM 输出归一化验证器 |
| 9 | `run_state.py` | A-model | ~100 | 运行状态与评估：`RunState`、`EvaluationReport`、`EvaluationDimension`、`RetryDecision`、`IterationRecord` |
| 10 | `state.py` | A-model (TypedDict) | ~40 | 全局状态容器：`GlobalState(TypedDict)` 含 `optimized_tree`、`CaseGenState(TypedDict)` 用于子图 |
| 11 | `xmind_models.py` | A-model | ~40 | XMind 导出专用树结构：`XMindTopic` |

---

## §3 逐文件分析

### §3.1 `__init__.py`

| 属性 | 值 |
|---|---|
| **类型** | 包初始化 |
| **职责** | 标记 `app/domain/` 为 Python 包 |
| **内容** | 空文件 |

无导入、无 re-export。各消费模块直接 `from app.domain.xxx_models import ...` 引用具体模型。

---

### §3.2 `api_models.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（API 边界模型） |
| **职责** | 定义 HTTP API 请求体与响应体的数据契约 |

**关键类与签名：**

```python
class CaseGenerationRequest(BaseModel):
    prd_content: str                  # PRD 原文内容
    project_id: str | None = None     # 可选项目 ID，用于关联上下文
    output_format: str | None = None  # 可选输出格式指定

class IterationSummary(BaseModel):
    iteration: int                    # 迭代轮次编号
    score: float                      # 本轮评估得分
    passed: bool                      # 是否通过质量门槛
    # ... 其他摘要字段

class CaseGenerationResponse(BaseModel):
    # 包含最终生成结果与各轮迭代摘要
    iterations: list[IterationSummary]
    # ... 最终用例数据、状态等
```

**依赖关系：**
- 内部：可能引用 `case_models.TestCase`（作为响应载荷的一部分）
- 外部：`pydantic.BaseModel`

**设计说明：**
- `project_id` 和 `output_format` 均为可选参数，体现"渐进增强"的 API 设计——最简调用仅需 PRD 原文
- `IterationSummary` 将迭代式质量优化过程暴露给调用方，支持前端展示优化轨迹

---

### §3.3 `case_models.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（核心业务模型） |
| **职责** | 定义最终输出的测试用例结构与质量报告 |

**关键类与签名：**

```python
class TestCase(BaseModel):
    id: str                           # 用例唯一标识
    title: str                        # 用例标题
    preconditions: list[str]          # 前置条件列表
    steps: list[str]                  # 测试步骤
    expected_results: list[str]       # 预期结果
    priority: str                     # 优先级（如 P0/P1/P2）
    checkpoint_id: str                # 关联的 Checkpoint ID（可溯源）
    evidence_refs: list[...]          # 证据引用列表，链接回 ResearchFact

class QualityReport(BaseModel):
    # 用例集整体质量评估报告
    # ... 覆盖率、重复率、缺陷分布等维度
```

**依赖关系：**
- 内部：`checkpoint_id` → `checkpoint_models.Checkpoint.id`；`evidence_refs` → `research_models.EvidenceRef`
- 外部：`pydantic.BaseModel`

**设计模式：**
- **可溯源设计**：每个 `TestCase` 通过 `checkpoint_id` 和 `evidence_refs` 可以回溯到产生它的检查点和原始研究事实，形成完整的生成链路审计
- `steps` / `expected_results` / `preconditions` 均为 `list[str]`，适合结构化展示与逐条比对

---

### §3.4 `checklist_models.py` ★ 关键文件

| 属性 | 值 |
|---|---|
| **类型** | A-model（核心树结构模型） |
| **职责** | 定义检查清单的多叉树结构与规范化大纲树，是连接 checkpoint 层与用例生成层的枢纽 |

**关键类与签名：**

```python
class ChecklistNode(BaseModel):
    name: str                                    # 节点名称
    node_type: Literal[
        "root",                                  # 根节点（唯一）
        "group",                                 # 分组节点（功能模块/场景类别）
        "expected_result",                        # 预期结果节点
        "precondition_group",                     # 前置条件分组
        "case"                                   # 测试用例叶节点
    ]
    children: list["ChecklistNode"] = []         # 子节点列表（递归引用）
    checkpoint_id: str | None = None             # 关联 Checkpoint（叶节点有值）
    metadata: dict | None = None                 # 扩展元数据

class CanonicalOutlineNode(BaseModel):
    path_segment: str                            # 当前路径片段
    full_path: str                               # 完整路径（如 "登录/手机号登录/验证码校验"）
    checkpoint_ids: list[str] = []               # 该节点关联的所有 checkpoint
    children: list["CanonicalOutlineNode"] = []  # 子节点

class CheckpointPathMapping(BaseModel):
    checkpoint_id: str                           # Checkpoint ID
    path: str                                    # 在大纲树中的路径

class CheckpointPathCollection(BaseModel):
    mappings: list[CheckpointPathMapping]        # 全部映射关系
```

**依赖关系：**
- 内部：`checkpoint_id` → `checkpoint_models.Checkpoint.id`
- 外部：`pydantic.BaseModel`；使用 `Literal` 做 `node_type` 枚举

**设计模式：**
- **Composite 模式**：`ChecklistNode` 是经典的组合模式实现——叶节点（`case`/`expected_result`）与容器节点（`root`/`group`/`precondition_group`）共享相同接口
- **双树结构**：`ChecklistNode` 面向最终渲染输出（带 node_type 语义），`CanonicalOutlineNode` 面向中间处理（基于路径的规范化视图）
- **递归自引用**：`children: list["ChecklistNode"]` 使用 Pydantic v2 的延迟引用

---

### §3.5 `checkpoint_models.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（核心业务模型） |
| **职责** | 定义检查点——从 PRD 研究事实中提炼出的可测试验证点 |

**关键类与签名：**

```python
class Checkpoint(BaseModel):
    id: str                           # SHA-256 确定性 ID（基于内容哈希）
    source_fact_ids: list[str]        # 产生此 checkpoint 的 ResearchFact ID 列表
    title: str                        # 检查点标题
    description: str                  # 详细描述
    test_objective: str               # 测试目标
    preconditions: list[str]          # 前置条件
    expected_behaviors: list[str]     # 预期行为列表
    priority: str                     # 优先级
    metadata: dict | None = None      # 扩展元数据
```

**ID 生成策略：**
```python
# 推测的 ID 生成逻辑（基于内容的确定性哈希）
id = sha256(f"{title}|{description}|{test_objective}".encode()).hexdigest()
```

**依赖关系：**
- 内部：`source_fact_ids` → `research_models.ResearchFact.id`
- 外部：`pydantic.BaseModel`、`hashlib.sha256`

**设计模式：**
- **内容寻址 ID（Content-Addressable ID）**：相同内容的 Checkpoint 总是产生相同 ID，天然去重且幂等
- **溯源链**：`source_fact_ids` 维持了到上游 `ResearchFact` 的多对多关联

---

### §3.6 `document_models.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（输入阶段模型） |
| **职责** | PRD 文档解析结果的结构化表示 |

**关键类与签名：**

```python
class DocumentSection(BaseModel):
    # 文档中的一个结构化段落/章节
    title: str | None = None          # 章节标题
    content: str                      # 章节内容
    level: int = 0                    # 标题层级
    # ... 可能的其他字段（子章节、位置等）

class ParsedDocument(BaseModel):
    # 解析后的完整文档
    sections: list[DocumentSection]   # 所有章节
    raw_content: str                  # 原始内容
    # ... 文档元数据
```

**依赖关系：**
- 内部：无（位于数据流最上游）
- 外部：`pydantic.BaseModel`

**设计说明：**
- 作为管道的入口模型，将非结构化 PRD 文本转化为结构化的 `DocumentSection` 列表
- 保留 `raw_content` 以便后续处理阶段按需回溯原文

---

### §3.7 `project_models.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（CRUD 模型） |
| **职责** | 项目上下文的创建/读取/更新三套模型 |

**关键类与签名：**

```python
class ProjectContext(BaseModel):
    # 完整的项目上下文（读取用）
    id: str
    name: str
    # ... 项目配置、历史记录等

class ProjectContextCreate(BaseModel):
    # 创建时的字段子集
    name: str
    # ... 必填字段

class ProjectContextUpdate(BaseModel):
    # 更新时的可选字段
    name: str | None = None
    # ... 所有字段均可选
```

**依赖关系：**
- 内部：无直接模型依赖
- 外部：`pydantic.BaseModel`

**设计模式：**
- **三段式 CRUD 模型**：`Context` / `ContextCreate` / `ContextUpdate` 分离读写关注点，`Update` 模型所有字段可选，是 FastAPI 项目的常见模式

---

### §3.8 `research_models.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（中间阶段模型） |
| **职责** | PRD 研究阶段的产出物：证据引用、研究事实、计划场景、研究输出汇总 |

**关键类与签名：**

```python
class EvidenceRef(BaseModel):
    # 证据引用——指向原始文档中的具体位置
    source: str                       # 来源标识
    section: str | None = None        # 所在章节
    quote: str | None = None          # 原文引用片段

class ResearchFact(BaseModel):
    id: str                           # 事实唯一标识
    content: str                      # 事实内容
    evidence_refs: list[EvidenceRef]  # 支撑证据列表
    category: str | None = None       # 分类标签

    @model_validator(mode="before")
    @classmethod
    def coerce_evidence_refs(cls, values):
        """防御性归一化：当 LLM 返回单个字符串而非列表时，自动包装为列表"""
        refs = values.get("evidence_refs")
        if isinstance(refs, str):
            values["evidence_refs"] = [refs]
        return values

class PlannedScenario(BaseModel):
    # 从事实推导出的计划测试场景
    title: str
    description: str
    related_fact_ids: list[str]       # 关联的 ResearchFact ID

class ResearchOutput(BaseModel):
    # 研究阶段的完整输出
    facts: list[ResearchFact]
    scenarios: list[PlannedScenario]
    # ... 可能的汇总统计
```

**依赖关系：**
- 内部：被 `checkpoint_models.Checkpoint.source_fact_ids` 引用
- 外部：`pydantic.BaseModel`、`pydantic.model_validator`

**设计模式：**
- **防御性 model_validator**：针对 LLM 输出不稳定性的务实处理。LLM 可能将本应为 `list[str]` 的字段输出为单个 `str`，验证器在数据进入系统前完成归一化
- **证据链**：`ResearchFact` → `EvidenceRef` 构成可溯源的证据链条

---

### §3.9 `run_state.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（运行时状态模型） |
| **职责** | 管理迭代运行状态、质量评估报告和重试决策 |

**关键类与签名：**

```python
class EvaluationDimension(BaseModel):
    name: str                         # 评估维度名称（如"覆盖率"、"可执行性"）
    score: float                      # 该维度得分
    feedback: str | None = None       # 维度反馈意见

class EvaluationReport(BaseModel):
    dimensions: list[EvaluationDimension]  # 多维度评估
    overall_score: float                    # 综合得分
    pass_: bool                             # 是否通过（注意下划线避免与关键字冲突）

class RetryDecision(BaseModel):
    should_retry: bool                # 是否需要重试
    reason: str | None = None         # 决策理由
    # ... 可能的重试策略参数

class IterationRecord(BaseModel):
    iteration: int                    # 迭代轮次
    evaluation: EvaluationReport      # 本轮评估
    # ... 本轮生成的中间产物引用

class RunState(BaseModel):
    # 整个运行的状态追踪
    current_iteration: int = 0
    iterations: list[IterationRecord] = []
    # ... 运行配置、超时等
```

**依赖关系：**
- 内部：`IterationRecord` 组合 `EvaluationReport`；被 `state.GlobalState` 引用
- 外部：`pydantic.BaseModel`

**设计模式：**
- **迭代式优化状态机**：`RunState` → `EvaluationReport` → `RetryDecision` 构成"生成→评估→决策"的闭环
- **`pass_` 命名**：使用尾部下划线避免 Python 关键字 `pass` 冲突，是 Pydantic 项目中处理保留字的标准做法

---

### §3.10 `state.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（TypedDict 状态容器） |
| **职责** | 定义 LangGraph 图执行所需的全局状态和子图状态 |

**关键类与签名：**

```python
class GlobalState(TypedDict):
    # LangGraph 主图的状态容器
    parsed_document: ParsedDocument | None
    research_output: ResearchOutput | None
    checkpoints: list[Checkpoint]
    optimized_tree: list[ChecklistNode]        # ← 优化后的检查清单树（核心输出）
    test_cases: list[TestCase]
    run_state: RunState | None
    # ... 其他流转状态字段

class CaseGenState(TypedDict):
    # 用例生成子图的局部状态
    checkpoint: Checkpoint                      # 当前处理的 checkpoint
    # ... 子图专属字段
```

**依赖关系：**
- 内部：聚合几乎所有其他模型——`ParsedDocument`、`ResearchOutput`、`Checkpoint`、`ChecklistNode`、`TestCase`、`RunState`
- 外部：`typing.TypedDict`

**设计模式：**
- **TypedDict 而非 BaseModel**：LangGraph 要求状态为普通 dict 子类型（`TypedDict`），而非 Pydantic 模型。这是框架约束
- **状态聚合器**：`GlobalState` 是全部领域模型的"汇聚点"，体现了管道式数据流——上游阶段写入、下游阶段读取
- **子图隔离**：`CaseGenState` 为用例生成子图提供隔离的状态空间，避免子图意外修改全局状态

---

### §3.11 `xmind_models.py`

| 属性 | 值 |
|---|---|
| **类型** | A-model（导出格式模型） |
| **职责** | XMind 思维导图导出的树结构定义 |

**关键类与签名：**

```python
class XMindTopic(BaseModel):
    title: str                                  # 节点标题
    children: list["XMindTopic"] = []           # 子主题列表（递归引用）
    # ... 可能的样式、标注等 XMind 特有属性
```

**依赖关系：**
- 内部：数据来源于 `ChecklistNode` 树的转换
- 外部：`pydantic.BaseModel`

**设计说明：**
- 与 `ChecklistNode` 结构类似但更简单，面向 XMind 文件格式的特定需求
- 职责单一：仅用于序列化为 `.xmind` 文件，不参与核心业务流程

---

## §4 模型依赖关系

### 4.1 核心数据流管道

```
ParsedDocument                      （文档解析阶段入口）
    │
    ▼
ResearchFact ◄── EvidenceRef        （研究阶段：提取事实 + 证据引用）
    │
    ▼
Checkpoint ◄── source_fact_ids      （检查点提炼：事实 → 可测试验证点）
    │
    ├──────────────────────┐
    ▼                      ▼
ChecklistNode          CanonicalOutlineNode    （树结构组织）
    │                      │
    ▼                      ▼
TestCase ◄── checkpoint_id, evidence_refs      （用例生成）
    │
    ▼
XMindTopic                           （导出格式转换）
```

### 4.2 状态容器关系

```
GlobalState (TypedDict)
    ├── parsed_document:  ParsedDocument
    ├── research_output:  ResearchOutput
    │                       ├── facts:     list[ResearchFact]
    │                       └── scenarios: list[PlannedScenario]
    ├── checkpoints:      list[Checkpoint]
    ├── optimized_tree:   list[ChecklistNode]      ← 核心产出
    ├── test_cases:       list[TestCase]
    └── run_state:        RunState
                            └── iterations: list[IterationRecord]
                                              └── evaluation: EvaluationReport
                                                                └── dimensions: list[EvaluationDimension]

CaseGenState (TypedDict)              ← 子图局部状态
    └── checkpoint: Checkpoint
```

### 4.3 ID 引用链

```
EvidenceRef.source ──────────────────► 原始文档定位
ResearchFact.id ◄────────────────────► Checkpoint.source_fact_ids  (多对多)
Checkpoint.id (SHA-256) ◄────────────► ChecklistNode.checkpoint_id (一对一)
Checkpoint.id ◄──────────────────────► TestCase.checkpoint_id      (一对多)
Checkpoint.id ◄──────────────────────► CheckpointPathMapping       (一对一路径映射)
ResearchFact → EvidenceRef ◄─────────► TestCase.evidence_refs      (溯源链)
```

---

## §5 补充观察

### 5.1 ChecklistNode 的 node_type 枚举设计

`ChecklistNode` 使用 `Literal["root", "group", "expected_result", "precondition_group", "case"]` 定义了五种节点类型，形成了清晰的层次语义：

| node_type | 角色 | 典型位置 | 是否叶节点 |
|---|---|---|---|
| `root` | 树根（唯一） | 第 0 层 | 否 |
| `group` | 功能模块/场景分组 | 第 1~N 层 | 否 |
| `precondition_group` | 前置条件聚合 | group 子节点 | 否 |
| `expected_result` | 预期结果节点 | group/precondition_group 子节点 | 可能 |
| `case` | 测试用例叶节点 | 最底层 | 是 |

**职责边界分析：**
- `root` 和 `group` 负责结构组织，不携带测试语义
- `precondition_group` 是一个巧妙的设计——将共享前置条件的用例聚合在一起，避免了前置条件在每个 `case` 中的重复声明，同时在 XMind 等可视化输出中形成自然的"条件→用例"层次
- `expected_result` 介于结构节点和叶节点之间，可以独立存在也可以包含子节点，体现了检查清单中"预期结果"这一概念的灵活性
- 使用 `Literal` 而非 `Enum` 是 Pydantic v2 中更惯用的做法：JSON 序列化直接为字符串，无需额外的枚举值转换

### 5.2 CanonicalOutlineNode vs ChecklistNode 的关系

项目维护了两套树结构，这并非冗余设计，而是服务于不同阶段的不同需求：

| 维度 | ChecklistNode | CanonicalOutlineNode |
|---|---|---|
| **服务阶段** | 最终输出与渲染 | 中间处理与路径规范化 |
| **核心标识** | `node_type`（语义角色） | `full_path`（路径定位） |
| **checkpoint 关联** | 单个 `checkpoint_id`（叶节点） | `checkpoint_ids` 列表（聚合节点） |
| **用途** | XMind 导出、前端展示 | checkpoint 去重、路径匹配、树优化 |

**为什么需要两套：**
1. **路径规范化需求**：`CanonicalOutlineNode` 的 `full_path`（如 `"登录/手机号登录/验证码校验"`）是确定性的字符串路径，便于 checkpoint 的精确定位和去重合并
2. **语义 vs 结构**：`ChecklistNode` 的 `node_type` 承载了测试领域的语义信息（什么是前置条件组、什么是预期结果），而 `CanonicalOutlineNode` 只关心层次路径结构
3. **一个节点多个 checkpoint**：`CanonicalOutlineNode.checkpoint_ids` 是列表，允许同一个大纲路径关联多个 checkpoint（后续可能拆分或合并），而 `ChecklistNode` 在叶节点层面是一对一关联
4. **优化管道**：数据流为 `CanonicalOutlineNode`（规范化）→ 树优化 → `ChecklistNode`（语义化输出），`CheckpointPathMapping`/`CheckpointPathCollection` 作为两者之间的桥梁

### 5.3 Checkpoint 的 SHA-256 ID 生成策略

**优点：**
1. **幂等性**：相同内容的 Checkpoint 始终生成相同 ID。在迭代优化场景中，如果某轮优化未改变特定 checkpoint 的核心内容，其 ID 不变，下游可安全复用已生成的 TestCase
2. **天然去重**：多个 ResearchFact 推导出语义相同的 Checkpoint 时，SHA-256 碰撞概率极低，自动去重无需额外逻辑
3. **无状态生成**：不依赖数据库自增 ID 或 UUID 生成器，纯函数计算，便于分布式或无服务器环境
4. **可验证性**：任何持有 Checkpoint 内容的一方可独立验证 ID 的正确性

**缺点：**
1. **内容敏感**：任何微小的描述变更（如多一个空格、措辞调整）都会产生全新 ID，导致下游所有关联（TestCase.checkpoint_id、ChecklistNode.checkpoint_id）失效，引发不必要的重新生成
2. **哈希字段选择**：参与哈希的字段集合必须精心选择——如果包含 `metadata` 等易变字段，ID 稳定性会大打折扣；如果排除太多字段，可能出现语义不同但 ID 相同的情况
3. **可读性差**：SHA-256 十六进制字符串（64 字符）对调试和日志阅读不友好，相比 `CP-001` 这样的人类可读 ID 辨识度低
4. **不可逆**：无法从 ID 推导出生成它的原始内容，调试时必须同时持有完整的 Checkpoint 对象

### 5.4 GlobalState 中 optimized_tree 字段的设计意图

`optimized_tree: list[ChecklistNode]` 是 `GlobalState` 中最关键的字段之一：

1. **"optimized" 的含义**：该字段存储的不是初始生成的检查清单树，而是经过迭代评估和优化后的最终版本。命名暗示了其在"生成→评估→优化"循环中的定位——它是优化的**产出物**
2. **为什么是 `list` 而非单个 `ChecklistNode`**：虽然逻辑上应有一个 `root` 节点作为树根，但使用 `list` 允许：
   - 多棵独立子树并存（例如 PRD 包含多个独立功能模块时）
   - 与 LangGraph 的 reducer 机制兼容（列表更容易做增量合并）
   - 灵活处理根节点缺失或多根的异常情况
3. **状态流转**：在 LangGraph 的图执行过程中，`optimized_tree` 在多个节点间流转——树构建节点写入初始版本，评估节点读取并评分，优化节点修改并写回。TypedDict 的可变性使这种流转自然发生
4. **下游消费**：`optimized_tree` 最终被转换为 `XMindTopic`（XMind 导出）和 `TestCase` 列表（用例输出），是两个主要输出形式的共同源头

### 5.5 模型验证器的防御性设计

`research_models.py` 中的 `model_validator` 体现了对 LLM 输出不确定性的务实应对：

**问题根源：**
LLM（大语言模型）的 JSON 输出存在固有不稳定性：
- 要求 `list[str]` 时可能返回单个 `str`（省略了列表包装）
- 要求 `list[EvidenceRef]` 时可能返回 `str`（将整个对象扁平化为文本）
- 偶尔返回 `null` 而非空列表 `[]`

**防御策略：**
```python
@model_validator(mode="before")
def coerce_evidence_refs(cls, values):
    refs = values.get("evidence_refs")
    if isinstance(refs, str):
        values["evidence_refs"] = [refs]  # str → list[str] 强制转换
    return values
```

**设计意义：**
1. **mode="before"**：在 Pydantic 字段验证之前执行，确保归一化在类型检查之前完成。如果使用 `mode="after"`，类型不匹配会直接抛出 `ValidationError`，来不及修复
2. **仅做安全转换**：`str → list[str]` 是无损的向上转换（任何 `str` 都是合法的单元素 `list[str]`），不会引入语义歧义
3. **隔离层**：将 LLM 输出的"脏数据处理"封装在模型层，而非散落在调用 LLM 的业务代码中。上层代码可以信任：一旦数据通过 Pydantic 构造，字段类型必然正确
4. **可扩展性**：如果未来 LLM 出现新的格式异常模式（如返回逗号分隔字符串），只需在验证器中增加一个 `elif` 分支，无需修改业务逻辑

这种"宽进严出"的防御性设计是 LLM 应用工程中的最佳实践——在系统边界处做最大限度的输入归一化，在系统内部保持严格的类型约束。
