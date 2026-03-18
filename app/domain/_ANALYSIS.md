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
| `category` | `str` | `"functional"` | — | 类别（functional/edge_case/performance/security） |
| `risk` | `str` | `"medium"` | — | 风险等级（low/medium/high） |
| `branch_hint` | `str` | `""` | — | 测试分支提示 |
| `fact_ids` | `list[str]` | `[]` | — | 上游事实 ID 列表 |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | — | PRD 原文证据引用 |
| `preconditions` | `list[str]` | `[]` | — | 前置条件 |
| `coverage_status` | `str` | `"uncovered"` | — | 覆盖状态（uncovered/partial/covered） |

##### 类 `CheckpointCoverage(BaseModel)`

单个 checkpoint 的用例覆盖记录。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `checkpoint_id` | `str` | *(必填)* | — | 对应的 checkpoint 标识 |
| `covered_by_test_ids` | `list[str]` | `[]` | — | 覆盖该 checkpoint 的测试用例 ID 列表 |
| `coverage_status` | `str` | `"uncovered"` | — | 覆盖状态 |

##### 函数 `generate_checkpoint_id(fact_ids: list[str], title: str) -> str`

基于 fact_ids 和 title 生成稳定的 checkpoint ID。

- **算法**: 将 `sorted(fact_ids)` 用 `|` 连接，拼接 `||` 分隔符后追加 `title.strip().casefold()`，取 SHA-256 哈希前 8 位。
- **输出格式**: `CP-<hash8>`（如 `CP-a1b2c3d4`）
- **幂等性**: 相同输入始终产生相同 ID，支持增量更新与评估回路的可比性。
- **排序处理**: `fact_ids` 先排序再拼接，确保不同顺序的相同输入产生相同哈希。
- **大小写处理**: `title` 使用 `casefold()` 进行 Unicode 感知的小写化。

```python
raw = "|".join(sorted(fact_ids)) + "||" + title.strip().casefold()
digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
return f"CP-{digest}"
```

#### §3.4.2 依赖关系

- 内部依赖: `app.domain.research_models` → `EvidenceRef`
- 外部依赖: `pydantic` (BaseModel, Field), `hashlib`

#### §3.4.3 关键逻辑 / 数据流

- `Checkpoint` 是 **fact → checkpoint → testcase** 三层链路的中间锚点。
- `fact_ids` 字段指向上游 `ResearchFact.fact_id`，`checkpoint_id` 被下游 `TestCase.checkpoint_id` 引用。
- `CheckpointCoverage` 是评估阶段的覆盖度追踪模型，在 `GlobalState.checkpoint_coverage` 中维护。
- `coverage_status` 的三值状态（uncovered/partial/covered）驱动评估回路是否触发重试。

---

### §3.5 `document_models.py`

- **路径**: `app/domain/document_models.py`
- **行数**: 58
- **职责**: 定义 PRD 文档解析后的结构化表示，包含文档来源、章节结构和完整解析结果

#### §3.5.1 核心内容

##### 类 `DocumentSource(BaseModel)`

文档来源元信息。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `source_path` | `str` | *(必填)* | — | 原始文件路径 |
| `source_type` | `str` | *(必填)* | — | 文件类型 |
| `title` | `str` | `""` | — | 文档标题 |
| `checksum` | `str` | `""` | — | 内容校验和（SHA-256） |

##### 类 `DocumentSection(BaseModel)`

文档中的一个章节。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `heading` | `str` | *(必填)* | — | 章节标题文本 |
| `level` | `int` | *(必填)* | — | 标题层级（1=`#`，2=`##`...） |
| `content` | `str` | `""` | — | 章节正文（不含标题行） |
| `line_start` | `int` | *(必填)* | — | 起始行号（从 1 开始） |
| `line_end` | `int` | *(必填)* | — | 结束行号（含） |

##### 类 `ParsedDocument(BaseModel)`

完整的文档解析结果。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `raw_text` | `str` | *(必填)* | — | 原始全文（供 LLM prompt 引用） |
| `sections` | `list[DocumentSection]` | `[]` | — | 按章节拆分的结构化数据 |
| `references` | `list[str]` | `[]` | — | 文档引用列表 |
| `metadata` | `dict[str, Any]` | `{}` | — | 元数据字典 |
| `source` | `DocumentSource \| None` | `None` | — | 文档来源信息 |

