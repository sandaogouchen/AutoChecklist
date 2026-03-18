# app/nodes/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 12 | 分析策略: 业务逻辑

## §1 目录职责

`app/nodes/` 是 AutoChecklist 项目的**核心处理单元目录**，包含 LangGraph 工作流图中的全部节点实现。每个模块对应工作流中的一个独立处理阶段，节点签名统一遵循 `(state: State) -> State增量` 的 LangGraph 约定——接收全局/局部状态字典，返回需要合并的增量字段。

该目录实现了一条完整的**PRD → 测试用例**自动化生成流水线，核心流程为：

```
输入解析 → 项目上下文加载 → 上下文研究(LLM) → 场景规划 → 检查点生成(LLM)
→ 检查点评估 → 证据映射 → 草稿编写(LLM) → 结构组装 → 评估 → 反思
```

节点分为两大类：
- **纯逻辑节点**（直接函数）：`input_parser`、`scenario_planner`、`checkpoint_evaluator`、`evidence_mapper`、`structure_assembler`、`evaluation`、`reflection`
- **LLM 交互节点**（工厂函数 + 闭包）：`project_context_loader`、`context_research`、`checkpoint_generator`、`draft_writer`

工厂模式节点通过 `build_xxx_node(llm_client)` 在图构建时注入依赖，运行时通过闭包访问客户端实例。

---

## §2 文件清单

| 序号 | 文件名 | 行数(约) | 节点类型 | 核心职责 | 消费的 State 字段 | 产出的 State 字段 |
|------|--------|----------|----------|----------|-------------------|-------------------|
| 1 | `__init__.py` | ~5 | 包声明 | 定义子包，说明节点签名约定 | — | — |
| 2 | `input_parser.py` | ~45 | 纯逻辑 | 解析 PRD 文档为 `ParsedDocument` | `file_path`, `request` | `parsed_document` |
| 3 | `project_context_loader.py` | ~70 | 工厂(Service) | 加载项目上下文摘要文本 | `project_id` | `project_context_summary` |
| 4 | `context_research.py` | ~60 | 工厂(LLM) | LLM 提取测试相关上下文和结构化 facts | `parsed_document`, `project_context_summary`, `language`, `model_config` | `research_output` |
| 5 | `scenario_planner.py` | ~60 | 纯逻辑 | 从研究输出规划测试场景列表 | `research_output` | `planned_scenarios` |
| 6 | `checkpoint_generator.py` | ~180 | 工厂(LLM) | LLM 将 facts 转换为可验证检查点 | `research_output`, `language` | `checkpoints` |
| 7 | `checkpoint_evaluator.py` | ~40 | 纯逻辑 | Checkpoint 去重 + 初始化覆盖状态 | `checkpoints` | `checkpoints`, `checkpoint_coverage` |
| 8 | `evidence_mapper.py` | ~55 | 纯逻辑 | 关键词交集匹配场景与文档章节 | `parsed_document`, `planned_scenarios` | `mapped_evidence` |
| 9 | `draft_writer.py` | ~110 | 工厂(LLM) | LLM 生成测试用例草稿 | `checkpoints`, `planned_scenarios`, `mapped_evidence`, `project_context_summary` | `draft_cases` |
| 10 | `structure_assembler.py` | ~45 | 纯逻辑 | 字段补全、ID 编号、文本规范化 | `draft_cases`, `mapped_evidence` | `test_cases` |
| 11 | `evaluation.py` | ~250 | 纯逻辑 | 6 维度结构化评估 | `test_cases`, `checkpoints`, `research_output` | `EvaluationReport` (返回值) |
| 12 | `reflection.py` | ~160 | 纯逻辑 | 去重 + checkpoint 覆盖 + 质量报告 | `test_cases`, `planned_scenarios`, `checkpoints`, `research_output`, `project_context_summary` | `test_cases`, `quality_report`, `checkpoint_coverage` |

---

## §3 文件详细分析

---

### §3.1 `__init__.py`

#### §3.1.1 核心内容

```python
"""工作流节点子包。
每个模块对应工作流图中的一个处理节点，
节点签名统一为：接收 State → 返回 State 增量更新。
"""
```

这是一个纯声明性的包初始化文件，仅包含 docstring。其关键作用在于：

- **约定声明**：明确所有节点的统一签名 — `(State) -> State增量`，即每个节点接收全局状态字典，返回需要合并（merge）到状态中的增量字段字典
- **不导出任何符号**：各节点通过完整模块路径（如 `app.nodes.input_parser`）被图构建代码导入，`__init__.py` 不做统一 re-export

#### §3.1.2 依赖关系

无任何导入。

#### §3.1.3 关键逻辑 / 数据流

无运行时逻辑。定义了整个目录的架构契约：所有节点函数必须是 `dict → dict` 签名（LangGraph state reducer 模式）。

---

### §3.2 `input_parser.py`

#### §3.2.1 核心内容

**公开函数：**

```python
def input_parser_node(state: GlobalState) -> GlobalState:
```

- **功能**：工作流的入口节点，负责从状态中获取 PRD 文件路径，通过工厂函数 `get_parser()` 获取对应格式的解析器，将文档解析为结构化的 `ParsedDocument` 对象
- **输入 State 字段**：`file_path`（直接指定路径）或 `request.file_path`（从请求对象提取）
- **输出 State 字段**：`parsed_document` — 类型为 `ParsedDocument`
- **无 LLM 调用**

**私有函数：**

```python
def _resolve_file_path(state: GlobalState) -> Path:
```

- **路径解析优先级**：
  1. `state["file_path"]` — 直接指定
  2. `state["request"].file_path` — 从请求对象提取
