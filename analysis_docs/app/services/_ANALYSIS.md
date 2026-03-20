# app/services/_ANALYSIS.md — 服务层分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `app/services/` |
| 文件数 | 14 |
| 分析文件 | 13（排除 `__init__.py`） |
| 目录职责 | 业务服务层：Checklist 整合、工作流编排、输出渲染、平台分发 |

本目录是 AutoChecklist 项目的**核心业务逻辑层**，承载了从 checkpoint 输入到最终 checklist 输出的全部服务编排、树结构构建、文本归一化、输出渲染及平台分发能力。其中 Checklist 整合方案（即 checkpoint → 结构化 checklist 树的转换过程）是整个系统质量的关键决定因素。

---

## §2 文件清单

| # | 文件名 | 大小 | 核心类/函数 | 职责摘要 |
|---|--------|------|-------------|----------|
| 1 | `checklist_merger.py` | ~5KB | `ChecklistMerger` | Trie 树合并 NormalizedChecklistPath → ChecklistNode 树 |
| 2 | `checkpoint_outline_planner.py` | ~15KB | `CheckpointOutlinePlanner` | LLM 驱动的 outline 层级规划 + expected_results 挂载 |
| 3 | `semantic_path_normalizer.py` | ~8.5KB | `SemanticPathNormalizer` | LLM 两阶段路径归一化 |
| 4 | `precondition_grouper.py` | ~11.5KB | `PreconditionGrouper` | 基于前置条件关键词的测试用例分桶分组 |
| 5 | `workflow_service.py` | ~13.3KB | `WorkflowService` | 主编排服务：LangGraph 构建 + 迭代执行 + 输出渲染 |
| 6 | `iteration_controller.py` | ~8.6KB | `IterationController` | 多轮评估迭代控制：evaluate_and_decide → IterationDecision |
| 7 | `text_normalizer.py` | ~7.6KB | `normalize_text()` / `normalize_test_case()` | 中英文文本归一化（空白、标点、编码修复） |
| 8 | `markdown_renderer.py` | ~5.3KB | `render_test_cases_markdown()` | Markdown 渲染：扁平列表模式 + 树模式 |
| 9 | `platform_dispatcher.py` | ~5.7KB | `PlatformDispatcher` | 多平台输出分发（markdown / xmind） |
| 10 | `xmind_connector.py` | ~3KB | `XMindConnector` (Protocol) / `FileXMindConnector` | XMind 连接器协议 + 文件实现 |
| 11 | `xmind_delivery_agent.py` | ~3KB | `XMindDeliveryAgent` | XMind 交付代理：防御性错误处理 |
| 12 | `xmind_payload_builder.py` | ~4KB | `XMindPayloadBuilder` | ChecklistNode 树 → XMind topic 树构建 |
| 13 | `project_context_service.py` | ~4KB | `ProjectContextService` | 项目上下文 CRUD（SQLite 持久化） |

---

## §3 逐文件分析

### §3.1 `checklist_merger.py` — ChecklistMerger

**核心类**: `ChecklistMerger`

**职责**: 将一组 `NormalizedChecklistPath` 对象通过 trie 树结构合并为 `ChecklistNode` 层级树。

**关键方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `merge()` | `merge(paths: list[NormalizedChecklistPath]) → list[ChecklistNode]` | 公开入口，调用内部 trie 构建与转换 |
| `_build_trie()` | 内部方法 | 将路径列表插入 trie 数据结构，每个路径段作为一个 trie 节点 |
| `_trie_to_checklist()` | 内部方法 | 将 trie 递归转换为 `ChecklistNode` 树，根据深度分配节点类型 |

**节点类型映射**:
- 深度 0 → `root` 节点
- 中间层 → `group` 节点
- 叶节点 → `expected_result` 节点

**设计特点**:
- 纯算法实现，不依赖 LLM
- 合并质量完全取决于输入路径的归一化质量
- 当路径层级不一致时，trie 可能产生不平衡的树结构

**当前状态**: 属于**方案 A**（已弃用）的组件，与 `SemanticPathNormalizer` 配合使用。

---

### §3.2 `checkpoint_outline_planner.py` — CheckpointOutlinePlanner

**核心类**: `CheckpointOutlinePlanner`

**职责**: 使用 LLM 对 checkpoint 列表进行层级 outline 规划，再将 expected_results 挂载为叶节点，产出完整的 `ChecklistNode` 树。

**关键方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `plan()` | `plan(checkpoints) → list[CanonicalOutlineNode]` | 将 checkpoint 标题/描述输入 LLM，获取结构化的 outline JSON |
| `attach_expected_results_to_outline()` | `(outline_nodes, checkpoints) → list[ChecklistNode]` | 遍历 outline 叶节点，将 checkpoint 的 expected_behaviors 匹配挂载 |
| `_find_group_node()` | 内部 helper | 在树中按名称查找 group 节点，用于 expected_results 的定位挂载 |

**工作流程**:
1. **Step 1 — LLM Outline 规划**: 将所有 checkpoint 的标题组装为 prompt，要求 LLM 返回层级化的 `CanonicalOutlineNode` JSON 数组
2. **Step 2 — Expected Results 挂载**: 遍历 outline 的每个叶节点，根据 checkpoint 的 expected_behaviors 字段匹配并创建 `expected_result` 类型的子节点

**约束与限制**:
- LLM 单次调用处理所有 checkpoints，存在 context window 和规划质量的瓶颈
- outline JSON 解析依赖 LLM 严格遵循格式约定
- expected_results 挂载使用字符串匹配，可能出现漏挂或错挂

