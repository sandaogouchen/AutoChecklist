# tests/unit/ 目录分析 (Part 2/2)

> 生成时间: 2026-03-18 | 源文件数: 8 (共 17, 本篇 10-17) | 分析策略: Test — for each file list all test functions with brief descriptions, fixtures used, coverage targets

## §1 目录职责

`tests/unit/` 目录包含 AutoChecklist 项目的**单元测试**，覆盖领域模型、工作流节点、服务层、仓储层和工具函数。17 个测试文件按功能模块组织，各自聚焦一个被测模块或紧密相关的一组模块。测试以 pytest 为框架，广泛使用 `tmp_path`、`monkeypatch` 内置 fixture 和 `conftest.py` 中的 Fake LLM 客户端。本篇为 Part 2/2，覆盖第 10-17 个测试文件。Part 1 见 `tests/unit/_ANALYSIS_1.md`。

## §2 文件清单

| 序号 | 文件名 | 行数 | 测试函数/方法数 | 覆盖目标 |
|------|--------|------|----------------|----------|
| 1 | `test_checkpoint.py` | ~125 | 12 | checkpoint 模型、生成节点、评估节点 |
| 2 | `test_evaluation.py` | ~290 | 16 | 评估节点 `evaluate()` + `IterationController` |
| 3 | `test_health.py` | ~8 | 1 | `/healthz` 端点 |
| 4 | `test_llm_client.py` | ~210 | 12 | `OpenAICompatibleLLMClient` 配置验证、URL 处理、JSON 解析、重试 |
| 5 | `test_markdown_parser.py` | ~10 | 1 | `MarkdownParser` section 提取 |
| 6 | `test_models.py` | ~8 | 1 | `CaseGenerationRequest` 默认值 |
| 7 | `test_nodes.py` | ~105 | 4 | reflection 去重、scenario_planner、context_research prompt |
| 8 | `test_project_context_loader.py` | ~130 | 9 | `build_project_context_loader` 工厂函数 |
| 9 | `test_project_context_service.py` | ~40 | 6 | `ProjectContextService` CRUD |
| 10 | `test_project_models.py` | ~40 | 4 | `ProjectContext` 模型默认值、summary_text、ID 唯一性 |
| 11 | `test_project_repository.py` | ~35 | 6 | `ProjectRepository` 内存 CRUD |
| 12 | `test_project_routes.py` | ~50 | 7 | `/projects` REST API 端点 |
| 13 | `test_run_id.py` | ~140 | 8 | `generate_run_id()` 格式、冲突处理、时区、UUID 回退 |
| 14 | `test_run_repository.py` | ~9 | 1 | `FileRunRepository` 保存/加载 |
| 15 | `test_run_state.py` | ~190 | 11 | RunState/EvaluationReport 模型 + RunStateRepository |
| 16 | `test_text_normalizer.py` | ~260 | 30+ | `normalize_text()` / `normalize_test_case()` 文本规范化 |
| 17 | `test_xmind_delivery.py` | ~470 | 15 | XMind 全链路：PayloadBuilder、FileXMindConnector、DeliveryAgent、PlatformDispatcher |

## §3 文件详细分析

### §3.10 test_project_models.py

- **路径**: `tests/unit/test_project_models.py`
- **行数**: ~40
- **职责**: `ProjectContext` 模型测试

#### §3.10.1 核心内容