- **路径处理**：`expanduser()` → 相对路径转绝对路径（基于 `cwd`）→ `resolve()`
- **错误处理**：
  - 路径缺失 → `ValueError("Workflow state is missing file_path")`
  - 文件不存在 → `FileNotFoundError(path)`

**核心算法步骤：**
1. 调用 `_resolve_file_path()` 获取文件绝对路径
2. 调用 `get_parser(file_path)` 工厂函数获取匹配的解析器（按文件扩展名分派）
3. 调用 `parser.parse(file_path)` 执行解析
4. 返回 `{"parsed_document": parsed_document}`

#### §3.2.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `pathlib` | `Path` | 文件路径处理 |
| `app.domain.state` | `GlobalState` | 状态类型定义 |
| `app.parsers.factory` | `get_parser` | 解析器工厂，按文件类型分派 |

#### §3.2.3 关键逻辑 / 数据流

```
state["file_path"] or state["request"].file_path
  → Path 解析 & 验证 (expanduser → absolute → exists check)
  → get_parser(path) → parser 实例
  → parser.parse(path) → ParsedDocument
  → {"parsed_document": parsed_document}
```

**位置**：工作流图的第 1 个节点（起点）。后续所有节点均依赖其产出的 `parsed_document`。

---

### §3.3 `project_context_loader.py`

#### §3.3.1 核心内容

**工厂函数：**

```python
def build_project_context_loader(
    service: ProjectContextService,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
```

- **设计模式**：工厂 + 闭包。在图构建阶段通过工厂注入 `ProjectContextService` 依赖，返回的闭包函数才是实际注册到 LangGraph 的节点
- **闭包捕获**：`service` 实例

**闭包节点函数：**

```python
def _load_project_context(state: dict[str, Any]) -> dict[str, Any]:
```

- **输入 State 字段**：`project_id`（可选）
- **输出 State 字段**：`project_context_summary`（字符串，可能为空）
- **无 LLM 调用**（纯 Service 层调用）

**核心算法步骤：**
1. 从 state 获取 `project_id`，若为空则返回空字符串（优雅跳过）
2. 调用 `service.get_project(project_id)` 查找项目上下文
3. 调用 `project.summary_text()` 生成文本摘要
4. 返回 `{"project_context_summary": summary}`

**优雅降级设计（Graceful Degradation）**——四重保护：

| 异常场景 | 处理方式 | 日志级别 |
|----------|----------|----------|
| `project_id` 缺失 | 返回空字符串 | `INFO` |
| `service.get_project()` 抛异常 | 捕获 `Exception`，返回空字符串 | `ERROR` (含 traceback) |
| 项目未找到（返回 `None`） | 返回空字符串 | `WARNING` |
| `summary_text()` 抛异常 | 捕获 `Exception`，返回空字符串 | `ERROR` (含 traceback) |

这确保了无论项目上下文系统是否可用，工作流都不会中断。

#### §3.3.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `logging` | `logging` | 日志记录 |
| `typing` | `Any`, `Callable` | 类型标注 |
| `app.domain.project_models` | `ProjectContext` | 项目上下文领域模型 |
| `app.services.project_context_service` | `ProjectContextService` | 项目上下文服务 |

#### §3.3.3 关键逻辑 / 数据流

```
state["project_id"]
  → service.get_project(project_id)
  → ProjectContext | None
  → project.summary_text() → str
  → {"project_context_summary": summary}
  (任何阶段失败均返回 {"project_context_summary": ""})
```

**位置**：工作流图中的第 2 个节点（紧接 input_parser 之后），为后续 context_research 和 draft_writer 提供项目级别的上下文信息。

---

### §3.4 `context_research.py`

#### §3.4.1 核心内容

**工厂函数：**

```python
def build_context_research_node(llm_client: LLMClient):
```

- **设计模式**：工厂 + 闭包，注入 `LLMClient`
- **返回的闭包即 LangGraph 节点**

**闭包节点函数：**

```python
def context_research_node(state: GlobalState) -> GlobalState:
```

- **输入 State 字段**：`parsed_document`, `project_context_summary`(可选), `language`(默认 `zh-CN`), `model_config`(可选)
- **输出 State 字段**：`research_output`（类型 `ResearchOutput`）
- **LLM 交互**：是（结构化输出）

**LLM 交互模式：**

| 要素 | 内容 |
|------|------|
| 调用方法 | `llm_client.generate_structured()` |
| System Prompt | 详细指令，要求从 PRD 中提取 `feature_topics`、`user_scenarios`、`constraints`、`ambiguities`、`test_signals` 和 `facts` |
| User Prompt | `[Project Context]\n{summary}` + `Language: {lang}` + `Document title: {title}` + `Document body:\n{raw_text}` |
| Response Model | `ResearchOutput`（Pydantic 模型，LLM 被约束返回匹配的 JSON） |
| 模型选择 | 优先使用 `model_config.model`，否则使用客户端默认值 |

**System Prompt 要点：**
- 要求提取 `facts` 列表——每个 fact 是 PRD 中一条离散的、可测试的信息，包含 `fact_id`(如 FACT-001)、`description`、`source_section`、`category`(requirement/constraint/assumption/behavior)、`evidence_refs`
- `evidence_refs` 必须严格遵循 `{section_title, excerpt, line_start, line_end, confidence}` 结构
- **双语规则**：通用描述使用中文，英文专有名词保留原文（产品名、UI 按钮文案、字段名等）
- 中英文混排格式：「中文动作 + 原文对象」如 "点击 `Create campaign`"

**项目上下文注入：**
- 当 `project_context_summary` 非空时，在 user prompt 开头插入 `[Project Context]\n{summary}\n\n`
- 为 LLM 提供项目级别的业务背景信息，提升提取质量

