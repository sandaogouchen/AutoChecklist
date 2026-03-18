# app/services/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 9 | 分析策略: Business logic / service layer analysis

## §1 目录职责

`app/services/` 是 AutoChecklist 项目的**核心业务逻辑层**，位于 API 层与底层基础设施（仓储、LLM 客户端、LangGraph 工作流引擎）之间。该目录承担以下关键职责：

1. **工作流编排** — `WorkflowService` 作为中央协调者，串联运行创建、迭代评估回路、产物持久化的完整生命周期。
2. **迭代控制** — `IterationController` 实现基于质量阈值的多轮评估决策引擎（pass/retry/fail），包含无改进连续检测（no-improvement-streak）。
3. **平台分发** — `PlatformDispatcher` 统一管理本地产物持久化和可选的 XMind 思维导图交付，采用容错设计确保 XMind 失败不阻断主流程。
4. **XMind 交付链** — `XMindPayloadBuilder` → `XMindDeliveryAgent` → `XMindConnector` 三级流水线，将测试用例层次结构序列化为 `.xmind` ZIP 归档文件。
5. **文本规范化** — `TextNormalizer` 提供中英文混排场景下的术语翻译，保护代码标识符不被误替换。
6. **项目上下文管理** — `ProjectContextService` 封装项目 CRUD 操作的薄业务层。

## §2 文件清单

| # | 文件名 | 行数 | 主要导出 | 职责概要 |
|---|--------|------|----------|----------|
| 1 | `__init__.py` | 1 | — | 包声明，标记 `services` 为 Python 子包 |
| 2 | `iteration_controller.py` | 251 | `IterationDecision`, `IterationController` | 迭代评估决策引擎：pass/retry/fail/no-improvement-streak |
| 3 | `platform_dispatcher.py` | 247 | `PlatformDispatcher` | 产物持久化 + 可选 XMind 交付的统一分发器 |
| 4 | `project_context_service.py` | 64 | `ProjectContextService` | 项目上下文 CRUD 薄服务层 |
| 5 | `text_normalizer.py` | 193 | `normalize_text()`, `normalize_test_case()` | 中英文混排文本规范化（含保护模式） |
| 6 | `workflow_service.py` | 437 | `WorkflowService` | 工作流编排中枢，管理完整迭代生命周期 |
| 7 | `xmind_connector.py` | 218 | `XMindConnector` (Protocol), `FileXMindConnector` | XMind 连接器协议及基于文件的 ZIP 归档实现 |
| 8 | `xmind_delivery_agent.py` | 170 | `XMindDeliveryAgent` | XMind 交付代理，防御性错误处理 |
| 9 | `xmind_payload_builder.py` | 227 | `XMindPayloadBuilder` | XMind 层次节点树构建器 |

## §3 文件详细分析

### §3.1 `__init__.py`

- **路径**: `app/services/__init__.py`
- **行数**: 1
- **职责**: 包声明文件，仅含文档字符串 `"""业务服务子包。"""`，标记目录为可导入的 Python 子包。

#### §3.1.1 核心内容

空包初始化文件，无导出符号，无 `__all__` 定义。

#### §3.1.2 依赖关系

无任何导入。

#### §3.1.3 关键逻辑 / 数据流

无逻辑，纯结构性文件。

---

### §3.2 `iteration_controller.py`

- **路径**: `app/services/iteration_controller.py`
- **行数**: 251
- **职责**: 迭代评估回路的控制引擎，管理运行状态的生命周期，在每轮评估后决策下一步动作。

#### §3.2.1 核心内容

**类 `IterationDecision`** — 迭代决策结果值对象：
- `action`: `Literal["pass", "retry", "fail"]` — 三种决策类型
- `reason`: `str` — 决策原因说明
- `target_stage`: `str` — retry 时的回流目标阶段

**类 `IterationController`** — 核心控制器：
- 构造参数: `max_iterations=3`, `pass_threshold=0.7`, `min_improvement=0.03`
- `initialize_state(run_id)` → 创建 `RunState`，初始阶段为 `CONTEXT_RESEARCH`
- `decide(state, evaluation)` → 四级决策链:
  1. `score >= pass_threshold` → **pass**
  2. `iteration_index >= max_iterations - 1` → **fail**（达到上限）
  3. `_no_improvement_streak()` → **fail**（连续两轮改进幅度 < `min_improvement`）
  4. 其余情况 → **retry**，目标阶段取自 `evaluation.suggested_retry_stage`