**当前状态**: 属于**方案 B**（当前使用）的核心组件。

#### §3.2.1 PR #21 更新 — `feat/checklist-action-verbs-and-steps-passthrough`

> 同步自 PR #21 · 重大重构

**变更概要**: 此文件经历了一次重大重写，涵盖 prompt 改进、签名简化、新 helper 方法和 async 化。

**1. `_OUTLINE_SYSTEM_PROMPT` — 动作动词注入规则**

系统提示词新增中文动作动词（action verbs）注入规则，要求 `display_text` 字段使用规范化的中文动词开头（如"验证"、"检查"、"确认"等），使 outline 节点文本更具可操作性和一致性。

**2. `attach_expected_results_to_outline()` — 签名简化**

| 维度 | 变更前 | 变更后 |
|------|--------|--------|
| 签名 | `(outline_nodes, checkpoints, checkpoint_paths, canonical_outline_nodes)` — 4 参数 | `(optimized_tree, test_cases)` — 2 参数 |
| 匹配源 | 基于 checkpoint 的 expected_behaviors | 基于 test_cases 的结构化数据 |
| 职责 | 遍历 outline 叶节点，字符串匹配 checkpoint | 遍历优化树，将 test_case 数据直接填充到节点 |

**3. 新增 `_fill_node_from_testcase(node, tc)` helper**

填充节点的多个字段：`steps`、`preconditions`、`expected_results`、`priority`、`category`、`evidence_refs`、`test_case_ref`。将原来分散的字段赋值逻辑集中为单一 helper，提升可维护性。

**4. 新增 `_enrich_children(children, tc_map)` 递归充实**

递归遍历子节点树，使用 `tc_map`（test_case 映射字典）逐节点匹配并调用 `_fill_node_from_testcase`。支持任意深度的树结构充实。

**5. 类方法 async 化**

核心方法从同步改为 `async`，与上游 LangGraph 异步执行模型对齐。

**6. 潜在破坏性变更**

> `structure_assembler.py` 中仍以 4 参数形式调用 `attach_expected_results_to_outline()`。签名简化为 2 参数后，若 `structure_assembler.py` 未同步更新，将产生 `TypeError` 运行时错误。需确认 PR #21 是否同步修改了 `structure_assembler.py` 的调用点。

---

### §3.3 `semantic_path_normalizer.py` — SemanticPathNormalizer

**核心类**: `SemanticPathNormalizer`

**职责**: 通过 LLM 两阶段处理，将 checkpoint 的标题和描述归一化为标准的路径形式（`NormalizedChecklistPath`）。

**两阶段流程**:

| 阶段 | 输入 | 输出 | 说明 |
|------|------|------|------|
| Phase 1 — 原始路径提取 | checkpoint 标题 + 描述 | 原始路径字符串列表 | 从非结构化文本中提取层级路径 |
| Phase 2 — 路径归一化 | 原始路径列表 | `NormalizedChecklistPath` 对象列表 | LLM 将路径标准化为统一的命名和层级 |

**输出格式**: `NormalizedChecklistPath` 包含有序的路径段列表，如 `["登录模块", "正常流程", "用户名密码登录"]`

**问题分析**:
- Phase 1 的路径提取高度依赖 checkpoint 描述的质量和格式
- Phase 2 归一化时，LLM 对同义词的统一处理不一致（如"登录"/"登陆"/"Sign In"）
- 两次 LLM 调用增加延迟和成本
- 输出格式不一致导致下游 ChecklistMerger 合并异常

**当前状态**: 属于**方案 A**（已弃用）的组件。

---

### §3.4 `precondition_grouper.py` — PreconditionGrouper

**核心类**: `PreconditionGrouper`

**职责**: 基于测试用例的前置条件（precondition）关键词，将用例分桶并在 `ChecklistNode` 树中插入 `precondition_group` 节点。

**工作机制**:
1. **关键词提取**: 从每个测试用例的 precondition 字段提取中文关键词
2. **相似度匹配**: 使用关键词交集/并集的相似度算法对用例进行分桶
3. **节点插入**: 在 ChecklistNode 树的适当层级插入 `precondition_group` 类型节点，将同组用例聚集为其子节点

**设计特点**:
- 不依赖 LLM，使用纯关键词匹配
- 支持中文分词和关键词提取
- 分组粒度由相似度阈值控制

**局限性**:
- 关键词匹配无法处理语义等价但措辞不同的前置条件（如"用户已登录"vs"登录状态下"）
- 中文分词质量影响关键词提取精度
- 阈值需要人工调优，缺乏自适应能力

**当前状态**: 属于**方案 B**（当前使用）的后处理组件。

---

### §3.5 `workflow_service.py` — WorkflowService

**核心类**: `WorkflowService`

**职责**: 主编排服务，负责构建 LangGraph 子图、执行迭代循环、协调输出渲染。

**关键方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `compile_and_run()` | 主入口方法 | 构建 LangGraph → invoke 执行 → 迭代循环 → 输出渲染 |

**编排流程**:
```
compile_and_run()
  ├── 构建 LangGraph subgraph
  │     ├── checkpoint_outline_planner node
  │     ├── evidence_mapper node
  │     ├── draft_writer node
  │     └── structure_assembler node
  ├── invoke subgraph（含迭代循环）
  │     └── IterationController.evaluate_and_decide()
  └── 输出渲染
        ├── MarkdownRenderer → markdown 文件
        └── PlatformDispatcher → xmind 等
```

**设计特点**:
- 基于 LangGraph 的声明式工作流定义
- 迭代循环由 `IterationController` 控制终止条件
- 输出渲染支持多格式（markdown + xmind）