#### §3.5.2 依赖关系

- 内部依赖: 无
- 外部依赖: `pydantic` (BaseModel, Field), `typing` (Any)

#### §3.5.3 关键逻辑 / 数据流

- `ParsedDocument` 是工作流最前端的产物，由文档解析节点生成后注入 `GlobalState.parsed_document`。
- `raw_text` 保留原始全文供 LLM 直接使用，`sections` 提供结构化索引用于证据引用定位。
- `DocumentSection.line_start` / `line_end` 与 `EvidenceRef.line_start` / `line_end` 对应，支持精确的行号级引用追溯。
- `DocumentSource.checksum` 可用于缓存判断，避免相同文档重复解析。

---

### §3.6 `project_models.py`

- **路径**: `app/domain/project_models.py`
- **行数**: 68
- **职责**: 定义项目级上下文信息，包含项目类型枚举、合规框架枚举和项目上下文快照模型

#### §3.6.1 核心内容

##### 枚举 `ProjectType(str, Enum)`

支持的项目/技术类型。

| 成员 | 值 | 说明 |
|------|-----|------|
| `WEB_APP` | `"web_app"` | Web 应用 |
| `MOBILE_APP` | `"mobile_app"` | 移动应用 |
| `API_SERVICE` | `"api_service"` | API 服务 |
| `DATA_PIPELINE` | `"data_pipeline"` | 数据管道 |
| `EMBEDDED` | `"embedded"` | 嵌入式系统 |
| `DESKTOP` | `"desktop"` | 桌面应用 |
| `OTHER` | `"other"` | 其他 |

##### 枚举 `RegulatoryFramework(str, Enum)`

已知的法规/标准框架。

| 成员 | 值 | 说明 |
|------|-----|------|
| `DO_178C` | `"DO-178C"` | 航空软件安全标准 |
| `IEC_62304` | `"IEC-62304"` | 医疗设备软件生命周期 |
| `ISO_26262` | `"ISO-26262"` | 汽车功能安全 |
| `IEC_61508` | `"IEC-61508"` | 工业功能安全 |
| `GDPR` | `"GDPR"` | 欧盟数据保护条例 |
| `HIPAA` | `"HIPAA"` | 美国健康保险可携性法案 |
| `SOC2` | `"SOC2"` | 服务组织控制标准 |
| `CUSTOM` | `"custom"` | 自定义标准 |

##### 类 `ProjectContext(BaseModel)`

项目上下文不可变快照，存储一次，被所有 run 引用。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `id` | `str` | `uuid4().hex` | `Field(default_factory=lambda: uuid4().hex)` | 项目唯一 ID |
| `name` | `str` | *(必填)* | `min_length=1, max_length=200` | 项目名称 |
| `description` | `str` | `""` | `max_length=5000` | 项目描述 |
| `project_type` | `ProjectType` | `ProjectType.OTHER` | — | 项目类型 |
| `regulatory_frameworks` | `list[RegulatoryFramework]` | `[]` | — | 适用的合规框架列表 |
| `tech_stack` | `list[str]` | `[]` | — | 技术栈 |
| `custom_standards` | `list[str]` | `[]` | — | 自定义标准 |
| `metadata` | `dict[str, Any]` | `{}` | — | 元数据 |
| `created_at` | `datetime` | `datetime.utcnow()` | — | 创建时间 |
| `updated_at` | `datetime` | `datetime.utcnow()` | — | 更新时间 |

**方法 `summary_text() -> str`**: 生成适合注入 LLM prompt 的一段话摘要。拼接逻辑：
1. 始终包含 `Project '{name}'`
2. 有描述时追加 `— {description}`
3. 非 OTHER 类型时追加 `Type: {value}.`
4. 有合规框架时追加 `Regulatory frameworks: {names}.`
5. 有技术栈时追加 `Tech stack: {items}.`
6. 有自定义标准时追加 `Custom standards: {items}.`

#### §3.6.2 依赖关系

- 内部依赖: 无
- 外部依赖: `pydantic` (BaseModel, Field), `enum` (Enum), `datetime`, `uuid`

#### §3.6.3 关键逻辑 / 数据流