- `update_state_after_evaluation(state, evaluation, decision, artifacts_snapshot)` → 根据决策更新状态（记录迭代日志、回流决策、时间戳）
- `mark_error(state, exception)` → 标记不可恢复错误

**辅助方法**:
- `_no_improvement_streak()`: 检查最近两轮改进是否都低于 `min_improvement`
- `_build_retry_reason()`: 从评估维度中提取不达标项构建原因
- `_find_weakest_dimension()`: 选取得分最低的评估维度名

**模块级函数**:
- `_now_iso()`: 返回 UTC ISO 格式时间字符串

#### §3.2.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.run_state` | `EvaluationReport`, `IterationRecord`, `RetryDecision`, `RunStage`, `RunState`, `RunStatus` |
| `datetime` (stdlib) | `datetime`, `timezone` |
| `typing` (stdlib) | `Literal` |

仅依赖领域模型层，无外部库依赖。

#### §3.2.3 关键逻辑 / 数据流

```
EvaluationReport ─────→ decide() ─────→ IterationDecision
       │                    │                    │
       ▼                    ▼                    ▼
  overall_score        四级优先级链          action: pass/retry/fail
  dimensions[]        (阈值→上限→         reason: 详细说明
  suggested_retry_     连续无改进→         target_stage: 回流目标
    stage              回流)
```

**no-improvement-streak 检测逻辑**: 要求 `iteration_history` 至少有 2 条记录，检查 `current_score - history[-1].score` 和 `history[-1].score - history[-2].score` 是否均低于 `min_improvement`。

**回流阶段映射**: `context_research` / `checkpoint_generation` / `draft_generation` → 对应 `RunStage` 枚举，默认回流到 `DRAFT_GENERATION`。

---

### §3.3 `platform_dispatcher.py`

- **路径**: `app/services/platform_dispatcher.py`
- **行数**: 247
- **职责**: 统一管理运行产物的本地持久化和可选的多平台交付（当前支持 XMind）。

#### §3.3.1 核心内容

**类 `PlatformDispatcher`**:
- 构造参数: `repository: FileRunRepository`, `xmind_agent: XMindDeliveryAgent | None`, `xmind_agent_factory: Callable[[Path], XMindDeliveryAgent] | None`
- 支持两种 XMind 交付模式: 直接实例（向后兼容）和工厂函数（per-run 动态创建）
- `dispatch(run_id, run, workflow_result)` → 核心分发方法:
  1. 调用 `_persist_local_artifacts()` 持久化本地产物
  2. 获取 `run_dir` 路径
  3. 优先用工厂函数创建 agent，否则使用直接实例
  4. 执行 XMind 交付（失败不阻断主流程，仅 log warning）
  5. 返回合并的产物路径字典

**`_persist_local_artifacts()`** — 持久化 7 类产物:
- `parsed_document.json` — 文档解析结果
- `research_output.json` — 研究输出
- `checkpoints.json` — 检查点列表
- `checkpoint_coverage.json` — 检查点覆盖率
- `test_cases.json` — 测试用例 JSON
- `test_cases.md` — 测试用例 Markdown
- `quality_report.json` — 质量报告

**模块级函数 `_render_test_cases_markdown()`**: 将 `TestCase` 列表渲染为中文 Markdown 文档，包含前置条件、步骤、预期结果。

#### §3.3.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.case_models` | `TestCase` |
| `app.domain.api_models` | `CaseGenerationRun` (TYPE_CHECKING) |
| `app.repositories.run_repository` | `FileRunRepository` (TYPE_CHECKING) |
| `app.services.xmind_delivery_agent` | `XMindDeliveryAgent` (TYPE_CHECKING) |
| `logging`, `pathlib`, `typing` (stdlib) | 标准库组件 |

#### §3.3.3 关键逻辑 / 数据流

```
dispatch()
  ├── _persist_local_artifacts()
  │     ├── repository.save() × N  → JSON 文件
  │     └── repository.save_text() → Markdown 文件
  └── XMind 交付（可选）
        ├── xmind_agent_factory(run_dir) [优先]
        │   或 xmind_agent [向后兼容]
        └── agent.deliver() → XMindDeliveryResult
              ├── success → artifacts["xmind_file"]
              └── failure → logger.warning()（不阻断）
```

**容错设计要点**: XMind 相关的所有操作均被 `try/except` 包裹，包括工厂函数创建、`deliver()` 调用。任何异常仅 `logger.exception()` 记录，不向上传播。

