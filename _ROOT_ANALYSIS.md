# _ROOT_ANALYSIS.md — 根目录文件分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `/` |
| 文件数 | 6（已排除 uv.lock） |
| 分析文件 | .env.example, .gitignore, README.md, prd.md, testprd.md, pyproject.toml |
| 目录职责 | 项目根目录：配置、文档、依赖声明 |

## §2 文件清单

| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | .env.example | K-配置 | ~10 | 环境变量模板 |
| 2 | .gitignore | K-配置 | ~160 | Python/IDE 忽略规则 |
| 3 | README.md | D-文档 | ~80 | 项目说明与使用指南 |
| 4 | prd.md | D-文档 | ~500 | 产品需求文档-四层架构 |
| 5 | testprd.md | D-文档 | ~200 | 测试用 PRD 样本 |
| 6 | pyproject.toml | K-配置 | ~35 | 项目元数据与依赖 |

## §3 逐文件分析

### §3.1 .env.example
- **类型**: K-配置文件
- **职责**: 定义 LLM 服务连接所需的环境变量模板
- **关键变量**: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`（默认60）, `LLM_TEMPERATURE`（默认0.3）, `LLM_MAX_TOKENS`（默认16384）
- **设计意图**: 通过 .env 文件隔离敏感配置，配合 pydantic-settings 自动加载

### §3.2 .gitignore
- **类型**: K-配置文件
- **职责**: 标准 Python 项目忽略规则，覆盖 __pycache__、.venv、dist、IDE 配置等

### §3.3 README.md
- **类型**: D-文档
- **职责**: 项目入口文档
- **关键内容**:
  - 项目定位：读取 Markdown PRD → LangGraph 工作流 → 结构化测试用例
  - 三个 API 端点：GET /healthz、POST /api/v1/case-generation/runs、GET /api/v1/case-generation/runs/{id}
  - 技术栈：Python 3.11+, FastAPI, LangGraph, OpenAI API

### §3.4 prd.md
- **类型**: D-文档（需求规格）
- **职责**: 产品需求文档，定义 AutoChecklist 的四层架构
- **关键架构**:
  - Layer 1: Input Parsing — 解析 Markdown PRD
  - Layer 2: Context Research — 上下文研究、场景规划
  - Layer 3: Case Generation — 子图流水线（scenario_planner → checkpoint_generator → checkpoint_evaluator → checkpoint_outline_planner → evidence_mapper → draft_writer → structure_assembler）
  - Layer 4: Reflection — 评估、去重、质量检查
- **设计理念**: Checkpoint 作为中间抽象层（ResearchFact → Checkpoint → TestCase）

### §3.5 testprd.md
- **类型**: D-文档（测试数据）
- **职责**: 真实业务 PRD 样本（Consideration Ads 二级优化目标），用于端到端测试
- **价值**: 提供复杂业务场景验证，包含多级功能需求和交互逻辑

### §3.6 pyproject.toml
- **类型**: K-配置文件
- **职责**: 项目元数据与依赖声明
- **运行时依赖**: fastapi, httpx, langgraph(>=0.4), openai, pydantic(>=2.0), pydantic-settings, python-dotenv, uvicorn
- **开发依赖**: pytest, pytest-asyncio
- **Python 版本**: >=3.11

## §4 补充观察

1. **配置集中度高**: 所有 LLM 参数通过 .env → pydantic-settings 链路加载，配置管理规范
2. **PRD 驱动设计**: prd.md 详细定义了四层架构，与实际代码结构高度一致，说明开发遵循了良好的 design-first 实践
3. **测试数据真实**: testprd.md 使用真实业务 PRD，有利于发现边界问题
4. **依赖精简**: 运行时仅 8 个直接依赖，无冗余引入

## §5 PR #24 变更 — 根目录文件更新

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

PR #24 修改了根目录的两个配置文件，新增知识检索相关的环境变量和依赖。

### .env.example 变更

新增 11 个知识检索相关的环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_KNOWLEDGE_RETRIEVAL` | `false` | 知识检索总开关 |
| `KNOWLEDGE_WORKING_DIR` | `./knowledge_db` | LightRAG 工作目录 |
| `KNOWLEDGE_DOCS_DIR` | `./knowledge_docs` | 知识文档源目录 |
| `KNOWLEDGE_RETRIEVAL_MODE` | `hybrid` | 检索模式 |
| `KNOWLEDGE_TOP_K` | `10` | 检索结果数量上限 |
| `KNOWLEDGE_EMBEDDING_MODEL` | _(空)_ | Embedding 模型，空则复用 LLM_MODEL |
| `KNOWLEDGE_MAX_DOC_SIZE_KB` | `1024` | 单文档最大 KB 数 |

以及对应的注释说明行。

### pyproject.toml 变更

新增运行时依赖：

| 依赖 | 版本约束 | 说明 |
|------|---------|------|
| `lightrag-hku` | `>=1.1.0` | LightRAG GraphRAG 框架（HKU 发布版） |

此依赖会间接引入 `numpy` 等科学计算包。