- `ProjectContext` 通过 `project_id` 被 `CaseGenerationRequest`、`CaseGenerationRun`、`RunState`、`TestCase` 等多个模型引用。
- `summary_text()` 方法的输出注入到 `GlobalState.project_context_summary`，供 LLM 节点感知项目上下文。
- `name` 字段的 `min_length=1` 约束确保项目名称非空——这是该目录下少数几个带显式验证约束的字段之一。
- 两个枚举均继承 `str, Enum`，确保 JSON 序列化时输出字符串值而非枚举名。

---

### §3.7 `research_models.py`

- **路径**: `app/domain/research_models.py`
- **行数**: 254
- **职责**: 定义 PRD 上下文研究阶段的数据结构，含最复杂的 `model_validator` 链路以兼容不同 LLM 输出格式

#### §3.7.1 核心内容

##### 模块级常量

```python
EVIDENCE_REF_PATTERN = re.compile(
    r"^\s*(?P<section>.+?)\s*\((?P<line_start>\d+)(?:-(?P<line_end>\d+))?\)\s*:\s*(?P<excerpt>.*)\s*$"
)
```

正则表达式，匹配格式如 `"章节标题 (10-20): 摘录文本"` 的证据引用字符串。

##### 类 `EvidenceRef(BaseModel)`

PRD 原文证据引用，是全项目最基础的引用模型。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `section_title` | `str` | *(必填)* | — | 引用来源章节标题 |
| `excerpt` | `str` | `""` | — | 摘录片段 |
| `line_start` | `int` | `0` | — | 起始行号 |
| `line_end` | `int` | `0` | — | 结束行号 |
| `confidence` | `float` | `0.0` | — | 置信度 |

**model_validator (`mode="before"`)**: `coerce_string_reference` — 处理三种输入形态：

1. **dict 输入**: 做字段名归一化
   - `section` → `section_title`
   - `quote` → `excerpt`
2. **str 输入 — 匹配正则**: 解析 `"章节 (行号-行号): 摘录"` 格式
3. **str 输入 — 含冒号**: 按 `":"` 分割为 `section_title` + `excerpt`
4. **str 输入 — 纯文本**: 整个字符串作为 `section_title`
5. **空字符串**: 返回 `{"section_title": "generated_ref"}`

##### 类 `ResearchFact(BaseModel)`

从 PRD 中提取的业务变化事实。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `fact_id` | `str` | `""` | — | 事实唯一标识（如 FACT-001） |
| `description` | `str` | *(必填)* | — | 事实描述 |
| `source_section` | `str` | `""` | — | 来源章节标题 |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | — | PRD 证据引用 |
| `category` | `str` | `"requirement"` | — | 类别（requirement/constraint/assumption/behavior） |
| `requirement` | `str` | `""` | — | 需求描述 |
| `branch_hint` | `str` | `""` | — | 分支提示 |

**model_validator (`mode="before"`)**: `coerce_requirement_object` — 处理遗留字段名映射：
- `id` → `fact_id`
- `summary` → `description`
- `section_title` → `source_section`
- `change_type` → `category`
- 若 `requirement` 是 dict 类型（含 `scope` / `detail`），则拼接为 `"scope | detail"` 字符串

##### 类 `PlannedScenario(BaseModel)`

规划的测试场景。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `title` | `str` | *(必填)* | — | 场景标题 |
| `fact_id` | `str` | `""` | — | 关联的事实 ID |
| `category` | `str` | `"functional"` | — | 场景类别 |
| `risk` | `str` | `"medium"` | — | 风险等级 |
| `rationale` | `str` | `""` | — | 选择理由 |
| `branch_hint` | `str` | `""` | — | 分支提示 |

##### 辅助函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `_value_to_str` | `(value: object) -> str` | 将任意值转为紧凑字符串，list 用 `, ` 连接 |
| `_extract_text_from_dict` | `(d: dict, primary_key: str) -> str` | 从 LLM 返回的 dict 中提取人类可读字符串；优先取 primary_key，其余用 ` \| ` 连接 |

##### 模块级常量 `_PRIMARY_KEY_MAP`

```python
_PRIMARY_KEY_MAP: dict[str, str] = {
    "feature_topics": "topic",
    "user_scenarios": "scenario",
    "constraints": "constraint",
    "ambiguities": "ambiguity",
    "test_signals": "signal",
}
```