---

### §3.4 `project_context_service.py`

- **路径**: `app/services/project_context_service.py`
- **行数**: 64
- **职责**: 项目上下文的 CRUD 业务服务层，位于 API 层和仓储层之间。

#### §3.4.1 核心内容

**类 `ProjectContextService`**:
- 构造参数: `repo: Optional[ProjectRepository]`，默认创建新 `ProjectRepository` 实例
- **命令方法**:
  - `create_project(name, description, project_type, regulatory_frameworks, tech_stack, custom_standards, metadata)` → 创建 `ProjectContext` 并持久化
  - `update_project(project_id, **updates)` → 加载 → 合并更新 → 重建 → 保存，不存在时抛 `KeyError`
  - `delete_project(project_id)` → 委托仓储删除
- **查询方法**:
  - `get_project(project_id)` → 按 ID 查找
  - `list_projects()` → 列出全部

#### §3.4.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.project_models` | `ProjectContext`, `ProjectType`, `RegulatoryFramework` |
| `app.repositories.project_repository` | `ProjectRepository` |
| `datetime` (stdlib) | `datetime` |

#### §3.4.3 关键逻辑 / 数据流

`update_project` 采用 **load-merge-rebuild** 模式：通过 `model_dump()` 序列化现有对象，合并 `**updates` 后重新构造 `ProjectContext` 实例。注意 `updated_at` 使用 `datetime.utcnow()` 手动设置（未使用 timezone-aware 方式）。

---

### §3.5 `text_normalizer.py`

- **路径**: `app/services/text_normalizer.py`
- **行数**: 193
- **职责**: 中英文混排场景下的文本规范化处理，将英文操作动词和结构性术语替换为中文等价词，同时保护代码标识符。

#### §3.5.1 核心内容

**保护模式 (Protected Patterns)** — 7 类不应被替换的内容（按优先级排列）:
1. `_RE_BACKTICK` — 反引号包裹内容 `` `...` ``
2. `_RE_URL` — HTTP/HTTPS URL
3. `_RE_DOT_PATH` — 点号分隔路径（如 `response.data.items`）
4. `_RE_SNAKE_CASE` — snake_case 标识符（至少含一个 `_`）
5. `_RE_CAMEL_CASE` — camelCase 标识符
6. `_RE_PASCAL_CASE` — PascalCase 标识符
7. `_RE_ALL_CAPS` — 全大写缩写词（API, URL, JSON 等）

**占位符机制**: 使用 `\x00PH{index}\x00` 作为唯一占位符，先替换保护内容，处理完映射后再还原。

**动作词映射 (`_ACTION_MAP`)** — 30 组英文→中文映射:
- Navigate, Click, Select, Input, Enter, Check, Verify, Confirm, Create, Submit, Delete, Remove, Open, Close, Save, Cancel, Edit, Update, Search, Login, Logout, Upload, Download, Refresh 等
- 部分支持复合形式（如 `Double-click` → `双击`, `Right-click` → `右键点击`）

**结构性术语映射 (`_STRUCTURAL_MAP`)** — 7 组:
- Preconditions → 前置条件, Steps → 步骤, Expected Results → 预期结果, Main branch → 主分支, Edge cases → 边界场景, Exception/Error branch → 异常分支

**核心函数**:
- `normalize_text(text)` → 四步处理: 保护 → 动作词替换 → 术语替换 → 还原
- `normalize_test_case(case)` → 使用 `model_copy(update=...)` 对 TestCase 的 title/preconditions/steps/expected_results 进行规范化，不修改原对象

#### §3.5.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.case_models` | `TestCase` (TYPE_CHECKING) |
| `re` (stdlib) | 正则表达式 |

零运行时外部依赖，仅依赖标准库 `re`。

#### §3.5.3 关键逻辑 / 数据流

```
normalize_text(text)
  │
  ├── 快速短路: 空文本或无 ASCII 字母 → 直接返回
  │
  ├── Step 1: 保护模式扫描
  │     7 个正则按优先级依次匹配
  │     匹配内容存入 protected[] 列表，原文替换为 \x00PH{idx}\x00
  │
  ├── Step 2: _ACTION_MAP 逐项 sub()
  │
  ├── Step 3: _STRUCTURAL_MAP 逐项 sub()
  │
  └── Step 4: 遍历 protected[] 还原占位符
```

