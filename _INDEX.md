# AutoChecklist — 源码分析索引

> 本分支由自动化工具生成，为 AI 消费者提供结构化的代码理解入口。
> 生成时间: 2026-03-18 | 源分支: main | 源文件总数: ~76 | 分析文件数: 18

## §1 项目概览

### §1.1 项目定位
AutoChecklist 是一个基于 FastAPI 的自动化测试用例生成服务。它读取 Markdown 格式的 PRD（产品需求文档），通过 LangGraph 编排的多步骤工作流和 LLM 调用，自动生成结构化的测试用例。

### §1.2 技术栈
| 类别 | 技术 | 版本/说明 |
|------|------|----------|
| Web 框架 | FastAPI | ASGI 异步框架 |
| 工作流引擎 | LangGraph | 基于 StateGraph 的有向图编排 |
| 数据模型 | Pydantic v2 | BaseModel + TypedDict 双模式 |
| LLM 客户端 | OpenAI API (兼容) | 支持任意 OpenAI-compatible 端点 |
| HTTP 客户端 | httpx | 异步 HTTP 调用 |
| 测试框架 | pytest + pytest-asyncio | 单元测试 + 集成测试 |
| 运行时 | Python 3.11+ / uvicorn | ASGI 服务器 |
| 包管理 | uv | PEP 735 dependency-groups |

### §1.3 核心架构
四层流水线架构，支持迭代评估循环：

1. **输入层 (Input)**: Markdown PRD 解析 → `ParsedDocument`
2. **上下文研究层 (Context Research)**: LLM 提取事实 → `ResearchOutput`
3. **用例生成层 (Case Generation)**: 6 节点子图流水线 → `TestCase[]`
4. **反思层 (Reflection)**: 质量评估 + 去重 → 迭代决策

**主工作流**: `input_parser → [project_context_loader] → context_research → case_generation → reflection`

**用例生成子图**: `scenario_planner → checkpoint_generator → checkpoint_evaluator → evidence_mapper → draft_writer → structure_assembler`

### §1.4 关键状态模型
- `GlobalState` (TypedDict): 主工作流状态，贯穿全流程
- `CaseGenState` (TypedDict): 子图状态，通过 bridge 函数与 GlobalState 双向映射
- `RunState` (Pydantic BaseModel): 迭代运行状态，持久化到 JSON

## §2 目录结构

```
AutoChecklist/
├── app/                    # 应用主包
│   ├── api/                # FastAPI 路由层 (8 endpoints)
│   ├── clients/            # 外部服务客户端 (LLM)
│   ├── config/             # 配置管理 (Settings)
│   ├── domain/             # 领域模型层 (10 model files)
│   ├── graphs/             # LangGraph 图定义
│   ├── nodes/              # 工作流节点实现 (12 nodes)
│   ├── parsers/            # 文档解析器
│   ├── repositories/       # 数据持久化层
│   ├── services/           # 业务服务层
│   └── utils/              # 工具函数
├── docs/plans/             # 设计文档
├── tests/                  # 测试套件
│   ├── fixtures/           # 测试固件
│   ├── integration/        # 集成测试
│   └── unit/               # 单元测试 (17 files)
├── .env.example            # 环境变量模板
├── pyproject.toml          # 项目配置
├── README.md               # 项目文档
└── prd.md                  # 产品需求文档
```

## §3 分析文件索引

