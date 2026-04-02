# app/domain/_ANALYSIS.md — 领域模型分析
> 分析分支自动生成 · 源分支 `main`
---
## §1 目录概述
| 属性 | 值 |
|---|---|
| **路径** | `app/domain/` |
| **文件数量** | 11（1 `__init__.py` + 10 模型文件）— PR #23 扩展了 template_models.py、checklist_models.py、state.py、api_models.py |
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
| 12 | `template_models.py` | A-model | ~130 | **关键文件 (PR #23 扩展)**：项目级 Checklist 模版领域模型：`ProjectChecklistTemplateNode`（+mandatory）、`ProjectChecklistTemplateMetadata`（+mandatory_levels）、`ProjectChecklistTemplateFile`、`TemplateLeafTarget`、`MandatorySkeletonNode`（新增） |
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
    prd_content: str                    # PRD 原文内容
    project_id: str | None = None       # 可选项目 ID，用于关联上下文
    output_format: str | None = None    # 可选输出格式指定
    # ... 其他摘要字段

class IterationSummary(BaseModel):
    iteration: int                      # 迭代轮次编号
    score: float                        # 本轮评估得分
    passed: bool                        # 是否通过质量门槛

class CaseGenerationResponse(BaseModel):
    # 包含最终生成结果与各轮迭代摘要
    iterations: list[IterationSummary]
    # ... 最终用例数据、状态等
```
**PR #23 变更：**
- `CaseGenerationRequest` 新增 `template_name: str | None` 字段，支持按名称从 `templates/` 目录加载模版（不含扩展名）
- `template_name` 与 `template_file_path` 二选一，`template_name` 优先
- 使用场景：用户在 API 请求中指定 `template_name: "brand_spp_consideration"` 即可自动加载对应模版

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
    id: str                             # 用例唯一标识
    title: str                          # 用例标题
    preconditions: list[str]            # 前置条件列表
    steps: list[str]                    # 测试步骤
    expected_results: list[str]         # 预期结果
    priority: str                       # 优先级（如 P0/P1/P2）
    checkpoint_id: str                  # 关联的 Checkpoint ID（可溯源）
    evidence_refs: list[...]            # 证据引用列表，链接回 ResearchFact

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
    name: str                           # 节点名称
    node_type: Literal[
        "root",                         # 根节点（唯一）
        "group",                        # 分组节点（功能模块/场景类别）
        "expected_result",              # 预期结果节点
        "precondition_group",           # 前置条件分组
        "case"                          # 测试用例叶节点
    ]
    children: list["ChecklistNode"] = [] # 子节点列表（递归引用）
    checkpoint_id: str | None = None    # 关联 Checkpoint（叶节点有值）
    metadata: dict | None = None        # 扩展元数据

class CanonicalOutlineNode(BaseModel):
    path_segment: str                   # 当前路径片段
    full_path: str                      # 完整路径（如 "登录/手机号登录/验证码校验"）
    checkpoint_ids: list[str] = []      # 该节点关联的所有 checkpoint
    children: list["CanonicalOutlineNode"] = []  # 子节点

class CheckpointPathMapping(BaseModel):
    checkpoint_id: str                  # Checkpoint ID
    path: str                           # 在大纲树中的路径

class CheckpointPathCollection(BaseModel):
    mappings: list[CheckpointPathMapping]  # 全部映射关系
```
**依赖关系：**
- 内部：`checkpoint_id` → `checkpoint_models.Checkpoint.id`
- 外部：`pydantic.BaseModel`；使用 `Literal` 做 `node_type` 枚举

**设计模式：**
- **Composite 模式**：`ChecklistNode` 是经典的组合模式实现——叶节点（`case`/`expected_result`）与容器节点（`root`/`group`/`precondition_group`）共享相同接口
- **双树结构**：`ChecklistNode` 面向最终渲染输出（带 node_type 语义），`CanonicalOutlineNode` 面向中间处理（基于路径的规范化视图）
- **递归自引用**：`children: list["ChecklistNode"]` 使用 Pydantic v2 的延迟引用
---
**PR #23 变更 — source 与 is_mandatory 字段：**

`ChecklistNode` 新增两个字段以支持强制模版骨架功能：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source` | `Literal["template", "generated", "overflow"]` | `"generated"` | 标记节点来源：来自模版骨架 / LLM 自由生成 / 溢出未匹配 |
| `is_mandatory` | `bool` | `False` | 标记节点是否为强制节点（不可被 LLM 删除或重命名） |

**source 三值语义：**
- `"template"` — 节点来自模版强制骨架，标题和 ID 与模版一致，LLM 不可修改
- `"generated"` — 节点由 LLM 自由生成，可在非强制层级自由创建
- `"overflow"` — 节点未匹配到骨架中任何位置，被收集到 `_overflow` 容器

**下游消费：**
- `markdown_renderer.py`：`source == "template"` → 标题后追加 `[模版]`；`source == "overflow"` → 追加 `[待分配]`
- `xmind_payload_builder.py`：`source == "template"` → 蓝色旗标；`source == "overflow"` → 红色旗标

### §3.5 `checkpoint_models.py`
| 属性 | 值 |
|---|---|
| **类型** | A-model（核心业务模型） |
| **职责** | 定义检查点——从 PRD 研究事实中提炼出的可测试验证点 |
**关键类与签名：**
```python
class Checkpoint(BaseModel):
    id: str                             # SHA-256 确定性 ID（基于内容哈希）
    source_fact_ids: list[str]          # 产生此 checkpoint 的 ResearchFact ID 列表
    title: str                          # 检查点标题
    description: str                    # 详细描述
    test_objective: str                 # 测试目标
    preconditions: list[str]            # 前置条件
    expected_behaviors: list[str]       # 预期行为列表
    priority: str                       # 优先级
    metadata: dict | None = None        # 扩展元数据
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
    title: str | None = None            # 章节标题
    content: str                        # 章节内容
    level: int = 0                      # 标题层级

class ParsedDocument(BaseModel):
    sections: list[DocumentSection]     # 所有章节
    raw_content: str                    # 原始内容
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
    id: str
    name: str

class ProjectContextCreate(BaseModel):
    name: str

class ProjectContextUpdate(BaseModel):
    name: str | None = None
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
    source: str
    section: str | None = None
    quote: str | None = None

class ResearchFact(BaseModel):
    id: str
    content: str
    evidence_refs: list[EvidenceRef]
    category: str | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_evidence_refs(cls, values):
        """防御性归一化：当 LLM 返回单个字符串而非列表时，自动包装为列表"""
        refs = values.get("evidence_refs")
        if isinstance(refs, str):
            values["evidence_refs"] = [refs]
        return values

class PlannedScenario(BaseModel):
    title: str
    description: str
    related_fact_ids: list[str]

class ResearchOutput(BaseModel):
    facts: list[ResearchFact]
    scenarios: list[PlannedScenario]
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
    name: str
    score: float
    feedback: str | None = None

class EvaluationReport(BaseModel):
    dimensions: list[EvaluationDimension]
    overall_score: float
    pass_: bool

class RetryDecision(BaseModel):
    should_retry: bool
    reason: str | None = None

class IterationRecord(BaseModel):
    iteration: int
    evaluation: EvaluationReport

class RunState(BaseModel):
    current_iteration: int = 0
    iterations: list[IterationRecord] = []
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
    parsed_document: ParsedDocument | None
    research_output: ResearchOutput | None
    checkpoints: list[Checkpoint]
    optimized_tree: list[ChecklistNode]
    test_cases: list[TestCase]
    run_state: RunState | None

class CaseGenState(TypedDict):
    checkpoint: Checkpoint
```
**PR #23 变更 — mandatory_skeleton 字段：**

`GlobalState` 和 `CaseGenState` 均新增 `mandatory_skeleton: MandatorySkeletonNode` 字段：
- **写入者**: `template_loader` 节点 — 加载模版后调用 `MandatorySkeletonBuilder.build()` 构建骨架
- **桥接传递**: `main_workflow.py` 的 `_build_case_generation_bridge()` 负责将 `mandatory_skeleton` 从 `GlobalState` 映射到 `CaseGenState`
- **消费者**:
  1. `checkpoint_outline_planner` — 将骨架注入 LLM prompt（软约束）+ 后处理修复（硬约束）
  2. `structure_assembler` — 最终防线：确保输出树与骨架一致 + source 标注
- **可选性**: 当未提供模版或模版无强制约束时，该字段为 `None`，所有消费者安全跳过，保持向后兼容

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
    title: str
    children: list["XMindTopic"] = []
```
**依赖关系：**
- 内部：数据来源于 `ChecklistNode` 树的转换
- 外部：`pydantic.BaseModel`

**设计说明：**
- 与 `ChecklistNode` 结构类似但更简单，面向 XMind 文件格式的特定需求
- 职责单一：仅用于序列化为 `.xmind` 文件，不参与核心业务流程

### §3.12 `template_models.py` ★ 关键文件 (PR #23 扩展)
| 属性 | 值 |
|---|---|
| **类型** | A-model（模版领域模型） |
| **职责** | 定义项目级 Checklist 模版的完整数据结构，包括模版节点、元数据、叶子目标和强制骨架节点 |
**关键类与签名：**
```python
class ProjectChecklistTemplateNode(BaseModel):
    id: str
    title: str
    description: str = ""
    priority: str = ""
    note: str = ""
    status: str = ""
    mandatory: bool = False
    children: list[ProjectChecklistTemplateNode] = []

class ProjectChecklistTemplateMetadata(BaseModel):
    name: str = ""
    version: str = ""
    description: str = ""
    mandatory_levels: list[int] = []

    @field_validator("mandatory_levels")
    def validate_mandatory_levels(cls, v):
        """校验层级编号为正整数，返回排序去重后的列表。"""

class ProjectChecklistTemplateFile(BaseModel):
    metadata: ProjectChecklistTemplateMetadata
    nodes: list[ProjectChecklistTemplateNode]

class TemplateLeafTarget(BaseModel):
    leaf_id: str
    leaf_title: str
    path_ids: list[str]
    path_titles: list[str]
    path_text: str = ""

class MandatorySkeletonNode(BaseModel):
    id: str
    title: str
    depth: int
    is_mandatory: bool
    source: Literal["template"] = "template"
    original_metadata: dict = {}
    children: list[MandatorySkeletonNode] = []
```
**依赖关系：**
- 内部：`MandatorySkeletonNode` 被 `state.GlobalState` / `state.CaseGenState` 引用
- 外部：`pydantic.BaseModel`、`pydantic.field_validator`、`typing.Literal`

**PR #23 核心变更：**
1. **`ProjectChecklistTemplateNode` 扩展**: 新增 `description`、`priority`、`note`、`status` 元信息字段（均可选）；新增 `mandatory: bool = False`
2. **`ProjectChecklistTemplateMetadata` 扩展**: 新增 `mandatory_levels: list[int]`（层级编号从 1 开始）；`field_validator` 确保正整数、排序去重
3. **`MandatorySkeletonNode` 新增**: 从模版中提取的仅包含强制节点的子树；`depth` 字段记录绝对深度；`original_metadata` 保留 priority/note/status；`source` 固定为 `"template"`
4. **自引用 model_rebuild()**: `MandatorySkeletonNode.model_rebuild()` — PR #23 新增，支持自引用递归结构

**强制性判定的双通道设计：**

| 通道 | 粒度 | 字段 | 说明 |
|------|------|------|------|
| 层级级强制 | 整层所有节点 | `metadata.mandatory_levels` | 适用于"Campaign/AdGroup/Ad 三层必须存在"的场景 |
| 节点级强制 | 单个特定节点 | `node.mandatory` | 适用于"Campaign name 这个特定节点不可遗漏"的场景 |

---
## §4 模型依赖关系
### 4.1 核心数据流管道
```
ParsedDocument （文档解析阶段入口）
│
▼
ResearchFact ◄── EvidenceRef （研究阶段：提取事实 + 证据引用）
│
▼
Checkpoint ◄── source_fact_ids （检查点提炼：事实 → 可测试验证点）
│
├──────────────────────┐
▼                      ▼
ChecklistNode    CanonicalOutlineNode （树结构组织）
│                      │
▼                      ▼
TestCase ◄── checkpoint_id, evidence_refs （用例生成）
│
▼
XMindTopic （导出格式转换）
```
### 4.2 状态容器关系
```
GlobalState (TypedDict)
├── parsed_document: ParsedDocument
├── research_output: ResearchOutput
│   ├── facts: list[ResearchFact]
│   └── scenarios: list[PlannedScenario]
├── checkpoints: list[Checkpoint]
├── optimized_tree: list[ChecklistNode] ← 核心产出
├── test_cases: list[TestCase]
├── run_state: RunState
├── mandatory_skeleton: MandatorySkeletonNode ← PR #23 新增
└── iterations: list[IterationRecord]
    └── evaluation: EvaluationReport
        └── dimensions: list[EvaluationDimension]

CaseGenState (TypedDict) ← 子图局部状态
└── checkpoint: Checkpoint
```
### 4.3 ID 引用链
```
EvidenceRef.source ──────────────────► 原始文档定位
ResearchFact.id ◄────────────────────► Checkpoint.source_fact_ids (多对多)
Checkpoint.id (SHA-256) ◄────────────► ChecklistNode.checkpoint_id (一对一)
Checkpoint.id ◄──────────────────────► TestCase.checkpoint_id (一对多)
Checkpoint.id ◄──────────────────────► CheckpointPathMapping (一对一路径映射)
ResearchFact → EvidenceRef ◄─────────► TestCase.evidence_refs (溯源链)
MandatorySkeletonNode.id ◄───────────► ProjectChecklistTemplateNode.id (一对一骨架映射)
MandatorySkeletonNode.id ◄───────────► ChecklistNode.node_id (强制节点恢复/合并)
ChecklistNode.source ────────────────► "template" | "generated" | "overflow" (来源标记)
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

### 5.2 CanonicalOutlineNode vs ChecklistNode 的关系

| 维度 | ChecklistNode | CanonicalOutlineNode |
|---|---|---|
| **服务阶段** | 最终输出与渲染 | 中间处理与路径规范化 |
| **核心标识** | `node_type`（语义角色） | `full_path`（路径定位） |
| **checkpoint 关联** | 单个 `checkpoint_id`（叶节点） | `checkpoint_ids` 列表（聚合节点） |
| **用途** | XMind 导出、前端展示 | checkpoint 去重、路径匹配、树优化 |

### 5.3 Checkpoint 的 SHA-256 ID 生成策略

**优点：** 幂等性、天然去重、无状态生成、可验证性
**缺点：** 内容敏感（微小变更产生全新 ID）、哈希字段选择敏感、可读性差、不可逆

### 5.4 GlobalState 中 optimized_tree 字段的设计意图

`optimized_tree: list[ChecklistNode]` 存储经过迭代评估和优化后的最终版本。使用 `list` 允许多棵独立子树并存、与 LangGraph 的 reducer 机制兼容。

### 5.5 模型验证器的防御性设计

`research_models.py` 中的 `model_validator` 体现了对 LLM 输出不确定性的务实应对——"宽进严出"的防御性设计是 LLM 应用工程中的最佳实践。

### 5.6 MandatorySkeletonNode 的设计意图 (PR #23)

**为什么需要独立的骨架模型：** 关注点分离、深度标注、元信息保留、source 固定。

**骨架在管道中的生命周期：**
```
template_loader 节点
│ MandatorySkeletonBuilder.build(template)
▼
GlobalState.mandatory_skeleton
│ _build_case_generation_bridge() 映射
▼
CaseGenState.mandatory_skeleton
│
├──→ checkpoint_outline_planner (软约束 + 硬约束)
└──→ structure_assembler (最终防线 + source 标注)
```

**向后兼容保证：** 当模版无强制约束时，`mandatory_skeleton` 为 `None`，所有消费者安全跳过。

## §6 PR #24 变更 — 知识检索状态字段

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

PR #24 在 `GlobalState` (TypedDict) 中新增 3 个字段，用于在工作流状态中传递知识检索结果。

### 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `knowledge_context` | `str` | 格式化后的知识检索文本，注入 context_research 节点的 prompt |
| `knowledge_sources` | `list[str]` | 检索命中的知识文档 ID 列表 |
| `knowledge_retrieval_success` | `bool` | 知识检索是否成功执行 |

### 设计说明

1. **三字段对应**: 三个字段与 `retriever.retrieve_knowledge()` 返回的三元组一一对应
2. **降级友好**: `knowledge_context` 为空字符串时，下游节点不注入额外知识上下文


## §7 PR #36 变更 — MR 代码分析领域模型

> 同步自 PR #36 `feat/mr-code-analysis-integration`

PR #36 引入了 MR（Merge Request）代码分析能力，在领域模型层新增 `mr_models.py` 并扩展了 4 个现有模型文件，为从代码变更中提取测试检查点提供完整的数据结构支撑。

### §7.1 新增文件：mr_models.py

| 属性 | 值 |
|---|---|
| **类型** | A-model（MR 分析领域模型） |
| **行数** | ~295 |
| **职责** | 定义 MR 代码分析全流程中的 11 个 Pydantic 模型，覆盖从 MR 元数据解析到代码一致性校验的完整数据链路 |

**关键类与签名：**

```python
class MRMetadata(BaseModel):
    mr_url: str
    title: str
    description: str = ""
    source_branch: str
    target_branch: str
    author: str = ""

class MRFileDiff(BaseModel):
    file_path: str
    change_type: Literal["added", "modified", "deleted", "renamed"]
    additions: int = 0
    deletions: int = 0
    patch: str = ""

class MRCodeFact(BaseModel):
    id: str
    file_path: str
    fact_type: Literal["behavior_change", "api_change", "config_change",
                        "dependency_change", "logic_branch"]
    content: str
    evidence: str = ""
    impact_scope: str = ""

class MRAnalysisResult(BaseModel):
    metadata: MRMetadata
    file_diffs: list[MRFileDiff]
    code_facts: list[MRCodeFact]
    affected_modules: list[str]
    risk_assessment: str = ""

class CodeConsistencyCheck(BaseModel):
    checkpoint_id: str
    code_fact_ids: list[str]
    consistency_score: float
    discrepancies: list[str] = []
    verified: bool = False
```

**设计模式：**
- **fact_type 枚举化**：五值 `Literal` 枚举，为下游分类过滤和优先级排序提供结构化语义
- **双向溯源**：`MRCodeFact` 通过 `file_path` + `evidence` 回溯到 diff 原文，通过 `id` 被 `Checkpoint.source_fact_ids` 引用
- **一致性校验闭环**：`CodeConsistencyCheck` 将 checkpoint 与 code fact 关联并评分

### §7.2 修改文件：state.py

**变更：** `GlobalState` 和 `CaseGenState` 新增 MR 分析相关字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `mr_analysis_result` | `MRAnalysisResult | None` | MR 分析完整结果，由 mr_analyzer 节点写入 |
| `mr_code_facts` | `list[MRCodeFact]` | 从 MR diff 提取的代码事实列表 |
| `code_consistency_checks` | `list[CodeConsistencyCheck]` | 代码一致性校验结果 |

**设计说明：**
- `mr_code_facts` 独立于 `mr_analysis_result.code_facts` 存储，允许下游节点增量追加经过 agentic search 补充的事实

### §7.3 修改文件：api_models.py

**变更：**
- 新增 `MRRequestConfig` 内嵌模型，包含 `mr_url`、`repository`、`target_branch` 等字段
- 新增 `frontend_mr: MRRequestConfig | None` 和 `backend_mr: MRRequestConfig | None` 字段
- 前后端双 MR 设计适配微服务/前后端分离项目

### §7.4 修改文件：case_models.py

**变更：**
- `TestCase` 新增 `tags: list[str] = []`（如 `"mr_derived"`、`"prd_derived"`、`"code_consistency"`）
- `TestCase` 新增 `code_consistency: CodeConsistencyCheck | None = None`

### §7.5 修改文件：checkpoint_models.py

**变更：**
- `Checkpoint` 新增 `code_consistency: CodeConsistencyCheck | None = None`

### §7.6 模型依赖关系更新

```
MR 代码分析数据流:

MRMetadata + MRFileDiff[]
│
▼
MRAnalysisResult ◄── mr_analyzer 节点
│
├── MRCodeFact[] ◄── agentic search 补充
│   │
│   ▼
│   Checkpoint.source_fact_ids (复用现有链路)
│   │
│   ▼
│   TestCase.checkpoint_id + TestCase.tags["mr_derived"]
│
└── CodeConsistencyCheck[]
    ├── → Checkpoint.code_consistency
    └── → TestCase.code_consistency
```

**ID 引用链扩展：**
```
MRCodeFact.id ◄────────────────► Checkpoint.source_fact_ids (多对多, 复用)
MRCodeFact.id ◄────────────────► CodeConsistencyCheck.code_fact_ids (多对多)
Checkpoint.id ◄────────────────► CodeConsistencyCheck.checkpoint_id (一对一)
```