---

### §3.6 `iteration_controller.py` — IterationController

**核心类**: `IterationController`

**职责**: 管理 checklist 生成的多轮评估迭代，决定是否继续迭代、通过或终止。

**关键方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `evaluate_and_decide()` | → `IterationDecision` | 评估当前轮次结果，返回 pass/retry/abort 决策 |

**返回值**: `IterationDecision` 枚举
- `pass` — 质量达标，终止迭代
- `retry` — 需要改进，进入下一轮
- `abort` — 达到最大轮次或不可恢复错误，终止

**追踪机制**: 使用 `IterationRecords` 记录每轮迭代的评估结果和决策原因，便于调试和回溯。

---

### §3.7 `text_normalizer.py` — 文本归一化

**核心函数**:

| 函数 | 说明 |
|------|------|
| `normalize_text(text: str) → str` | 通用文本归一化：空白字符统一、中英文标点标准化、编码修复 |
| `normalize_test_case(case: TestCase) → TestCase` | 将归一化应用到 TestCase 的各字段（标题、步骤、预期结果等） |

**处理内容**:
- 全角/半角标点统一
- 多余空白字符压缩
- 中英文混排间距标准化
- Unicode 编码异常修复
- 首尾空白去除

**作用**: 确保下游处理（LLM 输入、关键词提取、字符串匹配）不受文本格式差异干扰。

---

### §3.8 `markdown_renderer.py` — Markdown 渲染

**核心函数**: `render_test_cases_markdown()`

**两种渲染模式**:

| 模式 | 输入 | 输出 | 说明 |
|------|------|------|------|
| 扁平列表模式 | `list[TestCase]` | Markdown 表格或列表 | 简单的编号列表输出 |
| 树模式 | `list[ChecklistNode]` | 层级 Markdown 标题 | 按 ChecklistNode 树结构渲染多级标题和子项 |

**树模式渲染规则**:
- `root` 节点 → `#` 一级标题
- `group` 节点 → `##`/`###` 等对应层级标题
- `expected_result` 叶节点 → 列表项
- TestCase 内容嵌套在叶节点下方

---

### §3.9 `platform_dispatcher.py` — PlatformDispatcher

**核心类**: `PlatformDispatcher`

**职责**: 根据配置将生成结果分发到不同输出平台。

**支持的输出**:
- **Markdown**: 调用 `MarkdownRenderer` 生成 `.md` 文件
- **XMind**: 通过 `XMindPayloadBuilder` → `XMindDeliveryAgent` → `XMindConnector` 链路生成 `.xmind` 文件

**设计特点**:
- 基于策略模式，便于扩展新的输出格式
- 输出格式可通过配置独立开关

---

### §3.10 `xmind_connector.py` — XMind 连接器

**核心定义**:
- `XMindConnector` — Protocol（接口协议），定义 XMind 输出的标准契约
- `FileXMindConnector` — 基于文件系统的实现，将 XMind 数据写入本地 `.xmind` 文件

**设计特点**: Protocol-based 设计，支持替换为网络上传或其他 XMind 后端实现。

---

### §3.11 `xmind_delivery_agent.py` — XMind 交付代理

**核心类**: `XMindDeliveryAgent`

**职责**: 封装 XMind 交付过程的防御性错误处理，确保 XMind 输出失败不会导致整体流程崩溃。

**错误处理策略**:
- 捕获并记录所有 XMind 相关异常
- 失败时回退到仅 Markdown 输出
- 提供详细的错误日志便于排查

---

### §3.12 `xmind_payload_builder.py` — XMind Payload 构建

**核心类**: `XMindPayloadBuilder`

**职责**: 将 `ChecklistNode` 树转换为 XMind 的 topic 树数据结构。

**转换规则**:
- `ChecklistNode` → XMind Topic
- 子节点递归转换为子 Topic
- 支持 checkpoint fallback：当 ChecklistNode 树不完整时，直接从 checkpoint 数据构建 topic

**Checkpoint Fallback**: 当主流程的树结构构建失败时，可绕过 outline 直接从原始 checkpoint 构建扁平的 XMind 结构。

---

### §3.13 `project_context_service.py` — 项目上下文服务

**核心类**: `ProjectContextService`

**职责**: 项目上下文的 CRUD 操作，通过 SQLite 持久化存储。

**功能**:
- 创建/更新项目上下文
- 查询项目上下文
- 删除项目上下文

**用途**: 在多轮对话或跨会话场景下保持项目级别的配置和状态。

---

## §4 服务依赖图

### §4.1 调用链全景

