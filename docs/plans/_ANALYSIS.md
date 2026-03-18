# docs/plans/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 2 | 分析策略: Documentation — purpose, structure, key decisions, architecture described

## §1 目录职责

`docs/plans/` 目录承载 AutoChecklist 项目的**顶层设计文档和实施计划**。两份文档均以 2026-03-13 为基准日期，分别定义了 MVP 阶段的系统架构设计（design）和逐任务实施计划（implementation plan）。它们共同构成项目从 “做什么” 到 “怎么做” 的完整规划闭环，是后续编码、测试和评审的权威参考。

## §2 文件清单

| 序号 | 文件名 | 行数 | 职责概述 |
|------|--------|------|----------|
| 1 | `2026-03-13-autochecklist-mvp-design.md` | ~272 | MVP 架构设计文档：目标、范围、架构、API、数据模型、节点职责、LLM 集成、持久化、错误处理、测试策略 |
| 2 | `2026-03-13-autochecklist-mvp.md` | ~446 | MVP 实施计划：10 个 TDD 任务，每个任务包含失败测试、实现、验证、提交步骤 |

## §3 文件详细分析

### §3.1 2026-03-13-autochecklist-mvp-design.md

- **路径**: `docs/plans/2026-03-13-autochecklist-mvp-design.md`
- **行数**: ~272
- **职责**: 定义 MVP 阶段的完整系统架构设计

#### §3.1.1 核心内容

文档以 Goal -> Scope -> Architecture -> API Design -> Core Data Model -> Node Responsibilities -> LLM Integration -> Persistence -> Error Handling -> Testing Strategy -> Project Layout 的结构展开，涵盖以下关键决策：

**目标**: 构建可运行的 MVP API 服务，读取本地 Markdown/PRD 文件，执行 LangGraph 工作流，调用真实 LLM API，返回结构化测试用例（JSON + Markdown）。

**架构**: FastAPI 应用 + LangGraph 编排引擎，HTTP 层刻意保持轻薄。工作流分为：
- **主图（Main Graph）**: `InputParserNode` -> `ContextResearchNode` -> `CaseGenSubgraph` -> `ReflectionNode`
- **子图（CaseGenSubgraph）**: `ScenarioPlanner` -> `EvidenceMapper` -> `DraftWriter` -> `StructureAssembler`

**API 端点**:
- `POST /api/v1/case-generation/runs` — 创建并执行工作流运行
- `GET /api/v1/case-generation/runs/{run_id}` — 查询运行结果
- `GET /healthz` — 健康检查

**数据模型**: 定义了 `DocumentSource`, `ParsedDocument`, `ResearchOutput`, `EvidenceRef`, `PlannedScenario`, `TestCase`, `QualityReport`, `CaseGenerationRun` 等领域对象，以及 `GlobalState` / `CaseGenState` 工作流状态模型。

**LLM 集成**: 通过 OpenAI 兼容客户端抽象，使用环境变量配置（`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`），Pydantic 模型强制结构化输出解析。

**持久化**: 每次运行写入 `output/runs/<run_id>/` 下 8 个 artifact 文件（request.json, parsed_document.json, research_output.json, test_cases.json, test_cases.md, quality_report.json, run_result.json, run.log）。

**错误处理**: 四类错误（请求验证、解析、LLM 客户端、工作流执行），结构化错误响应，失败时也写入部分 artifact 便于调试。

#### §3.1.2 依赖关系

- 作为上游设计文档被 `2026-03-13-autochecklist-mvp.md` 实施计划引用
- 定义了 `app/` 下各包的分层架构：`api/`, `clients/`, `config/`, `domain/`, `graphs/`, `nodes/`, `parsers/`, `repositories/`, `services/`, `utils/`
- 定义了 `tests/` 下的三层测试结构：`unit/`, `integration/`, `fixtures/`

#### §3.1.3 关键逻辑 / 数据流

数据流路径: `HTTP Request` -> `InputParserNode`（文件 -> ParsedDocument）-> `ContextResearchNode`（LLM 调用 -> ResearchOutput）-> `CaseGenSubgraph`（ScenarioPlanner -> EvidenceMapper -> DraftWriter -> StructureAssembler -> TestCase 列表）-> `ReflectionNode`（去重 + 质量检查 -> QualityReport）-> `HTTP Response`

明确的扩展点设计：
- Parser 层通过 `BaseDocumentParser` 协议支持未来 Feishu 解析器
- ContextResearch 接口预留多步研究图扩展
- Reflection 预留 LLM 修复 pass 扩展

---

### §3.2 2026-03-13-autochecklist-mvp.md

- **路径**: `docs/plans/2026-03-13-autochecklist-mvp.md`
- **行数**: ~446
- **职责**: TDD 驱动的 MVP 逐任务实施计划

#### §3.2.1 核心内容

