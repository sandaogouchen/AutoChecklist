# / (项目根目录) 目录分析

> 生成时间: 2025-01-20 | 源文件数: 5 | 分析策略: Config file, Config/Other, Documentation, Config

## §1 目录职责

项目根目录是 AutoChecklist 服务的顶层配置与文档中枢，承载了项目元数据定义、依赖管理、环境变量模板、版本控制配置以及用户指南与产品需求文档。该目录不包含业务逻辑代码，而是通过 `pyproject.toml` 定义构建体系与依赖关系，通过 `.env.example` 规范运行时配置契约，通过 `README.md` 提供开发者入口指引，通过 `prd.md` 描述产品的完整架构设计与功能规划。所有根目录文件共同构成了项目的"外壳"——开发者首次接触仓库时的第一层信息界面。

## §2 文件清单

| 文件名 | 行数 | 主要职责 | 分析策略 |
|---------|------|----------|----------|
| `.env.example` | 6 | 环境变量模板，定义 LLM 服务连接参数 | Config file |
| `.gitignore` | 7 | Git 版本控制忽略规则 | Config/Other |
| `README.md` | 59 | 项目使用指南与 API 文档 | Documentation |
| `prd.md` | 105 | 产品需求文档，四层架构设计规划 | Documentation |
| `pyproject.toml` | 20 | 项目元数据、依赖声明与构建配置 | Config |

## §3 文件详细分析

### §3.1 `.env.example`

- **路径**: `/.env.example`
- **行数**: 6
- **职责**: 为开发者提供环境变量模板，定义连接 OpenAI 兼容 LLM 服务所需的全部配置参数

#### §3.1.1 核心内容

该文件是一个环境变量示例模板，项目通过 `python-dotenv` 在运行时加载 `.env` 文件中的实际值。变量清单如下：

| 变量名 | 类型 | 默认值 | 描述 |
|--------|------|--------|------|
| `LLM_API_KEY` | `str` | _(空)_ | LLM 服务的 API 密钥，必须由用户手动填写，是唯一没有默认值的必填项 |
| `LLM_BASE_URL` | `str` | `https://api.openai.com/v1` | LLM API 的基础 URL，默认指向 OpenAI 官方端点；支持替换为任何 OpenAI 兼容服务（如 Azure OpenAI、本地 Ollama 等） |
| `LLM_MODEL` | `str` | `gpt-4.1-mini` | 使用的模型标识符，默认为 `gpt-4.1-mini`，这是一个较新的 OpenAI 模型，兼顾性能与成本 |
| `LLM_TIMEOUT_SECONDS` | `int` | `6000` | 单次 LLM 请求的超时时间（秒），默认 6000 秒（100 分钟），表明工作流可能涉及长时间运行的复杂推理链 |
| `LLM_TEMPERATURE` | `float` | `0.2` | 生成温度参数，`0.2` 偏低，有利于输出确定性更强的测试用例文本，减少随机性 |
| `LLM_MAX_TOKENS` | `int` | `1600` | 单次请求最大生成 token 数，`1600` 对于结构化测试用例输出是一个合理的上限 |

**设计特征**：所有变量均以 `LLM_` 为前缀，形成清晰的命名空间。敏感凭证（`LLM_API_KEY`）留空，非敏感配置提供合理默认值，这是业界推荐的 `.env.example` 编写模式。

#### §3.1.2 依赖关系

- 内部依赖: 被 `app/config/settings.py` 中的 `Settings` 类（基于 Pydantic `BaseSettings`）读取解析
- 外部依赖: 依赖 `python-dotenv` 库加载 `.env` 文件

#### §3.1.3 关键逻辑 / 数据流

配置加载流程：`.env.example` → 用户复制为 `.env` → `python-dotenv` 在应用启动时加载 → `Settings` (Pydantic BaseSettings) 验证并注入类型 → 通过 `app.state.settings` 注入 FastAPI 应用 → 最终传递给 `WorkflowService` 用于构建 LLM 客户端。超时时间设为 6000 秒说明 LangGraph 工作流的单次完整执行可能耗时较长，需要足够的超时容忍度。

---

### §3.2 `.gitignore`

- **路径**: `/.gitignore`
- **行数**: 7
- **职责**: 定义 Git 版本控制的忽略规则，防止敏感信息、临时文件和生成产物进入代码仓库

#### §3.2.1 核心内容

该文件定义了 7 条忽略规则，覆盖了项目开发中的关键排除类别：