**注意**: 替换采用线性扫描（30 + 7 = 37 次正则替换），对大规模文本性能可能成为瓶颈。

---

### §3.6 `workflow_service.py`

- **路径**: `app/services/workflow_service.py`
- **行数**: 437
- **职责**: 系统的**中央编排服务**，集成迭代评估回路，协调 LangGraph 工作流引擎、评估节点、迭代控制器和平台分发器。

#### §3.6.1 核心内容

**类 `WorkflowService`** — 核心编排服务:

**构造函数参数** (8 个):
- `settings: Settings` — 全局配置
- `repository: FileRunRepository | None` — 运行记录仓储
- `llm_client: LLMClient | None` — LLM 客户端
- `state_repository: RunStateRepository | None` — 运行状态仓储
- `iteration_controller: IterationController | None` — 迭代控制器
- `platform_dispatcher: PlatformDispatcher | None` — 平台分发器
- `enable_xmind: bool = False` — XMind 交付开关
- `project_context_service: ProjectContextService | None` — 项目上下文服务

**核心公开方法**:
- `create_run(request)` → 完整运行创建与执行:
  1. `generate_run_id()` 生成 UTC+8 时间戳 ID
  2. 持久化 `request.json`
  3. `initialize_state()` 创建初始运行状态
  4. `_execute_with_iteration()` 执行迭代评估回路
  5. 构建 `CaseGenerationRun` 结果对象
  6. `_persist_run_artifacts()` 持久化所有产物
  7. 异常时: `mark_error()` 记录错误，仍然持久化失败运行
- `get_run(run_id)` → 查询: 内存缓存 → 文件系统 → 补充迭代摘要

**核心私有方法**:
- `_execute_with_iteration()` — 迭代评估回路主循环:
  ```
  while True:
      设置状态 RUNNING → 执行 workflow.invoke() → 设置状态 EVALUATING
      → evaluate() → save_evaluation_report() → decide()
      → update_state_after_evaluation() → save_run_state()
      → if pass/fail: break; if retry: continue
  ```
- `_prepare_retry_input()` — 回流时保留上游结果的策略:
  - `CONTEXT_RESEARCH`: 从头重跑
  - `CHECKPOINT_GENERATION`: 保留 parsed_document + research_output
  - `DRAFT_GENERATION`: 保留所有中间结果
- `_get_workflow()` — 懒加载 + 缓存 LangGraph 工作流实例
- `_get_llm_client()` — 懒加载 + 缓存 LLM 客户端
- `_create_xmind_agent_factory()` — 返回工厂闭包，per-run 创建 XMind 交付链
- `_build_iteration_summary()` — 从 RunState 构建轻量 IterationSummary
- `_persist_run_artifacts()` — 通过 PlatformDispatcher 持久化，补充状态/评估/日志路径

#### §3.6.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.clients.llm` | `LLMClient`, `LLMClientConfig`, `OpenAICompatibleLLMClient` |
| `app.config.settings` | `Settings` |
| `app.domain.api_models` | `CaseGenerationRequest`, `CaseGenerationRun`, `ErrorInfo`, `IterationSummary` |
| `app.domain.case_models` | `QualityReport`, `TestCase` |
| `app.domain.run_state` | `RunStage`, `RunStatus` |
| `app.graphs.main_workflow` | `build_workflow` |
| `app.nodes.evaluation` | `evaluate` |
| `app.nodes.project_context_loader` | `build_project_context_loader` |
| `app.repositories.run_repository` | `FileRunRepository` |
| `app.repositories.run_state_repository` | `RunStateRepository` |
| `app.services.iteration_controller` | `IterationController` |
| `app.services.platform_dispatcher` | `PlatformDispatcher` |
| `app.services.project_context_service` | `ProjectContextService` |
| `app.services.xmind_connector` | `FileXMindConnector` |
| `app.services.xmind_delivery_agent` | `XMindDeliveryAgent` |
| `app.services.xmind_payload_builder` | `XMindPayloadBuilder` |
| `app.utils.run_id` | `generate_run_id` |

**最高扇入/扇出的文件**: 导入跨越 5 个内部子包（clients, config, domain, graphs, nodes, repositories, services, utils），是整个系统依赖最密集的模块。

#### §3.6.3 关键逻辑 / 数据流

