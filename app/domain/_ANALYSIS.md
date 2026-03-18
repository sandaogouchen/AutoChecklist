# app/domain/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 10 | 分析策略: 数据模型

## §1 目录职责

`app/domain/` 是 AutoChecklist 项目的**领域模型层**（Domain Layer），采用 Pydantic v2 BaseModel 与 Python TypedDict 定义了贯穿 LangGraph 工作流全生命周期的核心数据结构。该层职责包括：

1. **API 边界契约** — 定义 FastAPI 请求/响应的序列化 schema（`api_models.py`）
2. **业务实体建模** — 测试用例、检查点、文档解析结果、项目上下文等核心领域对象
3. **研究分析中间态** — PRD 文档的结构化研究输出，含证据引用链路与 LLM 输出兼容性验证器
4. **工作流状态管理** — LangGraph 增量更新所需的 TypedDict 状态定义与运行状态枚举
5. **交付物模型** — XMind 思维导图节点树与交付结果

该层不包含业务逻辑或 I/O 操作，是纯粹的数据定义层，所有模型均为不可变或浅可变的值对象。

---

## §2 文件清单

| 文件名 | 行数 | 主要职责 | 分析策略 |
|---------|------|----------|----------|
| `__init__.py` | 5 | 包初始化，模块文档字符串 | 数据模型 |
| `api_models.py` | 92 | API 请求/响应模型（6 个类） | 数据模型 |
| `case_models.py` | 56 | 测试用例与质量报告模型（2 个类） | 数据模型 |
| `checkpoint_models.py` | 77 | 检查点模型与 ID 生成函数（2 个类 + 1 个函数） | 数据模型 |
| `document_models.py` | 58 | PRD 文档解析结构模型（3 个类） | 数据模型 |
| `project_models.py` | 68 | 项目上下文与枚举定义（2 个枚举 + 1 个类） | 数据模型 |
| `research_models.py` | 254 | 研究分析模型与 LLM 输出兼容验证器（5 个类 + 辅助函数） | 数据模型 |
| `run_state.py` | 119 | 迭代评估回路运行状态模型（2 个枚举 + 5 个类） | 数据模型 |
| `state.py` | 71 | LangGraph 工作流 TypedDict 状态定义（2 个 TypedDict） | 数据模型 |
| `xmind_models.py` | 55 | XMind 思维导图节点与交付结果模型（2 个类） | 数据模型 |
| **合计** | **855** | | |

---

## §3 文件详细分析

---

### §3.1 `__init__.py`

- **路径**: `app/domain/__init__.py`
- **行数**: 5
- **职责**: 领域模型子包初始化，仅含模块级文档字符串

#### §3.1.1 核心内容

该文件仅包含一段 docstring，声明该子包定义了"贯穿整个工作流的核心数据结构"。无任何 `__all__` 导出声明或 re-export 逻辑。

```python
"""领域模型子包。

定义了贯穿整个工作流的核心数据结构，
包括 API 模型、测试用例模型、检查点模型、文档模型、研究分析模型和运行状态模型。
"""
```

#### §3.1.2 依赖关系

- 内部依赖: 无
- 外部依赖: 无

#### §3.1.3 关键逻辑 / 数据流

无逻辑。各模块通过直接 `from app.domain.xxx import ...` 方式互相引用，不经过 `__init__.py` 中转。

---

### §3.2 `api_models.py`

- **路径**: `app/domain/api_models.py`
- **行数**: 92
- **职责**: 定义 FastAPI 用例生成端点的请求/响应 schema，包含 6 个 Pydantic 模型

#### §3.2.1 核心内容

##### 类 `ModelConfigOverride(BaseModel)`

LLM 调用参数覆盖，所有字段可选。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `model` | `str \| None` | `None` | — | LLM 模型名称 |
| `temperature` | `float \| None` | `None` | — | 采样温度 |
| `max_tokens` | `int \| None` | `None` | — | 最大 token 数 |

##### 类 `RunOptions(BaseModel)`

运行时选项。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `include_intermediate_artifacts` | `bool` | `False` | — | 是否在结果中包含中间产物 |

##### 类 `ErrorInfo(BaseModel)`

错误信息载体。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `code` | `str` | *(必填)* | — | 错误编码 |
| `message` | `str` | *(必填)* | — | 错误消息 |
| `detail` | `dict[str, Any]` | `{}` | `Field(default_factory=dict)` | 附加详情 |