| 模式 | 用途分类 | 说明 |
|------|----------|------|
| `.worktrees/` | Git 管理 | Git worktree 工作目录，用于多分支并行开发场景 |
| `.pytest_cache/` | 测试缓存 | pytest 运行时生成的缓存目录，包含测试发现和执行状态 |
| `__pycache__/` | Python 编译缓存 | Python 字节码编译缓存 (`.pyc` 文件)，由解释器自动生成 |
| `.venv/` | 虚拟环境 | Python 虚拟环境目录，与 `README.md` 中的安装指引一致 |
| `output/` | 生成产物 | 工作流执行的输出目录（`output/runs/<run_id>/`），包含生成的测试用例文件 |
| `*.egg-info/` | 打包元数据 | Python 包安装时生成的元数据目录，由 `pip install -e .` 产生 |
| `.env` | 敏感配置 | 包含实际 API 密钥的环境变量文件，**安全关键**——防止凭证泄露 |

**特征分析**：该 `.gitignore` 文件非常精简（仅 7 行），没有使用 GitHub 官方的 Python `.gitignore` 模板。它仅关注本项目实际会产生的文件类型，体现了最小化原则。最关键的安全规则是忽略 `.env` 文件，确保 `LLM_API_KEY` 等敏感凭证不会被误提交。

#### §3.2.2 依赖关系

- 内部依赖: 无（`.gitignore` 是 Git 基础设施文件）
- 外部依赖: Git 版本控制系统

#### §3.2.3 关键逻辑 / 数据流

`.gitignore` 规则在 `git add` / `git status` 等操作中自动生效。`output/` 目录的忽略尤其值得关注：API 端点 `POST /api/v1/case-generation/runs` 会将生成的测试用例写入 `output/runs/<run_id>/`，这些产物是运行时动态生成的，不应纳入版本控制。`.env` 的忽略确保了 `.env.example`（模板）与 `.env`（实际配置）的安全分离模式。

---

### §3.3 `README.md`

- **路径**: `/README.md`
- **行数**: 59
- **职责**: 项目的用户入口文档，提供安装、配置、运行和测试的完整指南

#### §3.3.1 核心内容

**文档结构概览**：

| 章节 | 内容摘要 |
|------|----------|
| 标题 (`# AutoChecklist`) | 项目名称 |
| 简介段落 | 一句话定位：FastAPI 服务，读取本地 Markdown PRD → LangGraph 工作流 → LLM 调用 → 返回 JSON 和 Markdown 格式的结构化测试用例 |
| Requirements | 最低要求 Python 3.11+ |
| Setup | 三步安装：创建虚拟环境 → `pip install -e ".[dev]"` → 复制 `.env.example` 为 `.env` |
| 环境变量列表 | 引用 `.env.example` 中的 6 个 `LLM_*` 变量 |
| Run The API | 使用 `uvicorn app.main:app --reload` 启动 |
| API Endpoints | 列出 3 个端点及 curl 示例 |
| Run Tests | 使用 `pytest -q` 运行测试 |

**API 端点设计**：
1. `GET /healthz` — 健康检查端点
2. `POST /api/v1/case-generation/runs` — 创建测试用例生成任务（核心端点）
3. `GET /api/v1/case-generation/runs/{run_id}` — 查询任务执行结果

**请求体结构**（从 curl 示例提取）：
- `file_path`: 本地 PRD 文件的绝对路径
- `language`: 输出语言代码（如 `"zh-CN"`）
- `model_config`: LLM 参数覆盖，包含 `temperature` 和 `max_tokens`

**关键设计洞察**：
- 使用 `pip install -e ".[dev]"` 的可编辑安装模式，说明项目通过 `pyproject.toml` 管理构建
- API 设计采用 RESTful 风格，使用 `/api/v1/` 版本前缀，`runs` 资源名暗示异步任务模式
- 产物输出到 `output/runs/<run_id>/`，按运行 ID 隔离

#### §3.3.2 依赖关系

- 内部依赖: 引用 `.env.example`（配置说明）、`app.main:app`（uvicorn 入口点）
- 外部依赖: 无（纯文档文件）

#### §3.3.3 关键逻辑 / 数据流

README 描述的核心数据流：用户准备本地 Markdown PRD 文件 → 通过 `POST /api/v1/case-generation/runs` 提交文件路径和配置 → 服务内部执行 LangGraph 工作流（多步 LLM 调用）→ 生成结构化测试用例 → 用户通过 `GET /api/v1/case-generation/runs/{run_id}` 获取结果，同时产物写入本地 `output/` 目录。这个流程说明当前版本仅支持服务器本地文件读取，不支持文件上传。

---

### §3.4 `prd.md`

- **路径**: `/prd.md`
- **行数**: 105
- **职责**: 产品需求文档，定义 AutoChecklist 的完整四层架构设计、核心功能模块与技术实现规划

#### §3.4.1 核心内容

**文档结构**：共五大章节，采用中文编写。