文档以 Claude 执行指令开头（`REQUIRED SUB-SKILL: Use superpowers:executing-plans`），定义了 **10 个顺序任务**，每个任务严格遵循 TDD 五步流程：

| 任务 | 标题 | 核心产出 |
|------|------|----------|
| Task 1 | Scaffold project structure | pyproject.toml, FastAPI app, /healthz 端点 |
| Task 2 | Define domain models | api_models, document_models, research_models, case_models, state |
| Task 3 | Build parser abstraction | BaseDocumentParser 协议, MarkdownParser, parser factory |
| Task 4 | Implement LLM client | OpenAI 兼容 LLM 客户端抽象, config 验证 |
| Task 5 | Implement workflow nodes | 7 个节点函数（input_parser 到 reflection） |
| Task 6 | Build LangGraph graphs | case_generation 子图, main_workflow 主图 |
| Task 7 | Add run repository | FileRunRepository, artifact 持久化 |
| Task 8 | Expose workflow via API | routes, workflow_service, API 集成 |
| Task 9 | Add documentation | README.md, .env.example |
| Task 10 | Run full verification | 共享 fixtures, 全量测试通过 |

**每个任务的五步结构**：
1. **Write the failing test** — 先写期望行为的测试代码
2. **Run test to verify it fails** — 运行确认红灯
3. **Write minimal implementation** — 编写最小实现
4. **Run test to verify it passes** — 运行确认绿灯
5. **Commit** — 提交代码

**技术栈声明**: Python 3.11+, FastAPI, Uvicorn, LangGraph, LangChain Core, Pydantic v2, pytest, httpx, respx/unittest.mock

#### §3.2.2 依赖关系

- 依赖 `2026-03-13-autochecklist-mvp-design.md` 中定义的架构方案
- 每个 Task 产出对应 `app/` 和 `tests/` 下的具体文件
- Task 10 的 `conftest.py` 是后续所有测试的共享 fixture 基础

#### §3.2.3 关键逻辑 / 数据流

任务依赖链：Task 1（骨架）-> Task 2（模型）-> Task 3（解析器）-> Task 4（LLM 客户端）-> Task 5（节点）-> Task 6（图）-> Task 7（持久化）-> Task 8（API 路由）-> Task 9（文档）-> Task 10（全量验证）

每个任务的测试代码片段直接内嵌于文档中，形成 “可执行规格说明” 的效果。

## §4 目录级依赖关系

```
docs/plans/
  ├── mvp-design.md ──── 定义架构 ──────────> app/ 各层实现
  │                                           tests/ 各层测试
  └── mvp.md ───────── 实施步骤 ──────────> 10 个 TDD 迭代
                          引用 design.md 架构
```

- **上游**: 无（作为项目根规划文档）
- **下游**: `app/` 全部包结构、`tests/` 全部测试结构、`conftest.py` fixture 设计

## §5 设计模式与架构特征

| 模式/特征 | 体现位置 |
|-----------|----------|
| **TDD（测试驱动开发）** | mvp.md 每个 Task 均遵循 Red-Green-Commit 流程 |
| **分层架构** | API -> Service -> Graph/Node -> Domain/Repository 四层解耦 |
| **策略模式（Parser Registry）** | `BaseDocumentParser` 协议 + `get_parser()` 工厂选择解析器 |
| **子图模式（LangGraph Subgraph）** | CaseGenSubgraph 封装四个节点为独立可测试单元 |
| **结构化输出（Pydantic Enforcement）** | LLM 调用结果强制 Pydantic 模型解析 |
| **Artifact 持久化** | 每次运行产出 8 个 JSON/MD/Log 文件，支持事后调试 |
| **渐进式设计** | 明确标注 "extension point, not requirement"，MVP 保持轻量 |

## §6 潜在关注点

1. **计划与实现偏差**: mvp.md 中 Task 5 列出的节点文件名（如 `scenario_planner.py`, `evidence_mapper.py`）在实际代码库中可能已经演化为不同的模块划分（如引入 `checkpoint_generator.py`, `checkpoint_evaluator.py`），需要对照实际代码确认一致性。
2. **迭代评估回路未在设计文档中出现**: 实际代码已引入 `IterationController` + `EvaluationReport` 回路机制，但 design.md 中未涉及此扩展，文档可能需要更新。
3. **XMind 交付功能未在设计文档中提及**: 实际代码已实现 `XMindDeliveryAgent` + `XMindPayloadBuilder`，但两份设计文档均未涵盖此功能。
4. **Project Context 功能未在设计文档中提及**: 实际代码已实现 `ProjectContext` 模型和 `/projects` API 路由，但设计文档未涉及。
5. **Claude 执行指令耦合**: mvp.md 顶部包含 Claude Agent 特定指令（`superpowers:executing-plans`），暗示文档设计为 AI-assisted 开发流程的一部分。