#### §3.4.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `app.clients.llm` | `LLMClient` | LLM 客户端抽象 |
| `app.domain.research_models` | `ResearchOutput` | 研究输出的 Pydantic 模型 |
| `app.domain.state` | `GlobalState` | 全局状态类型 |

#### §3.4.3 关键逻辑 / 数据流

```
state["parsed_document"] + state["project_context_summary"]
  → 构造 user prompt (项目上下文前缀 + 语言 + 文档标题 + 文档正文)
  → llm_client.generate_structured(system_prompt, user_prompt, ResearchOutput)
  → ResearchOutput { feature_topics, user_scenarios, constraints, ambiguities, test_signals, facts }
  → {"research_output": response}
```

**位置**：工作流图中的第 3 个节点。是整条流水线中第一个 LLM 调用点，其输出 `research_output` 被后续 4 个节点（scenario_planner, checkpoint_generator, evaluation, reflection）消费。

---

### §3.5 `scenario_planner.py`

#### §3.5.1 核心内容

**公开函数：**

```python
def scenario_planner_node(state: GlobalState) -> GlobalState:
```

- **输入 State 字段**：`research_output`
- **输出 State 字段**：`planned_scenarios`（`list[PlannedScenario]`）
- **无 LLM 调用**（纯逻辑规划）

**场景规划的三级优先级策略：**

| 优先级 | 来源 | 处理 |
|--------|------|------|
| 1 (最高) | `research_output.user_scenarios` | 直接使用场景标题 |
| 2 | `research_output.feature_topics` | 添加 `"Validate "` 前缀派生 |
| 3 (兜底) | 硬编码常量 | `"Validate core workflow"` |

**核心算法步骤：**
1. 调用 `_collect_scenario_titles()` 按优先级获取场景标题列表
2. 取前两个约束条件拼接为 `rationale`（场景理由说明）
3. 为每个标题创建 `PlannedScenario` 对象（category="functional", risk="medium"）

**去重机制 `_dedupe_preserving_order()`：**
- 使用 `casefold()` 进行大小写不敏感比较（如 "Login" 和 "login" 视为同一项）
- 保留首次出现的原始大小写形式
- 使用 `set` + `list` 实现 O(n) 有序去重

#### §3.5.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `app.domain.research_models` | `PlannedScenario`, `ResearchOutput` | 领域模型 |
| `app.domain.state` | `GlobalState` | 状态类型 |

#### §3.5.3 关键逻辑 / 数据流

```
state["research_output"]
  → _collect_scenario_titles(): user_scenarios > feature_topics > fallback
  → _dedupe_preserving_order(): casefold 去重
  → 为每个 title 构造 PlannedScenario(title, category="functional", risk="medium", rationale=约束摘要)
  → {"planned_scenarios": [...]}
```

**位置**：工作流图中的第 4 个节点。产出的 `planned_scenarios` 被 evidence_mapper 和 draft_writer（兼容路径）消费。

---

### §3.6 `checkpoint_generator.py`

#### §3.6.1 核心内容

这是整个目录中**最复杂的文件**（~180行），包含 Pydantic 模型定义、LLM 交互和多个辅助函数。

**Pydantic 模型：**

```python
class CheckpointDraft(BaseModel):
    title: str
    objective: str = ""
    category: str = "functional"
    risk: str = "medium"
    branch_hint: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
```

- **`coerce_and_strip_extra_fields()` (model_validator, mode="before")**：
  - 移除 LLM 可能错误输出的字段：`steps`, `expected_result`, `expected_results`, `checkpoint_id`
  - 如果 `preconditions` 是字符串而非列表，按 `。\n；;` 分隔符自动拆分为列表
  - 这是典型的 **LLM 输出修复（coercion）** 模式

```python
class CheckpointDraftCollection(BaseModel):
    checkpoints: list[CheckpointDraft] = Field(default_factory=list)
```

**工厂函数：**

```python
def build_checkpoint_generator_node(llm_client: LLMClient):
```

**闭包节点函数 `checkpoint_generator_node(state: CaseGenState)`：**

- **输入 State 字段**：`research_output`, `language`(默认 `zh-CN`)
- **输出 State 字段**：`checkpoints`（`list[Checkpoint]`）

**核心算法步骤：**
1. 从 `research_output.facts` 获取事实列表
2. 若 facts 为空，调用 `_synthesize_facts_from_legacy()` 从 `user_scenarios`, `feature_topics`, `constraints` 合成
3. 若仍为空，返回空 checkpoints
4. 调用 `_build_checkpoint_prompt()` 构建 prompt
5. 调用 `llm_client.generate_structured()` 获取 `CheckpointDraftCollection`
6. **后处理**：为每个 draft 生成稳定 ID（`generate_checkpoint_id(fact_ids, title)`），从 fact_lookup 聚合 evidence_refs，构造最终 `Checkpoint` 对象

**LLM 交互模式：**

| 要素 | 内容 |
|------|------|
| System Prompt | 详细的 JSON Schema 约束 + 禁止字段列表 + 正/反面示例 |
| User Prompt | 由 `_build_checkpoint_prompt()` 构建的 fact 列表格式化文本 |
| Response Model | `CheckpointDraftCollection` |
| 输出修复 | `CheckpointDraft.coerce_and_strip_extra_fields()` 自动修正 |

**System Prompt 的防御性设计：**
- 明确列出允许的字段和**禁止的字段**（steps, expected_result 等）
- 强调 `preconditions` 必须是字符串数组，不能合并为单个字符串
- 提供正确示例和错误示例对比
- 双语规则：描述用中文，枚举值保留英文