```
┌──────────────────────────────────────────────────────────────────┐
│                      WorkflowService                             │
│                    (主编排 · LangGraph)                           │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                    │
│  │ IterationController│   │ ProjectContext   │                    │
│  │  (迭代控制)        │   │   Service        │                    │
│  └────────┬─────────┘    └──────────────────┘                    │
│           │                                                      │
│  ┌────────▼──────────────────────────────────────┐               │
│  │            LangGraph Subgraph Nodes            │              │
│  │                                                │              │
│  │  ┌─────────────────────┐  ┌────────────────┐  │              │
│  │  │ CheckpointOutline   │  │ EvidenceMapper │  │              │
│  │  │ Planner (方案 B)    │  │   (graph 层)    │  │              │
│  │  └────────┬────────────┘  └────────────────┘  │              │
│  │           │                                    │              │
│  │  ┌────────▼────────────┐  ┌────────────────┐  │              │
│  │  │ PreconditionGrouper │  │  DraftWriter   │  │              │
│  │  │  (前置条件分组)      │  │  (graph 层)    │  │              │
│  │  └────────┬────────────┘  └────────────────┘  │              │
│  │           │                                    │              │
│  │  ┌────────▼────────────────────────────────┐   │              │
│  │  │       StructureAssembler (graph 层)     │   │              │
│  │  └────────┬────────────────────────────────┘   │              │
│  └───────────┼────────────────────────────────────┘              │
│              │                                                   │
│  ┌───────────▼───────────────────────────────────────┐           │
│  │              PlatformDispatcher                    │           │
│  │                                                    │           │
│  │  ┌──────────────────┐  ┌────────────────────────┐ │           │
│  │  │ MarkdownRenderer │  │ XMindPayloadBuilder    │ │           │
│  │  └──────────────────┘  └──────────┬─────────────┘ │           │
│  │                                   │                │           │
│  │                        ┌──────────▼─────────────┐ │           │
│  │                        │ XMindDeliveryAgent     │ │           │
│  │                        └──────────┬─────────────┘ │           │
│  │                                   │                │           │
│  │                        ┌──────────▼─────────────┐ │           │
│  │                        │ FileXMindConnector     │ │           │
│  │                        └────────────────────────┘ │           │
│  └────────────────────────────────────────────────────┘           │
│                                                                  │
│  ┌───────────────────────────────────────────────────┐           │
│  │  TextNormalizer (横切关注点 · 各节点均可调用)       │           │
│  └───────────────────────────────────────────────────┘           │
│                                                                  │
│  ══════════════ 已弃用组件（方案 A）══════════════               │
│  ┌─────────────────────┐  ┌──────────────────┐                   │
│  │ SemanticPath         │→│ ChecklistMerger  │                   │
│  │ Normalizer           │  │  (trie 合并)     │                   │
│  └─────────────────────┘  └──────────────────┘                   │
└──────────────────────────────────────────────────────────────────┘
```

### §4.2 数据流向

```
Checkpoints (输入)
    │
    ▼
CheckpointOutlinePlanner.plan()
    │  LLM → CanonicalOutlineNode JSON
    ▼
attach_expected_results_to_outline()
    │  checkpoint.expected_behaviors → 叶节点
    ▼
PreconditionGrouper
    │  关键词分桶 → precondition_group 节点插入
    ▼
ChecklistNode 树 (核心中间数据结构)
    │
    ├──→ MarkdownRenderer → .md 文件
    └──→ XMindPayloadBuilder → XMindDeliveryAgent → .xmind 文件
```

### §4.3 横切依赖

| 服务 | 被依赖者 | 说明 |
|------|---------|------|
| `TextNormalizer` | 几乎所有节点 | 文本归一化作为预处理步骤被广泛调用 |
| `ProjectContextService` | `WorkflowService` | 提供项目级配置上下文 |
| `IterationController` | `WorkflowService` | 控制迭代循环的终止条件 |

---

## §5 Checklist 整合方案深度分析

> **这是整个分析的核心部分。** Checklist 整合——即将散乱的 checkpoint 列表转化为结构清晰、层级合理的 checklist 树——是 AutoChecklist 系统最关键、也是当前效果最需提升的环节。以下从架构、代码路径、问题根因、改进方向四个维度展开深入分析。

---

### §5.1 现有方案架构

当前系统中存在**两套并行的 Checklist 整合方案**，方案 A 已弃用但代码仍保留，方案 B 为当前生产路径。

#### 方案 A（已弃用）: SemanticPathNormalizer → ChecklistMerger

**设计思路**: 先归一化，后合并。将每个 checkpoint 的语义信息提取为标准化路径，再通过 trie 树结构自动合并为层级树。

**流程**:
```
Checkpoints
    │
    ▼
SemanticPathNormalizer
    │  Phase 1: 从 title + description 提取原始路径
    │  Phase 2: LLM 将原始路径归一化为标准形式
    ▼
list[NormalizedChecklistPath]
    │  例: ["登录模块", "正常流程", "用户名密码登录"]
    │      ["登录模块", "正常流程", "手机号验证码登录"]
    │      ["登录模块", "异常流程", "密码错误"]
    ▼
ChecklistMerger._build_trie()
    │  将路径段逐层插入 trie 节点
    ▼
ChecklistMerger._trie_to_checklist()
    │  trie 递归转换为 ChecklistNode 树
    ▼
list[ChecklistNode]
```

**优点**:
- 路径归一化的抽象层次正确：将非结构化的 checkpoint 信息转化为结构化路径是合理的中间表示
- Trie 合并是确定性算法，可预测、可调试
- 路径粒度可控：通过控制路径段数量来控制树的深度

**弃用原因**:
1. **路径归一化质量不稳定**: LLM 对不同 checkpoint 生成的路径层级深度不一致（有的 2 层，有的 5 层），导致 trie 树极度不平衡
2. **LLM 输出格式不一致**: Phase 2 的归一化结果偶发性地不遵循约定格式（如混入自然语言描述而非纯路径），导致解析失败
3. **同义词统一困难**: "登录"/"登陆"/"Sign In"/"用户认证" 等语义等价的路径段被 trie 视为不同分支，产生冗余
4. **Trie 合并产生过深/过浅的层级**: 缺乏全局视角，纯局部合并容易产生退化的树结构（如单链退化或根节点下直接挂叶子）

---

#### 方案 B（当前使用）: CheckpointOutlinePlanner → PreconditionGrouper

**设计思路**: 先规划整体骨架，后挂载叶节点。用 LLM 一次性理解所有 checkpoint 并生成层级 outline，再将具体的 expected_results 挂载到 outline 叶节点。

