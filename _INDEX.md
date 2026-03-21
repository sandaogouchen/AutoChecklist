# _INDEX.md — AutoChecklist 代码分析索引

> 分析分支自动生成 · 源分支 `main` · 提交 `88e1848`
>
> **最新同步**: PR #23 `feat/mandatory-template-levels` — 8 个分析文件更新（domain、services、nodes、graphs、api、config、templates(新增)、本索引）
>
> **最新同步**: PR #24 `feat/graphrag-knowledge-retrieval` — 知识检索层接入, 11 个分析文件更新

---

## 项目概况

| 维度 | 值 |
|------|-----|
| 项目名称 | AutoChecklist |
| 定位 | 读取 Markdown PRD → LangGraph 工作流 → 结构化测试用例 |
| 技术栈 | Python 3.11+, FastAPI, LangGraph, OpenAI API, Pydantic v2 |
| 源文件数 | ~93 |
| 分析文档数 | 17 |
| 分析总量 | ~134 KB |

## 架构概览

```
PRD 文本输入
    │
    ▼
┌─────────────────── 主工作流 (GlobalState) ───────────────────┐
│  input_parser → template_loader → [project_context_loader]   │
│                  (mandatory_skeleton)  → context_research     │
│                                                │              │
│                                                ▼              │
│  ┌────────── 子图 (CaseGenState) ──────────────────┐ │
│  │ scenario_planner → checkpoint_generator →                │ │
│  │ checkpoint_evaluator → checkpoint_outline_planner →      │ │
│  │ evidence_mapper → draft_writer → structure_assembler     │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                │              │
│                                                ▼              │
│                          reflection → 最终输出                │
└───────────────────────────────────────────────────────┘
    │
    ▼
测试用例 (JSON + Markdown + XMind)
```

## 分析文档目录

### 根目录

| 文档 | 覆盖范围 | 大小 |
|------|---------|------|
| [_ROOT_ANALYSIS.md](./_ROOT_ANALYSIS.md) | 根目录文件：.env.example, README.md, prd.md, pyproject.toml 等 | 3.4 KB |

### app/ — 应用代码

| 文档 | 覆盖范围 | 文件数 | 大小 | 重要度 |
|------|---------|--------|------|--------|
| [app/api/_ANALYSIS.md](./app/api/_ANALYSIS.md) | REST API 路由层 | 2 | 2.9 KB | ★★☆ |
| [app/clients/_ANALYSIS.md](./app/clients/_ANALYSIS.md) | LLM 客户端抽象 | 1 | 3.1 KB | ★★★ |
| [app/config/_ANALYSIS.md](./app/config/_ANALYSIS.md) | 配置管理 | 1 | 5.1 KB | ★★☆ |
| [app/domain/_ANALYSIS.md](./app/domain/_ANALYSIS.md) | 领域模型层（Pydantic v2） | 10 | 26.0 KB | ★★★ |
| [app/knowledge/_ANALYSIS.md](./app/knowledge/_ANALYSIS.md) | 知识检索模块（GraphRAG） | 5 | 7.9 KB | ★★☆ |
| [app/graphs/_ANALYSIS.md](./app/graphs/_ANALYSIS.md) | LangGraph 工作流图定义 | 2 | 3.7 KB | ★★★ |
| [app/nodes/_ANALYSIS.md](./app/nodes/_ANALYSIS.md) | 工作流节点（12 个节点） | 12 | 12.2 KB | ★★★ |
| [app/parsers/_ANALYSIS.md](./app/parsers/_ANALYSIS.md) | 文档解析器 | 3 | 3.3 KB | ★★☆ |
| [app/repositories/_ANALYSIS.md](./app/repositories/_ANALYSIS.md) | 数据持久化 | 3 | 3.3 KB | ★★☆ |
| [app/services/_ANALYSIS.md](./app/services/_ANALYSIS.md) | 业务服务层（含 Checklist 核心 + 强制骨架构建） | 14 | 46.0 KB | ★★★ |
| [app/utils/_ANALYSIS.md](./app/utils/_ANALYSIS.md) | 工具函数 | 2 | 2.8 KB | ★☆☆ |

### tests/ — 测试代码