**辅助函数 `_synthesize_facts_from_legacy()`：**
- 向后兼容机制，当 LLM 未返回 facts 时
- 将 `user_scenarios` → category="behavior" 的 fact
- 将 `feature_topics` → category="requirement" 的 fact（添加 "Feature:" 前缀）
- 将 `constraints` → category="constraint" 的 fact
- 自动生成 `FACT-001`, `FACT-002`, ... 格式的 ID

**辅助函数 `_build_checkpoint_prompt()`：**
- 格式化 facts 为 `- [FACT-001] (category) description` 格式
- 包含 source_section 信息
- 末尾附加输出语言约束和 preconditions 格式强调

#### §3.6.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `re` | — | 正则分割 preconditions 字符串 |
| `pydantic` | `BaseModel`, `Field`, `model_validator` | LLM 输出模型定义 |
| `app.clients.llm` | `LLMClient` | LLM 客户端 |
| `app.domain.checkpoint_models` | `Checkpoint`, `generate_checkpoint_id` | 领域模型和 ID 生成 |
| `app.domain.research_models` | `ResearchFact` | 研究事实模型 |
| `app.domain.state` | `CaseGenState` | 用例生成子状态 |

#### §3.6.3 关键逻辑 / 数据流

```
state["research_output"].facts
  → (若为空) _synthesize_facts_from_legacy() 从 user_scenarios/feature_topics/constraints 合成
  → _build_checkpoint_prompt(facts, language) 构建 user prompt
  → llm_client.generate_structured(system_prompt, user_prompt, CheckpointDraftCollection)
  → CheckpointDraft[] (经 coerce_and_strip_extra_fields 自动修复)
  → 为每个 draft:
      - generate_checkpoint_id(fact_ids, title) → 稳定 ID
      - 从 fact_lookup 聚合 evidence_refs
      - 构造 Checkpoint(checkpoint_id, title, ..., coverage_status="uncovered")
  → {"checkpoints": [...]}
```

**位置**：工作流图中的第 5 个节点。这是流水线的**关键转换点**——将非结构化的 facts 转换为可追溯的检查点，是后续 draft_writer 生成测试用例的直接输入。

---

### §3.7 `checkpoint_evaluator.py`

#### §3.7.1 核心内容

**公开函数：**

```python
def checkpoint_evaluator_node(state: CaseGenState) -> CaseGenState:
```

- **输入 State 字段**：`checkpoints`
- **输出 State 字段**：`checkpoints`（去重后）, `checkpoint_coverage`（初始覆盖记录列表）
- **无 LLM 调用**

**核心算法步骤：**
1. **去重**：遍历 checkpoints，以 `title.strip().casefold()` 为去重键，保留首次出现的 checkpoint
2. **初始化覆盖记录**：为每个去重后的 checkpoint 创建 `CheckpointCoverage` 对象，初始状态为 `covered_by_test_ids=[]`, `coverage_status="uncovered"`

**设计意图：**
- 在 checkpoint 生成（LLM 输出）和 draft 写入之间插入一个"质量关卡"
- 确保不会有重复的 checkpoint 导致 draft_writer 生成重复用例
- 初始化覆盖追踪数据结构，供后续 reflection 节点更新

#### §3.7.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `app.domain.checkpoint_models` | `Checkpoint`, `CheckpointCoverage` | 领域模型 |
| `app.domain.state` | `CaseGenState` | 状态类型 |

#### §3.7.3 关键逻辑 / 数据流

```
state["checkpoints"]
  → 按 title.casefold() 去重 (保留首次出现)
  → 为每个 checkpoint 创建 CheckpointCoverage(status="uncovered")
  → {"checkpoints": deduped, "checkpoint_coverage": coverage_records}
```

**位置**：工作流图中的第 6 个节点。是 checkpoint_generator 和 evidence_mapper/draft_writer 之间的质量守门员。

---

### §3.8 `evidence_mapper.py`

#### §3.8.1 核心内容

**公开函数：**

```python
def evidence_mapper_node(state: CaseGenState) -> CaseGenState:
```

- **输入 State 字段**：`parsed_document`, `planned_scenarios`
- **输出 State 字段**：`mapped_evidence`（`dict[str, list[EvidenceRef]]`，场景标题 → 证据列表的映射）
- **无 LLM 调用**

**匹配算法 —— 基于关键词交集：**
1. 将场景标题通过 `_tokenize()` 分词得到 token 集合
2. 遍历 `parsed_document.sections`，将每个章节的 heading 和 content 分别分词
3. **匹配条件**：`scenario_tokens & (heading_tokens | content_tokens)` 非空（交集存在）
4. 匹配成功则创建 `EvidenceRef`，置信度为 0.85
5. **兜底机制**：若某场景无任何匹配，使用文档首章节作为兜底证据，置信度为 0.4

**分词函数 `_tokenize()`：**
```python
def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", value.casefold())
```
- 同时支持英文单词（连续字母数字）和中文单字（CJK 统一表意文字 `\u4e00-\u9fff`）
- 使用 `casefold()` 确保大小写不敏感匹配
- 过滤标点和空白

**常量配置：**
- `_EXCERPT_MAX_LENGTH = 200`：证据摘录最大字符数
- `_FALLBACK_CONFIDENCE = 0.4`：兜底证据置信度
- `_MATCH_CONFIDENCE = 0.85`：关键词命中置信度

#### §3.8.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `re` | — | 正则表达式分词 |
| `app.domain.research_models` | `EvidenceRef` | 证据引用模型 |
| `app.domain.state` | `CaseGenState` | 状态类型 |

#### §3.8.3 关键逻辑 / 数据流

```
for each scenario in state["planned_scenarios"]:
  scenario_tokens = _tokenize(scenario.title)
  for each section in state["parsed_document"].sections:
    if scenario_tokens ∩ (heading_tokens ∪ content_tokens) ≠ ∅:
      → EvidenceRef(section_title, excerpt[:200], line_start, line_end, confidence=0.85)
  if no match:
    → EvidenceRef(first_section, ..., confidence=0.4)  // 兜底
→ {"mapped_evidence": {scenario_title: [EvidenceRef, ...]}}
```