**流程**:
```
Checkpoints
    │
    ▼
CheckpointOutlinePlanner.plan(checkpoints)
    │  将所有 checkpoint 标题组装为 prompt
    │  LLM 返回 CanonicalOutlineNode JSON
    │  ┌──────────────────────────────────┐
    │  │ CanonicalOutlineNode 结构:        │
    │  │   name: "登录功能"                │
    │  │   children:                       │
    │  │     - name: "正常登录"             │
    │  │       children:                   │
    │  │         - name: "用户名密码"       │
    │  │         - name: "手机号验证码"     │
    │  │     - name: "异常登录"             │
    │  │       children:                   │
    │  │         - name: "密码错误"         │
    │  └──────────────────────────────────┘
    ▼
attach_expected_results_to_outline(outline_nodes, checkpoints)
    │  遍历 outline 叶节点
    │  对每个叶节点：
    │    1. 在 checkpoints 中查找匹配的 checkpoint
    │    2. 将 checkpoint.expected_behaviors 作为 expected_result 子节点挂载
    ▼
ChecklistNode 树 (含 expected_result 叶节点)
    │
    ▼
PreconditionGrouper
    │  遍历树中的 expected_result 节点
    │  提取关联 TestCase 的 precondition 字段
    │  基于中文关键词的相似度进行分桶
    │  在原层级中插入 precondition_group 节点
    ▼
最终 ChecklistNode 树
```

**优点**:
- LLM 具有全局视角，能理解 checkpoint 之间的逻辑关系
- 一次调用产出完整的层级结构，避免了逐个路径合并的碎片化问题
- PreconditionGrouper 补充了按前置条件的横切分组维度

**现存问题** (详见 §5.3):
1. LLM 单次处理大量 checkpoint 时层级规划质量下降
2. PreconditionGrouper 使用关键词匹配而非语义理解，分组精度有限
3. expected_results 挂载是简单的字符串匹配，可能遗漏或错配
4. 缺乏对 outline 质量的自动评估和反馈机制

---

### §5.2 关键代码路径分析

#### §5.2.1 主流程调用链

以下为从 `WorkflowService` 入口到最终 ChecklistNode 树产出的完整代码路径：

```
WorkflowService.compile_and_run()
  │
  ├── 1. 构建 LangGraph subgraph
  │     └── 定义节点: outline_planner → evidence_mapper → draft_writer → structure_assembler
  │
  ├── 2. invoke subgraph（迭代执行）
  │     │
  │     ├── [Node] checkpoint_outline_planner
  │     │     │
  │     │     ├── CheckpointOutlinePlanner.plan(checkpoints)
  │     │     │     ├── 组装 prompt: checkpoint 标题列表 + 层级规划指令
  │     │     │     ├── LLM 调用: → JSON 响应
  │     │     │     ├── JSON 解析: → list[CanonicalOutlineNode]
  │     │     │     └── 返回 outline 骨架
  │     │     │
  │     │     └── attach_expected_results_to_outline(outline, checkpoints)
  │     │           ├── 遍历 outline 叶节点
  │     │           ├── 对每个叶节点:
  │     │           │     ├── 在 checkpoints 中按名称查找匹配项
  │     │           │     ├── 提取 checkpoint.expected_behaviors
  │     │           │     └── 创建 expected_result 子节点挂载
  │     │           └── 返回 list[ChecklistNode]（含 expected_result 叶节点）
  │     │
  │     ├── [Node] evidence_mapper
  │     │     └── 将 evidence 映射到 ChecklistNode 节点（graph 层实现）
  │     │
  │     ├── [Node] draft_writer
  │     │     ├── _resolve_path_context(optimized_tree)
  │     │     │     └── 为每个叶节点注入完整的层级路径上下文
  │     │     │         例: "登录功能 > 正常登录 > 用户名密码"
  │     │     └── LLM 调用: 基于路径上下文 + evidence 生成 TestCase
  │     │
  │     └── [Node] structure_assembler
  │           ├── 收集所有 draft_writer 产出的 TestCase
  │           ├── attach_expected_results_to_outline()  ← 再次调用，最终版本
  │           │     └── 将最终的 TestCase 挂载到 ChecklistNode 树
  │           └── PreconditionGrouper 后处理
  │                 ├── 提取各 TestCase 的 precondition 字段
  │                 ├── 中文关键词提取
  │                 ├── 关键词相似度分桶
  │                 └── 插入 precondition_group 节点
  │
  ├── 3. IterationController.evaluate_and_decide()
  │     ├── 评估当前轮次的 ChecklistNode 树质量
  │     └── 返回 IterationDecision: pass / retry / abort
  │
  └── 4. 输出渲染
        ├── MarkdownRenderer → render_test_cases_markdown(tree_mode)
        └── PlatformDispatcher
              └── XMindPayloadBuilder → XMindDeliveryAgent → FileXMindConnector
```

#### §5.2.2 关键数据变换节点

| 变换节点 | 输入 | 输出 | 变换类型 |
|----------|------|------|----------|
| `plan()` | `list[Checkpoint]` | `list[CanonicalOutlineNode]` | LLM 生成（非确定性） |
| `attach_expected_results` | `outline + checkpoints` | `list[ChecklistNode]` | 规则匹配（确定性） |
| `_resolve_path_context` | `ChecklistNode tree` | 带路径上下文的树 | 树遍历（确定性） |
| `draft_writer LLM` | 路径上下文 + evidence | `list[TestCase]` | LLM 生成（非确定性） |
| `PreconditionGrouper` | `ChecklistNode tree` | 增强的树（含分组节点） | 关键词匹配（确定性） |