| 测试方法 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_defaults` | 默认值正确（type=OTHER, 空列表） | 无 | 模型默认值 |
| `test_summary_text_minimal` | 最小输入的 summary_text() | 无 | summary 生成 |
| `test_summary_text_full` | 完整输入的 summary_text() 含所有字段 | 无 | summary 全字段 |
| `test_id_uniqueness` | 不同实例 ID 不同 | 无 | UUID 生成 |

#### §3.10.2 依赖关系

- **被测模块**: `app.domain.project_models.ProjectContext`, `ProjectType`, `RegulatoryFramework`

#### §3.10.3 关键逻辑 / 数据流

验证 `summary_text()` 方法根据 project_type、regulatory_frameworks、tech_stack、custom_standards 等字段生成人类可读的摘要文本。

---

### §3.11 test_project_repository.py

- **路径**: `tests/unit/test_project_repository.py`
- **行数**: ~35
- **职责**: `ProjectRepository` 内存仓储 CRUD 测试

#### §3.11.1 核心内容

| 测试方法 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_save_and_get` | 保存并获取 | 无 | save + get |
| `test_get_missing_returns_none` | 不存在返回 None | 无 | get 空结果 |
| `test_list_all_empty` | 空仓储列表为空 | 无 | list 空结果 |
| `test_list_all` | 多条目列表 | 无 | list |
| `test_delete_existing` | 删除已存在条目 | 无 | delete |
| `test_delete_missing` | 删除不存在条目返回 False | 无 | delete 异常 |

#### §3.11.2 依赖关系

- **被测模块**: `app.repositories.project_repository.ProjectRepository`

#### §3.11.3 关键逻辑 / 数据流

标准内存仓储 CRUD 模式，通过 `_make_repo()` 工厂方法创建新实例。

---

### §3.12 test_project_routes.py

- **路径**: `tests/unit/test_project_routes.py`
- **行数**: ~50
- **职责**: `/projects` REST API 端点测试

#### §3.12.1 核心内容

| 测试方法 | 描述 | Fixture | 关键断言 |
|----------|------|---------|----------|
| `test_create_project` | POST /projects 创建项目 | 无 | status=201, name 正确, id 存在 |
| `test_list_projects` | GET /projects 列出项目 | 无 | status=200, 返回列表 |
| `test_get_project` | GET /projects/{id} 获取 | 无 | status=200, id 匹配 |
| `test_get_project_not_found` | GET 不存在项目 | 无 | status=404 |
| `test_update_project` | PATCH /projects/{id} 更新 | 无 | status=200, name 更新 |
| `test_delete_project` | DELETE /projects/{id} 删除 | 无 | status=204 |
| `test_delete_project_not_found` | DELETE 不存在项目 | 无 | status=404 |

**注意**: 使用全局 `app` 实例和模块级 `client = TestClient(app)`，测试之间共享应用状态。

#### §3.12.2 依赖关系

- **被测模块**: `app.main.app`（全局 FastAPI 实例）
- **无 tmp_path 隔离**: 测试依赖全局内存仓储

#### §3.12.3 关键逻辑 / 数据流

REST API 标准 CRUD 测试，覆盖 201/200/204/404 状态码。

---

### §3.13 test_run_id.py

- **路径**: `tests/unit/test_run_id.py`
- **行数**: ~140
- **职责**: `generate_run_id()` 函数的 ID 生成逻辑全面测试

#### §3.13.1 核心内容

使用 `TestGenerateRunId` 测试类。