**位置**：工作流图中的第 7 个节点。产出的 `mapped_evidence` 被 draft_writer（兼容路径）和 structure_assembler 消费。

---

### §3.9 `draft_writer.py`

#### §3.9.1 核心内容

**Pydantic 模型：**

```python
class DraftCaseCollection(BaseModel):
    test_cases: list[TestCase] = Field(default_factory=list)
```

**工厂函数：**

```python
def build_draft_writer_node(llm_client: LLMClient):
```

**闭包节点函数 `draft_writer_node(state: CaseGenState)`：**

- **输入 State 字段**：`checkpoints`, `planned_scenarios`(向后兼容), `mapped_evidence`(向后兼容), `project_context_summary`(可选)
- **输出 State 字段**：`draft_cases`（`list[TestCase]`）

**双路径 Prompt 构建策略：**

| 路径 | 条件 | Prompt 构建函数 | 数据来源 |
|------|------|-----------------|----------|
| **Checkpoint 路径**（主路径） | `checkpoints` 非空 | `_format_checkpoint_prompt()` | checkpoint 元信息 + evidence_refs |
| **Scenario 路径**（向后兼容） | `checkpoints` 为空 | `_format_scenario_prompt()` | scenario 信息 + mapped_evidence |

**Checkpoint Prompt 格式化 `_format_checkpoint_prompt()`：**
- 包含：序号、标题、checkpoint_id、objective、category、risk、branch_hint、preconditions、source facts、evidence_refs
- 末尾指令：`Generate test case(s) for this checkpoint. Set checkpoint_id to '{checkpoint.checkpoint_id}'.`
- 这确保了 LLM 输出的 test case 与 checkpoint 的可追溯性

**项目上下文注入：**
- 当 `project_context_summary` 非空时，在所有 prompt 片段最前面插入 `[Project Checklist Constraints]` 段落

**LLM 交互模式：**

| 要素 | 内容 |
|------|------|
| System Prompt | 要求生成包含 id, title, steps, expected_results, evidence_refs, checkpoint_id 的 JSON |
| User Prompt | 所有 checkpoint/scenario 的格式化文本拼接（`\n\n` 分隔） |
| Response Model | `DraftCaseCollection` |
| 双语规则 | title/steps/expected_results/preconditions 中文，id/priority/category 英文，UI 元素用反引号 |

#### §3.9.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `pydantic` | `BaseModel`, `Field` | 输出模型定义 |
| `app.clients.llm` | `LLMClient` | LLM 客户端 |
| `app.domain.case_models` | `TestCase` | 测试用例模型 |
| `app.domain.checkpoint_models` | `Checkpoint` | 检查点模型 |
| `app.domain.state` | `CaseGenState` | 状态类型 |

#### §3.9.3 关键逻辑 / 数据流

```
if state["checkpoints"] 非空:
  for each checkpoint → _format_checkpoint_prompt(index, checkpoint)
else:  // 向后兼容
  for each scenario → _format_scenario_prompt(index, scenario, evidence)

if project_context_summary:
  prompt_lines.insert(0, project context block)

→ llm_client.generate_structured(system_prompt, joined_prompts, DraftCaseCollection)
→ {"draft_cases": response.test_cases}
```

**位置**：工作流图中的第 8 个节点。这是流水线中第三个（也是最关键的）LLM 调用点——直接产出测试用例草稿。

---

### §3.10 `structure_assembler.py`

#### §3.10.1 核心内容

**公开函数：**

```python
def structure_assembler_node(state: CaseGenState) -> CaseGenState:
```

- **输入 State 字段**：`draft_cases`, `mapped_evidence`
- **输出 State 字段**：`test_cases`（标准化后的用例列表）
- **无 LLM 调用**

**字段补全规则：**

| 字段 | 补全逻辑 |
|------|----------|
| `id` | 为空时按序号生成 `TC-001`, `TC-002`, ... |
| `preconditions` | 为空时设为 `[]` |
| `steps` | 为空时设为 `[]` |
| `expected_results` | 为空时设为 `[]` |
| `priority` | 为空时默认 `"P2"` |
| `category` | 为空时默认 `"functional"` |
| `evidence_refs` | 优先使用 LLM 生成值，为空时从 `mapped_evidence` 按标题查找 |
| `checkpoint_id` | 保留 draft_writer 生成的值，为空时设为 `""` |

**文本规范化：**
- 调用 `normalize_test_case(assembled)` 进行中英文混排规范化处理
- 该函数来自 `app.services.text_normalizer`

**使用 Pydantic 的 `model_copy(update={...})` 实现不可变更新**——创建新对象而非原地修改。

#### §3.10.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `app.domain.case_models` | `TestCase` | 测试用例模型 |
| `app.domain.state` | `CaseGenState` | 状态类型 |
| `app.services.text_normalizer` | `normalize_test_case` | 中英文混排规范化 |

#### §3.10.3 关键逻辑 / 数据流

```
for index, case in enumerate(state["draft_cases"], start=1):
  → model_copy(update={
      id: case.id or "TC-{index:03d}",
      preconditions/steps/expected_results: fallback to [],
      priority: "P2", category: "functional",
      evidence_refs: case.evidence_refs or mapped_evidence.get(title, []),
      checkpoint_id: case.checkpoint_id or ""
    })
  → normalize_test_case(assembled)  // 文本规范化
→ {"test_cases": assembled_cases}
```

**位置**：工作流图中的第 9 个节点。是 LLM 输出到最终结构化数据的"标准化桥梁"。