| 文档 | 覆盖范围 | 文件数 | 大小 |
|------|---------|--------|------|
| [tests/_ANALYSIS.md](./tests/_ANALYSIS.md) | 测试基础设施 (conftest, Fake Clients) | 1 | 2.8 KB |
| [tests/integration/_ANALYSIS.md](./tests/integration/_ANALYSIS.md) | 集成测试（API、工作流、迭代） | 4 | 3.3 KB |
| [tests/unit/_ANALYSIS.md](./tests/unit/_ANALYSIS.md) | 单元测试（24 个文件） | 24 | 6.8 KB |

### docs/ — 文档

| 文档 | 覆盖范围 | 文件数 | 大小 |
|------|---------|--------|------|
| [docs/plans/_ANALYSIS.md](./docs/plans/_ANALYSIS.md) | 架构设计与实施计划 | 2 | 4.1 KB |

---


### templates/ — 模版文件

| 文档 | 覆盖范围 | 文件数 | 大小 |
|------|---------|--------|------|
| [templates/_ANALYSIS.md](./templates/_ANALYSIS.md) | Checklist 模版 YAML 文件（brand_spp_consideration.yaml） | 1 | 3.2 KB |
## 重点分析：Checklist 整合方案

> 用户特别关注的焦点领域。以下内容汇总了分散在多个分析文档中的 Checklist 相关深度分析。

### 问题背景

Checklist 整合的目标是将零散的 Checkpoint（检查点）组织成层级化的测试用例清单树（ChecklistNode 树）。当前效果不佳，用例组织结构不够合理，层级划分质量波动大。

### 现有方案演进

| 阶段 | 方案 | 核心组件 | 状态 |
|------|------|---------|------|
| V1 | SemanticPathNormalizer + ChecklistMerger | `checklist_optimizer.py` | 已弃用 |
| V2 | CheckpointOutlinePlanner + PreconditionGrouper | `checkpoint_outline_planner.py` + `precondition_grouper.py` | 当前使用 |

### PR #21 对 Checklist 整合的影响

> 同步自 PR #21 `feat/checklist-action-verbs-and-steps-passthrough`

PR #21 对 Checklist 整合链条中的两个关键节点进行了重大改进：

| 变更文件 | 影响摘要 |
|----------|----------|
| `app/services/checkpoint_outline_planner.py` | `_OUTLINE_SYSTEM_PROMPT` 新增中文动作动词注入规则；`attach_expected_results_to_outline` 签名简化为 2 参数；新增 `_fill_node_from_testcase` 和 `_enrich_children` helper；async 化 |
| `app/nodes/draft_writer.py` | 从工厂函数重写为 `DraftWriterNode` 类；系统提示词改为中文路径-步骤衍接规则（4 条）；移除模板继承/场景 fallback/`DraftCaseCollection` |
| `tests/unit/test_attach_expected_results.py` | **新增** 14 个测试用例覆盖重构后的挂载逻辑 |
| `tests/unit/test_xmind_steps_rendering.py` | **新增** 11 个测试用例覆盖 XMind steps 渲染 |

详细分析见：
- [app/services/_ANALYSIS.md §3.2.1](./analysis_docs/app/services/_ANALYSIS.md) — outline planner 重构详情
- [app/nodes/_ANALYSIS.md §3.10.1](./analysis_docs/app/nodes/_ANALYSIS.md) — draft_writer 重写详情
- [tests/unit/_ANALYSIS.md §3.7-§3.8](./analysis_docs/tests/unit/_ANALYSIS.md) — 新增测试文件分析


### PR #23 对 Checklist 整合的影响：强制模版骨架

> 同步自 PR #23 `feat/mandatory-template-levels`

PR #23 引入了 **Checklist 模版强制层级（Mandatory Levels）** 功能，允许模版定义者通过 `mandatory_levels` 和 `mandatory` 字段约束 LLM 生成的 Checklist 结构，确保关键业务节点不被遗漏或篡改。这是对上述“改进路线图”中 **P0 PRD 章节锚定** 建议的落地实现。

#### 核心机制：双重约束策略

| 约束层 | 类型 | 实现位置 | 说明 |
|--------|------|---------|------|
| LLM Prompt 注入 | 软约束 | `checkpoint_outline_planner.py` | 将强制骨架序列化后注入 system prompt，引导 LLM 遵循模版结构 |
| 确定性后处理 | 硬约束 | `checkpoint_outline_planner.py` + `structure_assembler.py` | 两次后处理修复，确保强制层级 100% 合规 |

