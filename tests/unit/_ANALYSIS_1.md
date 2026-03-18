# tests/unit/ 目录分析 (Part 1/2)

> 生成时间: 2026-03-18 | 源文件数: 9 (共 17, 本篇 1-9) | 分析策略: Test — for each file list all test functions with brief descriptions, fixtures used, coverage targets

## §1 目录职责

`tests/unit/` 目录包含 AutoChecklist 项目的**单元测试**，覆盖领域模型、工作流节点、服务层、仓储层和工具函数。17 个测试文件按功能模块组织，各自聚焦一个被测模块或紧密相关的一组模块。测试以 pytest 为框架，广泛使用 `tmp_path`、`monkeypatch` 内置 fixture 和 `conftest.py` 中的 Fake LLM 客户端。

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

### §3.1 test_checkpoint.py

- **路径**: `tests/unit/test_checkpoint.py`
- **行数**: ~125
- **职责**: 测试 checkpoint 模型、ID 生成、评估节点去重和覆盖初始化

#### §3.1.1 核心内容

| 测试函数 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_generate_checkpoint_id_is_stable` | 相同输入生成相同 CP-ID | 无 | `generate_checkpoint_id` |
| `test_generate_checkpoint_id_differs_for_different_input` | 不同输入生成不同 CP-ID | 无 | `generate_checkpoint_id` |
| `test_generate_checkpoint_id_case_insensitive` | 大小写不敏感 | 无 | `generate_checkpoint_id` |
| `test_checkpoint_model_defaults` | Checkpoint 默认值 | 无 | `Checkpoint` 模型 |
| `test_checkpoint_coverage_model` | CheckpointCoverage 构建 | 无 | `CheckpointCoverage` 模型 |
| `test_synthesize_facts_from_legacy` | 从旧版字段合成 facts | 无 | `_synthesize_facts_from_legacy` |
| `test_checkpoint_evaluator_deduplicates` | 按标题去重（大小写不敏感） | 无 | `checkpoint_evaluator_node` |
| `test_checkpoint_evaluator_initializes_coverage` | 初始化覆盖记录 | 无 | `checkpoint_evaluator_node` |
| `test_research_fact_model` | ResearchFact 构建 | 无 | `ResearchFact` 模型 |
| `test_research_output_backward_compatible` | facts 字段默认空列表 | 无 | `ResearchOutput` 模型 |

#### §3.1.2 依赖关系

- **被测模块**: `app.domain.checkpoint_models`, `app.domain.research_models`, `app.nodes.checkpoint_evaluator`, `app.nodes.checkpoint_generator`
- **Fixture**: 无外部 fixture（纯模型和函数测试）

#### §3.1.3 关键逻辑 / 数据流

checkpoint_evaluator_node 接收 `{"checkpoints": [...]}` 状态字典，执行标题去重（大小写不敏感）后返回去重结果和初始化的覆盖记录。`_synthesize_facts_from_legacy` 从 ResearchOutput 的 feature_topics/user_scenarios/constraints 字段合成 ResearchFact 列表。

---

### §3.2 test_evaluation.py

- **路径**: `tests/unit/test_evaluation.py`
- **行数**: ~290
- **职责**: 评估节点 `evaluate()` 函数和 `IterationController` 的全面测试

#### §3.2.1 核心内容

**评估节点测试（8 个）**:

| 测试函数 | 描述 | 覆盖目标 |
|----------|------|----------|
| `test_evaluate_returns_structured_report` | 返回含 6 个维度的结构化报告 | `evaluate()` |
| `test_evaluate_detects_uncovered_facts` | 检测未被 checkpoint 覆盖的 facts | fact_coverage 维度 |
| `test_evaluate_detects_uncovered_checkpoints` | 检测未被 testcase 覆盖的 checkpoints | checkpoint_coverage 维度 |
| `test_evaluate_detects_missing_evidence` | 检测缺 evidence 的 testcase | evidence_completeness 维度 |
| `test_evaluate_detects_duplicates` | 检测重复标题 | duplicate_rate 维度 |
| `test_evaluate_detects_incomplete_cases` | 检测缺步骤/缺预期结果 | case_completeness 维度 |
| `test_evaluate_suggests_retry_stage_for_low_fact_coverage` | 低 fact 覆盖率建议回到 context_research | suggested_retry_stage |
| `test_evaluate_comparison_with_previous` | 有前一轮分数时生成比较说明 | comparison_with_previous |

**评估 6 个维度**: fact_coverage, checkpoint_coverage, evidence_completeness, duplicate_rate, case_completeness, branch_coverage

**迭代控制器测试（8 个）**:

| 测试函数 | 描述 | 覆盖目标 |
|----------|------|----------|
| `test_controller_passes_on_high_score` | 高分时返回 pass | `IterationController.decide()` |
| `test_controller_retries_on_low_score` | 低分时返回 retry + target_stage | `IterationController.decide()` |
| `test_controller_fails_on_max_iterations` | 达最大迭代数返回 fail | `IterationController.decide()` |
| `test_controller_fails_on_no_improvement_streak` | 连续无改进返回 fail | min_improvement 逻辑 |
| `test_controller_update_state_after_pass` | pass 后状态更新为 succeeded | `update_state_after_evaluation()` |
| `test_controller_update_state_after_retry` | retry 后状态更新为 retrying | `update_state_after_evaluation()` |
| `test_controller_update_state_after_fail` | fail 后状态更新为 failed | `update_state_after_evaluation()` |
| `test_controller_mark_error` | 异常后标记 failed + 错误信息 | `mark_error()` |

#### §3.2.2 依赖关系

- **被测模块**: `app.nodes.evaluation.evaluate`, `app.services.iteration_controller.IterationController`
- **模型依赖**: `TestCase`, `Checkpoint`, `ResearchOutput`, `ResearchFact`, `EvidenceRef`, `EvaluationReport`, `RunState`, `RunStatus`, `RunStage`
- **Fixture**: 无外部 fixture

#### §3.2.3 关键逻辑 / 数据流

`evaluate()` 接收 test_cases + checkpoints + research_output，计算 6 个维度分数后加权得到 overall_score，并根据最低维度建议 retry_stage。`IterationController` 基于 overall_score vs pass_threshold + iteration_index vs max_iterations + improvement_streak 三重判断返回 pass/retry/fail 决策。

---

### §3.3 test_health.py

- **路径**: `tests/unit/test_health.py`
- **行数**: ~8
- **职责**: 健康检查端点最小验证

#### §3.3.1 核心内容

| 测试函数 | 描述 | Fixture | 关键断言 |
|----------|------|---------|----------|
| `test_healthz_returns_ok` | GET /healthz 返回 200 | 无 | status_code == 200 |

使用全局 `app` 实例和 `TestClient`。

#### §3.3.2 依赖关系

- **被测模块**: `app.main.app`

#### §3.3.3 关键逻辑 / 数据流

最简 smoke test，验证 FastAPI 应用启动和路由注册正常。

---

### §3.4 test_llm_client.py

- **路径**: `tests/unit/test_llm_client.py`
- **行数**: ~210
- **职责**: LLM 客户端配置验证、URL 标准化、JSON 解析容错、重试逻辑

#### §3.4.1 核心内容

**辅助类**: `_FakeResponse`, `_RecordingHttpxClient`, `_StructuredResponse`, `_build_client()` 函数

| 测试函数 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_llm_config_requires_api_key` | 空 API key 抛 ValueError | 无 | `LLMClientConfig` 验证 |
| `test_llm_client_uses_expected_chat_completions_url` | 参数化: base_url -> 正确请求 URL | `monkeypatch` | URL 标准化 |
| `test_llm_client_uses_extended_read_timeout_floor` | read timeout 最低 120s | `monkeypatch` | httpx.Timeout 配置 |
| `test_llm_client_accepts_fenced_json_response` | 处理 \`\`\`json 包裹的响应 | `monkeypatch` | JSON 提取 |
| `test_llm_client_accepts_single_wrapper_object_response` | 处理单层包装对象 | `monkeypatch` | JSON 解包 |
| `test_llm_client_accepts_top_level_list_for_single_list_field_model` | 处理顶层数组响应 | `monkeypatch` | 数组 -> 对象转换 |
| `test_llm_client_coerces_string_evidence_refs_into_objects` | 字符串 evidence_ref -> 结构化对象 | `monkeypatch` | evidence_ref 强制转换 |
| `test_llm_client_coerces_research_evidence_refs_with_section_and_quote_keys` | section/quote 键名 -> section_title/excerpt | `monkeypatch` | 键名别名转换 |
| `test_llm_client_coerces_research_requirement_objects_into_strings` | requirement 对象 -> 字符串拼接 | `monkeypatch` | requirement 强制转换 |
| `test_llm_client_retries_read_timeout_and_returns_success` | 首次超时后重试成功 | `monkeypatch` | 重试逻辑 |
| `test_llm_client_raises_after_exhausting_read_timeout_retries` | 3 次超时后抛异常 | `monkeypatch` | 重试耗尽 |

#### §3.4.2 依赖关系

- **被测模块**: `app.clients.llm.LLMClientConfig`, `app.clients.llm.OpenAICompatibleLLMClient`
- **Fixture**: `monkeypatch`（替换 `httpx.Client` 为 `_RecordingHttpxClient`）
- **模型依赖**: `ResearchOutput`, `DraftCaseCollection`

#### §3.4.3 关键逻辑 / 数据流

`_RecordingHttpxClient` 记录所有 `post()` 调用，支持通过 `next_post_outcomes` 列表预设多轮响应（包括异常）。`_build_client()` 工厂函数统一构建 monkeypatched 的 LLM 客户端实例。测试覆盖了 LLM 响应的 6 种异常格式（fenced JSON、wrapper object、top-level list、string evidence_ref、alternative key names、object requirement）。

---

### §3.5 test_markdown_parser.py

- **路径**: `tests/unit/test_markdown_parser.py`
- **行数**: ~10
- **职责**: Markdown 解析器最小验证

#### §3.5.1 核心内容

| 测试函数 | 描述 | Fixture | 关键断言 |
|----------|------|---------|----------|
| `test_markdown_parser_extracts_sections` | 解析 sample_prd.md 提取 sections | 无 | sections 非空, 首个 heading == "Login Flow" |

#### §3.5.2 依赖关系

- **被测模块**: `app.parsers.factory.get_parser`
- **文件依赖**: `tests/fixtures/sample_prd.md`

#### §3.5.3 关键逻辑 / 数据流

通过 `get_parser()` 工厂获取 MarkdownParser，调用 `parse()` 验证输出结构。

---

### §3.6 test_models.py

- **路径**: `tests/unit/test_models.py`
- **行数**: ~8
- **职责**: API 模型默认值验证

#### §3.6.1 核心内容

| 测试函数 | 描述 | Fixture | 关键断言 |
|----------|------|---------|----------|
| `test_case_generation_request_defaults_language` | 请求模型默认 language 为 "zh-CN" | 无 | language == "zh-CN" |

#### §3.6.2 依赖关系

- **被测模块**: `app.domain.api_models.CaseGenerationRequest`

#### §3.6.3 关键逻辑 / 数据流

验证 Pydantic 模型的 `default` 字段行为。

---

### §3.7 test_nodes.py

- **路径**: `tests/unit/test_nodes.py`
- **行数**: ~105
- **职责**: 工作流节点函数的单元测试（reflection、scenario_planner、context_research）

#### §3.7.1 核心内容

| 测试函数 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_deduplicate_cases_removes_identical_titles` | 去重移除同标题用例 | 无 | `deduplicate_cases()` |
| `test_scenario_planner_uses_research_scenarios` | 从 ResearchOutput 生成 PlannedScenario | 无 | `scenario_planner_node()` |
| `test_deduplicate_preserves_checkpoint_id` | 去重保留 checkpoint_id | 无 | `deduplicate_cases()` |
| `test_context_research_prompt_requires_compatibility_guidance` | context_research prompt 包含兼容性指导 | 无 | `build_context_research_node()` prompt 内容 |