##### 类 `IterationSummary(BaseModel)`

迭代摘要信息，作为 `CaseGenerationRun` 的轻量字段，对外展示迭代回路关键状态。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `iteration_count` | `int` | `0` | — | 迭代总轮次 |
| `last_evaluation_score` | `float` | `0.0` | — | 最后一次评估分数 |
| `had_retries` | `bool` | `False` | — | 是否发生过回流 |
| `final_stage` | `str` | `""` | — | 最终停留阶段 |
| `retry_reasons` | `list[str]` | `[]` | `Field(default_factory=list)` | 回流原因列表 |

##### 类 `CaseGenerationRequest(BaseModel)`

用例生成请求，配置了 `ConfigDict(populate_by_name=True)` 以支持别名与字段名双向填充。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `file_path` | `str` | *(必填)* | — | PRD 文件路径 |
| `language` | `str` | `"zh-CN"` | — | 输出语言 |
| `llm_config` | `ModelConfigOverride` | `ModelConfigOverride()` | `alias="model_config"`, `serialization_alias="model_config"` | LLM 配置覆盖 |
| `options` | `RunOptions` | `RunOptions()` | — | 运行选项 |
| `project_id` | `str \| None` | `None` | — | 项目 ID |

**序列化行为**: `llm_config` 字段使用 `alias="model_config"` 和 `serialization_alias="model_config"`，在 JSON 输入/输出中统一使用 `model_config` 名称，避免与 Pydantic v2 的 `model_config` 保留名冲突。`populate_by_name=True` 允许同时接受 `llm_config` 和 `model_config` 作为输入键。

##### 类 `CaseGenerationRun(BaseModel)`

一次用例生成任务的完整运行结果，是 API 层最大的响应模型。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `run_id` | `str` | *(必填)* | — | 运行唯一标识 |
| `status` | `Literal["pending", "running", "evaluating", "retrying", "succeeded", "failed"]` | *(必填)* | 6 值 Literal | 运行状态 |
| `input` | `CaseGenerationRequest` | *(必填)* | — | 原始请求 |
| `parsed_document` | `ParsedDocument \| None` | `None` | — | 解析后的文档 |
| `research_summary` | `ResearchOutput \| None` | `None` | — | 研究摘要 |
| `test_cases` | `list[TestCase]` | `[]` | — | 生成的测试用例列表 |
| `quality_report` | `QualityReport` | `QualityReport()` | — | 质量报告 |
| `checkpoint_count` | `int` | `0` | — | 检查点数量 |
| `artifacts` | `dict[str, str]` | `{}` | — | 产物路径映射 |
| `error` | `ErrorInfo \| None` | `None` | — | 错误信息 |
| `iteration_summary` | `IterationSummary` | `IterationSummary()` | — | 迭代摘要 |
| `project_id` | `str \| None` | `None` | — | 项目 ID |

#### §3.2.2 依赖关系

- 内部依赖:
  - `app.domain.case_models` → `QualityReport`, `TestCase`
  - `app.domain.document_models` → `ParsedDocument`
  - `app.domain.research_models` → `ResearchOutput`
- 外部依赖: `pydantic` (BaseModel, ConfigDict, Field), `typing` (Any, Literal)

#### §3.2.3 关键逻辑 / 数据流

- `CaseGenerationRequest` 是整个工作流的入口模型，在 FastAPI 端点接收后被嵌入 `GlobalState.request`。
- `CaseGenerationRun` 是工作流完成后的出口模型，聚合了文档解析、研究输出、测试用例、质量报告、迭代摘要等所有产物。
- `llm_config` / `model_config` 的别名设计是 Pydantic v2 迁移的典型技巧——避免与 `BaseModel.model_config` 保留属性冲突。
- `status` 使用 `Literal` 而非 `RunStatus` 枚举，保持 API 序列化输出为纯字符串。

---

### §3.3 `case_models.py`

- **路径**: `app/domain/case_models.py`
- **行数**: 56
- **职责**: 定义测试用例（`TestCase`）和质量报告（`QualityReport`）——工作流最终输出的核心模型

#### §3.3.1 核心内容

##### 类 `TestCase(BaseModel)`