映射 `ResearchOutput` 的列表字段名到 dict 元素中的预期主键。

##### 类 `ResearchOutput(BaseModel)`

上下文研究的完整输出。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `feature_topics` | `list[str]` | `[]` | — | 功能主题列表 |
| `user_scenarios` | `list[str]` | `[]` | — | 用户场景列表 |
| `constraints` | `list[str]` | `[]` | — | 约束条件列表 |
| `ambiguities` | `list[str]` | `[]` | — | 歧义/模糊点列表 |
| `test_signals` | `list[str]` | `[]` | — | 测试信号列表 |
| `facts` | `list[ResearchFact]` | `[]` | — | 结构化事实列表 |

**model_validator (`mode="before"`)**: `coerce_dict_items_to_str` — 遍历 `_PRIMARY_KEY_MAP` 中的 5 个字段，将 `list[dict]` 格式的 LLM 输出智能转换为 `list[str]`：
- `str` 元素：保留
- `dict` 元素：通过 `_extract_text_from_dict` 提取主键值并拼接其余字段
- 其他类型：`str()` 转换

#### §3.7.2 依赖关系

- 内部依赖: 无（`EvidenceRef` 定义在本文件内，被其他模块引用）
- 外部依赖: `pydantic` (BaseModel, Field, model_validator), `re`, `typing` (Any)

#### §3.7.3 关键逻辑 / 数据流

- `EvidenceRef` 是全项目引用最频繁的基础模型，被 `TestCase`、`Checkpoint`、`ResearchFact` 三个模型引用。
- 三个 `model_validator(mode="before")` 验证器构成了 LLM 输出兼容层的核心：
  - `EvidenceRef.coerce_string_reference` — 处理字符串/dict/空值 → 标准化 dict
  - `ResearchFact.coerce_requirement_object` — 处理遗留字段名 + 嵌套 requirement dict
  - `ResearchOutput.coerce_dict_items_to_str` — 处理 list[dict] → list[str] 批量转换
- 这些验证器本质上是 **LLM 输出归一化适配器**，确保不同模型（GPT-4、Claude 等）返回的结构差异被统一吸收。
- `ResearchFact` → `Checkpoint`（通过 `fact_ids`）→ `TestCase`（通过 `checkpoint_id`）构成三层追溯链。

---

### §3.8 `run_state.py`

- **路径**: `app/domain/run_state.py`
- **行数**: 119
- **职责**: 定义迭代评估回路的运行状态模型，包含 2 个枚举和 5 个 Pydantic 模型

#### §3.8.1 核心内容

##### 枚举 `RunStatus(str, Enum)`

运行状态枚举。

| 成员 | 值 | 说明 |
|------|-----|------|
| `PENDING` | `"pending"` | 待运行 |
| `RUNNING` | `"running"` | 运行中 |
| `EVALUATING` | `"evaluating"` | 评估中 |
| `RETRYING` | `"retrying"` | 回流重试中 |
| `SUCCEEDED` | `"succeeded"` | 成功 |
| `FAILED` | `"failed"` | 失败 |

##### 枚举 `RunStage(str, Enum)`

运行阶段枚举。

| 成员 | 值 | 说明 |
|------|-----|------|
| `CONTEXT_RESEARCH` | `"context_research"` | 上下文研究 |
| `CHECKPOINT_GENERATION` | `"checkpoint_generation"` | 检查点生成 |
| `DRAFT_GENERATION` | `"draft_generation"` | 草稿生成 |
| `EVALUATION` | `"evaluation"` | 评估 |
| `OUTPUT_DELIVERY` | `"output_delivery"` | 输出交付 |
| `XMIND_DELIVERY` | `"xmind_delivery"` | XMind 交付 |

##### 类 `EvaluationDimension(BaseModel)`

单个评估维度的结果。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `name` | `str` | *(必填)* | — | 维度名称 |
| `score` | `float` | `0.0` | — | 得分 |
| `max_score` | `float` | `1.0` | — | 最大分 |
| `details` | `str` | `""` | — | 详情说明 |
| `failed_items` | `list[str]` | `[]` | — | 失败项列表 |

##### 类 `EvaluationReport(BaseModel)`