---

### §3.11 `evaluation.py`

#### §3.11.1 核心内容

这是最大的文件（~250行），实现了完整的**多维度结构化评估体系**。

**公开函数（注意：这不是 LangGraph 节点函数，是纯工具函数）：**

```python
def evaluate(
    *,
    test_cases: list[TestCase],
    checkpoints: list[Checkpoint],
    research_output: ResearchOutput | None = None,
    previous_score: float = 0.0,
) -> EvaluationReport:
```

- **参数**：全部为仅关键字参数（`*`）
- **返回类型**：`EvaluationReport`（非 state 增量，而是结构化报告对象）
- **无 LLM 调用**

**六维度评估体系：**

| 维度 | 函数 | 评估内容 | 分数计算 |
|------|------|----------|----------|
| 1. `fact_coverage` | `_evaluate_fact_coverage()` | 有多少 fact 被至少一个 checkpoint 引用 | `covered / total` |
| 2. `checkpoint_coverage` | `_evaluate_checkpoint_coverage()` | 有多少 checkpoint 被至少一个 test case 覆盖 | `covered / total` |
| 3. `evidence_completeness` | `_evaluate_evidence_completeness()` | 有多少 test case 关联了 evidence_refs | `with_evidence / total` |
| 4. `duplicate_rate` | `_evaluate_duplicate_rate()` | test case 标题重复率 | `unique / total` |
| 5. `case_completeness` | `_evaluate_case_completeness()` | 缺少 steps 或 expected_results 的比例 | `complete / total` |
| 6. `branch_coverage` | `_evaluate_branch_coverage()` | 非功能性 checkpoint 的覆盖情况 | `covered_nf / total_nf` |

**总体分数计算：**
- 简单算术平均：`sum(scores) / 6`（六维度等权重）
- 关键失败项：score < 0.5 的维度的前 3 个 failed_items

**回流阶段决策 `_determine_retry_stage()`：**

| 条件 | 建议回流阶段 |
|------|-------------|
| `fact_coverage` < 0.6 | `"context_research"` |
| `checkpoint_coverage` < 0.6 | `"checkpoint_generation"` |
| 任一质量维度 < 0.6（evidence/duplicate/completeness/branch） | `"draft_generation"` |
| 全部达标 | `None` |

优先级：fact 覆盖 > checkpoint 覆盖 > test case 质量

**与上一轮的比较逻辑：**
- delta > 0.05 → "相较上轮提升"
- delta < -0.05 → "相较上轮退化"
- 其他 → "与上轮基本持平"

**改进建议生成 `_generate_improvement_summary()`：**
- 列出所有 score < 0.7 的维度名称、分数和详情

#### §3.11.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `app.domain.case_models` | `TestCase` | 测试用例模型 |
| `app.domain.checkpoint_models` | `Checkpoint` | 检查点模型 |
| `app.domain.research_models` | `ResearchOutput` | 研究输出模型 |
| `app.domain.run_state` | `EvaluationDimension`, `EvaluationReport` | 评估结果模型 |

#### §3.11.3 关键逻辑 / 数据流

```
evaluate(test_cases, checkpoints, research_output, previous_score)
  → 6 个维度评估函数并行执行
  → overall_score = mean(dim.score for dim in dimensions)
  → critical_failures = [items from dims where score < 0.5]
  → suggested_retry_stage = _determine_retry_stage(dimensions)
  → improvement_summary = _generate_improvement_summary(dimensions)
  → comparison_with_previous = 与上轮分数对比文本
  → EvaluationReport(overall_score, dimensions, critical_failures, ...)
```

**位置**：这是一个**工具函数**而非 LangGraph 节点。从函数签名看，它被其他节点（很可能是 reflection 或图的 conditional edge）调用来决定是否需要回流（retry loop）。`_determine_retry_stage()` 的返回值直接决定工作流的分支走向。

---

### §3.12 `reflection.py`

#### §3.12.1 核心内容

这是工作流的**终端质量关卡节点**（~160行），综合执行去重、完整性检查和覆盖分析。

**公开函数：**

```python
def reflection_node(state: GlobalState) -> GlobalState:
```

- **输入 State 字段**：`test_cases`, `planned_scenarios`, `checkpoints`, `research_output`, `project_context_summary`
- **输出 State 字段**：`test_cases`（去重后）, `quality_report`, `checkpoint_coverage`（更新后）
- **无 LLM 调用**

**核心处理步骤：**

1. **去重**：调用 `deduplicate_cases()` 按标题 casefold 去重，记录重复组
2. **字段完整性检查**：遍历去重后的用例，标记缺少 `expected_results` 和 `evidence_refs` 的用例
3. **场景覆盖率评估**：比较生成用例数与 `planned_scenarios` 数
4. **Checkpoint 质量检查**：调用 `_check_checkpoint_quality()` 执行四项检查
5. **项目上下文感知提示**：当有项目上下文时添加审查提醒
6. **覆盖状态更新**：调用 `_compute_checkpoint_coverage()` 更新覆盖映射

**`deduplicate_cases()` 函数：**
```python
def deduplicate_cases(cases: list[TestCase]) -> tuple[list[TestCase], QualityReport]:
```
- 使用 `casefold()` 进行大小写不敏感的标题比较
- 保留首次出现的用例
- 返回 `(deduped_cases, QualityReport(duplicate_groups=[[id1, id2], ...]))`

**`_check_checkpoint_quality()` 函数——四项检查：**

| 检查项 | 检查内容 | 严重性 |
|--------|----------|--------|
| 1 | 是否存在未生成 checkpoint 的 fact | 覆盖缺失 |
| 2 | 是否存在未被 test case 覆盖的 checkpoint | 覆盖缺失 |
| 3 | 是否存在 evidence 不足的 checkpoint | 可追溯性问题 |
| 4 | 是否存在标题重叠的 checkpoint（包含关系检测） | 质量问题 |