#### §5.2.3 `attach_expected_results_to_outline` 匹配逻辑详解

这是连接 outline 骨架和 checkpoint 实际内容的桥梁，匹配逻辑的精度直接影响最终 checklist 的完整性：

```
对每个 outline 叶节点 leaf:
  1. 在 checkpoints 中查找 checkpoint.title 包含 leaf.name 的匹配项
     或 leaf.name 包含 checkpoint.title 的匹配项
  2. 如果找到匹配:
     - 遍历 checkpoint.expected_behaviors
     - 为每个 expected_behavior 创建一个 expected_result 类型的 ChecklistNode
     - 作为 leaf 的子节点挂载
  3. 如果未找到匹配:
     - leaf 保持无子节点（空叶节点）
     - 后续可能被 draft_writer 兜底处理
```

**匹配失败的典型场景**:
- LLM outline 中使用了概括性名称（如"登录验证"），而 checkpoint 标题是具体描述（如"使用正确的用户名和密码登录系统"）
- 一个 checkpoint 的 expected_behaviors 应该分散到多个 outline 叶节点下，但当前是一对一匹配
- 多个 checkpoint 的 expected_behaviors 有重叠，导致同一条 expected_result 出现在多个叶节点下

---

### §5.3 效果不佳的根本原因分析

#### §5.3.1 单次 LLM 规划的信息瓶颈

**问题描述**: `CheckpointOutlinePlanner.plan()` 将所有 checkpoint 的标题一次性输入 LLM，要求其返回完整的层级 outline。

**影响**:
- 当 checkpoint 数量超过 **20-30 个**时，LLM 的注意力分散，产生的层级结构趋于扁平（大量节点直接挂在根下）或过度嵌套（不必要的中间层级）
- checkpoint 之间的微妙逻辑关系（如"登录→权限→操作"的因果链）在大量输入中被淹没
- LLM 倾向于按表面词汇相似度而非业务逻辑进行分组

**量化表现**:
- 10 个以下 checkpoint: outline 质量通常可接受
- 10-30 个 checkpoint: 质量不稳定，部分层级合理、部分混乱
- 30 个以上 checkpoint: 质量显著下降，常出现"杂项"/"其他"兜底分组

**根因**: 单次 LLM 调用缺乏分治机制，将 O(n) 复杂度的结构化任务压缩为单次推理。

---

#### §5.3.2 缺乏领域知识锚定

**问题描述**: outline 规划完全依赖 LLM 的通用知识，未利用已有的结构化信息（如 PRD 原文的章节结构、PlannedScenario 的分组信息）作为锚点。

**影响**:
- LLM "发明"的层级结构可能与 PRD 的实际模块划分不一致
- 同一组 checkpoint 在不同运行中可能产生不同的 outline 结构（非幂等性）
- 缺乏业务约束导致 LLM 可能按技术维度（如"前端测试"/"后端测试"）而非业务维度（如"用户管理"/"订单管理"）分组

**根因**: prompt 中缺少结构化的领域锚点信息，LLM 只能依靠 checkpoint 标题的文本特征进行推理。

---

#### §5.3.3 前置条件分组过于机械

**问题描述**: `PreconditionGrouper` 基于中文关键词的桶分配策略，使用关键词交集/并集比值作为相似度指标。

**典型失败案例**:

| 前置条件 A | 前置条件 B | 实际关系 | 系统判断 |
|-----------|-----------|---------|----------|
| "用户已登录" | "登录状态下" | 语义等价 | **未分为同组**（关键词不同） |
| "用户已登录" | "用户已登录且为 VIP" | 包含关系 | 可能同组或不同组（取决于阈值） |
| "已创建订单" | "订单已存在" | 语义等价 | **未分为同组**（关键词不同） |
| "网络正常" | "网络连接正常" | 语义等价 | 可能同组（共享"网络"关键词） |

**根因**: 关键词匹配只能捕获词汇级别的相似性，无法理解语义级别的等价关系。中文的表达灵活性使得同义异构的情况极为普遍。

---

#### §5.3.4 expected_results 挂载逻辑脆弱

**问题描述**: `attach_expected_results_to_outline()` 使用名称包含关系进行匹配，这种简单的字符串匹配策略存在多种失败模式。

**失败模式分析**:

| 失败模式 | 描述 | 频率 |
|---------|------|------|
| **遗漏** | checkpoint 标题与 outline 叶节点名称无交集，导致 expected_results 未被挂载 | 高 |
| **错配** | 包含关系匹配到错误的叶节点（如"登录"匹配到"登录日志"而非"用户登录"） | 中 |
| **重复** | 一个 checkpoint 的 expected_results 被挂载到多个匹配的叶节点 | 中 |
| **空叶节点** | outline 叶节点未匹配到任何 checkpoint，成为空壳 | 高 |

**多对多关系问题**: 现实中 checkpoint 与 outline 叶节点之间是多对多关系：
- 一个 checkpoint 可能涉及多个功能模块（应拆分到多个叶节点）
- 一个 outline 叶节点可能对应多个 checkpoint 的 expected_results（应聚合）

当前的一对一匹配模型无法处理这种关系。

---

#### §5.3.5 缺乏反馈循环

**问题描述**: outline 生成后没有质量验证环节。`IterationController` 的评估粒度在最终 TestCase 层面，而非 outline 结构层面。

**影响**:
- outline 结构缺陷（如遗漏模块、层级混乱）会无声地传播到下游
- draft_writer 在有缺陷的 outline 上生成 TestCase，质量受限但不报错
- 迭代控制器可能将 outline 结构问题误判为 TestCase 质量问题，导致无效的重试