结构化评估报告，对应 PRD 要求的 `evaluation_report.json`。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `overall_score` | `float` | `0.0` | — | 总体评估分数 |
| `dimensions` | `list[EvaluationDimension]` | `[]` | — | 各维度评估结果 |
| `critical_failures` | `list[str]` | `[]` | — | 关键失败项 |
| `suggested_retry_stage` | `str \| None` | `None` | — | 建议回流阶段 |
| `improvement_summary` | `str` | `""` | — | 改进摘要 |
| `comparison_with_previous` | `str` | `""` | — | 与上轮对比 |
| `pass_threshold` | `float` | `0.7` | — | 通过阈值 |

##### 类 `RetryDecision(BaseModel)`

回流决策记录。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `iteration_index` | `int` | *(必填)* | — | 迭代轮次 |
| `retry_reason` | `str` | *(必填)* | — | 回流原因 |
| `target_stage` | `str` | *(必填)* | — | 目标回流阶段 |
| `trigger_dimension` | `str` | `""` | — | 触发维度 |
| `previous_score` | `float` | `0.0` | — | 前一轮分数 |
| `timestamp` | `str` | `""` | — | 时间戳 |

##### 类 `IterationRecord(BaseModel)`

单轮迭代记录，对应 `iteration_log.json` 中的一条记录。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `iteration_index` | `int` | *(必填)* | — | 迭代轮次 |
| `stage` | `str` | `""` | — | 所在阶段 |
| `evaluation_score` | `float` | `0.0` | — | 评估分数 |
| `evaluation_summary` | `str` | `""` | — | 评估摘要 |
| `retry_reason` | `str` | `""` | — | 回流原因 |
| `retry_target_stage` | `str` | `""` | — | 回流目标阶段 |
| `artifacts_snapshot` | `dict[str, str]` | `{}` | — | 产物快照路径 |
| `timestamp` | `str` | `""` | — | 时间戳 |

##### 类 `RunState(BaseModel)`

完整运行状态对象，对应 `run_state.json`。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `run_id` | `str` | *(必填)* | — | 运行唯一标识 |
| `status` | `RunStatus` | `RunStatus.PENDING` | — | 当前运行状态 |
| `current_stage` | `RunStage` | `RunStage.CONTEXT_RESEARCH` | — | 当前运行阶段 |
| `iteration_index` | `int` | `0` | — | 当前迭代轮次 |
| `max_iterations` | `int` | `3` | — | 最大迭代次数 |
| `last_evaluation_score` | `float` | `0.0` | — | 最新评估分数 |
| `last_evaluation_summary` | `str` | `""` | — | 最新评估摘要 |
| `retry_reason` | `str` | `""` | — | 最新回流原因 |
| `artifacts` | `dict[str, str]` | `{}` | — | 产物路径映射 |
| `timestamps` | `dict[str, str]` | `{}` | — | 各阶段时间戳 |
| `iteration_history` | `list[IterationRecord]` | `[]` | — | 迭代历史记录 |
| `retry_decisions` | `list[RetryDecision]` | `[]` | — | 回流决策记录 |
| `error` | `dict[str, Any] \| None` | `None` | — | 错误信息 |
| `project_id` | `str \| None` | `None` | — | 项目 ID |

#### §3.8.2 依赖关系

- 内部依赖: 无
- 外部依赖: `pydantic` (BaseModel, Field), `enum` (Enum), `typing` (Any)

#### §3.8.3 关键逻辑 / 数据流

- `RunState` 是迭代评估回路的中枢，维护完整的运行生命周期状态。
- `RunStatus` 的 6 个状态对应工作流的状态机：`PENDING → RUNNING → EVALUATING → (RETRYING → RUNNING →)* SUCCEEDED/FAILED`。
- `RunStage` 的 6 个阶段与 LangGraph 工作流图的节点一一对应。
- `EvaluationReport.pass_threshold = 0.7` 是评估回路的默认通过阈值。
- `RunState.max_iterations = 3` 限制最大重试轮次，防止无限回流。
- `iteration_history` + `retry_decisions` 提供完整的决策审计跟踪。

---

### §3.9 `state.py`

- **路径**: `app/domain/state.py`
- **行数**: 71
- **职责**: 定义 LangGraph 工作流中流转的 TypedDict 状态结构

#### §3.9.1 核心内容

