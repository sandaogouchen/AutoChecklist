# _INDEX.md — AutoChecklist 代码分析索引

> 分析分支自动生成 · 源分支 `main` · 提交 `88e1848`
>
> **最新同步**: PR #21 `feat/checklist-action-verbs-and-steps-passthrough` — 4 个分析文件更新（services、nodes、tests/unit、本索引）

---

## 项目概况

| 维度 | 值 |
|------|-----|
| 项目名称 | AutoChecklist |
| 定位 | 读取 Markdown PRD → LangGraph 工作流 → 结构化测试用例 |
| 技术栈 | Python 3.11+, FastAPI, LangGraph, OpenAI API, Pydantic v2 |
| 源文件数 | ~80 |
| 分析文档数 | 15 |
| 分析总量 | ~126 KB |

## 架构概览

```
PRD 文本输入
    │
    ▼
┌─────────────────── 主工作流 (GlobalState) ───────────────────┐
│  input_parser → [project_context_loader] → context_research  │
│                                                │              │
│                                                ▼              │
│  ┌────────── 子图 (CaseGenState) ──────────────────────────┐ │
│  │ scenario_planner → checkpoint_generator →                │ │
│  │ checkpoint_evaluator → checkpoint_outline_planner →      │ │
│  │ evidence_mapper → draft_writer → structure_assembler     │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                │              │
│                                                ▼              │
│                          reflection → 最终输出                │
└───────────────────────────────────────────────────────────────┘
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
| [app/graphs/_ANALYSIS.md](./app/graphs/_ANALYSIS.md) | LangGraph 工作流图定义 | 2 | 3.7 KB | ★★★ |
| [app/nodes/_ANALYSIS.md](./app/nodes/_ANALYSIS.md) | 工作流节点（12 个节点） | 12 | 12.2 KB | ★★★ |
| [app/parsers/_ANALYSIS.md](./app/parsers/_ANALYSIS.md) | 文档解析器 | 3 | 3.3 KB | ★★☆ |
| [app/repositories/_ANALYSIS.md](./app/repositories/_ANALYSIS.md) | 数据持久化 | 3 | 3.3 KB | ★★☆ |
| [app/services/_ANALYSIS.md](./app/services/_ANALYSIS.md) | 业务服务层（含 Checklist 核心） | 13 | 43.5 KB | ★★★ |
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
| `app/nodes/draft_writer.py` | 从工厂函数重写为 `DraftWriterNode` 类；系统提示词改为中文路径-步骤衔接规则（4 条）；移除模板继承/场景 fallback/`DraftCaseCollection` |
| `tests/unit/test_attach_expected_results.py` | **新增** 14 个测试用例覆盖重构后的挂载逻辑 |
| `tests/unit/test_xmind_steps_rendering.py` | **新增** 11 个测试用例覆盖 XMind steps 渲染 |

详细分析见：
- [app/services/_ANALYSIS.md §3.2.1](./analysis_docs/app/services/_ANALYSIS.md) — outline planner 重构详情
- [app/nodes/_ANALYSIS.md §3.10.1](./analysis_docs/app/nodes/_ANALYSIS.md) — draft_writer 重写详情
- [tests/unit/_ANALYSIS.md §3.7-§3.8](./analysis_docs/tests/unit/_ANALYSIS.md) — 新增测试文件分析

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
| P0 | PRD 章节锚定 — 用 PRD 标题作为 outline 骨架 | 高 | 低 | [services §5.5](./app/services/_ANALYSIS.md) |
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
                         └───────────────┼──────────────┘
                                         ▼
                                  ┌──────────────┐
                                  │ ChecklistNode │
                                  │   (最终树)    │
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
| 9 | `structure_assembler.py` 可能仍以旧 4 参数签名调用 `attach_expected_results_to_outline` | services/nodes | 高 | [services §3.2.1](./app/services/_ANALYSIS.md) |

---

> 本索引由分析分支自动生成工具创建。如需更新，请重新执行分析流水线。