**根因**: 评估体系缺少 outline 层面的质量指标，如覆盖率（outline 是否涵盖所有 checkpoint）、平衡度（层级深度分布是否合理）、一致性（命名风格是否统一）。

---

### §5.4 方案 A 与方案 B 的对比总结

| 维度 | 方案 A (弃用) | 方案 B (当前) |
|------|-------------|-------------|
| **核心思路** | 自底向上：路径归一化 → trie 合并 | 自顶向下：LLM 整体规划 → 叶节点挂载 |
| **LLM 使用** | 两次（路径提取 + 归一化） | 一次（outline 规划） |
| **确定性** | 合并步骤确定性，归一化非确定性 | 规划非确定性，挂载确定性 |
| **可调试性** | 中（可检查中间路径） | 低（outline 为黑盒输出） |
| **扩展性** | 路径数量增长时 trie 性能稳定 | checkpoint 数量增长时 LLM 质量下降 |
| **层级合理性** | 差（取决于路径归一化质量） | 中（取决于 LLM 理解深度） |
| **覆盖完整性** | 高（每个 checkpoint 必有路径） | 中（可能遗漏未匹配的 checkpoint） |
| **弃用/选用原因** | 路径归一化质量不稳定 | LLM 全局视角优于局部合并 |

**关键洞察**: 两套方案各有优劣，**混合使用可能优于任一单独方案**。方案 A 的路径归一化提供了结构化的中间表示，方案 B 的 LLM 规划提供了全局视角。

---

### §5.5 改进建议

#### 短期改进（Low-hanging Fruit · 1-2 周）

##### 建议 1: PRD 章节锚定

**思路**: 将 PRD 的一级/二级标题作为 outline 的顶层结构骨架，LLM 只需填充细分层级。

**实施方式**:
```
当前 prompt:
  "根据以下 checkpoint 列表，生成层级化的 outline..."

改进 prompt:
  "以下是 PRD 的章节结构：
   1. 用户管理
      1.1 注册
      1.2 登录
   2. 订单管理
      2.1 创建订单
      2.2 支付
   请将以下 checkpoint 分配到对应的 PRD 章节下，并在需要时创建子层级..."
```

**预期效果**: outline 的顶层结构与 PRD 对齐，LLM 的规划空间减小，输出质量提升。

**风险**: 需要确保 PRD 章节信息可用且格式可解析。

---

##### 建议 2: 分批规划

**思路**: 将 checkpoints 按已有的 `PlannedScenario` 分组，每组独立调用 LLM 规划子 outline，最后合并。

**实施方式**:
```python
def plan_batched(self, checkpoints, scenarios):
    sub_outlines = []
    for scenario in scenarios:
        scenario_cps = [cp for cp in checkpoints if cp.scenario_id == scenario.id]
        sub_outline = self.plan(scenario_cps)  # 小规模调用
        sub_outlines.append((scenario.name, sub_outline))
    return self._merge_sub_outlines(sub_outlines)
```

**预期效果**: 每次 LLM 调用处理的 checkpoint 数量可控（通常 < 10），规划质量稳定。

**风险**: 需要处理跨 scenario 的 checkpoint 以及子 outline 合并时的命名冲突。

---

##### 建议 3: PreconditionGrouper 升级

**思路**: 引入 embedding 向量计算语义相似度，替代纯关键词匹配。

**实施方式**:
```python
# 当前: 关键词交集/并集
similarity = len(kw_a & kw_b) / len(kw_a | kw_b)

# 改进: embedding cosine similarity
embedding_a = embed_model.encode(precondition_a)
embedding_b = embed_model.encode(precondition_b)
similarity = cosine_similarity(embedding_a, embedding_b)
```

**预期效果**: "用户已登录" 和 "登录状态下" 能被正确识别为语义等价。

**风险**: 增加 embedding 模型依赖和调用延迟。可考虑使用轻量级本地模型（如 text2vec-chinese）。

---

#### 中期改进（架构调整 · 2-4 周）

##### 建议 4: 恢复并改进方案 A

**思路**: `SemanticPathNormalizer` 的两阶段归一化思路正确，弃用的原因在于执行质量而非设计方向。通过以下改进可显著提升质量：

**改进项**:

| 改进 | 当前问题 | 解决方案 |
|------|---------|----------|
| Few-shot 示例 | LLM 输出格式不稳定 | 提供 10+ 高质量的路径归一化示例，覆盖各种边界情况 |
| 路径验证步骤 | 生成的路径可能不合理 | 增加后置验证：层级深度 2-5、段名长度 2-20 字、无重复段 |
| 同义词词典 | "登录"/"登陆" 等不统一 | 维护领域同义词表，在归一化后统一替换 |
| Trie 深度限制 | 树可能过深 | `ChecklistMerger` 增加 max_depth 参数，超深路径自动截断 |
| 节点合并策略 | 相似节点未合并 | 在 trie 构建后增加相似节点合并步骤（编辑距离 < 阈值的兄弟节点合并） |

---

##### 建议 5: 混合方案 (A+B)

**思路**: 结合方案 A 的结构化路径和方案 B 的 LLM 全局规划，取长补短。

**流程设计**:
```
Phase 1 — 路径预处理（方案 A 改进版）:
  checkpoints → SemanticPathNormalizer (改进版) → NormalizedChecklistPath 列表

Phase 2 — LLM 精调（方案 B 适配版）:
  将归一化路径列表输入 LLM，要求其：
  1. 审查路径的合理性（修正不合理的归一化结果）
  2. 补充缺失的中间层级
  3. 统一命名风格
  → 输出修正后的路径列表

Phase 3 — 确定性合并:
  修正后的路径 → ChecklistMerger (增强版) → ChecklistNode 树

Phase 4 — 后处理:
  → PreconditionGrouper (embedding 版) → 最终 ChecklistNode 树
```