##### 类 `GlobalState(TypedDict, total=False)`

主工作流的全局状态。`total=False` 表示所有字段均为可选——与 LangGraph 增量更新模式一致，每个节点只需返回自己修改的字段。

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | `str` | 运行标识 |
| `file_path` | `str` | PRD 文件路径 |
| `language` | `str` | 输出语言 |
| `request` | `CaseGenerationRequest` | 原始请求 |
| `model_config` | `ModelConfigOverride` | LLM 配置 |
| `parsed_document` | `ParsedDocument` | 解析后文档 |
| `research_output` | `ResearchOutput` | 研究输出 |
| `planned_scenarios` | `list[PlannedScenario]` | 规划场景列表 |
| `checkpoints` | `list[Checkpoint]` | 检查点列表 |
| `checkpoint_coverage` | `list[CheckpointCoverage]` | 覆盖度记录 |
| `mapped_evidence` | `dict[str, list[EvidenceRef]]` | 证据映射表 |
| `draft_cases` | `list[TestCase]` | 草稿用例 |
| `test_cases` | `list[TestCase]` | 最终用例 |
| `quality_report` | `QualityReport` | 质量报告 |
| `artifacts` | `dict[str, str]` | 产物路径 |
| `error` | `ErrorInfo` | 错误信息 |
| `run_state` | `RunState` | 运行状态对象 |
| `evaluation_report` | `EvaluationReport` | 评估报告 |
| `iteration_index` | `int` | 当前迭代轮次 |
| `project_id` | `str` | 项目 ID |
| `project_context_summary` | `str` | 项目上下文摘要文本 |

共 21 个字段，涵盖工作流全生命周期数据。

##### 类 `CaseGenState(TypedDict, total=False)`

用例生成子图的局部状态。

| 字段 | 类型 | 说明 |
|------|------|------|
| `language` | `str` | 输出语言 |
| `parsed_document` | `ParsedDocument` | 解析后文档 |
| `research_output` | `ResearchOutput` | 研究输出 |
| `planned_scenarios` | `list[PlannedScenario]` | 规划场景列表 |
| `checkpoints` | `list[Checkpoint]` | 检查点列表 |
| `checkpoint_coverage` | `list[CheckpointCoverage]` | 覆盖度记录 |
| `mapped_evidence` | `dict[str, list[EvidenceRef]]` | 证据映射表 |
| `draft_cases` | `list[TestCase]` | 草稿用例 |
| `test_cases` | `list[TestCase]` | 最终用例 |
| `project_context_summary` | `str` | 项目上下文摘要 |

共 10 个字段，是 `GlobalState` 的子集。

#### §3.9.2 依赖关系

- 内部依赖:
  - `app.domain.api_models` → `CaseGenerationRequest`, `ErrorInfo`, `ModelConfigOverride`
  - `app.domain.case_models` → `QualityReport`, `TestCase`
  - `app.domain.checkpoint_models` → `Checkpoint`, `CheckpointCoverage`
  - `app.domain.document_models` → `ParsedDocument`
  - `app.domain.research_models` → `EvidenceRef`, `PlannedScenario`, `ResearchOutput`
  - `app.domain.run_state` → `EvaluationReport`, `RunState`
- 外部依赖: `typing` (TypedDict)

#### §3.9.3 关键逻辑 / 数据流

- `GlobalState` 是 LangGraph 主工作流的**状态总线**，所有节点通过读写该 TypedDict 的字段进行通信。
- `CaseGenState` 是用例生成子图的局部状态，仅包含子图节点所需的字段子集，实现状态隔离。
- `total=False` 是关键设计决策：LangGraph 的增量更新模式要求节点只返回变更字段，而非完整状态。
- `GlobalState` 引用了除 `project_models.py` 和 `xmind_models.py` 之外的所有域模型文件中的类型，是最大的类型汇聚点。
- `draft_cases` vs `test_cases` 的区分体现了"草稿 → 质检 → 最终"的两阶段用例产出流程。

---

### §3.10 `xmind_models.py`

- **路径**: `app/domain/xmind_models.py`
- **行数**: 55
- **职责**: 定义 XMind 思维导图生成与交付的数据结构

#### §3.10.1 核心内容

##### 类 `XMindNode(BaseModel)`