| # | 分析文件路径 | 源目录 | 源文件数 | 分析策略 | 核心关注点 |
|---|-------------|--------|---------|----------|----------|
| 1 | [`_ROOT_ANALYSIS.md`](./_ROOT_ANALYSIS.md) | `/` | 5 | Config/文档 | 项目配置、依赖、PRD 架构蓝图 |
| 2 | [`app/_ANALYSIS.md`](./app/_ANALYSIS.md) | `app/` | 2 | 入口文件 | create_app() 工厂、依赖注入 |
| 3 | [`app/api/_ANALYSIS.md`](./app/api/_ANALYSIS.md) | `app/api/` | 3 | 路由/API | 8 个 HTTP 端点、请求/响应模型 |
| 4 | [`app/clients/_ANALYSIS.md`](./app/clients/_ANALYSIS.md) | `app/clients/` | 2 | 业务逻辑 | LLM 客户端、结构化输出解析 |
| 5 | [`app/config/_ANALYSIS.md`](./app/config/_ANALYSIS.md) | `app/config/` | 2 | 配置文件 | 12 个配置字段、环境变量映射 |
| 6 | [`app/domain/_ANALYSIS.md`](./app/domain/_ANALYSIS.md) | `app/domain/` | 10 | 数据模型 | 领域模型全景、字段级文档 |
| 7 | [`app/graphs/_ANALYSIS.md`](./app/graphs/_ANALYSIS.md) | `app/graphs/` | 3 | 业务逻辑 | 图拓扑、状态桥接、子图编排 |
| 8 | [`app/nodes/_ANALYSIS.md`](./app/nodes/_ANALYSIS.md) | `app/nodes/` | 12 | 业务逻辑 | 12 个节点实现、LLM 交互模式 |
| 9 | [`app/parsers/_ANALYSIS.md`](./app/parsers/_ANALYSIS.md) | `app/parsers/` | 4 | 业务逻辑/工具 | Protocol 接口、Markdown 解析 |
| 10 | [`app/repositories/_ANALYSIS.md`](./app/repositories/_ANALYSIS.md) | `app/repositories/` | 4 | 持久化 | 文件系统持久化、双轨版本策略 |
| 11 | [`app/services/_ANALYSIS.md`](./app/services/_ANALYSIS.md) | `app/services/` | 9 | 业务逻辑 | 迭代控制、XMind 交付链 |
| 12 | [`app/utils/_ANALYSIS.md`](./app/utils/_ANALYSIS.md) | `app/utils/` | 3 | 工具函数 | 文件 I/O、RunID 生成 |
| 13 | [`docs/plans/_ANALYSIS.md`](./docs/plans/_ANALYSIS.md) | `docs/plans/` | 2 | 文档 | MVP 设计文档、实施计划 |
| 14 | [`tests/_ANALYSIS.md`](./tests/_ANALYSIS.md) | `tests/` | 2 | 测试 | conftest 固件、Mock 策略 |
| 15 | [`tests/fixtures/_ANALYSIS.md`](./tests/fixtures/_ANALYSIS.md) | `tests/fixtures/` | 1 | 测试/文档 | 样例 PRD 数据 |
| 16 | [`tests/integration/_ANALYSIS.md`](./tests/integration/_ANALYSIS.md) | `tests/integration/` | 4 | 测试 | API/工作流集成测试 |
| 17 | [`tests/unit/_ANALYSIS_1.md`](./tests/unit/_ANALYSIS_1.md) | `tests/unit/` (1/2) | 9 | 测试 | 单元测试 Part 1 |
| 18 | [`tests/unit/_ANALYSIS_2.md`](./tests/unit/_ANALYSIS_2.md) | `tests/unit/` (2/2) | 8 | 测试 | 单元测试 Part 2 |

### §3.1 PR #15 新增分析文件 (Checklist 优化 F1-F5)

| # | 分析文件路径 | 源文件 | 功能编号 | 核心关注点 |
|---|-------------|--------|---------|----------|
| 19 | [`app/domain/checklist_models_ANALYSIS.md`](./app/domain/checklist_models_ANALYSIS.md) | `app/domain/checklist_models.py` | F1 | ChecklistNode 递归 Pydantic v2 模型、model_rebuild() |
| 20 | [`app/services/checklist_merger_ANALYSIS.md`](./app/services/checklist_merger_ANALYSIS.md) | `app/services/checklist_merger.py` | F1 | Trie 合并算法、归一化、单子链剪枝、_MAX_DEPTH=10 |
| 21 | [`app/nodes/checklist_optimizer_ANALYSIS.md`](./app/nodes/checklist_optimizer_ANALYSIS.md) | `app/nodes/checklist_optimizer.py` | F5/F1/F2 | LangGraph 节点、两步处理(refine→merge)、graceful degradation |
| 22 | [`app/services/markdown_renderer_ANALYSIS.md`](./app/services/markdown_renderer_ANALYSIS.md) | `app/services/markdown_renderer.py` | F4 | 共享 Markdown 渲染、flat + tree 模式、DRY 修复 |
| 23 | [`tests/unit/test_checklist_merger_ANALYSIS.md`](./tests/unit/test_checklist_merger_ANALYSIS.md) | `tests/unit/test_checklist_merger.py` | F1 | FakeTestCase 替身、归一化/合并/剪枝/深度限制测试 |
| 24 | [`tests/unit/test_checklist_optimizer_ANALYSIS.md`](./tests/unit/test_checklist_optimizer_ANALYSIS.md) | `tests/unit/test_checklist_optimizer.py` | F5 | mock patch 策略、正常流/降级/异常测试 |
| 25 | [`tests/unit/test_text_refiner_ANALYSIS.md`](./tests/unit/test_text_refiner_ANALYSIS.md) | `tests/unit/test_text_refiner.py` | F2 | 中英文精炼、标识符保护、长度约束、冗余步骤合并测试 |