**优势**: LLM 的工作从"从零生成 outline"降级为"审查和修正已有路径"，任务难度显著降低，输出质量更可控。

---

##### 建议 6: 增加 Outline 评估节点

**思路**: 在 outline 生成后、TestCase 生成前，增加一个专门的评估节点，检查 outline 的结构质量。

**评估指标**:

| 指标 | 计算方式 | 合格阈值 |
|------|---------|----------|
| **覆盖率** | 已匹配 checkpoint 数 / 总 checkpoint 数 | >= 0.95 |
| **平衡度** | std(各子树叶节点数) / mean(各子树叶节点数) | <= 1.5 |
| **深度合理性** | max_depth / log2(叶节点数) | 0.5 - 3.0 |
| **空叶节点率** | 无子节点的叶节点数 / 总叶节点数 | <= 0.1 |
| **命名一致性** | 同层节点命名风格相似度 | >= 0.7 |

**不合格时的处理**:
- 覆盖率不足 → 找到未匹配的 checkpoint，追加为新叶节点
- 平衡度失衡 → 将过大的子树拆分，过小的子树合并
- 深度不合理 → 压缩过深路径或展开过浅路径

---

#### 长期改进（能力升级 · 1-3 个月）

##### 建议 7: 多轮迭代 Outline

**思路**: 借鉴当前 TestCase 生成的 `IterationController` 迭代评估循环，对 outline 也实施多轮优化。

**迭代流程**:
```
Round 1: LLM 生成初始 outline → 评估节点打分
  → 如果不合格:
Round 2: 将评估结果 + 初始 outline 反馈给 LLM → 修正版 outline → 评估
  → 如果不合格:
Round 3: 进一步修正 → 评估
  → 最多 N 轮后 abort（使用最高分版本）
```

**关键设计**: 每轮迭代的 prompt 需要明确指出上轮的问题所在（如"以下 5 个 checkpoint 未被覆盖"），避免 LLM 盲目修改。

---

##### 建议 8: 用户反馈闭环

**思路**: 记录用户对生成的 outline/checklist 的手动修改，作为后续规划的参考信号。

**数据收集**:
- 用户在 XMind 中调整的节点移动/重命名/删除/新增操作
- 用户对 Markdown checklist 的编辑 diff
- 显式的满意度评分

**应用方式**:
- 构建"项目类型 → 常用 outline 模板"的映射
- 将用户修改频率最高的节点作为 few-shot 负例
- 训练轻量级的 outline 质量预测模型

---

##### 建议 9: 结构化知识库

**思路**: 构建测试场景的标准分类体系，作为 outline 规划的参考模板。

**知识库结构**:
```
测试场景分类体系:
├── 功能测试
│   ├── 用户管理 (注册/登录/权限/个人信息)
│   ├── 核心业务流程 (按行业/产品类型细分)
│   ├── 数据管理 (CRUD/导入导出/搜索过滤)
│   └── 系统集成 (第三方API/消息队列/文件系统)
├── 非功能测试
│   ├── 性能 (响应时间/并发/容量)
│   ├── 安全 (认证/授权/输入验证/数据加密)
│   └── 兼容性 (浏览器/设备/操作系统)
└── 边界与异常
    ├── 输入边界 (空值/极值/特殊字符)
    ├── 状态异常 (网络断开/超时/并发冲突)
    └── 数据异常 (格式错误/缺失字段/重复数据)
```

**应用**: 在 outline 规划时，LLM 可参考知识库中的标准分类，确保覆盖常见的测试维度，同时保持与具体产品特性的适配。

---

### §5.6 优先级排序与实施路线图

| 优先级 | 建议 | 预期收益 | 实施成本 | 风险 |
|--------|------|---------|---------|------|
| **P0** | 建议 1: PRD 章节锚定 | 高 — outline 顶层结构稳定 | 低 — 仅修改 prompt | 低 |
| **P0** | 建议 2: 分批规划 | 高 — 解决大规模 checkpoint 问题 | 低 — 增加循环逻辑 | 中 — 需处理跨组边界 |
| **P1** | 建议 6: Outline 评估节点 | 高 — 提前拦截结构缺陷 | 中 — 新增评估逻辑 | 低 |
| **P1** | 建议 3: PreconditionGrouper 升级 | 中 — 分组精度提升 | 中 — 引入 embedding 模型 | 低 |
| **P2** | 建议 5: 混合方案 (A+B) | 高 — 综合两套方案优势 | 高 — 重构整合流程 | 中 — 复杂度增加 |
| **P2** | 建议 4: 恢复改进方案 A | 中 — 恢复结构化中间表示 | 中 — 改进现有代码 | 中 — 方案 A 曾失败 |
| **P3** | 建议 7: 多轮迭代 Outline | 高 — 系统性质量提升 | 高 — 新增迭代框架 | 中 — 增加延迟和成本 |
| **P3** | 建议 8: 用户反馈闭环 | 长期高 — 持续改进 | 高 — 需要前端配合 | 低 |
| **P3** | 建议 9: 结构化知识库 | 长期高 — 标准化能力 | 高 — 需要领域专家参与 | 中 — 维护成本 |

**推荐实施顺序**: P0 建议 1 + 2 → P1 建议 6 → P1 建议 3 → P2 建议 5 → P3 建议 7-9

---

*分析完成 · 服务层 13 个文件 · 重点: Checklist 整合方案深度分析*