思维导图节点，支持递归嵌套子节点。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `title` | `str` | *(必填)* | — | 节点标题文本 |
| `children` | `list[XMindNode]` | `[]` | — | 子节点列表（递归引用） |
| `markers` | `list[str]` | `[]` | — | 标记列表（对应 XMind 图标） |
| `notes` | `str` | `""` | — | 备注文本 |
| `labels` | `list[str]` | `[]` | — | 标签列表 |

**递归结构**: `children: list[XMindNode]` 是自引用类型，Pydantic v2 通过 `from __future__ import annotations` 的延迟注解支持这种递归定义。这使得 `XMindNode` 可以表示任意深度的思维导图树。

##### 类 `XMindDeliveryResult(BaseModel)`

XMind 交付结果。

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `success` | `bool` | `False` | — | 交付是否成功 |
| `file_path` | `str` | `""` | — | 生成的 .xmind 文件路径 |
| `map_url` | `str` | `""` | — | 在线访问地址 |
| `map_id` | `str` | `""` | — | 思维导图唯一标识 |
| `error_message` | `str` | `""` | — | 失败时的错误信息 |
| `delivery_time` | `str` | `datetime.now().isoformat()` | `Field(default_factory=lambda: datetime.now().isoformat())` | 交付时间戳 |

#### §3.10.2 依赖关系

- 内部依赖: 无
- 外部依赖: `pydantic` (BaseModel, Field), `datetime`

#### §3.10.3 关键逻辑 / 数据流

- `XMindNode` 的递归树结构从 `TestCase` 列表映射而来，通常按 category → priority → individual case 三层组织。
- `XMindDeliveryResult` 作为 XMind 交付节点的输出，记录在 `RunState.artifacts` 中。
- `delivery_time` 使用 `default_factory` 而非直接默认值，确保每次实例化时取当前时间。

---

## §4 目录级依赖关系

### §4.1 内部模块依赖图

```
research_models.py          (无内部依赖 — 基础层)
    ↑
    ├── case_models.py          (引用 EvidenceRef)
    ├── checkpoint_models.py    (引用 EvidenceRef)
    │
    ├── api_models.py           (引用 case_models, document_models, research_models)
    │       ↑
    │       └── state.py        (引用 api_models + 几乎所有其他模块)
    │
    └── state.py                (引用 research_models, case_models, checkpoint_models,
                                 document_models, api_models, run_state)

document_models.py          (无内部依赖 — 基础层)
project_models.py           (无内部依赖 — 基础层)
run_state.py                (无内部依赖 — 基础层)
xmind_models.py             (无内部依赖 — 基础层)
```

### §4.2 依赖层次

| 层级 | 模块 | 说明 |
|------|------|------|
| **L0 (基础层)** | `research_models.py`, `document_models.py`, `project_models.py`, `run_state.py`, `xmind_models.py` | 无内部依赖 |
| **L1 (组合层)** | `case_models.py`, `checkpoint_models.py` | 依赖 L0 的 `EvidenceRef` |
| **L2 (聚合层)** | `api_models.py` | 依赖 L0 + L1 |
| **L3 (总线层)** | `state.py` | 依赖 L0 + L1 + L2，汇聚所有类型 |

### §4.3 外部依赖汇总

| 包 | 使用模块 | 用途 |
|----|----------|------|
| `pydantic` (v2) | 除 `__init__.py` 和 `state.py` 外的所有文件 | BaseModel, Field, ConfigDict, model_validator |
| `typing` / `typing_extensions` | 全部 | TypedDict, Any, Literal |
| `enum` | `project_models.py`, `run_state.py` | str Enum |
| `hashlib` | `checkpoint_models.py` | SHA-256 哈希 |
| `re` | `research_models.py` | 正则表达式匹配 |
| `datetime` | `project_models.py`, `xmind_models.py` | 时间戳 |
| `uuid` | `project_models.py` | UUID 生成 |

---

## §5 设计模式与架构特征

### §5.1 贫血领域模型 (Anemic Domain Model)

所有模型类几乎不包含业务逻辑方法（唯一例外是 `ProjectContext.summary_text()`），仅作为数据容器。业务逻辑分布在工作流节点函数中。这是 LangGraph 工作流架构下的典型选择——状态是数据，逻辑是节点。