单个测试用例。设置了 `__test__ = False` 类属性以防止 pytest 误将其识别为测试类。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `id` | `str` | *(必填)* | — | 用例编号（如 TC-001） |
| `title` | `str` | *(必填)* | — | 用例标题 |
| `preconditions` | `list[str]` | `[]` | — | 前置条件列表 |
| `steps` | `list[str]` | `[]` | — | 操作步骤列表 |
| `expected_results` | `list[str]` | `[]` | — | 预期结果列表 |
| `priority` | `str` | `"P2"` | — | 优先级（P0-P3） |
| `category` | `str` | `"functional"` | — | 用例类别 |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | — | PRD 原文证据引用 |
| `checkpoint_id` | `str` | `""` | — | 所属检查点标识 |
| `project_id` | `str` | `""` | — | 所属项目 ID |

**特殊属性**: `__test__ = False` — 这是 pytest 的约定，任何名称以 `Test` 开头的类都会被视为测试类。此属性显式关闭该行为。

##### 类 `QualityReport(BaseModel)`

测试用例质量报告，记录后处理阶段的各项指标。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `duplicate_groups` | `list[list[str]]` | `[]` | — | 去重分组（每组为重复用例 ID 列表） |
| `coverage_notes` | `list[str]` | `[]` | — | 覆盖率评估备注 |
| `warnings` | `list[str]` | `[]` | — | 质量警告信息 |
| `repaired_fields` | `list[str]` | `[]` | — | 自动修复的字段列表 |
| `checkpoint_warnings` | `list[str]` | `[]` | — | 检查点层面的质量告警 |
| `missing_required_modules` | `list[str]` | `[]` | — | 缺失的必需模块列表 |

#### §3.3.2 依赖关系

- 内部依赖: `app.domain.research_models` → `EvidenceRef`
- 外部依赖: `pydantic` (BaseModel, Field)

#### §3.3.3 关键逻辑 / 数据流

- `TestCase` 通过 `checkpoint_id` 字段关联到 `Checkpoint`，通过 `evidence_refs` 关联到 `EvidenceRef`，构成 **fact → checkpoint → testcase** 的完整追溯链路。
- `QualityReport` 在工作流的后处理/评估阶段填充，反馈用例质量状况。
- 所有列表字段均使用 `Field(default_factory=list)` 以避免可变默认值陷阱。

---

### §3.4 `checkpoint_models.py`

- **路径**: `app/domain/checkpoint_models.py`
- **行数**: 77
- **职责**: 定义检查点模型——fact 与 test case 之间的中间层，以及基于 SHA-256 的稳定 ID 生成函数

#### §3.4.1 核心内容

##### 类 `Checkpoint(BaseModel)`

单个检查点，代表从业务事实中提炼的可验证测试点。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `checkpoint_id` | `str` | `""` | — | 基于哈希的唯一标识 |
| `title` | `str` | *(必填)* | — | 检查点标题 |
| `objective` | `str` | `""` | — | 验证目标 |
| `category` | `str` | `"functional"` | — | 类别 |
| `risk` | `str` | `"medium"` | — | 风险等级 |
| `branch_hint` | `str` | `""` | — | 测试分支提示 |
| `fact_ids` | `list[str]` | `[]` | — | 上游事实 ID 列表 |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | — | PRD 原文证据引用 |
| `preconditions` | `list[str]` | `[]` | — | 前置条件 |
| `coverage_status` | `str` | `"uncovered"` | — | 覆盖状态 |

##### 类 `CheckpointCoverage(BaseModel)`

单个 checkpoint 的用例覆盖记录。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `checkpoint_id` | `str` | *(必填)* | — | 对应的 checkpoint 标识 |
| `covered_by_test_ids` | `list[str]` | `[]` | — | 覆盖该 checkpoint 的测试用例 ID 列表 |
| `coverage_status` | `str` | `"uncovered"` | — | 覆盖状态 |

##### 函数 `generate_checkpoint_id(fact_ids: list[str], title: str) -> str`

基于 fact_ids 和 title 生成稳定的 checkpoint ID。算法: 将 `sorted(fact_ids)` 用 `|` 连接，拼接 `||` 分隔符后追加 `title.strip().casefold()`，取 SHA-256 哈希前 8 位。输出格式: `CP-<hash8>`。

#### §3.4.2 依赖关系

- 内部依赖: `app.domain.research_models` → `EvidenceRef`
- 外部依赖: `pydantic` (BaseModel, Field), `hashlib`

#### §3.4.3 关键逻辑 / 数据流

