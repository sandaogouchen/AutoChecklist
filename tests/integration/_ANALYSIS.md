# tests/integration/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 4 | 分析策略: Test — for each test file list all test functions, what they test, fixture dependencies, assertions made

## §1 目录职责

`tests/integration/` 目录包含**集成测试**，验证多个模块协作时的端到端行为。测试覆盖四个维度：API HTTP 端点（test_api.py）、迭代评估回路（test_iteration_loop.py）、项目上下文工作流集成（test_project_workflow.py）、LangGraph 工作流执行（test_workflow.py）。所有测试均使用 `conftest.py` 提供的 Fake LLM 客户端替代真实 LLM 调用。

## §2 文件清单

| 序号 | 文件名 | 行数 | 测试函数数 | 职责概述 |
|------|--------|------|-----------|----------|
| 1 | `test_api.py` | ~99 | 4 | FastAPI HTTP 端点集成测试：创建运行、查询运行、checkpoint 验证 |
| 2 | `test_iteration_loop.py` | ~192 | 3 | 迭代评估回路集成测试：低质量触发重试、失败状态持久化、成功运行工件 |
| 3 | `test_project_workflow.py` | ~112 | 4 | 项目上下文 + 工作流集成：有/无 project_id、不存在项目、服务实例共享 |
| 4 | `test_workflow.py` | ~67 | 4 | LangGraph 工作流直接调用：测试用例生成、checkpoint 产物、覆盖状态 |

## §3 文件详细分析

### §3.1 test_api.py

- **路径**: `tests/integration/test_api.py`
- **行数**: ~99
- **职责**: 验证 FastAPI HTTP 端点的请求-响应行为

#### §3.1.1 核心内容

| 测试函数 | 测试目标 | Fixture | 关键断言 |
|----------|----------|---------|----------|
| `test_create_run_returns_generated_cases` | POST 创建运行返回生成的测试用例 | `tmp_path`, `fake_llm_client` | status=200, status="succeeded", test_cases 非空 |
| `test_get_run_returns_saved_result` | GET 查询已完成运行的持久化结果 | `tmp_path`, `fake_llm_client` | status=200, run_id 匹配, artifacts 包含 "run_result" |
| `test_create_run_includes_checkpoint_count` | 运行结果包含 checkpoint_count 字段 | `tmp_path`, `fake_llm_client` | status=200, "checkpoint_count" in data, checkpoint_count > 0 |
| `test_create_run_persists_checkpoint_artifacts` | 运行后持久化 checkpoints 和 coverage 工件 | `tmp_path`, `fake_llm_client` | status=200, artifacts 包含 "checkpoints" 和 "checkpoint_coverage" |

**测试模式**: 每个测试手动构建 `Settings` -> `FileRunRepository` -> `WorkflowService` -> `create_app()` -> `TestClient`，使用 `tmp_path` 隔离文件系统副作用。

#### §3.1.2 依赖关系

- **导入**: `Settings`, `create_app`, `FileRunRepository`, `WorkflowService`, `Path`, `TestClient`
- **Fixture**: `tmp_path`（pytest 内置）, `fake_llm_client`（conftest.py）
- **文件依赖**: `tests/fixtures/sample_prd.md`（通过 `Path.resolve()` 绝对路径引用）

#### §3.1.3 关键逻辑 / 数据流

```
TestClient --POST--> /api/v1/case-generation/runs (file_path=sample_prd.md)
    |
    v
WorkflowService.execute() --uses--> fake_llm_client
    |
    v
FileRunRepository.save() --> tmp_path/<run_id>/
    |
    v
HTTP Response (JSON: run_id, status, test_cases, artifacts)
    |
    v
TestClient --GET--> /api/v1/case-generation/runs/{run_id}
    |
    v
FileRunRepository.load() --> 返回持久化的运行结果
```

---

### §3.2 test_iteration_loop.py

- **路径**: `tests/integration/test_iteration_loop.py`
- **行数**: ~192
- **职责**: 验证迭代评估回路的回流、失败持久化和成功工件生成

#### §3.2.1 核心内容