## §4 模块依赖全景

### §4.1 层级依赖图
```
┌─────────────┐
│   app/api   │  ← HTTP 入口
└──────┬──────┘
       │ depends on
┌──────▼──────┐
│ app/services│  ← 业务编排
└──────┬──────┘
       │ depends on
┌──────▼──────────────────────┐
│ app/graphs  │  app/nodes        │  ← 工作流引擎
└──────┬──────┴────────┬──────────┘
       │               │ depends on
┌──────▼──────┐ ┌──────▼──────────┐
│ app/clients │ │ app/repositories│  ← 基础设施
└──────┬──────┘ └──────┬──────────┘
       │               │ depends on
┌──────▼───────────────▼──────────┐
│ app/domain  │  app/config       │  ← 领域模型 + 配置
└──────┬──────┴────────┬──────────┘
       │               │ depends on
┌──────▼───────────────▼──────────┐
│         app/utils               │  ← 零业务依赖工具层
└─────────────────────────────────┘
```

### §4.2 关键数据流
```
Markdown PRD (文件)
  → input_parser (MarkdownParser)
  → ParsedDocument { sections, references }
  → context_research (LLM)
  → ResearchOutput { facts, scenarios }
  → scenario_planner → PlannedScenario[]
  → checkpoint_generator (LLM) → Checkpoint[]
  → checkpoint_evaluator → Checkpoint[] (去重)
  → evidence_mapper → Checkpoint[] (关联证据)
  → draft_writer (LLM) → TestCase[]
  → structure_assembler → TestCase[] (规范化)
  → reflection → QualityReport + 迭代决策
  → [迭代 or 输出]
  → PlatformDispatcher → JSON + Markdown [+ XMind]
```

## §5 环境变量清单

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `APP_NAME` | str | `"AutoChecklist"` | 应用名称 |
| `DEBUG` | bool | `false` | 调试模式 |
| `LOG_LEVEL` | str | `"INFO"` | 日志级别 |
| `LLM_API_KEY` | str | (必填) | LLM API 密钥 |
| `LLM_BASE_URL` | str | `"https://api.openai.com/v1"` | LLM 端点 |
| `LLM_MODEL` | str | `"gpt-4o"` | 模型名称 |
| `LLM_TEMPERATURE` | float | `0.3` | 采样温度 |
| `LLM_MAX_TOKENS` | int | `16000` | 最大输出 token |
| `LLM_TIMEOUT` | int | `6000` | 请求超时(秒) |
| `MAX_ITERATIONS` | int | `3` | 最大迭代次数 |
| `EVALUATION_PASS_THRESHOLD` | float | `0.8` | 评估通过阈值 |
| `TIMEZONE` | str | `"Asia/Shanghai"` | 时区 |

## §6 AI 消费指南

### §6.1 快速理解项目
1. 先读本文件 (`_INDEX.md`) 了解全局架构
2. 读 `_ROOT_ANALYSIS.md` §3.4 (prd.md 分析) 了解业务需求
3. 读 `app/domain/_ANALYSIS.md` 了解数据模型全景
4. 读 `app/graphs/_ANALYSIS.md` 了解工作流拓扑

### §6.2 修改某个功能
1. 通过 §3 索引表定位相关目录的 `_ANALYSIS.md`
2. 在 `_ANALYSIS.md` 中找到目标文件的 §3.N 小节
3. 查看 §3.N.2 (依赖关系) 了解影响范围
4. 查看对应的 `tests/unit/_ANALYSIS_*.md` 确认测试覆盖

### §6.3 调试问题
1. 从 `app/services/_ANALYSIS.md` (WorkflowService) 开始追踪
2. 参考 `app/nodes/_ANALYSIS.md` 中各节点的状态消费/生产表
3. 查看 §4 依赖全景图定位上下游模块