#### 新增文件

| 文件 | 说明 |
|------|------|
| `app/services/mandatory_skeleton_builder.py` | `MandatorySkeletonBuilder` 类：从模版提取强制节点子树 |
| `templates/brand_spp_consideration.yaml` | 示例模版：brand S++ consideration，mandatory_levels=[1,2] |

#### 变更影响矩阵

| 变更文件 | 影响摘要 |
|----------|----------|
| `app/domain/template_models.py` | 新增 `MandatorySkeletonNode`、`mandatory_levels`、`mandatory` 字段 |
| `app/domain/checklist_models.py` | `ChecklistNode` 新增 `source`、`is_mandatory` 字段 |
| `app/domain/state.py` | `GlobalState`/`CaseGenState` 新增 `mandatory_skeleton` 字段 |
| `app/services/template_loader.py` | 新增 `load_by_name()`、`build_mandatory_skeleton()`、增强 `_parse_node()` |
| `app/services/checkpoint_outline_planner.py` | LLM prompt 注入 + `_enforce_mandatory_skeleton()` 后处理 |
| `app/services/markdown_renderer.py` | 新增 `[模版]` / `[待分配]` source 标签 |
| `app/services/xmind_payload_builder.py` | 新增 source 颜色标记（蓝=template / 红=overflow） |
| `app/nodes/structure_assembler.py` | 最终强制约束防线 + `_annotate_source()` + overflow 机制 |
| `app/nodes/template_loader.py` | 支持 `template_name` + 骨架构建 |
| `app/graphs/main_workflow.py` | 桥接节点新增 `mandatory_skeleton` 字段映射 |
| `app/api/routes.py` | 新增 GET `/api/v1/templates` 和 GET `/api/v1/templates/{name}` |
| `app/config/settings.py` | 新增 `template_dir`、`enable_mandatory_source_labels` |

#### 溢出机制

未能匹配到骨架节点的 LLM 生成内容被收集到 `_overflow` 容器中。当溢出比例超过 20% 时发出告警，提示模版与 PRD 的匹配度不足。

详细分析见：
- [app/domain/_ANALYSIS.md §3.12](./app/domain/_ANALYSIS.md) — MandatorySkeletonNode 模型
- [app/services/_ANALYSIS.md §3.14](./app/services/_ANALYSIS.md) — mandatory_skeleton_builder 分析
- [app/nodes/_ANALYSIS.md §3.13](./app/nodes/_ANALYSIS.md) — structure_assembler 强制约束
- [templates/_ANALYSIS.md](./templates/_ANALYSIS.md) — 模版文件分析
### 方案 V1（已弃用）分析

- **设计思路**: LLM 两阶段路径归一化 → Trie 树确定性合并
- **失败原因**:
  1. LLM 路径归一化输出格式不稳定（缺乏 few-shot 约束）
  2. Trie 合并对输入质量敏感（路径不一致 → 树结构不合理）
  3. 产生过深/过浅的层级，同义路径重复
- **保留价值**: 两阶段归一化思路正确，Trie 合并的确定性值得复用
- **详见**: [app/nodes/_ANALYSIS.md §5.2](./app/nodes/_ANALYSIS.md)、[app/services/_ANALYSIS.md §5.1](./app/services/_ANALYSIS.md)

### 方案 V2（当前）问题诊断

1. **单次 LLM 规划的规模瓶颈**: Checkpoint 超过 30 个时，LLM 一次性规划 outline 质量显著下降
2. **缺乏 PRD 结构锚定**: outline 规划未利用 PRD 原文章节结构作为锚点
3. **前置条件分组过于机械**: PreconditionGrouper 基于关键词匹配，无法处理语义等价的不同措辞
4. **expected_results 挂载脆弱**: 简单路径匹配无法处理多对多关系
5. **无质量反馈循环**: outline 生成后无验证环节，错误向下游传播
- **详见**: [app/nodes/_ANALYSIS.md §5.3-§5.5](./app/nodes/_ANALYSIS.md)、[app/services/_ANALYSIS.md §5.2-§5.3](./app/services/_ANALYSIS.md)

### 改进路线图