| 章节 | 标题 | 内容概要 |
|------|------|----------|
| 一 | 核心架构设计 | 四层架构体系、状态管理、工作流节点设计 |
| 二 | 核心功能模块 | 多模态文档解析、智能需求理解、测试用例生成、质量优化、业务适配 |
| 三 | 技术实现要点 | LangGraph 工作流、智能代理架构、数据处理管道 |
| 四 | 开发实施内容 | 核心模块开发、工作流实现、业务集成 |
| 五 | 关键优化特性 | 冗余优化、去重、权重打分、业务模板等实际效果数据 |

**四层架构体系**：
1. **输入层** — 多模态文档解析，支持飞书 PRD、Figma 设计、Wiki 页面等，归一化为统一文本格式
2. **上下文研究层** — Lead-Worker 智能代理架构，Lead Researcher 负责测试信号打标与研究计划，Sub Researcher 执行深度研究（搜索、代码查询、API 文档检索），输出知识图谱
3. **用例生成层** — 子图架构，包含四个有序节点：场景规划员 → 证据映射员 → 草稿撰写员 → 结构装配员
4. **反思优化层** — 冗余检查、语义去重、规则合规验证、最终组装

**状态管理设计**：
- `GlobalState`: 全局工作流数据中枢（PRD 输入、中间产物、配置参数、元数据）
- `CaseGenState`: 用例生成子图专用状态，隔离复杂中间产物

**工作流核心节点**：
- `InputParserNode`: 文档获取器工厂，按 URL 模式选择解析器
- `ContextResearchNode`: Lead-Worker 调度器，七类测试信号分类（行为、状态、条件、异常、UI 反馈、约束、模糊）
- `CaseGenNode`: 子图协调器，封装四阶段用例生成流水线
- `ReflectionNode`: 质量优化器，执行冗余分析与规则验证

**优化效果数据**（第五章）：
- Case 内部冗余优化：362 → 95 个用例
- Case 间去重优化：95 → 82 个，78 → 57 个
- 文档权重打分：82 → 57 个，104 → 70 个

#### §3.4.2 依赖关系

- 内部依赖: 定义了 `app/` 下各模块的设计蓝图，是代码实现的需求来源
- 外部依赖: 无（纯文档文件）

#### §3.4.3 关键逻辑 / 数据流

PRD 描述的核心数据流贯穿四层架构：

1. **输入层数据流**: 多源文档（飞书/Figma/Wiki）→ 类型识别 → 结构化提取 → 引用追踪 → 归一化文本
2. **研究层数据流**: 归一化文本 → 测试信号打标（7 类）→ Lead Researcher 制定研究计划 → Sub Researcher 并行执行深度研究 → 知识图谱构建（5 类实体 + 4 类关系）
3. **生成层数据流**: 知识图谱 → 场景规划（功能点拆解）→ 证据映射（三轮定位 + 置信度评分）→ 草稿撰写（正常/边界/异常三类场景）→ 结构装配（树状组装）
4. **优化层数据流**: 原始用例集 → 冗余检查 → 语义去重（嵌入向量聚类）→ 规则合规验证 → 多维质量评估 → 最终输出

**注意**: PRD 描述的是完整愿景，当前代码实现可能仅覆盖部分功能。例如 PRD 提到支持飞书、Figma 等多模态输入，但 `README.md` 显示当前仅支持本地 Markdown 文件。

---

### §3.5 `pyproject.toml`

- **路径**: `/pyproject.toml`
- **行数**: 20
- **职责**: 项目构建配置的核心文件，定义元数据、运行时依赖和开发依赖

#### §3.5.1 核心内容

**项目元数据**：

| 字段 | 值 | 说明 |
|------|-----|------|
| `name` | `auto-checklist` | 包名称（PyPI 规范的 kebab-case） |
| `version` | `0.1.0` | 初始版本，处于早期开发阶段 |
| `description` | `"Automated test checklist generation from PRD documents"` | 一句话描述 |
| `readme` | `README.md` | 长描述来源 |
| `requires-python` | `>=3.11` | 最低 Python 版本要求 |

**运行时依赖**（6 个）：

| 包名 | 版本约束 | 角色说明 |
|------|----------|----------|
| `fastapi` | `>=0.115.12` | Web 框架，提供 REST API 端点和依赖注入 |
| `httpx` | `>=0.28.1` | 异步 HTTP 客户端，用于 LLM API 调用（替代 `requests`） |
| `langgraph` | `>=0.3.34` | LangChain 生态的工作流编排框架，构建多步 LLM 调用管道 |
| `pydantic` | `>=2.11.1` | 数据验证与序列化库（v2），用于请求/响应模型和配置管理 |
| `python-dotenv` | `>=1.1.0` | `.env` 文件加载器，配合 Pydantic BaseSettings 使用 |
| `uvicorn` | `>=0.34.2` | ASGI 服务器，FastAPI 的运行时容器 |