```
create_run(request)
  │
  ├─ generate_run_id() ──────────────────────────── run_id
  ├─ repository.save(request.json) ───────────────── 持久化请求
  ├─ iteration_controller.initialize_state() ─────── RunState
  │
  ├─ _execute_with_iteration() ◄─── 核心迭代回路
  │   │
  │   ├── [Loop] workflow.invoke(input) ──────────── LangGraph 执行
  │   │     ├── evaluate(test_cases, checkpoints, ...) ─── 结构化评估
  │   │     ├── save_evaluation_report() ───────────── 持久化评估
  │   │     ├── decide(state, evaluation) ──────────── 迭代决策
  │   │     ├── update_state_after_evaluation() ──────── 更新状态
  │   │     └── pass/fail → break | retry → continue
  │   │
  │   └── _prepare_retry_input() ──── 回流时保留上游结果
  │
  ├─ CaseGenerationRun() ────────────────────── 构建结果对象
  │
  └─ _persist_run_artifacts()
        └── platform_dispatcher.dispatch() ──────── 本地持久化 + XMind
```

---

### §3.7 `xmind_connector.py`

- **路径**: `app/services/xmind_connector.py`
- **行数**: 218
- **职责**: 定义 XMind 连接器的协议接口和基于文件系统的默认实现（ZIP 归档 `.xmind` 文件生成）。

#### §3.7.1 核心内容

**Protocol `XMindConnector`** (runtime_checkable):
- `create_map(root_node: XMindNode, title: str) → XMindDeliveryResult`
- `health_check() → bool`

**类 `FileXMindConnector`** — Protocol 的文件系统实现:
- `__init__(output_dir)` — 确保输出目录存在
- `create_map(root_node, title)` → 生成 `.xmind` ZIP 文件:
  1. 固定文件名 `checklist.xmind`
  2. `_node_to_topic()` 递归转换节点树
  3. 构建 `content.json`（sheet + rootTopic）、`metadata.json`（creator info）、`manifest.json`（文件清单）
  4. 使用 `zipfile.ZipFile(ZIP_DEFLATED)` 写入
- `health_check()` → 在输出目录写/删临时文件检测可写性

**辅助函数**:
- `_node_to_topic(node: XMindNode)` → 递归将 `XMindNode` 转换为 XMind JSON topic 字典（处理 children/markers/notes/labels）
- `_sanitize_filename(name)` → 安全文件名转换（保留备用，当前未使用）

**常量**: `XMIND_DEFAULT_FILENAME = "checklist.xmind"`

#### §3.7.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.xmind_models` | `XMindDeliveryResult`, `XMindNode` |
| `json`, `zipfile`, `pathlib`, `uuid` (stdlib) | 标准库组件 |

#### §3.7.3 关键逻辑 / 数据流

```
XMindNode (tree)
  │
  ▼
_node_to_topic() ──── 递归转换
  │
  ▼
content.json = [{id, class:"sheet", title, rootTopic: {...}}]
metadata.json = {creator: {name:"AutoChecklist", version:"0.1.0"}}
manifest.json = {file-entries: {...}}
  │
  ▼
zipfile.ZipFile("checklist.xmind", "w", ZIP_DEFLATED)
  └── writestr() × 3 个 JSON 文件
```

XMind 文件格式兼容 XMind 8/Zen，本质是 ZIP 归档包含 JSON 描述。

---

### §3.8 `xmind_delivery_agent.py`

- **路径**: `app/services/xmind_delivery_agent.py`
- **行数**: 170
- **职责**: XMind 思维导图的构建与交付代理，编排 PayloadBuilder 和 Connector 的完整流程，并提供防御性错误处理。

#### §3.8.1 核心内容

**类 `XMindDeliveryAgent`**:
- 构造参数: `connector: XMindConnector`, `payload_builder: XMindPayloadBuilder`, `output_dir: str | Path`
- `deliver(run_id, test_cases, checkpoints, research_output, title, output_dir)`:
  1. 如果指定 `output_dir` 且 connector 是 `FileXMindConnector`，动态更新其 `output_dir`
  2. `payload_builder.build()` 构建 `XMindNode` 树
  3. `connector.create_map()` 生成 `.xmind` 文件
  4. 更新 `delivery_time`
  5. `_save_delivery_artifact()` 保存 `xmind_delivery.json` 元数据
  6. **外层 try/except 全捕获**: 失败时构造错误 `XMindDeliveryResult`，并尽力保存错误元数据

