# AutoChecklist — 项目分析总索引

> **维护方针**：每完成一轮分析后，在此文件追加条目并更新统计。
>
> | 元信息 | 值 |
> |-------|----|
> | 仓库 | `sandaogouchen/AutoChecklist` |
> | 基准 commit | `main` HEAD (2025-07) |
> | 源文件总数 | ~82 |
> | 分析文件数 | 25 |
> | 最后更新 | 2026-03-19 (PR #17 Checklist 前置条件分组优化 V2) |

---

## §1 项目概述

### §1.1 定位

AutoChecklist 是一个 **AI 驱动的测试用例自动生成工具**，核心使用 LangGraph 构建多步骤有状态工作流，将产品需求文档（PRD）自动转化为结构化测试检查清单。

### §1.2 技术栈速览

| 层 | 技术 |
|---|------|
| 语言 | Python 3.11+ |
| AI 框架 | LangGraph 0.x · LangChain 0.3 |
| LLM | OpenAI GPT-4o (默认) |
| 数据模型 | Pydantic v2 |
| API | FastAPI |
| 配置 | pydantic-settings + `.env` |
| 测试 | pytest · pytest-asyncio |

### §1.3 核心架构

```
用户请求 (PRD 文本)
  │
  ├─ 文档解析子图 (2 nodes)
  │    doc_loader → doc_splitter
  │
  ├─ 用例生成子图 (7 nodes)
  │    scenario_planner → checkpoint_generator → checkpoint_evaluator
  │    → evidence_mapper → draft_writer → structure_assembler
  │    → checklist_optimizer
  │
  └─ 质量保障子图 (2 nodes)
       reflection → final_output
```

### §1.4 关键状态模型

- `GraphState` (TypedDict): 贯穿整个图的主状态，包含 PRD 文本、分割块、场景、检查点、草稿等 15+ 字段
- `TestCase` / `TestStep` (Pydantic BaseModel): 标准化测试用例输出结构
- `QualityReport` (Pydantic BaseModel): 质量评估反馈结构
- `ChecklistNode` (Pydantic BaseModel): 前置条件分组优化树节点，支持 root/precondition_group/case 三种类型

---

## §2 目录结构

```
AutoChecklist/
├── app/
│   ├── config/          # 配置层 (3 files)
│   ├── domain/          # 领域模型 (11 files)
│   ├── graphs/          # LangGraph 图定义 (4 files)
│   ├── nodes/           # LangGraph 节点 (13 nodes)
│   ├── prompts/         # Prompt 模板 (6 files)
│   ├── routers/         # FastAPI 路由 (2 files)
│   ├── services/        # 业务服务 (11 files)
│   └── main.py          # 入口
├── tests/
│   ├── unit/            # 单元测试
│   └── integration/     # 集成测试
├── _INDEX.md            # ← 本文件
└── ...
```

---

## §3 分析文件索引

> 编号按分析创建时间排序。

| # | 分析文件路径 | 源文件/目录 | 关注点摘要 |
|---|-------------|------------|-----------|
| 1 | `app/config/_ANALYSIS.md` | `app/config/` (3 files) | 13 个配置字段、环境变量映射、默认值安全性 |
| 2 | `app/domain/_ANALYSIS.md` | `app/domain/` (11 model files) | Pydantic v2 模型设计、字段校验、序列化 |
| 3 | `app/graphs/_ANALYSIS.md` | `app/graphs/` (4 files) | 主图 + 子图拓扑、7-node 用例生成子图、条件路由 |
| 4 | `app/nodes/_ANALYSIS.md` | `app/nodes/` (13 nodes) | 各节点职责、输入输出契约、异常处理 |
| 5 | `app/prompts/_ANALYSIS.md` | `app/prompts/` (6 files) | Prompt 工程、模板变量、输出格式约束 |
| 6 | `app/routers/_ANALYSIS.md` | `app/routers/` (2 files) | API 端点设计、请求/响应模型 |
| 7 | `app/services/_ANALYSIS.md` | `app/services/` (11 files) | LLM 调用封装、文档解析、结果格式化 |
| 8 | `app/main_ANALYSIS.md` | `app/main.py` | FastAPI 应用初始化、中间件、CORS |
| 9 | `tests/unit/_ANALYSIS.md` | `tests/unit/` | 测试覆盖率、mock 策略、参数化 |
| 10 | `tests/integration/_ANALYSIS.md` | `tests/integration/` | 端到端流程、API 测试 |
| 11 | `app/nodes/doc_loader_ANALYSIS.md` | `doc_loader.py` | 文档加载节点深度分析 |
| 12 | `app/nodes/doc_splitter_ANALYSIS.md` | `doc_splitter.py` | 文档分割节点深度分析 |
| 13 | `app/nodes/scenario_planner_ANALYSIS.md` | `scenario_planner.py` | 场景规划节点深度分析 |
| 14 | `app/nodes/checkpoint_generator_ANALYSIS.md` | `checkpoint_generator.py` | 检查点生成节点深度分析 |
| 15 | `app/nodes/checkpoint_evaluator_ANALYSIS.md` | `checkpoint_evaluator.py` | 检查点评估节点深度分析 |
| 16 | `app/nodes/evidence_mapper_ANALYSIS.md` | `evidence_mapper.py` | 证据映射节点深度分析 |
| 17 | `app/nodes/draft_writer_ANALYSIS.md` | `draft_writer.py` | 草稿撰写节点深度分析 |
| 18 | `app/nodes/structure_assembler_ANALYSIS.md` | `structure_assembler.py` | 结构组装节点深度分析 |

### §3.1 PR #17 新增分析文件 (Checklist 前置条件分组优化 V2)

| # | 分析文件路径 | 源文件 | 功能编号 | 核心关注点 |
|---|-------------|--------|---------|----------|
| 19 | `app/domain/checklist_models_ANALYSIS.md` | `checklist_models.py` | F1 | ChecklistNode 递归树模型、Pydantic v2 model_rebuild() |
| 20 | `app/services/precondition_grouper_ANALYSIS.md` | `precondition_grouper.py` | F1 | 纯函数分组引擎、strip+NFKC+标点归一化、OrderedDict 分桶 |
| 21 | `app/nodes/checklist_optimizer_ANALYSIS.md` | `checklist_optimizer.py` | F3 | LangGraph 优化节点、配置开关、优雅降级 |
| 22 | `app/services/markdown_renderer_ANALYSIS.md` | `markdown_renderer.py` | F4 | 共享 Markdown 渲染、flat + tree 模式、DRY 修复 |
| 23 | `tests/unit/test_precondition_grouper_ANALYSIS.md` | `test_precondition_grouper.py` | F5 | 21 测试：规范化/分桶/分组/性能基线 |
| 24 | `tests/unit/test_checklist_optimizer_ANALYSIS.md` | `test_checklist_optimizer.py` | F5 | 6 测试：正常流/降级/异常/不可变性 |
| 25 | `tests/unit/test_markdown_renderer_ANALYSIS.md` | `test_markdown_renderer.py` | F5 | 14 测试：扁平模式兼容 + 树模式渲染 |

> ⚠️ PR #15 的 Trie 方案已在 PR #16 中 revert，原分析文件 `checklist_merger_ANALYSIS.md`、`test_checklist_merger_ANALYSIS.md`、`test_text_refiner_ANALYSIS.md` 已标记为 DEPRECATED。

---

## §4 横切面分析

### §4.1 数据流概览

```
PRD 文本输入
  → doc_loader → raw_doc
  → doc_splitter → chunks[]
  → scenario_planner → scenarios[]
  → checkpoint_generator → checkpoints[]
  → checkpoint_evaluator → evaluated_checkpoints[]
  → evidence_mapper → evidence_map
  → draft_writer → draft_cases[]
  → structure_assembler → TestCase[] (规范化)
  → checklist_optimizer → optimized_tree (前置条件分组)
  → reflection → QualityReport + 迭代决策
  → final_output → 最终 Checklist
```

### §4.2 关键数据流

| 阶段 | 输入 | 输出 | 关键转换 |
|------|------|------|---------|
| 文档解析 | PRD 原文 | chunks[] | 按语义边界分割 |
| 场景规划 | chunks[] | scenarios[] | LLM 提取测试场景 |
| 检查点生成 | scenarios[] | checkpoints[] | LLM 生成检查项 |
| 检查点评估 | checkpoints[] | evaluated[] | LLM 质量过滤 |
| 证据映射 | evaluated[] | evidence_map | 关联 PRD 原文证据 |
| 草稿撰写 | evidence_map | draft_cases[] | LLM 生成测试用例草稿 |
| 结构组装 | draft_cases[] | TestCase[] | Pydantic 规范化 |
| 前置条件分组 | TestCase[] | optimized_tree | 按前置条件分桶+树渲染 |
| 质量反思 | TestCase[] | QualityReport | LLM 评估 + 迭代 |

---

## §5 环境变量清单

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `OPENAI_API_KEY` | str | (required) | OpenAI API 密钥 |
| `OPENAI_MODEL` | str | `gpt-4o` | 默认模型 |
| `OPENAI_BASE_URL` | str | `None` | 自定义 API 端点 |
| `MAX_ITERATIONS` | int | `3` | 反思最大迭代次数 |
| `QUALITY_THRESHOLD` | float | `0.8` | 质量阈值 |
| `CHUNK_SIZE` | int | `2000` | 文档分割块大小 |
| `CHUNK_OVERLAP` | int | `200` | 分割重叠字符数 |
| `LOG_LEVEL` | str | `INFO` | 日志级别 |
| `CORS_ORIGINS` | str | `*` | CORS 允许来源 |
| `ENABLE_CHECKLIST_OPTIMIZATION` | bool | `true` | Checklist 前置条件分组优化开关 |

---

## §6 待办 & 已知问题

- [ ] 补充 `app/prompts/` 深度分析
- [ ] 补充 `app/routers/` 深度分析
- [ ] 补充集成测试分析
- [ ] 性能基线测试
- [ ] Prompt 版本管理策略

---

*本文件由 analysis 分支维护，随代码分析同步更新。*