**开发依赖**（`[dependency-groups]` 格式，PEP 735）：

| 包名 | 版本约束 | 角色说明 |
|------|----------|----------|
| `pytest` | `>=8.3.5` | Python 测试框架 |
| `pytest-asyncio` | `>=0.26.0` | pytest 的异步测试支持插件，用于测试 FastAPI 异步端点 |

**构建系统特征**：
- 未显式声明 `[build-system]`，将使用 pip 的默认后端（`setuptools`）
- 使用 `[dependency-groups]` 而非 `[project.optional-dependencies]`，这是 PEP 735 引入的新规范，表明项目跟进了 Python 打包生态的最新实践
- 所有版本约束使用 `>=` 最低版本策略（无上限锁定），适合快速迭代的早期项目

#### §3.5.2 依赖关系

- 内部依赖: 定义了整个项目的包名和入口，被 `pip install -e .` 安装流程引用
- 外部依赖: 声明了 6 个运行时依赖和 2 个开发依赖（详见上表）

#### §3.5.3 关键逻辑 / 数据流

`pyproject.toml` 在以下场景发挥作用：
1. **安装流程**: `pip install -e ".[dev]"` → 读取 `pyproject.toml` → 安装 `dependencies` + `dev` 组依赖 → 以可编辑模式注册包
2. **版本管理**: `version = "0.1.0"` 作为项目的唯一版本真相来源（Single Source of Truth）
3. **依赖链**: `fastapi` → `pydantic`（内部依赖），`langgraph` → `langchain-core`（传递依赖），`fastapi` + `uvicorn` 构成 Web 服务栈
4. **Python 版本门控**: `requires-python = ">=3.11"` 利用了 3.11 的类型联合语法 (`X | Y`) 和性能改进

值得注意的是，项目没有直接依赖 `openai` 包——LLM 调用可能通过 `httpx` 直接发起 HTTP 请求，或者通过 `langgraph` 的传递依赖间接获得 `langchain-openai` 支持。

## §4 目录级依赖关系

**向内依赖（根目录被谁依赖）**：
- `app/config/settings.py` 依赖 `.env.example` 定义的变量契约来构建 `Settings` 模型
- `app/main.py` 的 `create_app()` 函数是 `README.md` 中 `uvicorn app.main:app` 启动命令的入口
- `pyproject.toml` 被所有安装和构建工具引用
- `prd.md` 是 `app/` 下所有业务模块的需求规格来源

**向外依赖（根目录依赖谁）**：
- 根目录文件本身不依赖 `app/` 下的代码
- `README.md` 引用了 `app.main:app` 作为 uvicorn 入口点

## §5 设计模式与架构特征

1. **环境隔离模式 (Environment Isolation)**: 通过 `.env.example` + `.env` + `.gitignore` 三文件联动，实现了配置模板（版本控制）与实际凭证（本地隔离）的安全分离
2. **PEP 735 依赖分组**: 使用 `[dependency-groups]` 替代传统的 `[project.optional-dependencies]`，是现代 Python 打包实践
3. **最低版本约束策略**: 所有依赖仅设下界 (`>=`)，不设上界，适合快速演进项目，但长期可能面临兼容性风险
4. **文档驱动开发**: `prd.md` 作为产品需求文档与代码同仓管理，体现了 Docs-as-Code 的实践理念
5. **RESTful 异步任务模式**: API 设计（POST 创建 → GET 查询）暗示了后端的异步执行架构

## §6 潜在关注点

1. **`pyproject.toml` 缺少 `[build-system]` 声明**: 虽然 pip 会使用默认后端，但显式声明是 PEP 517/518 的推荐实践，缺失可能导致某些构建工具报警
2. **`.gitignore` 覆盖范围较窄**: 未包含常见的 Python 项目忽略项（如 `.mypy_cache/`、`.ruff_cache/`、`dist/`、`.coverage`），随着项目成长可能需要补充
3. **依赖版本无上限约束**: `>=` 策略在 `langgraph` 等快速迭代的库上存在隐性风险（breaking changes），建议考虑引入 `poetry.lock` 或 `pip-tools` 进行版本锁定
4. **`LLM_TIMEOUT_SECONDS=6000`**: 100 分钟的超时设置异常偏高，可能暗示工作流存在性能瓶颈或缺少中间超时控制
5. **PRD 与实现的差距**: `prd.md` 描述了飞书、Figma 等多模态输入支持，但 `README.md` 显示当前仅支持本地 Markdown 文件，存在显著的规划-实现差距
6. **缺少 LICENSE 文件**: 开源仓库没有 LICENSE 文件，法律上默认保留所有权利，可能影响社区贡献
7. **缺少 CI/CD 配置**: 没有 `.github/workflows/` 或类似的持续集成配置，测试可能仅依赖本地手动执行