检查项 4 的实现是 O(n^2) 的两两比较，使用字符串包含关系（`title_i in titles[j]`）检测相似性。

**`_compute_checkpoint_coverage()` 函数：**
- 建立 `checkpoint_id → list[test_id]` 的映射
- 根据覆盖关系更新每个 checkpoint 的 `coverage_status`（"covered" / "uncovered"）

#### §3.12.2 依赖关系

| 依赖模块 | 导入符号 | 用途 |
|----------|----------|------|
| `app.domain.case_models` | `QualityReport`, `TestCase` | 领域模型 |
| `app.domain.checkpoint_models` | `CheckpointCoverage` | 覆盖状态模型 |
| `app.domain.state` | `GlobalState` | 全局状态类型 |

#### §3.12.3 关键逻辑 / 数据流

```
state["test_cases"]
  → deduplicate_cases() → (deduped_cases, quality_report)
  → 字段完整性检查 → warnings[]
  → 场景覆盖率评估 → coverage_notes[]
  → _check_checkpoint_quality(checkpoints, test_cases, research_output) → checkpoint_warnings[]
  → 项目上下文感知检查 → additional warning
  → _compute_checkpoint_coverage(checkpoints, deduped_cases) → CheckpointCoverage[]
  → {
      "test_cases": deduped_cases,
      "quality_report": QualityReport(warnings, checkpoint_warnings, ...),
      "checkpoint_coverage": updated_coverage
    }
```

**位置**：工作流图中的最后一个节点（终端）。其输出的 `quality_report` 和 `checkpoint_coverage` 是工作流的最终质量评估成果。

---

## §4 目录级依赖关系

### §4.1 内部数据流图（节点间 State 字段传递）

```
[input_parser] ──parsed_document──→ [context_research] ──research_output──→ [scenario_planner]
                                         │                                        │
                                         │                                   planned_scenarios
                                         │                                        │
                                         ↓                                        ↓
                                  [checkpoint_generator]                  [evidence_mapper]
                                         │                                        │
                                     checkpoints                          mapped_evidence
                                         │                                        │
                                         ↓                                        │
                                  [checkpoint_evaluator]                          │
                                    checkpoints (去重)                             │
                                    checkpoint_coverage (初始)                     │
                                         │                                        │
                                         ↓                                        ↓
                                  [draft_writer] ←─────────────────────────────────┘
                                         │
                                     draft_cases
                                         │
                                         ↓
                                  [structure_assembler] ←── mapped_evidence
                                         │
                                     test_cases
                                         │
                                         ↓
                                  [evaluation] (工具函数，非节点)
                                         │
                                  EvaluationReport → suggested_retry_stage
                                         │
                                         ↓
                                  [reflection]
                                         │
                                  test_cases (去重), quality_report, checkpoint_coverage
```

**跨节点共享的关键 State 字段：**

| State 字段 | 产生节点 | 消费节点 |
|------------|----------|----------|
| `parsed_document` | input_parser | context_research, evidence_mapper |
| `project_context_summary` | project_context_loader | context_research, draft_writer, reflection |
| `research_output` | context_research | scenario_planner, checkpoint_generator, evaluation, reflection |
| `planned_scenarios` | scenario_planner | evidence_mapper, draft_writer(兼容), reflection |
| `checkpoints` | checkpoint_generator → checkpoint_evaluator(去重) | draft_writer, evaluation, reflection |
| `checkpoint_coverage` | checkpoint_evaluator(初始) → reflection(更新) | — (最终输出) |
| `mapped_evidence` | evidence_mapper | draft_writer(兼容), structure_assembler |
| `draft_cases` | draft_writer | structure_assembler |
| `test_cases` | structure_assembler → reflection(去重) | evaluation, reflection |
| `quality_report` | reflection | — (最终输出) |

### §4.2 外部依赖关系

| 外部模块 | 被引用节点 | 角色 |
|----------|-----------|------|
| `app.clients.llm.LLMClient` | context_research, checkpoint_generator, draft_writer | LLM 交互抽象层 |
| `app.parsers.factory.get_parser` | input_parser | 文档解析器工厂 |
| `app.services.project_context_service` | project_context_loader | 项目上下文服务 |
| `app.services.text_normalizer` | structure_assembler | 中英文文本规范化 |
| `app.domain.state` | 所有节点 | `GlobalState` / `CaseGenState` 类型 |
| `app.domain.case_models` | draft_writer, structure_assembler, evaluation, reflection | `TestCase`, `QualityReport` |
| `app.domain.checkpoint_models` | checkpoint_generator, checkpoint_evaluator, evaluation, reflection | `Checkpoint`, `CheckpointCoverage` |
| `app.domain.research_models` | context_research, scenario_planner, checkpoint_generator, evidence_mapper, evaluation | `ResearchOutput`, `ResearchFact`, `PlannedScenario`, `EvidenceRef` |
| `app.domain.run_state` | evaluation | `EvaluationDimension`, `EvaluationReport` |
| `app.domain.project_models` | project_context_loader | `ProjectContext` |

---

## §5 设计模式与架构特征

### §5.1 工厂 + 闭包模式（Factory + Closure）

**应用节点**：`project_context_loader`, `context_research`, `checkpoint_generator`, `draft_writer`

```python
def build_xxx_node(dependency) -> Callable[[dict], dict]:
    def xxx_node(state: dict) -> dict:
        # 通过闭包访问 dependency
        ...
    return xxx_node
```

**优势**：
- 将依赖注入（DI）时机推迟到图构建阶段，而非节点执行阶段
- LangGraph 节点注册只需要 `Callable[[dict], dict]`，闭包完美匹配
- 测试时可以 mock dependency 后调用工厂函数