| 测试函数 | 测试目标 | Fixture | 关键断言 |
|----------|----------|---------|----------|
| `test_evaluation_triggers_retry_on_low_quality` | 低质量首轮应触发至少一次回流 | `tmp_path`, `fake_llm_client_low_quality` | iteration_count >= 1, run_state 存在, iteration_history 非空 |
| `test_failed_run_state_persists_after_max_iterations` | 达到最大迭代后失败状态完整持久化 | `tmp_path`, `fake_llm_client_low_quality` | status=FAILED, run_state.json/evaluation_report.json/iteration_log.json 均可读取, GET API 仍可查询 |
| `test_successful_run_persists_all_iteration_artifacts` | 成功运行持久化所有迭代工件 | `tmp_path`, `fake_llm_client` | status="succeeded", artifacts 包含 run_state/evaluation_report/iteration_log, iteration_count >= 1, last_evaluation_score > 0 |

**核心组件实例化**: 每个测试手动构建完整的迭代控制链路：
- `Settings(max_iterations=N, evaluation_pass_threshold=T)`
- `RunStateRepository(tmp_path)`
- `IterationController(max_iterations=N, pass_threshold=T)`
- `WorkflowService(settings, repository, llm_client, state_repository, iteration_controller)`

#### §3.2.2 依赖关系

- **导入**: `Settings`, `RunStatus`, `create_app`, `FileRunRepository`, `RunStateRepository`, `IterationController`, `WorkflowService`
- **Fixture**: `tmp_path`, `fake_llm_client_low_quality`（低质量 mock）, `fake_llm_client`（高质量 mock）
- **关键配置**: `evaluation_pass_threshold` 控制通过/失败阈值

#### §3.2.3 关键逻辑 / 数据流

**回流测试**: `pass_threshold=0.7` + 低质量 mock -> 首轮评分不达标 -> IterationController 返回 retry -> 系统回流到指定 stage -> 再次执行 -> 断言多轮迭代

**失败持久化测试**: `pass_threshold=0.99`（极高阈值）+ `max_iterations=2` -> 必然失败 -> 验证 3 个持久化文件可读取 -> 验证 "服务重启" 后 GET API 仍可查询

**成功工件测试**: `pass_threshold=0.5`（低阈值）+ 高质量 mock -> 首轮通过 -> 验证工件完整性

---

### §3.3 test_project_workflow.py

- **路径**: `tests/integration/test_project_workflow.py`
- **行数**: ~112
- **职责**: 验证项目上下文（ProjectContext）与工作流的集成

#### §3.3.1 核心内容

使用 `TestProjectContextWorkflowIntegration` 测试类组织，包含类级 fixture `project_service`。

| 测试函数 | 测试目标 | Fixture | 关键断言 |
|----------|----------|---------|----------|
| `test_workflow_with_project_context` | 创建项目 -> 构建 loader -> 调用 -> summary 包含项目信息 | `project_service` | summary 非空, 包含 "E-Commerce Platform", "Python", "PCI-DSS compliance for payment" |
| `test_workflow_without_project_context` | 无 project_id 时 loader 返回空 summary | `project_service` | project_context_summary == "" |
| `test_workflow_with_nonexistent_project` | 不存在的 project_id 不抛异常，返回空 summary | `project_service` | project_context_summary == "" |
| `test_service_instance_shared_between_api_and_workflow` | API 和工作流共享同一服务实例 | 无（自建） | 创建后 summary 包含项目名, 删除后 summary 为空 |

**测试流程**: 创建真实 `ProjectRepository` + `ProjectContextService`（非 mock），通过 `build_project_context_loader()` 工厂构建 loader 闭包，传入模拟 LangGraph 状态字典。

#### §3.3.2 依赖关系

- **导入**: `ProjectContext`, `ProjectType`, `build_project_context_loader`, `ProjectRepository`, `ProjectContextService`
- **Fixture**: `project_service`（类级 fixture，创建真实 in-memory 服务实例）
- **不使用 Fake LLM 客户端**: 此测试仅验证 project context loader 节点逻辑，不涉及 LLM 调用

#### §3.3.3 关键逻辑 / 数据流

```
ProjectContextService.create_project() --> 内存存储项目
    |
    v
build_project_context_loader(service) --> loader 闭包
    |
    v
loader(state={"project_id": id}) --> {"project_context_summary": "..."}
```

核心验证: loader 闭包正确消费 project_id，通过 service 获取项目，调用 `summary_text()` 生成摘要文本。

---

### §3.4 test_workflow.py

- **路径**: `tests/integration/test_workflow.py`
- **行数**: ~67
- **职责**: 验证 LangGraph 工作流的直接调用行为

#### §3.4.1 核心内容