| 测试方法 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_basic_format` | YYYY-MM-DD_HH-mm-ss 格式 | `tmp_path` | 基本格式 |
| `test_no_conflict_uses_base_id` | 无冲突使用基础 ID | `tmp_path` | 无冲突路径 |
| `test_conflict_appends_sequence_number` | 冲突时追加 _2 后缀 | `tmp_path` | 单次冲突 |
| `test_multiple_conflicts_increment_sequence` | 多次冲突递增序号 | `tmp_path` | 多次冲突 |
| `test_exceeds_max_retries_falls_back_to_uuid` | 超过 100 次冲突回退 UUID | `tmp_path` | UUID 回退 |
| `test_uses_utc_plus_8_timezone` | 使用 UTC+8 时区 | `tmp_path` | 时区正确性 |
| `test_custom_timezone` | 支持自定义时区 | `tmp_path` | 时区参数 |
| `test_run_id_contains_only_safe_characters` | 仅含文件系统安全字符 | `tmp_path` | 字符安全性 |

#### §3.13.2 依赖关系

- **被测模块**: `app.utils.run_id.generate_run_id`
- **Mock**: `unittest.mock.patch("app.utils.run_id.datetime")` 固定时间
- **Fixture**: `tmp_path`

#### §3.13.3 关键逻辑 / 数据流

通过创建目录模拟冲突场景，验证 ID 生成的冲突解决策略：基础 ID -> _2 后缀 -> _3 ... -> _N -> UUID 回退。

---

### §3.14 test_run_repository.py

- **路径**: `tests/unit/test_run_repository.py`
- **行数**: ~9
- **职责**: `FileRunRepository` 最小验证

#### §3.14.1 核心内容

| 测试函数 | 描述 | Fixture | 关键断言 |
|----------|------|---------|----------|
| `test_file_run_repository_persists_run` | 保存后加载数据一致 | `tmp_path` | status == "succeeded" |

#### §3.14.2 依赖关系

- **被测模块**: `app.repositories.run_repository.FileRunRepository`

#### §3.14.3 关键逻辑 / 数据流

save -> load 往返验证。

---

### §3.15 test_run_state.py

- **路径**: `tests/unit/test_run_state.py`
- **行数**: ~190
- **职责**: 运行状态模型和仓储的全面测试

#### §3.15.1 核心内容

**模型测试（6 个）**:

| 测试函数 | 描述 | 覆盖目标 |
|----------|------|----------|
| `test_run_state_defaults` | RunState 默认值 | RunState 模型 |
| `test_run_status_enum_values` | RunStatus 枚举值 | 6 个状态值 |
| `test_run_stage_enum_values` | RunStage 枚举值 | 5 个阶段值 |
| `test_evaluation_report_model` | EvaluationReport 构建 | EvaluationReport 模型 |
| `test_iteration_record_model` | IterationRecord 构建 | IterationRecord 模型 |
| `test_retry_decision_model` | RetryDecision 构建 | RetryDecision 模型 |
| `test_run_state_serialization` | JSON 序列化往返 | model_dump + model_validate |

**仓储测试（5 个）**:

| 测试函数 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_run_state_repository_save_and_load` | run_state 保存/加载 | `tmp_path` | save_run_state + load_run_state |
| `test_run_state_repository_save_evaluation_report` | evaluation_report 保存/加载 | `tmp_path` | save_evaluation_report + load |
| `test_run_state_repository_save_iteration_log` | iteration_log 保存/加载 | `tmp_path` | save_iteration_log + load |
| `test_run_state_repository_exists_check` | 存在性检查 | `tmp_path` | run_state_exists |
| `test_run_state_repository_preserves_history_versions` | 多轮评估报告保留历史版本 | `tmp_path` | 版本化存储 |

#### §3.15.2 依赖关系

- **被测模块**: `app.domain.run_state` 全部模型, `app.repositories.run_state_repository.RunStateRepository`

#### §3.15.3 关键逻辑 / 数据流

RunStateRepository 使用 `tmp_path/<run_id>/` 目录结构存储 JSON 文件，支持 evaluation_report 的版本化存储（`evaluation_report_iter_N.json`）。

---

### §3.16 test_text_normalizer.py

- **路径**: `tests/unit/test_text_normalizer.py`
- **行数**: ~260
- **职责**: 文本规范化服务的全面测试

#### §3.16.1 核心内容

使用 8 个测试类组织，覆盖 30+ 测试方法：

| 测试类 | 测试方法数 | 覆盖目标 |
|--------|-----------|----------|
| `TestNormalizeCommonEnglishActions` | 23 | 英文动作词 -> 中文替换（click->点击, select->选择 等 23 个词） |
| `TestPreserveSnakeCase` | 3 | snake_case 标识符保护（campaign_id, user_name, order_status） |
| `TestPreserveCamelCase` | 3 | camelCase 标识符保护（handleClick, getUserInfo, isActive） |
| `TestPreserveAllCaps` | 5 | ALL_CAPS 缩写词保护（API, URL, JSON, ID, CTA） |
| `TestPreserveBacktickContent` | 3 | 反引号内容保护 |
| `TestMixedChineseEnglish` | 4 | 中英文混排处理、空字符串、空白字符串 |
| `TestNormalizeStructuralTerms` | 8 | 结构性术语替换（Preconditions->前置条件, Steps->步骤 等） |
| `TestNormalizeTestCase` | 1 | TestCase 对象整体规范化（title/steps/preconditions/expected_results 被处理，id/priority/checkpoint_id 不被修改） |
| `TestPreserveURL` | 2 | HTTP URL 保护 |
| `TestPreserveJSONFieldNames` | 2 | JSON 风格字段路径保护（response.data.items） |