- `Checkpoint` 是 **fact → checkpoint → testcase** 三层链路的中间锚点。
- `fact_ids` 字段指向上游 `ResearchFact.fact_id`，`checkpoint_id` 被下游 `TestCase.checkpoint_id` 引用。
- `CheckpointCoverage` 是评估阶段的覆盖度追踪模型。
- `coverage_status` 的三值状态（uncovered/partial/covered）驱动评估回路是否触发重试。

---

### §3.5 `document_models.py`

- **路径**: `app/domain/document_models.py`
- **行数**: 58
- **职责**: 定义 PRD 文档解析后的结构化表示

#### §3.5.1 核心内容

##### 类 `DocumentSource(BaseModel)`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source_path` | `str` | *(必填)* | 原始文件路径 |
| `source_type` | `str` | *(必填)* | 文件类型 |
| `title` | `str` | `""` | 文档标题 |
| `checksum` | `str` | `""` | 内容校验和 |

##### 类 `DocumentSection(BaseModel)`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `heading` | `str` | *(必填)* | 章节标题文本 |
| `level` | `int` | *(必填)* | 标题层级 |
| `content` | `str` | `""` | 章节正文 |
| `line_start` | `int` | *(必填)* | 起始行号 |
| `line_end` | `int` | *(必填)* | 结束行号 |

##### 类 `ParsedDocument(BaseModel)`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `raw_text` | `str` | *(必填)* | 原始全文 |
| `sections` | `list[DocumentSection]` | `[]` | 按章节拆分的结构化数据 |
| `references` | `list[str]` | `[]` | 文档引用列表 |
| `metadata` | `dict[str, Any]` | `{}` | 元数据字典 |
| `source` | `DocumentSource \| None` | `None` | 文档来源信息 |

#### §3.5.2 依赖关系

- 内部依赖: 无
- 外部依赖: `pydantic` (BaseModel, Field), `typing` (Any)

#### §3.5.3 关键逻辑 / 数据流

- `ParsedDocument` 是工作流最前端的产物，由文档解析节点生成后注入 `GlobalState.parsed_document`。
- `DocumentSection.line_start` / `line_end` 与 `EvidenceRef.line_start` / `line_end` 对应，支持精确的行号级引用追溯。

---

### §3.6 `project_models.py`

- **路径**: `app/domain/project_models.py`
- **行数**: 68
- **职责**: 定义项目级上下文信息

#### §3.6.1 核心内容

##### 枚举 `ProjectType(str, Enum)`

7 个成员: WEB_APP, MOBILE_APP, API_SERVICE, DATA_PIPELINE, EMBEDDED, DESKTOP, OTHER

##### 枚举 `RegulatoryFramework(str, Enum)`

8 个成员: DO_178C, IEC_62304, ISO_26262, IEC_61508, GDPR, HIPAA, SOC2, CUSTOM

##### 类 `ProjectContext(BaseModel)`

项目上下文不可变快照。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `id` | `str` | `uuid4().hex` | — | 项目唯一 ID |
| `name` | `str` | *(必填)* | `min_length=1, max_length=200` | 项目名称 |
| `description` | `str` | `""` | `max_length=5000` | 项目描述 |
| `project_type` | `ProjectType` | `OTHER` | — | 项目类型 |
| `regulatory_frameworks` | `list[RegulatoryFramework]` | `[]` | — | 适用的合规框架 |
| `tech_stack` | `list[str]` | `[]` | — | 技术栈 |
| `custom_standards` | `list[str]` | `[]` | — | 自定义标准 |
| `metadata` | `dict[str, Any]` | `{}` | — | 元数据 |
| `created_at` | `datetime` | `utcnow()` | — | 创建时间 |
| `updated_at` | `datetime` | `utcnow()` | — | 更新时间 |

**方法 `summary_text() -> str`**: 生成适合注入 LLM prompt 的摘要文本。

#### §3.6.2 依赖关系

- 外部依赖: `pydantic`, `enum`, `datetime`, `uuid`

---

### §3.7 `research_models.py`

- **路径**: `app/domain/research_models.py`
- **行数**: 254
- **职责**: PRD 上下文研究阶段的数据结构，含最复杂的 `model_validator` 链路

#### §3.7.1 核心内容

##### 类 `EvidenceRef(BaseModel)`