### §5.2 LLM 输出归一化适配器

`research_models.py` 中的三个 `model_validator(mode="before")` 构成了一个**防腐层 (Anti-Corruption Layer)**：
- `EvidenceRef.coerce_string_reference` — 字符串 / dict / 空值 → 标准化模型
- `ResearchFact.coerce_requirement_object` — 遗留字段名兼容
- `ResearchOutput.coerce_dict_items_to_str` — list[dict] → list[str] 批量归一化

这些验证器吸收了不同 LLM 返回格式的差异，使下游代码无需关心 LLM 输出的结构变化。

### §5.3 三层追溯链路

```
ResearchFact (fact_id)
    → Checkpoint (fact_ids[], checkpoint_id)
        → TestCase (checkpoint_id, evidence_refs[])
            → EvidenceRef (section_title, line_start, line_end)
                → DocumentSection (heading, line_start, line_end)
```

这条链路实现了从 PRD 原文到最终测试用例的完整可追溯性。

### §5.4 TypedDict 增量状态模式

`state.py` 使用 `TypedDict(total=False)` 而非 Pydantic BaseModel 定义工作流状态，这是 LangGraph 框架的惯用模式：
- 节点函数返回 `dict` 而非完整状态对象
- 框架负责将返回值增量合并到全局状态
- `total=False` 允许部分更新而非强制完整赋值

### §5.5 稳定哈希 ID 生成

`generate_checkpoint_id()` 使用确定性哈希（排序 + casefold + SHA-256）生成 checkpoint ID，支持：
- 增量更新时的 ID 稳定性
- 评估回路中跨迭代的可比性
- 去重检测

### §5.6 str-Enum 双继承序列化

`ProjectType`、`RegulatoryFramework`、`RunStatus`、`RunStage` 均采用 `(str, Enum)` 双继承，确保 JSON 序列化时输出字符串值而非枚举名，与 FastAPI 的 JSON schema 生成和 Pydantic v2 的序列化行为一致。

---

## §6 潜在关注点

### §6.1 字段验证宽松

除 `ProjectContext.name` 的 `min_length=1, max_length=200` 和 `description` 的 `max_length=5000` 外，大部分字符串字段无长度/格式约束。`priority` 字段接受任意字符串而非限定为 `P0`-`P3` 枚举；`category`、`risk`、`coverage_status` 等枚举语义字段也使用 `str` 而非 `Literal` 或 `Enum`，存在非法值传入的风险。

### §6.2 `datetime.utcnow()` 弃用警告

`project_models.py` 中 `ProjectContext.created_at` 和 `updated_at` 使用 `datetime.utcnow()`，该方法在 Python 3.12+ 已被标记为弃用（建议改用 `datetime.now(timezone.utc)`）。

### §6.3 `CaseGenerationRun.status` 类型不一致

`CaseGenerationRun.status` 使用 `Literal[...]` 定义，而 `RunState.status` 使用 `RunStatus` 枚举。两者的值域相同但类型不同，在状态转换时需手动 `.value` 转换，是潜在的维护负担。

### §6.4 递归模型的序列化深度

`XMindNode` 的递归 `children` 字段在深层嵌套时可能导致序列化/反序列化性能问题。Pydantic v2 默认不限制递归深度。

### §6.5 `__init__.py` 未定义 `__all__`

包的 `__init__.py` 未导出任何符号，也未定义 `__all__`。消费者需要通过完整路径 `from app.domain.xxx import Yyy` 导入，无法使用 `from app.domain import *`。这是有意的设计（避免命名空间污染），但缺少便捷的 re-export 入口。

### §6.6 model_validator 的鲁棒性边界

`EvidenceRef.coerce_string_reference` 的正则 `EVIDENCE_REF_PATTERN` 要求严格的格式 `"章节 (行号): 摘录"`。如果 LLM 输出格式略有偏差（如多余空格、缺少冒号），会 fall through 到字符串分割逻辑，可能导致 `section_title` 包含行号信息。

### §6.7 `XMindDeliveryResult.delivery_time` 使用本地时间

`delivery_time` 的 `default_factory` 使用 `datetime.now().isoformat()` 生成本地时间字符串，在跨时区部署时缺少时区信息，建议使用 `datetime.now(timezone.utc).isoformat()`。