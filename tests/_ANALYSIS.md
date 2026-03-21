# tests/_ANALYSIS.md — 测试基础设施分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `tests/` |
| 文件数 | 2（含 `__init__.py`），另有 3 个子目录 |
| 子目录 | `integration/`（4 测试文件）、`unit/`（22 测试文件）、`fixtures/`（测试数据） |
| 目录职责 | 测试基础设施层：全局 pytest 配置、共享 fixtures、Fake LLM 客户端 |

## §2 文件清单

| # | 文件 | 类型 | 概要 |
|---|------|------|------|
| 1 | `__init__.py` | - | 空 |
| 2 | `conftest.py` | J-测试基础设施 | 全局 pytest fixtures 与 Fake LLM 客户端定义 |

## §3 逐文件分析

### §3.1 conftest.py

- **类型**: J-测试基础设施
- **职责**: 定义全局共享的 pytest fixtures 和 Fake LLM 客户端

- **FakeLLMClient（正常质量）**:
  - 继承 `LLMClient` ABC
  - 通过 `model_class` 参数路由到对应的预置响应
  - 覆盖所有 LLM 调用点的结构化输出模型：
    - `ResearchOutput` → 预置研究事实和场景
    - `CheckpointDraft` → 预置检查点草稿
    - `EvaluationReport` → 预置评估报告（overall_score > 0.7, pass_=True）
    - `CanonicalOutlineNode` → 预置 outline 层级
  - 设计优势：单一 fake 客户端覆盖全流水线，无需每个节点独立 mock

- **FakeLLMClientLowQuality（低质量）**:
  - 生成低质量/不合格响应
  - 用途：测试 `IterationController` 的重试决策逻辑
  - 典型场景：evaluation_pass_threshold 未达标 → 触发重试 → 切换到正常客户端 → 通过

- **共享 Fixtures**:
  | Fixture | 类型 | 用途 |
  |---------|------|------|
  | `sample_parsed_document` | `ParsedDocument` | 预解析的 PRD 文档 |
  | `sample_research_output` | `ResearchOutput` | 研究阶段输出 |
  | `sample_checkpoints` | `list[Checkpoint]` | 检查点列表 |
  | `fake_llm_client` | `FakeLLMClient` | 正常质量 LLM 客户端 |
  | `fake_llm_client_low` | `FakeLLMClientLowQuality` | 低质量 LLM 客户端 |

## §4 补充观察

1. **Fake Client 策略优秀**: 通过 `model_class` 路由实现了全面的 LLM mock，避免了真实 API 调用的不确定性和成本
2. **双客户端设计巧妙**: 正常/低质量客户端的组合完美支持迭代控制逻辑的测试（低质量 → 重试 → 正常质量 → 通过）
3. **Fixture 粒度合理**: 从 `parsed_document` → `research_output` → `checkpoints` 逐层构建，每层可独立使用
4. **Fixture 集中管理**: 所有共享 fixture 放在根 `conftest.py`，子目录的 `conftest.py` 仅添加局部 fixture，层次清晰
5. **缺少 Checklist 专用 Fixture**: 缺少 `sample_optimized_tree` 或 `sample_outline_nodes` fixture，checklist 相关测试需各自构建测试数据

## §5 PR #24 变更 — 知识检索测试

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

PR #24 新增 4 个测试文件，共计 31 个测试用例，覆盖知识检索子系统的各层逻辑。

### 新增测试文件

| # | 文件 | 测试数 | 覆盖范围 |
|---|------|--------|--------|
| 1 | `tests/unit/test_knowledge_ingestion.py` | 12 | 文档扫描与校验 |
| 2 | `tests/unit/test_knowledge_retrieval.py` | 8 | 检索节点行为 |
| 3 | `tests/unit/test_graphrag_engine.py` | 6 | 引擎生命周期 |
| 4 | `tests/integration/test_knowledge_workflow.py` | 5 | 端到端工作流 |

### §5.1 test_knowledge_ingestion.py（12 个用例）

覆盖 `ingestion.py` 的两个公开函数：

| 测试分组 | 用例数 | 关键场景 |
|---------|--------|--------|
| `scan_knowledge_directory` | 7 | 正常扫描、空目录、目录不存在、超大文件过滤、非 UTF-8 过滤、空文件跳过、递归子目录 |
| `validate_document_path` | 5 | 正常校验、文件不存在、非 .md 格式、空文件、超大文件 |

### §5.2 test_knowledge_retrieval.py（8 个用例）

覆盖 `retriever.py` 和 `knowledge_retrieval.py` 节点：

| 测试分组 | 用例数 | 关键场景 |
|---------|--------|--------|
| `build_retrieval_query` | 2 | 正常查询构造、空文档处理 |
| `format_retrieval_result` | 2 | 正常格式化、超长截断 |
| `knowledge_retrieval_node` | 4 | 正常检索、引擎未就绪降级、异常降级、空查询 |

### §5.3 test_graphrag_engine.py（6 个用例）

覆盖 `GraphRAGEngine` 类的生命周期与索引：

| 用例 | 关键场景 |
|------|--------|
| 初始化 + 就绪检查 | mock LightRAG 初始化流程 |
| 插入文档 | 正常索引 + 幂等重复跳过 |
| 批量索引 | 多文档批量处理 |
| 查询 | 正常检索 + 失败降级 |
| 删除文档 | 正常删除 + 不存在文档 |
| 终结 | 资源释放 |

### §5.4 test_knowledge_workflow.py（5 个集成用例）

覆盖知识检索与主工作流的端到端集成：

| 用例 | 关键场景 |
|------|--------|
| 知识检索节点在工作流中正常执行 | 含 knowledge_retrieval 的完整工作流 |
| 知识上下文注入 context_research | 验证 prompt 中包含 [Domain Knowledge Reference] |
| 引擎未就绪时工作流正常降级 | 跳过知识检索，主流程不受影响 |
| 无知识文档时的空结果处理 | knowledge_context 为空 |
| 配置关闭时的完全跳过 | enable_knowledge_retrieval=False |

### 测试策略评价

1. **覆盖层次完整**: 单元测试覆盖模块内部逻辑，集成测试覆盖跨模块交互
2. **Mock 策略合理**: GraphRAG 引擎通过 mock 避免真实 LLM 调用
3. **降级场景充分**: 引擎未就绪、异常、空查询等降级路径均有测试覆盖
4. **与现有测试风格一致**: 使用 pytest-asyncio + conftest fixtures，融入现有测试体系