PRD 原文证据引用，全项目最基础的引用模型。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `section_title` | `str` | *(必填)* | 引用来源章节标题 |
| `excerpt` | `str` | `""` | 摘录片段 |
| `line_start` | `int` | `0` | 起始行号 |
| `line_end` | `int` | `0` | 结束行号 |
| `confidence` | `float` | `0.0` | 置信度 |

**model_validator**: `coerce_string_reference` — 处理字符串/dict/空值输入归一化。

##### 类 `ResearchFact(BaseModel)`

从 PRD 中提取的业务事实。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fact_id` | `str` | `""` | 事实唯一标识 |
| `description` | `str` | *(必填)* | 事实描述 |
| `source_section` | `str` | `""` | 来源章节 |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | 证据引用 |
| `category` | `str` | `"requirement"` | 类别 |
| `requirement` | `str` | `""` | 需求描述 |
| `branch_hint` | `str` | `""` | 分支提示 |

**model_validator**: `coerce_requirement_object` — 处理遗留字段名映射。

##### 类 `PlannedScenario(BaseModel)`

规划的测试场景（title, fact_id, category, risk, rationale, branch_hint）。

##### 类 `ResearchOutput(BaseModel)`

上下文研究的完整输出（feature_topics, user_scenarios, constraints, ambiguities, test_signals, facts）。

**model_validator**: `coerce_dict_items_to_str` — 将 list[dict] 格式的 LLM 输出转换为 list[str]。

#### §3.7.2 依赖关系

- 外部依赖: `pydantic`, `re`, `typing`

#### §3.7.3 关键逻辑 / 数据流

三个 `model_validator(mode="before")` 构成 LLM 输出归一化适配器（防腐层）。`ResearchFact` → `Checkpoint` → `TestCase` 构成三层追溯链。

---

### §3.8 `run_state.py`

- **路径**: `app/domain/run_state.py`
- **行数**: 119
- **职责**: 迭代评估回路的运行状态模型

#### §3.8.1 核心内容

##### 枚举 `RunStatus(str, Enum)`

6 个状态: PENDING, RUNNING, EVALUATING, RETRYING, SUCCEEDED, FAILED

##### 枚举 `RunStage(str, Enum)`

6 个阶段: CONTEXT_RESEARCH, CHECKPOINT_GENERATION, DRAFT_GENERATION, EVALUATION, OUTPUT_DELIVERY, XMIND_DELIVERY

##### 类 `EvaluationDimension(BaseModel)` — 单个评估维度结果
##### 类 `EvaluationReport(BaseModel)` — 结构化评估报告
##### 类 `RetryDecision(BaseModel)` — 回流决策记录
##### 类 `IterationRecord(BaseModel)` — 单轮迭代记录
##### 类 `RunState(BaseModel)` — 完整运行状态对象

`RunState` 字段包括: run_id, status, current_stage, iteration_index, max_iterations(=3), last_evaluation_score, last_evaluation_summary, retry_reason, artifacts, timestamps, iteration_history, retry_decisions, error, project_id。

#### §3.8.2 依赖关系

- 外部依赖: `pydantic`, `enum`, `typing`

#### §3.8.3 关键逻辑 / 数据流

`RunState` 是迭代评估回路的中枢。状态机: `PENDING → RUNNING → EVALUATING → (RETRYING → RUNNING →)* SUCCEEDED/FAILED`。`EvaluationReport.pass_threshold = 0.7` 是默认通过阈值。

---

### §3.9 `state.py`

- **路径**: `app/domain/state.py`
- **行数**: 71
- **职责**: LangGraph 工作流 TypedDict 状态定义

#### §3.9.1 核心内容

##### 类 `GlobalState(TypedDict, total=False)`

主工作流全局状态，21 个字段，涵盖工作流全生命周期数据。`total=False` 表示所有字段均为可选，与 LangGraph 增量更新模式一致。

##### 类 `CaseGenState(TypedDict, total=False)`

用例生成子图的局部状态，10 个字段，是 `GlobalState` 的子集。

#### §3.9.2 依赖关系

- 引用了除 `project_models.py` 和 `xmind_models.py` 之外的所有域模型文件中的类型

#### §3.9.3 关键逻辑 / 数据流

- `GlobalState` 是 LangGraph 主工作流的状态总线
- `total=False` 是关键设计决策：允许节点只返回变更字段
- `draft_cases` vs `test_cases` 体现了"草稿 → 质检 → 最终"的两阶段流程

---

### §3.10 `xmind_models.py`

- **路径**: `app/domain/xmind_models.py`
- **行数**: 55
- **职责**: XMind 思维导图生成与交付的数据结构

#### §3.10.1 核心内容

##### 类 `XMindNode(BaseModel)` — 递归嵌套的思维导图节点（title, children, markers, notes, labels）
##### 类 `XMindDeliveryResult(BaseModel)` — 交付结果（success, file_path, map_url, map_id, error_message, delivery_time）

---

## §4 目录级依赖关系

### §4.1 依赖层次

| 层级 | 模块 | 说明 |
|------|------|------|
| **L0 (基础层)** | `research_models.py`, `document_models.py`, `project_models.py`, `run_state.py`, `xmind_models.py` | 无内部依赖 |
| **L1 (组合层)** | `case_models.py`, `checkpoint_models.py` | 依赖 L0 的 `EvidenceRef` |
| **L2 (聚合层)** | `api_models.py` | 依赖 L0 + L1 |
| **L3 (总线层)** | `state.py` | 依赖 L0 + L1 + L2，汇聚所有类型 |

### §4.2 外部依赖汇总

| 包 | 使用模块 | 用途 |
|----|----------|------|
| `pydantic` (v2) | 除 `__init__.py` 和 `state.py` 外的所有文件 | BaseModel, Field, ConfigDict, model_validator |
| `typing` | 全部 | TypedDict, Any, Literal |
| `enum` | `project_models.py`, `run_state.py` | str Enum |
| `hashlib` | `checkpoint_models.py` | SHA-256 哈希 |
| `re` | `research_models.py` | 正则表达式匹配 |
| `datetime` | `project_models.py`, `xmind_models.py` | 时间戳 |
| `uuid` | `project_models.py` | UUID 生成 |

---

## §5 设计模式与架构特征

### §5.1 贫血领域模型 (Anemic Domain Model)

所有模型类几乎不包含业务逻辑方法（唯一例外是 `ProjectContext.summary_text()`），仅作为数据容器。业务逻辑分布在工作流节点函数中。

### §5.2 LLM 输出归一化适配器

`research_models.py` 中的三个 `model_validator(mode="before")` 构成了一个防腐层 (Anti-Corruption Layer)，吸收不同 LLM 返回格式的差异。

### §5.3 三层追溯链路

```
ResearchFact (fact_id)
    → Checkpoint (fact_ids[], checkpoint_id)
        → TestCase (checkpoint_id, evidence_refs[])
            → EvidenceRef (section_title, line_start, line_end)
                → DocumentSection (heading, line_start, line_end)