**辅助类**: `_RecordingResearchLLMClient` 记录 LLM 调用参数，用于验证 prompt 内容。

#### §3.7.2 依赖关系

- **被测模块**: `app.nodes.reflection.deduplicate_cases`, `app.nodes.scenario_planner.scenario_planner_node`, `app.nodes.context_research.build_context_research_node`
- **模型依赖**: `TestCase`, `ResearchOutput`, `ParsedDocument`, `DocumentSource`, `GlobalState`

#### §3.7.3 关键逻辑 / 数据流

`test_context_research_prompt_requires_compatibility_guidance` 是最复杂的测试，通过 `_RecordingResearchLLMClient` 捕获传入 LLM 的 system_prompt，然后断言 prompt 中包含 `fact_id`, `description`, `section_title`, `excerpt`, `line_start`, `line_end`, `confidence`, `section`, `quote`, `requirement must be a string` 等兼容性指导文本。

---

### §3.8 test_project_context_loader.py

- **路径**: `tests/unit/test_project_context_loader.py`
- **行数**: ~130
- **职责**: `build_project_context_loader` 工厂函数的全面测试

#### §3.8.1 核心内容

使用 `TestBuildProjectContextLoader` 测试类，包含 `mock_service` 和 `sample_project` fixture。

| 测试方法 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_factory_returns_callable` | 工厂返回可调用对象 | `mock_service` | 工厂函数 |
| `test_no_project_id_in_state` | 无 project_id 返回空 summary | `mock_service` | 空输入处理 |
| `test_project_id_empty_string` | 空字符串 project_id | `mock_service` | 空字符串处理 |
| `test_project_id_none` | None project_id | `mock_service` | None 处理 |
| `test_project_not_found` | 项目不存在返回空 summary | `mock_service` | 未找到处理 |
| `test_project_found_returns_summary` | 项目存在返回 summary_text() | `mock_service`, `sample_project` | 正常路径 |
| `test_service_exception_graceful` | 服务异常优雅降级 | `mock_service` | 异常处理 |
| `test_summary_text_exception_graceful` | summary_text() 异常优雅降级 | `mock_service` | 异常处理 |
| `test_returns_dict_not_mutated_state` | 返回新 dict 不修改输入 state | `mock_service` | 不可变性 |

#### §3.8.2 依赖关系

- **被测模块**: `app.nodes.project_context_loader.build_project_context_loader`
- **Fixture**: `mock_service`（MagicMock of ProjectContextService）, `sample_project`（ProjectContext 实例）
- **Mock 策略**: 使用 `unittest.mock.MagicMock(spec=ProjectContextService)` 而非 Fake 对象

#### §3.8.3 关键逻辑 / 数据流

全面覆盖 loader 闭包的所有输入变体（无 ID、空 ID、None、不存在、存在、异常），确保任何异常都优雅降级为空 summary 而不抛出。

---

### §3.9 test_project_context_service.py

- **路径**: `tests/unit/test_project_context_service.py`
- **行数**: ~40
- **职责**: `ProjectContextService` CRUD 操作测试

#### §3.9.1 核心内容

| 测试方法 | 描述 | Fixture | 覆盖目标 |
|----------|------|---------|----------|
| `test_create_and_get` | 创建并获取项目 | 无 | create + get |
| `test_list_projects` | 列出多个项目 | 无 | list |
| `test_update_project` | 更新项目名称 | 无 | update |
| `test_update_missing_raises` | 更新不存在项目抛 KeyError | 无 | update 异常 |
| `test_delete_project` | 删除项目 | 无 | delete |
| `test_delete_missing` | 删除不存在项目返回 False | 无 | delete 异常 |

#### §3.9.2 依赖关系

- **被测模块**: `app.services.project_context_service.ProjectContextService`
- **每个测试通过 `_svc()` 方法创建新实例，确保隔离**

#### §3.9.3 关键逻辑 / 数据流

标准 CRUD 测试模式，使用内存仓储。