#### §3.16.2 依赖关系

- **被测模块**: `app.services.text_normalizer.normalize_text`, `app.services.text_normalizer.normalize_test_case`
- **模型依赖**: `app.domain.case_models.TestCase`
- **Fixture**: 无

#### §3.16.3 关键逻辑 / 数据流

`normalize_text()` 流程: 保护 backtick/URL/snake_case/camelCase/ALL_CAPS -> 替换英文动作词和结构性术语 -> 恢复受保护内容。`normalize_test_case()` 对 TestCase 的 title/steps/preconditions/expected_results 字段逐一调用 `normalize_text()`，跳过 id/priority 等标识符字段。

---

### §3.17 test_xmind_delivery.py

- **路径**: `tests/unit/test_xmind_delivery.py`
- **行数**: ~470
- **职责**: XMind 交付全链路测试

#### §3.17.1 核心内容

**辅助工厂函数**: `_make_test_case()`, `_make_checkpoint()`, `_make_research_output()` 创建测试数据。

使用 5 个测试类组织：

| 测试类 | 测试方法数 | 覆盖目标 |
|--------|-----------|----------|
| `TestXMindPayloadBuilder` | 6 | 树结构构建、多用例分组、空用例、无研究输出、节点结构、优先级标签 |
| `TestFileXMindConnector` | 3 | .xmind ZIP 文件生成、运行目录输出、健康检查 |
| `TestXMindDeliveryAgent` | 3 | 成功交付流程、connector 异常优雅降级、空用例交付 |
| `TestPlatformDispatcher` | 3 | xmind_agent_factory 集成、xmind_agent 向后兼容、XMind 失败不影响整体 |
| `TestXMindDeliveryResultInArtifacts` | 1 | 交付结果元数据持久化 |

**关键验证**:
- .xmind 文件是有效 ZIP，包含 `content.json` 和 `metadata.json`
- content.json 结构正确：`sheet.class == "sheet"`, `rootTopic.title` 匹配
- 文件名固定为 `checklist.xmind`
- 元数据文件 `xmind_delivery.json` 包含 success 和 delivery_time

#### §3.17.2 依赖关系

- **被测模块**: `XMindPayloadBuilder`, `FileXMindConnector`, `XMindDeliveryAgent`, `PlatformDispatcher`
- **模型依赖**: `TestCase`, `Checkpoint`, `ResearchOutput`, `XMindNode`, `XMindDeliveryResult`, `CaseGenerationRequest`, `CaseGenerationRun`, `QualityReport`, `FileRunRepository`
- **Fixture**: `tmp_path`
- **Mock**: `MagicMock` 用于模拟 connector 异常和 xmind_agent 失败

#### §3.17.3 关键逻辑 / 数据流

```
XMindPayloadBuilder.build(test_cases, checkpoints, research_output, title)
    --> XMindNode 树
        --> FileXMindConnector.create_map(root, title)
            --> .xmind ZIP 文件 (content.json + metadata.json)
                --> XMindDeliveryAgent.deliver(...)
                    --> XMindDeliveryResult + xmind_delivery.json
                        --> PlatformDispatcher.dispatch(...)
                            --> artifacts dict (含 xmind_file 路径)
```

## §4 目录级依赖关系