```

### §5.4 TypedDict 增量状态模式

`state.py` 使用 `TypedDict(total=False)` 而非 Pydantic BaseModel 定义工作流状态——LangGraph 框架的惯用模式。

### §5.5 稳定哈希 ID 生成

`generate_checkpoint_id()` 使用确定性哈希（排序 + casefold + SHA-256）生成 checkpoint ID。

### §5.6 str-Enum 双继承序列化

所有枚举均采用 `(str, Enum)` 双继承，确保 JSON 序列化时输出字符串值。

---

## §6 潜在关注点

### §6.1 字段验证宽松

大部分字符串字段无长度/格式约束。`priority`、`category`、`risk`、`coverage_status` 等枚举语义字段使用 `str` 而非 `Literal` 或 `Enum`。

### §6.2 `datetime.utcnow()` 弃用警告

`project_models.py` 中使用了 Python 3.12+ 已弃用的 `datetime.utcnow()`。

### §6.3 `CaseGenerationRun.status` 类型不一致

API 层使用 `Literal[...]`，状态层使用 `RunStatus` 枚举，两者值域相同但类型不同。

### §6.4 递归模型的序列化深度

`XMindNode` 的递归 `children` 字段在深层嵌套时可能导致性能问题。

### §6.5 `__init__.py` 未定义 `__all__`

消费者需要通过完整路径 `from app.domain.xxx import Yyy` 导入。

### §6.6 model_validator 的鲁棒性边界

`EvidenceRef.coerce_string_reference` 的正则在 LLM 输出格式略有偏差时可能导致解析降级。

### §6.7 `XMindDeliveryResult.delivery_time` 使用本地时间

`datetime.now().isoformat()` 在跨时区部署时缺少时区信息。