### §5.2 优雅降级模式（Graceful Degradation）

**核心体现**：
- `project_context_loader`：四重 try/except 保护，任何失败都返回空字符串而非中断
- `checkpoint_generator`：facts 为空时从旧版字段合成，合成也失败返回空列表
- `draft_writer`：checkpoints 为空时回退到 scenario 路径
- `evidence_mapper`：无匹配时使用首章节作为兜底

### §5.3 LLM 输出修复模式（Output Coercion）

**核心体现**：`CheckpointDraft.coerce_and_strip_extra_fields()` (Pydantic `model_validator`)
- 移除 LLM 可能错误输出的多余字段
- 自动将字符串类型的 `preconditions` 拆分为列表
- 这反映了工程实践中 LLM 输出不可靠的现实

### §5.4 向后兼容模式（Backward Compatibility）

**核心体现**：
- `checkpoint_generator._synthesize_facts_from_legacy()`：从旧版 ResearchOutput 字段合成 facts
- `draft_writer`：checkpoint 路径和 scenario 路径并存
- 体现了系统从 "scenario-based" 向 "checkpoint-based" 架构演进的过渡

### §5.5 统一去重策略（Casefold Deduplication）

**核心体现**：`scenario_planner._dedupe_preserving_order()`, `checkpoint_evaluator`, `reflection.deduplicate_cases()`, `evaluation._evaluate_duplicate_rate()`

所有去重均使用 `str.casefold()` 进行大小写不敏感比较，保留首次出现的原始形式。这是贯穿整个流水线的一致性策略。

### §5.6 可追溯性链路（Traceability Chain）

```
ResearchFact(fact_id) → Checkpoint(fact_ids, checkpoint_id) → TestCase(checkpoint_id)
                  ↑ evidence_refs ↑                    ↑ evidence_refs ↑
```

每个测试用例都可追溯到原始 PRD 事实和文档证据，这是测试管理领域的核心需求。

### §5.7 双状态类型设计

- `GlobalState`：全局工作流状态，用于 input_parser, context_research, scenario_planner, reflection 等操作全局数据的节点
- `CaseGenState`：用例生成子状态，用于 checkpoint_generator, checkpoint_evaluator, evidence_mapper, draft_writer, structure_assembler 等聚焦于用例生成的节点
- `evaluate()` 函数使用纯参数而非 state，保持工具函数的纯净性

---

## §6 潜在关注点

### §6.1 性能与扩展性

1. **`_check_checkpoint_quality()` 中的 O(n^2) 标题重叠检测**：当 checkpoint 数量较大时（如 >100），两两比较的时间复杂度可能成为瓶颈。建议考虑基于 n-gram 或编辑距离的近似算法。

2. **evidence_mapper 的关键词交集匹配**：对于中文文档，单字分词（CJK 范围）的精度较低，"用"、"户"、"的" 等高频字会导致大量虚假匹配。建议引入停用词过滤或使用分词库（如 jieba）。

3. **LLM 调用次数**：checkpoint_generator 和 draft_writer 均为单次 LLM 调用处理所有输入。当 facts/checkpoints 数量很多时，prompt 可能超出上下文窗口。缺少分批处理（batching）机制。

### §6.2 错误处理一致性

4. **input_parser 直接抛异常**（`ValueError`, `FileNotFoundError`），而 project_context_loader 采用全面的优雅降级。两种策略混用可能导致调用方需要不同的错误处理逻辑。建议统一策略或在图层面有统一的异常处理。

5. **LLM 节点缺少 LLM 调用失败的 try/except**：`context_research`, `checkpoint_generator`, `draft_writer` 三个 LLM 节点均直接调用 `llm_client.generate_structured()` 而无异常捕获。若 LLM 返回无法解析的格式或网络超时，将直接导致工作流中断。

### §6.3 架构演进痕迹

6. **scenario-based vs checkpoint-based 双路径并存**：`draft_writer` 同时支持两种路径，`evidence_mapper` 仅服务于 scenario 路径。若 checkpoint 路径已成为主流，scenario 路径和 evidence_mapper 的中间产物可能变为冗余代码。建议评估是否可以弃用 scenario 路径。

7. **`evaluation.py` 不是 LangGraph 节点**：`evaluate()` 函数使用纯参数签名而非 `(state) -> state`，与目录内其他模块的约定不一致。它可能被图的 conditional edge 或其他节点内部调用，但这种调用关系在当前目录内不可见。

### §6.4 数据质量风险

8. **`_synthesize_facts_from_legacy()` 生成的合成 fact 缺少 `source_section` 和 `evidence_refs`**：这些合成 fact 在后续 checkpoint 生成中将缺少证据链，影响可追溯性。

9. **`structure_assembler` 按标题匹配 `mapped_evidence`**：`evidence_lookup.get(case.title, [])`——当 LLM 生成的 test case 标题与 scenario 标题不完全一致时（几乎总是如此），此查找将失效，用例将缺少证据引用。

10. **checkpoint_evaluator 仅做标题去重**：缺少语义级别的相似度检测。两个标题文字不同但语义相同的 checkpoint 不会被去重。

### §6.5 测试与可观测性

11. **缺少日志记录**：除 `project_context_loader` 使用了 `logging` 外，其余 11 个文件均无日志输出。对于一个多步骤 LLM 工作流，缺少中间步骤的日志会严重影响调试和监控。

12. **evaluation 的等权重假设**：六个维度使用简单算术平均，未考虑维度重要性差异。在实际场景中，`fact_coverage` 和 `checkpoint_coverage` 可能比 `duplicate_rate` 更重要，建议引入可配置的权重系数。