| 优先级 | 改进项 | 预期收益 | 实现成本 | 详见 |
|--------|--------|---------|---------|------|
| P0 | ~~PRD 章节锚定~~ → **已实现 (PR #23)**: 模版强制骨架代替 PRD 标题锚定 | 高 | 低 | [services §3.14](./app/services/_ANALYSIS.md) |
| P0 | 分批规划 — 按场景分组 checkpoint，每组独立规划 | 高 | 低 | [nodes §5.7](./app/nodes/_ANALYSIS.md) |
| P1 | Outline 验证节点 — 复用 evaluator 模式 | 中 | 中 | [nodes §5.7](./app/nodes/_ANALYSIS.md) |
| P1 | 混合方案 — V1 路径归一化预处理 + V2 LLM 精调 | 高 | 中 | [services §5.5](./app/services/_ANALYSIS.md) |
| P1 | PreconditionGrouper 语义升级 — embedding 替代关键词 | 中 | 中 | [services §5.5](./app/services/_ANALYSIS.md) |
| P2 | 多轮迭代 outline — 参照迭代评估循环 | 高 | 高 | [nodes §5.7](./app/nodes/_ANALYSIS.md) |
| P2 | 结构化模板库 — 标准分类体系参考 | 中 | 高 | [services §5.5](./app/services/_ANALYSIS.md) |
| P3 | 用户反馈闭环 — 人工修改作为微调信号 | 高 | 高 | [services §5.5](./app/services/_ANALYSIS.md) |

### Checklist 相关测试空白

| 缺失项 | 影响 | 建议优先级 |
|--------|------|------------|
| PreconditionGrouper 无单元测试 | 分组逻辑未验证 | P0 |
| structure_assembler 无单元测试 | 挂载逻辑未验证（PR #21 的 `test_attach_expected_results.py` 部分缓解） | P0 |
| Checklist 端到端集成测试缺失 | outline→用例链路质量不可追踪 | P1 |
| 大规模 checkpoint（30+）压力测试 | LLM 规模瓶颈不可量化 | P1 |

- **详见**: [tests/unit/_ANALYSIS.md §5](./tests/unit/_ANALYSIS.md)、[tests/integration/_ANALYSIS.md §4](./tests/integration/_ANALYSIS.md)

---

## Knowledge Retrieval 整合方案 (PR #24)

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

### 功能概述

PR #24 引入了基于 LightRAG 的 GraphRAG 知识检索层，允许在工作流执行前检索外部知识文档，将领域知识注入 LLM prompt 以提升测试用例生成质量。

### 架构集成

```
知识文档 (.md)
│
▼
scan_knowledge_directory() → GraphRAGEngine.insert_batch()
                              │
                              ▼
                         LightRAG 图谱索引
                              │
PRD 输入 ────────────────▶ retrieve_knowledge()
                              │
                              ▼
                         knowledge_context (注入 GlobalState)
                              │
                              ▼
                    context_research 节点 prompt 中
                    追加 [Domain Knowledge Reference]
```

### 变更影响矩阵

| 变更文件/模块 | 影响摘要 |
|--------------|----------|
| `app/knowledge/` (新模块) | 5 个文件：models、ingestion、graphrag_engine、retriever、\_\_init\_\_ |
| `app/nodes/knowledge_retrieval.py` (新) | 工厂闭包模式知识检索节点 |
| `app/nodes/context_research.py` | 知识上下文注入 prompt |
| `app/api/knowledge_routes.py` (新) | 6 个 REST 端点 |
| `app/config/settings.py` | 7 个 `knowledge_*` 配置字段 |
| `app/domain/state.py` | 3 个 GlobalState 知识字段 |
| `app/graphs/main_workflow.py` | 动态 prev_node 节点链接 |
| `app/services/workflow_service.py` | graphrag_engine 注入 |
| `app/main.py` | \_lifespan() 引擎生命周期 + 路由注册 |
| `.env.example` | 11 个环境变量 |
| `pyproject.toml` | lightrag-hku>=1.1.0 依赖 |
| `tests/` | 4 个测试文件, 31 个测试用例 |

### 降级策略

| 场景 | 行为 |
|------|------|
| `enable_knowledge_retrieval=False` | 引擎不初始化，节点不注入，零开销 |
| 引擎初始化失败 | `is_ready()=False`，节点返回空结果 |
| 检索异常 | try/except 捕获，返回空 context，工作流继续 |
| 知识文档目录为空 | 正常启动，检索返回空结果 |

### 详细分析索引

- [app/knowledge/\_ANALYSIS.md](./app/knowledge/_ANALYSIS.md) — 知识检索模块完整分析
- [app/config/\_ANALYSIS.md §6](./app/config/_ANALYSIS.md) — 7 个配置字段
- [app/domain/\_ANALYSIS.md §6](./app/domain/_ANALYSIS.md) — 3 个 GlobalState 字段
- [app/graphs/\_ANALYSIS.md §5](./app/graphs/_ANALYSIS.md) — 工作流拓扑变更
- [app/nodes/\_ANALYSIS.md §6](./app/nodes/_ANALYSIS.md) — 知识检索节点 + context_research 注入
- [app/services/\_ANALYSIS.md §6](./app/services/_ANALYSIS.md) — WorkflowService 引擎注入
- [app/api/\_ANALYSIS.md §4](./app/api/_ANALYSIS.md) — 6 个 REST 端点
- [app/\_ANALYSIS.md §7](./app/_ANALYSIS.md) — Lifespan 引擎生命周期
- [\_ROOT\_ANALYSIS.md §5](./_ROOT_ANALYSIS.md) — 根目录文件更新
- [tests/\_ANALYSIS.md §5](./tests/_ANALYSIS.md) — 31 个测试用例

## 核心数据流

```
                    数据流关键路径
┌──────────┐    ┌──────────────┐    ┌─────────────┐
│ PRD 文本  │ →  │ ParsedDocument│ →  │ ResearchFact │
└──────────┘    └──────────────┘    └──────┬──────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │  Checkpoint  │
                                    └──────┬──────┘
                                           │
                          ┌────────────────┼────────────────┐
                          ▼                ▼                ▼
                 ┌────────────────┐ ┌──────────┐ ┌──────────────┐
                 │CanonicalOutline│ │EvidenceRef│ │  TestCase     │
                 │    Node        │ │          │ │               │
                 └───────┬────────┘ └────┬─────┘ └──────┬───────┘
                         │               │              │
                         └─────────────┼─────────────┘
                                         ▼
                                  ┌──────────────┐
                                  │MandatorySkeletonNode│
                                  │  (强制骨架约束)      │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                  ┌──────────────┐
                                  │ ChecklistNode │
                                  │  (最终树)     │
                                  │  +source      │
                                  │  +is_mandatory │
                                  └──────────────┘
```

## 技术债务清单

| # | 债务项 | 所在模块 | 风险等级 | 详见 |
|---|--------|---------|---------|------|
| 1 | checklist_optimizer 残留代码 | nodes/ | 低 | [nodes §3.7](./app/nodes/_ANALYSIS.md) |
| 2 | API 路由前缀不一致 | api/ | 低 | [api §4](./app/api/_ANALYSIS.md) |
| 3 | LLM 客户端无重试机制 | clients/ | 中 | [clients §4](./app/clients/_ANALYSIS.md) |
| 4 | 文件写入非原子操作 | repositories/ | 中 | [repositories §4](./app/repositories/_ANALYSIS.md) |
| 5 | 数据目录无清理机制 | repositories/ | 低 | [repositories §4](./app/repositories/_ANALYSIS.md) |
| 6 | Checklist 方案演进未文档化 | docs/ | 中 | [docs §4](./docs/plans/_ANALYSIS.md) |
| 7 | Markdown 解析器不处理代码块内标题 | parsers/ | 低 | [parsers §4](./app/parsers/_ANALYSIS.md) |
| 8 | 状态桥接手动维护 | graphs/ | 中 | [graphs §4](./app/graphs/_ANALYSIS.md) |
| 9 | `structure_assembler.py` 可能仍以旧 4 参数签名调用 `attach_expected_results_to_outline` | services/nodes | 中 | [services §3.2.1](./app/services/_ANALYSIS.md) — PR #23 简化了部分调用路径 |
| 10 | `mandatory_skeleton` 桥接字段需手动同步 — 与现有 `template_leaf_targets` 相同的维护成本 | graphs/ | 中 | [graphs §4](./app/graphs/_ANALYSIS.md) |
| 11 | `embedding_dim=1536` 硬编码 — 切换非 OpenAI 模型需手动修改 | knowledge/ | 低 | [knowledge §5](./app/knowledge/_ANALYSIS.md) |

---

> 本索引由分析分支自动生成工具创建。如需更新，请重新执行分析流水线。