```
tests/unit/
  ├── 模型层测试
  │   ├── test_models.py -----------> app.domain.api_models
  │   ├── test_project_models.py ---> app.domain.project_models
  │   ├── test_checkpoint.py -------> app.domain.checkpoint_models, research_models
  │   └── test_run_state.py --------> app.domain.run_state
  │
  ├── 节点层测试
  │   ├── test_nodes.py ------------> app.nodes.reflection, scenario_planner, context_research
  │   ├── test_project_context_loader.py -> app.nodes.project_context_loader
  │   └── test_evaluation.py -------> app.nodes.evaluation, app.services.iteration_controller
  │
  ├── 客户端层测试
  │   └── test_llm_client.py -------> app.clients.llm
  │
  ├── 仓储层测试
  │   ├── test_run_repository.py ---> app.repositories.run_repository
  │   ├── test_run_state.py --------> app.repositories.run_state_repository
  │   └── test_project_repository.py -> app.repositories.project_repository
  │
  ├── 服务层测试
  │   ├── test_project_context_service.py -> app.services.project_context_service
  │   ├── test_text_normalizer.py ---------> app.services.text_normalizer
  │   └── test_xmind_delivery.py ----------> app.services.xmind_*
  │
  ├── 工具层测试
  │   └── test_run_id.py -----------> app.utils.run_id
  │
  ├── API 层测试
  │   ├── test_health.py -----------> app.main (healthz)
  │   ├── test_project_routes.py ---> app.main (projects)
  │   └── test_markdown_parser.py --> app.parsers.factory
  │
  └── 共同依赖
      ├── tests/conftest.py (fake_llm_client fixtures)
      └── tests/fixtures/sample_prd.md
```

## §5 设计模式与架构特征

| 模式/特征 | 体现位置 |
|-----------|----------|
| **一模块一测试文件** | 每个测试文件对应一个或一组紧密相关的被测模块 |
| **测试类组织** | 复杂文件使用测试类分组（TestXMindPayloadBuilder 等 5 个类） |
| **参数化测试** | test_llm_client.py 使用 `@pytest.mark.parametrize` 覆盖多种 URL 格式 |
| **Recording Mock** | `_RecordingHttpxClient`, `_RecordingResearchLLMClient` 记录调用历史 |
| **MagicMock + spec** | test_project_context_loader.py 使用 `MagicMock(spec=...)` 保持类型安全 |
| **工厂方法隔离** | `_svc()`, `_make_repo()`, `_build_client()` 每个测试创建新实例 |
| **文件系统验证** | test_xmind_delivery.py 验证 ZIP 结构、JSON 内容、文件名和目录 |
| **辅助工厂函数** | `_make_test_case()`, `_make_checkpoint()` 简化测试数据构建 |
| **防御性测试** | test_project_context_loader.py 覆盖 9 种输入变体包括异常路径 |

## §6 潜在关注点

1. **测试深度不均衡**: `test_text_normalizer.py`（30+ 测试）和 `test_xmind_delivery.py`（15 测试）极为详尽，而 `test_markdown_parser.py`（1 测试）、`test_models.py`（1 测试）、`test_run_repository.py`（1 测试）覆盖极为薄弱。
2. **test_project_routes.py 使用全局状态**: 使用模块级 `client = TestClient(app)` 和全局 `app` 实例，测试之间可能产生状态污染（前一个测试创建的项目影响后续测试）。
3. **test_xmind_delivery.py 中 `_make_test_case` 使用非标准字段**: 辅助函数使用 `module`, `steps`(str), `expected_result`(str), `test_category` 等字段名，与主代码中 `TestCase` 的 `steps`(list), `expected_results`(list), `category` 可能存在命名不一致，暗示 XMind 模块可能使用了不同的 TestCase 定义或别名。
4. **缺少 parser 错误路径测试**: `test_markdown_parser.py` 仅有一个正向测试，未覆盖空文件、无标题文件、编码异常等错误路径。
5. **text_normalizer 测试仅验证包含关系**: 多数断言为 `"点击" in result`，不验证完整输出字符串，可能遗漏副作用（如意外替换其他文本）。