- `_save_delivery_artifact(run_id, result, base_dir)`:
  - 智能路径判断: 如果 `base_dir.name == run_id` 则直接写入，否则在 `base_dir/run_id/` 下写入
  - 输出 `xmind_delivery.json`

#### §3.8.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.xmind_models` | `XMindDeliveryResult`, `XMindNode` |
| `app.services.xmind_connector` | `XMindConnector`, `FileXMindConnector` (运行时) |
| `app.services.xmind_payload_builder` | `XMindPayloadBuilder` |
| `app.domain.case_models` | `TestCase` (TYPE_CHECKING) |
| `app.domain.checkpoint_models` | `Checkpoint` (TYPE_CHECKING) |
| `app.domain.research_models` | `ResearchOutput` (TYPE_CHECKING) |

#### §3.8.3 关键逻辑 / 数据流

```
deliver()
  │
  ├── [可选] 动态更新 connector.output_dir
  │
  ├── payload_builder.build()
  │     test_cases + checkpoints + research_output
  │     → XMindNode (root)
  │
  ├── connector.create_map(root_node, title)
  │     → XMindDeliveryResult
  │
  ├── _save_delivery_artifact()
  │     → xmind_delivery.json
  │
  └── [异常] → XMindDeliveryResult(success=False)
              → 尽力保存错误元数据
```

**防御性设计**: `deliver()` 方法绝不抛出异常。外层 `try/except Exception` 捕获所有错误，内层的元数据保存也有独立的 `try/except`。

---

### §3.9 `xmind_payload_builder.py`

- **路径**: `app/services/xmind_payload_builder.py`
- **行数**: 227
- **职责**: 将测试用例、检查点和研究输出映射为 XMind 思维导图的 `XMindNode` 层次结构。

#### §3.9.1 核心内容

**常量映射**:
- `_CATEGORY_MARKERS`: 分类 → XMind 星标颜色 (functional→blue, edge_case→orange, performance→green, security→red, usability→purple)
- `_PRIORITY_MARKERS`: 优先级 → XMind 优先级标记 (P0→priority-1 ... P3→priority-4)

**类 `XMindPayloadBuilder`**:
- `build(test_cases, checkpoints, research_output, run_id, title)`:
  1. 构建 `checkpoint_id → Checkpoint` 查找表
  2. 按 `checkpoint_id` 对测试用例分组（无关联的归入 ungrouped）
  3. 构建一级节点: 每个 checkpoint 一个分组节点
  4. 未关联用例归到「其他用例」节点
  5. 检测未覆盖的 fact（通过 `fact_ids` 集合差集），生成「未覆盖的事实」节点（红旗标记）
  6. 返回根节点 `XMindNode`

- `_build_checkpoint_node(checkpoint, cases)` → checkpoint 级节点:
  - markers: 按分类选择星标颜色
  - notes: 聚合目标描述和证据引用（section_title + line_range + excerpt）
  - labels: [risk, category]
  - children: 测试用例节点列表

- `_build_case_node(case)` → 测试用例级节点:
  - labels: [priority]
  - markers: 优先级图标
  - children: 前置条件节点 + 步骤节点（带编号）+ 预期结果节点

#### §3.9.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.xmind_models` | `XMindNode` |
| `app.domain.case_models` | `TestCase` (TYPE_CHECKING) |
| `app.domain.checkpoint_models` | `Checkpoint` (TYPE_CHECKING) |
| `app.domain.research_models` | `ResearchOutput` (TYPE_CHECKING) |

#### §3.9.3 关键逻辑 / 数据流

```
build()
  │
  ├── checkpoint_id → Checkpoint 查找表
  ├── test_cases 按 checkpoint_id 分组
  │     ├── grouped: {cp_id: [cases...]}
  │     └── ungrouped: [cases...]
  │
  ├── 一级节点构建:
  │     ├── [CP-001] checkpoint_title
  │     │     └── [TC-001] case_title
  │     │           ├── 前置条件 → [子节点...]
  │     │           ├── 步骤 → [1. xxx, 2. yyy...]
  │     │           └── 预期结果 → [子节点...]
  │     ├── 其他用例
  │     └── 未覆盖的事实 (N) 🚩
  │
  └── XMindNode(title=root_title, children=[...])

层次结构: Root → Checkpoint → TestCase → Steps/Results
```

## §4 目录级依赖关系

### 内部依赖（services 目录内）