| 测试函数 | 测试目标 | Fixture | 关键断言 |
|----------|----------|---------|----------|
| `test_workflow_returns_test_cases` | 工作流返回测试用例且标题正确 | `fake_llm_client` | test_cases 非空, 首个用例 title == "User logs in with SMS code" |
| `test_workflow_produces_checkpoints` | 工作流生成 checkpoint 中间产物 | `fake_llm_client` | "checkpoints" in result, 非空, 每个 checkpoint_id 以 "CP-" 开头 |
| `test_workflow_produces_checkpoint_coverage` | 工作流生成 checkpoint 覆盖记录 | `fake_llm_client` | "checkpoint_coverage" in result, 非空 |
| `test_workflow_test_cases_have_checkpoint_id` | 测试用例携带 checkpoint_id | `fake_llm_client` | 至少部分用例的 checkpoint_id 非空 |

**测试模式**: 直接调用 `build_workflow(fake_llm_client).invoke(state)` 绕过 HTTP 层，验证工作流图的纯逻辑行为。

#### §3.4.2 依赖关系

- **导入**: `build_workflow`, `Path`
- **Fixture**: `fake_llm_client`（conftest.py）
- **文件依赖**: `tests/fixtures/sample_prd.md`（相对路径，不使用 `.resolve()`）

#### §3.4.3 关键逻辑 / 数据流

```
build_workflow(fake_llm_client)
    |
    v
workflow.invoke({"file_path": "tests/fixtures/sample_prd.md", "language": "zh-CN"})
    |
    v
InputParserNode --> ContextResearchNode --> CaseGenSubgraph --> ReflectionNode
    |                     |                      |                    |
    v                     v                      v                    v
ParsedDocument      ResearchOutput         checkpoints +          QualityReport
                                            test_cases
```

## §4 目录级依赖关系

```
tests/integration/
  ├── test_api.py ──────────────> app.main.create_app, WorkflowService, FileRunRepository
  ├── test_iteration_loop.py ──> 上述 + RunStateRepository, IterationController, RunStatus
  ├── test_project_workflow.py -> ProjectContextService, build_project_context_loader, ProjectRepository
  └── test_workflow.py ────────> app.graphs.main_workflow.build_workflow
      |
      ├── 共同依赖: tests/conftest.py (fake_llm_client, fake_llm_client_low_quality)
      └── 共同依赖: tests/fixtures/sample_prd.md (标准输入文件)
```

## §5 设计模式与架构特征

| 模式/特征 | 体现位置 |
|-----------|----------|
| **端到端 HTTP 测试** | test_api.py 使用 `TestClient` 发送真实 HTTP 请求 |
| **手动 DI（依赖注入）** | test_api.py / test_iteration_loop.py 手动构建完整组件图 |
| **分层验证** | test_workflow.py 绕过 HTTP 层直接测试图逻辑；test_api.py 包含 HTTP 层 |
| **状态隔离** | 所有文件系统测试使用 `tmp_path` 确保隔离 |
| **双质量对比** | test_iteration_loop.py 使用高/低质量两种 mock 验证不同路径 |
| **闭包测试** | test_project_workflow.py 验证 `build_project_context_loader` 工厂闭包行为 |
| **服务重启模拟** | test_iteration_loop.py 重新创建 WorkflowService 实例验证持久化恢复 |

## §6 潜在关注点

1. **重复的组件构建代码**: test_api.py 和 test_iteration_loop.py 中每个测试函数都重复构建 Settings -> Repository -> Service -> TestClient 链路，可考虑提取为 fixture 或 helper 函数。
2. **test_workflow.py 使用相对路径**: `Path("tests/fixtures/sample_prd.md")` 未调用 `.resolve()`，依赖 pytest 的工作目录为项目根目录，如果从子目录运行可能失败。
3. **迭代回路测试中低质量 mock 每轮返回相同数据**: `FakeLLMClientLowQuality` 不会在 retry 后返回改善的数据，因此 `test_evaluation_triggers_retry_on_low_quality` 的 "系统能触发回流并改进" 断言实际上只验证了回流触发，未验证改进效果。
4. **test_project_routes.py 在 unit 目录下但行为像集成测试**: `test_project_workflow.py` 在 integration 目录下正确分类，但 `test_project_routes.py` 使用了全局 `app` 实例和 `TestClient`，实际上也是集成测试行为。
5. **缺少负面路径集成测试**: 无效文件路径、不存在的文件、非 Markdown 扩展名等错误场景未在集成测试中覆盖。