```
workflow_service.py ──────┬──→ iteration_controller.py
                          ├──→ platform_dispatcher.py
                          ├──→ project_context_service.py
                          ├──→ xmind_connector.py (FileXMindConnector)
                          ├──→ xmind_delivery_agent.py
                          └──→ xmind_payload_builder.py

platform_dispatcher.py ───┬──→ xmind_delivery_agent.py (TYPE_CHECKING)
                          └──→ run_repository.py (TYPE_CHECKING)

xmind_delivery_agent.py ──┬──→ xmind_connector.py
                          └──→ xmind_payload_builder.py
```

### 外部依赖（依赖其他子包）

| 被依赖子包 | 依赖文件 |
|-----------|--------|
| `app.domain.*` | 所有 service 文件（领域模型是核心数据载体） |
| `app.repositories.*` | `workflow_service`, `platform_dispatcher` |
| `app.clients.llm` | `workflow_service` |
| `app.config.settings` | `workflow_service` |
| `app.graphs.main_workflow` | `workflow_service` |
| `app.nodes.*` | `workflow_service` |
| `app.utils.run_id` | `workflow_service` |

### 反向依赖（谁依赖 services）

预期被 `app/api/` 层（FastAPI 路由）调用。

## §5 设计模式与架构特征

1. **Strategy Pattern（策略模式）** — `XMindConnector` Protocol 定义连接器接口，`FileXMindConnector` 提供文件系统实现，可替换为云端 API 实现。

2. **Factory Method（工厂方法）** — `WorkflowService._create_xmind_agent_factory()` 返回闭包工厂函数，实现 per-run 的 XMind Agent 动态创建。

3. **Chain of Responsibility（职责链）** — `IterationController.decide()` 的四级优先级链：阈值通过 → 达到上限 → 无改进连续 → 回流重试。

4. **Mediator Pattern（中介者模式）** — `WorkflowService` 充当中央协调者，编排 `IterationController`、`PlatformDispatcher`、LangGraph 工作流等多个组件。

5. **Defensive Programming（防御性编程）** — XMind 交付链的三层错误隔离: `PlatformDispatcher` → `XMindDeliveryAgent` → `XMindConnector`，每层独立 try/except，确保交付失败不影响主流程。

6. **Placeholder-Protect-Replace Pattern（占位符保护替换模式）** — `text_normalizer.py` 的四步处理流程：保护 → 替换 → 替换 → 还原，确保代码标识符在文本规范化过程中不被误修改。

7. **Lazy Initialization（延迟初始化）** — `WorkflowService` 的 `_workflow` 和 `_llm_client` 使用懒加载 + 缓存模式。

8. **命令/查询分离 (CQS)** — `ProjectContextService` 明确分离命令方法（create/update/delete）和查询方法（get/list）。

## §6 潜在关注点

1. **`workflow_service.py` 依赖过重** — 437 行代码导入 17 个内部模块，扇出度极高。建议考虑拆分为独立的 RunFactory、IterationLoop、ArtifactPersister 等更细粒度的组件。

2. **`_render_test_cases_markdown()` 重复定义** — 该函数在 `platform_dispatcher.py` 和 `workflow_service.py` 中各定义了一份完全相同的实现，违反 DRY 原则。应提取到共享工具模块。

3. **`text_normalizer.py` 性能隐患** — 每次 `normalize_text()` 调用执行 7 次保护模式正则扫描 + 37 次替换正则扫描，合计 44 次正则操作。对批量处理大量测试用例场景可能成为瓶颈。

4. **`project_context_service.py` 使用 `datetime.utcnow()`** — 已被 Python 3.12 标记为 deprecated，建议统一使用 `datetime.now(timezone.utc)`（与 `iteration_controller.py` 中的 `_now_iso()` 保持一致）。

5. **`xmind_delivery_agent.py` 中的 `isinstance` 检查** — `deliver()` 方法在运行时检查 `isinstance(self.connector, FileXMindConnector)` 来决定是否可以动态更新 `output_dir`，打破了 Protocol 的多态性。建议将 `output_dir` 设为 Protocol 的可选属性或通过构造函数注入。

6. **内存缓存无上限** — `WorkflowService._run_registry` 为 `dict[str, CaseGenerationRun]`，无 TTL 或容量限制，长时间运行可能导致内存增长。

7. **XMind 固定文件名** — `XMIND_DEFAULT_FILENAME = "checklist.xmind"` 意味着同一 run 目录只能有一个 XMind 文件。如果未来支持增量更新或多版本，需要调整命名策略。