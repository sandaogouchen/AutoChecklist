# app/services/_ANALYSIS.md — 服务层分析
> 分析分支自动生成 · 源分支 `main`
---
## §1 目录概述
| 维度 | 值 |
|------|-----|
| 路径 | `app/services/` |
| 文件数 | 15 |
| 分析文件 | 14（排除 `__init__.py`）— PR #23 新增 `mandatory_skeleton_builder.py` |
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
│ ┌──────────────────────────────────┐ │
│ │ MandatorySkeletonBuilder │ ← PR #23 新增 │
│ │ (强制骨架构建) │ │
│ └────────────┬─────────────────────┘ │
│ │ 被 ProjectTemplateLoader 调用 │
| 7 | `text_normalizer.py` | ~7.6KB | `normalize_text()` / `normalize_test_case()` | 中英文文本归一化（空白、标点、编码修复） |
| 8 | `markdown_renderer.py` | ~5.3KB | `render_test_cases_markdown()` | Markdown 渲染：扁平列表模式 + 树模式 |
| 9 | `platform_dispatcher.py` | ~5.7KB | `PlatformDispatcher` | 多平台输出分发（markdown / xmind） |
| 10 | `xmind_connector.py` | ~3KB | `XMindConnector` (Protocol) / `FileXMindConnector` | XMind 连接器协议 + 文件实现 |
| 11 | `xmind_delivery_agent.py` | ~3KB | `XMindDeliveryAgent` | XMind 交付代理：防御性错误处理 |
| 12 | `xmind_payload_builder.py` | ~4KB | `XMindPayloadBuilder` | ChecklistNode 树 → XMind topic 树构建 |
| 13 | `project_context_service.py` | ~4KB | `ProjectContextService` | 项目上下文 CRUD（SQLite 持久化） |
| 14 | `template_loader.py` | ~10KB | `ProjectTemplateLoader` | 模版加载/校验/拍平/强制骨架构建（PR #23 增强：`load_by_name()`、`build_mandatory_skeleton()`、增强 `_parse_node()`、`_get_max_depth()`） |
| 15 | `mandatory_skeleton_builder.py` | ~5KB | `MandatorySkeletonBuilder` | **[PR #23 新增]** 从模版提取强制节点，构建强制骨架树（MandatorySkeletonNode） |
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
---
**PR #23 变更 — 强制骨架约束注入：**
PR #23 对 `CheckpointOutlinePlanner` 进行了重大增强，引入双重约束机制确保 LLM 输出遵循模版强制骨架。
**新增方法：**
| 方法 | 签名 | 说明 |
|------|------|------|
| `_build_mandatory_constraint_prompt()` | `(skeleton: MandatorySkeletonNode) → str` | 将强制骨架序列化为约束 prompt 文本 |
| `_serialize_skeleton()` | `(node, indent) → str` | 递归将骨架节点序列化为缩进文本，`[MANDATORY]` 标记强制节点 |
| `_enforce_mandatory_skeleton()` | `(optimized_tree, skeleton) → list[ChecklistNode]` | 后处理修复：以骨架为 ground truth 合并 LLM 输出 |
| `_merge_skeleton_node()` | `(skeleton_node, llm_lookup) → ChecklistNode` | 将单个骨架节点与 LLM 对应节点合并 |
| `_index_nodes()` | `(node, lookup) → None` | 递归索引 ChecklistNode 树 |
| `_collect_skeleton_ids()` | `(node) → set[str]` | 收集骨架中所有节点 ID |
**plan() 方法变更：**
- 签名新增可选参数：`mandatory_skeleton: MandatorySkeletonNode | None = None`
- 当 `mandatory_skeleton` 非 None 时：
  1. **软约束注入**：在 `_OUTLINE_SYSTEM_PROMPT` 和 `_PATH_SYSTEM_PROMPT` 末尾追加 `_MANDATORY_CONSTRAINT_TEMPLATE`
  2. **硬约束后处理**：LLM 输出后调用 `_enforce_mandatory_skeleton()` 修复
**新增 prompt 模版 — `_MANDATORY_CONSTRAINT_TEMPLATE`：**
```
## 强制模版约束
以下是本次生成必须严格遵循的模版骨架结构。标记为 [MANDATORY] 的节点是强制节点，
你不可以增加、删除、修改或重命名这些节点。
强制骨架：
{skeleton_text}
约束规则：
1. 强制层级的节点必须与上述骨架完全一致
2. 所有 checkpoint 必须被分配到上述骨架节点的某个子路径下
3. 在非强制层级，你可以自由创建子节点来进一步组织 checkpoint
4. 输出的 JSON 中，强制节点必须保留原始 id 和 title，不可更改
```
**`_enforce_mandatory_skeleton()` 后处理策略：**
```
输入: LLM 生成的 optimized_tree + 强制骨架 skeleton
│
├── 1. 建立 LLM 树的 node_id → ChecklistNode 索引
│
├── 2. 遍历骨架的每个顶层子节点:
│   └── _merge_skeleton_node(): 递归合并
│       ├── 查找 LLM 树中的对应节点
│       ├── 保留骨架的 id + title (不可变)
│       ├── 递归处理子骨架节点
│       └── 保留 LLM 为该节点生成的非骨架子节点
│
├── 3. 收集未被骨架覆盖的 LLM 节点
│   └── 追加到结果列表（非强制层级的额外节点）
│
└── 返回: 合并后的 list[ChecklistNode]
```
**节点函数变更 — `checkpoint_outline_planner_node()`：**
- 从 `state` 读取 `mandatory_skeleton` 字段
- 传递给 `planner.plan(mandatory_skeleton=mandatory_skeleton)`
**设计评价：**
- 双重约束策略（软+硬）是务实的工程选择：LLM prompt 注入提高遵循概率，确定性后处理保证 100% 合规
- `_merge_skeleton_node()` 的合并策略是"骨架优先、LLM 补充"——骨架节点的 id/title 不可变，但允许 LLM 在骨架节点下自由创建子节点
- 未覆盖的 LLM 节点直接追加而非丢弃，避免信息丢失
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
│   ├── checkpoint_outline_planner node
│   ├── evidence_mapper node
│   ├── draft_writer node
│   └── structure_assembler node
├── invoke subgraph（含迭代循环）
│   └── IterationController.evaluate_and_decide()
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
**PR #23 变更 — source 标签支持：**
`render_test_cases_markdown()` 新增 `enable_source_labels: bool = True` 参数。
**树模式渲染增强：**
- `_render_tree()` 和 `_render_node()` 传播 `enable_source_labels` 参数
- `_render_group_node()` 在渲染标题时检查 `node.source` 字段：
  - `source == "template"` → 标题后追加 ` [模版]`
  - `source == "overflow"` → 标题后追加 ` [待分配]`
  - `source == "generated"` → 无额外标签（默认行为）
- 标签渲染受 `enable_source_labels` 参数控制，可通过 `settings.enable_mandatory_source_labels` 全局关闭
**渲染示例：**
```markdown
## Campaign [模版]
### Campaign name [模版]
### Campaign objective
## 待分配 (Overflow) [待分配]
```
**向后兼容：** `enable_source_labels` 默认为 `True`，但当 `ChecklistNode.source` 为默认值 `"generated"` 时不追加任何标签，因此对无模版的工作流无影响。
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
**PR #23 变更 — source 颜色标记：**
`XMindPayloadBuilder.build()` 新增 `enable_source_labels: bool = True` 参数。
**新增全局常量 — `_SOURCE_MARKERS`：**
```python
_SOURCE_MARKERS: dict[str, str] = {
    "template": "flag-blue",   # 蓝色旗标 = 模版强制节点
    "overflow": "flag-red",    # 红色旗标 = 溢出未匹配节点
}
```
**变更影响：**
- `_build_tree_root()` / `_build_tree_children()` / `_build_group_xmind_node()` 传播 `enable_source_labels` 参数
- `_build_group_xmind_node()` 在构建 XMindNode 时检查 `node.source`，将对应 marker 加入 `markers` 列表
- 蓝色旗标（template）和红色旗标（overflow）在 XMind 中直观标识节点来源
- 与 priority markers（如 `priority-1` 等）并存，一个节点可同时拥有 source marker + priority marker
**视觉效果：**
- 模版强制节点：蓝色旗标 — 表示"来自模版、不可修改"
- 溢出节点：红色旗标 — 表示"未匹配到模版、需要人工分配"
- LLM 生成节点：无额外旗标 — 正常生成的内容
### §3.13 `project_context_service.py` — 项目上下文服务
**核心类**: `ProjectContextService`
**职责**: 项目上下文的 CRUD 操作，通过 SQLite 持久化存储。
**功能**:
- 创建/更新项目上下文
- 查询项目上下文
- 删除项目上下文
**用途**: 在多轮对话或跨会话场景下保持项目级别的配置和状态。
---
### §3.14 `mandatory_skeleton_builder.py` — MandatorySkeletonBuilder ★ [PR #23 新增]
**核心类**: `MandatorySkeletonBuilder`
**职责**: 从 Checklist 模版中提取强制节点，构建强制骨架树（`MandatorySkeletonNode`）。骨架作为 outline 规划和 case 挂载的硬约束输入。
**关键方法**:
| 方法 | 签名 | 说明 |
|------|------|------|
| `build()` | `(template: ProjectChecklistTemplateFile) → MandatorySkeletonNode \| None` | 公开入口：构建强制骨架或返回 None |
| `_build_node()` | `(node, depth, mandatory_levels) → MandatorySkeletonNode \| None` | 递归构建单个骨架节点 |
| `_has_any_mandatory_node()` | `(nodes) → bool` | 检查节点树中是否存在 mandatory=True 的节点 |
| `_count_mandatory_nodes()` | `(node) → int` | 统计骨架中的强制节点数量 |
**强制性判定规则（三条规则，满足任一即为强制）：**
| # | 规则 | 判定条件 | 适用场景 |
|---|------|---------|----------|
| 1 | 层级级强制 | `depth ∈ mandatory_levels` | "第 1、2 层所有节点必须保留" |
| 2 | 节点级强制 | `node.mandatory == True` | "Campaign name 这个特定节点不可遗漏" |
| 3 | 路径连接 | 后代中包含强制节点 | 非强制节点作为连接路径保留（确保树连通） |
**构建流程：**
```
输入: ProjectChecklistTemplateFile
│
├── 1. 提取 mandatory_levels（如 [1, 2]）
├── 2. 检查是否存在任何强制约束
│   ├── mandatory_levels 非空？
│   └── 任何节点 mandatory == True？
│   → 均为否则返回 None
│
├── 3. 递归遍历模版树:
│   对每个节点 (depth=当前深度):
│   ├── 规则 1: depth ∈ mandatory_levels → 标记 mandatory
│   ├── 规则 2: node.mandatory == True → 标记 mandatory
│   ├── 递归处理子节点
│   ├── 规则 3: 任何子节点被保留 → 保留当前节点（路径连接）
│   └── 无子节点被保留且自身非 mandatory → 返回 None（剪枝）
│
└── 4. 返回: MandatorySkeletonNode 根节点（或 None）
```
**输出模型 — `MandatorySkeletonNode`：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 节点唯一 ID（与模版节点 ID 对应） |
| `title` | str | 节点标题 |
| `mandatory` | bool | 是否为强制节点（True = 不可省略/重命名） |
| `children` | list[MandatorySkeletonNode] | 子骨架节点 |
**设计评价：**
- 三规则判定体系覆盖了"层级强制"和"节点强制"两种常见的模版约束模式
- 规则 3（路径连接）确保输出的骨架树是连通的——不会出现孤立的强制节点
- 剪枝策略有效：无强制约束时返回 None，避免下游处理空骨架
- 与 `CheckpointOutlinePlanner` 的 `_enforce_mandatory_skeleton()` 形成完整的约束链
---
## §4 服务依赖图
```
┌─────────────────────────────────────────────────────────────────┐
│ WorkflowService (§3.5) │
│ 主编排服务 │
│ │
│ ┌──────────┐ ┌──────────────────┐ ┌──────────────────┐ │
│ │Iteration │ │CheckpointOutline │ │ Precondition │ │
│ │Controller│ │Planner │ │ Grouper │ │
│ │ (§3.6) │ │ (§3.2) │ │ (§3.4) │ │
│ └──────────┘ └──────────────────┘ └──────────────────┘ │
│ │
│ 方案 A (弃用): 方案 B (当前): │
│ ┌──────────────┐ ┌──────────────────┐ │
│ │ Semantic │ │CheckpointOutline │ │
│ │ PathNorm │ │ Planner │ │
│ │ (§3.3) │ │ (§3.2) │ │
│ └──────┬───────┘ └──────────────────┘ │
│ │ │
│ ┌──────┴───────┐ │
│ │ Checklist │ │
│ │ Merger │ │
│ │ (§3.1) │ │
│ └──────────────┘ │
│ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ 输出管线 │ │
│ │ │ │
│ │ TextNormalizer → MarkdownRenderer │ │
│ │ (§3.7) (§3.8) │ │
│ │ │ │
│ │ PlatformDispatcher │ │
│ │ (§3.9) │ │
│ │ ┌──────────────────────────┐ │ │
│ │ │ XMind 子管线 │ │ │
│ │ │ XMindPayloadBuilder │ │ │
│ │ │ (§3.12) │ │ │
│ │ │ ↓ │ │ │
│ │ │ XMindDeliveryAgent │ │ │
│ │ │ (§3.11) │ │ │
│ │ │ ↓ │ │ │
│ │ │ XMindConnector │ │ │
│ │ │ (§3.10) │ │ │
│ │ └──────────────────────────┘ │ │
│ └──────────────────────────────────────────────────────────┘ │
│ │
│ ┌──────────────────────┐ │
│ │ ProjectContextService│ │
│ │ (§3.13) │ │
│ │ SQLite 持久化 │ │
│ └──────────────────────┘ │
│ │
│ ┌──────────────────────────────────┐ │
│ │ MandatorySkeletonBuilder │ ← PR #23 新增 │
│ │ (强制骨架构建) │ │
│ └────────────┬─────────────────────┘ │
│ │ 被 ProjectTemplateLoader 调用 │
│ ↓ │
│ CheckpointOutlinePlanner │
│ (骨架约束注入) │
└─────────────────────────────────────────────────────────────────┘
```
---
## §5 Checklist 整合方案深度分析
### §5.1 方案总览
本项目存在**两套 Checklist 整合方案**（checkpoint → 结构化 ChecklistNode 树的转换路径），其中方案 A 已弃用、方案 B 为当前使用方案。两套方案共享同一套输出管线（TextNormalizer → MarkdownRenderer / PlatformDispatcher）。
```
Checkpoints (from checkpoint_generator/evaluator)
│
├── 方案 A (弃用): SemanticPathNormalizer → ChecklistMerger
│ 自底向上：先将 checkpoint 归一化为路径，再通过 trie 合并
│
└── 方案 B (当前): CheckpointOutlinePlanner → (PreconditionGrouper)
 自顶向下：LLM 直接生成整体 outline，再挂载 expected_results
```
### §5.2 方案 B 当前流程详解
```
checkpoint 列表 (来自 checkpoint_evaluator 的输出)
│
├── Step 1: CheckpointOutlinePlanner.plan()
│ └── LLM 输入: 所有 checkpoint 标题
│ └── LLM 输出: CanonicalOutlineNode JSON 数组 (层级化的 outline)
│
├── Step 2: CheckpointOutlinePlanner.attach_expected_results_to_outline()
│ └── 遍历 outline 叶节点
│ └── 按 checkpoint 名称匹配 → 挂载 expected_behaviors
│ └── 产出: ChecklistNode 树 (含 expected_result 叶节点)
│
├── Step 3: PreconditionGrouper (可选)
│ └── 对 ChecklistNode 树中的测试用例按前置条件分组
│ └── 插入 precondition_group 中间层节点
│
├── Step 4: TextNormalizer
│ └── 中英文文本归一化处理
│
└── Step 5: 输出管线
 ├── MarkdownRenderer → .md 文件
 └── PlatformDispatcher → XMind 等
```
### §5.3 方案 B 深度问题分析
#### §5.3.1 LLM 单次规划的规模上限
**问题描述**: `CheckpointOutlinePlanner.plan()` 将所有 checkpoint 标题一次性发送给 LLM 进行 outline 规划。当 checkpoint 数量大于约 30 个时，LLM 的规划质量显著下降。
**表现**:
- outline 层级变浅（趋于扁平化）
- 分组逻辑混乱（相关 checkpoint 被拆散到不同分组）
- 部分 checkpoint 被遗漏或重复归类
**量化观察**:
| Checkpoint 数量 | Outline 质量 | 典型问题 |
|----------------|-------------|---------|
| 1-10 | 高 | 层级合理，分组准确 |
| 11-20 | 中 | 偶尔出现分组不合理 |
| 21-30 | 中偏低 | 层级开始扁平化，部分遗漏 |
| 30+ | 低 | 严重扁平化，大量遗漏和错配 |
**根因**: LLM 的 context window 和 reasoning 能力有限，当输入超过一定规模时，难以维持全局一致的层级规划。
---
#### §5.3.2 outline 分组维度偏差
**问题描述**: LLM 有时按技术维度（如"前端测试"/"后端测试"）而非业务维度（如"用户管理"/"订单管理"）分组
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
### §5.6 PR #23 对改进路线图的推进
PR #23 的强制模版骨架功能直接推进了 §5.5 中的多项改进建议：
| 原建议 | 状态 | PR #23 实现方式 |
|--------|------|----------------|
| **建议 1: PRD 章节锚定** | ✅ 已实现（变体） | 模版强制骨架替代 PRD 标题作为 outline 顶层骨架 |
| **建议 6: Outline 评估节点** | ⚡ 部分实现 | `_enforce_mandatory_skeleton()` 是确定性校验，但非独立评估节点 |
| **建议 9: 结构化知识库** | ⚡ 初步实现 | `templates/` 目录 + YAML 模版是结构化知识库的雏形 |
**与原建议的差异分析：**
1. **锚定源不同**: 原建议使用 PRD 原文标题作为锚点（零配置、自动化），PR #23 使用预定义模版（需要人工维护模版文件）。两种方案可互补——无模版时用 PRD 标题锚定，有模版时用模版骨架锚定。
2. **约束强度不同**: 原建议仅是"锚点参考"（LLM 可以调整），PR #23 的强制层级是"硬约束"（不可修改）。硬约束在标准化流程（如广告 Campaign 结构）中价值更高，软锚点在探索性 PRD 中更灵活。
3. **评估方式不同**: 原建议 6 是独立的评估节点（多维度打分），PR #23 的后处理修复是"修复即评估"——不打分、直接修复。优势是零额外 LLM 调用，劣势是缺乏质量度量。
**仍未覆盖的改进建议：**
- 建议 2（分批规划）：PR #23 未改变单次 LLM 规划的模式
- 建议 3（PreconditionGrouper 语义升级）：未涉及
- 建议 5（混合方案 A+B）：未涉及
- 建议 7（多轮迭代 Outline）：未涉及
- 建议 8（用户反馈闭环）：未涉及
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
| **覆盖率** | 已匹配 checkpoint 数 / 总 checkpoint 数 | ≥ 0.95 |
| **平衡度** | std(各子树叶节点数) / mean(各子树叶节点数) | ≤ 1.5 |
| **深度合理性** | max_depth / log2(叶节点数) | 0.5 - 3.0 |
| **空叶节点率** | 无子节点的叶节点数 / 总叶节点数 | ≤ 0.1 |
| **命名一致性** | 同层节点命名风格相似度 | ≥ 0.7 |
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
## §6 PR #24 变更 — WorkflowService 知识引擎注入

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

PR #24 修改了 `WorkflowService`，支持将 GraphRAG 引擎注入工作流。

### \_\_init\_\_ 签名变更

```python
# 修改前
def __init__(self, llm_client, settings, run_repository, project_context_loader=None):

# 修改后
def __init__(self, llm_client, settings, run_repository, project_context_loader=None, graphrag_engine=None):
```

新增可选参数 `graphrag_engine: Optional[GraphRAGEngine]`，存储为 `self._graphrag_engine`。

### _get_workflow() 变更

```python
def _get_workflow(self):
    knowledge_retrieval_node = None
    if self._graphrag_engine is not None and self._graphrag_engine.is_ready():
        knowledge_retrieval_node = build_knowledge_retrieval_node(
            self._graphrag_engine, self._settings
        )
    self._workflow = build_workflow(
        self._llm_client,
        project_context_loader=self._project_context_loader,
        knowledge_retrieval_node=knowledge_retrieval_node,
    )
    return self._workflow
```

- 当 `graphrag_engine` 存在且 `is_ready()` 时，构建 knowledge_retrieval 节点
- 将节点传入 `build_workflow()`，由工作流图层决定拓扑
- `self._workflow = None` 缓存失效机制：首次调用或需要重新构建时触发

### 设计评价

1. **依赖注入一致**: 与 `project_context_loader` 的注入模式完全对称，学习成本低
2. **就绪检查**: 通过 `is_ready()` 门控，避免将未初始化的引擎注入工作流
3. **惰性构建**: 工作流在首次执行时构建，引擎的注入不影响 WorkflowService 的初始化速度

## §7 PR #36 变更 — MR 代码分析服务层新增

> 同步自 PR #36 `feat/mr-code-analysis-integration`

PR #36 在 `app/services/` 下新增 3 个文件，为 MR（Merge Request）代码分析功能提供服务层支撑：Agentic search 工具集、Coco Agent 异步客户端、以及 Coco 响应容错验证器。

### §7.1 新增文件清单

| # | 文件名 | 行数(估) | 核心类/函数 | 职责摘要 |
|---|--------|----------|-------------|----------|
| 16 | `codebase_tools.py` | ~627 | `CODEBASE_TOOLS`, `execute_tool()` | Agentic search 工具实现，为 LLM 提供代码库搜索能力 |
| 17 | `coco_client.py` | ~482 | `CocoClient` | ByteDance Coco Agent 异步客户端（任务提交 + 轮询 + 结果提取） |
| 18 | `coco_response_validator.py` | ~335 | `CocoResponseValidator` | Coco Agent 响应的 3 层容错验证 |

### §7.2 `codebase_tools.py` — Agentic Search 工具集

**职责**: 为 LLM function calling 提供代码库搜索工具，支撑 MR 分析节点的 agentic search 循环。

**核心组件**:

| 组件 | 类型 | 说明 |
|------|------|------|
| `CODEBASE_TOOLS` | `list[dict]` | 5 个工具的 JSON Schema 定义列表，供 LLM function calling 使用 |
| `execute_tool()` | 函数 | 工具调度器：根据 LLM 返回的 tool name 分发到对应实现函数 |

**5 个工具定义**:

| # | 工具名 | 实现方式 | 说明 |
|---|--------|---------|------|
| 1 | `grep_codebase` | `subprocess.run("grep -rn ...")` | 在代码库中搜索关键词，返回匹配行及行号 |
| 2 | `find_references` | 基于 grep 的引用搜索 | 查找符号（函数名、类名等）的引用位置 |
| 3 | `get_file_content` | 文件读取 | 获取指定文件的完整内容或指定行范围 |
| 4 | `ast_analyze` | Python `ast` 模块 | 对 Python 文件进行 AST 分析，提取类/函数/导入等结构信息 |
| 5 | `get_call_graph` | AST 分析 + 引用搜索 | 构建指定函数/类的调用关系图 |

**安全机制**:
- **Path traversal 防护**: 所有文件路径参数经过校验，防止 `../` 等路径穿越攻击
- **Subprocess 超时**: `grep` 等子进程调用设置超时限制，避免恶意输入导致的长时间阻塞

**设计模式**:
- **Stateless 工具函数**: 每个工具函数无状态，接收参数、返回结果，适合 LLM 多轮调用
- **JSON Schema 定义**: 工具定义遵循 OpenAI function calling schema 规范，包含 `name`、`description`、`parameters` 字段
- **调度器模式**: `execute_tool()` 作为统一入口，根据 tool name 路由到具体实现，便于新增工具

### §7.3 `coco_client.py` — Coco Agent 异步客户端

**核心类**: `CocoClient`

**职责**: 封装与 ByteDance Coco Agent（`codebase-api.byted.org`）的异步 HTTP 交互，支持任务提交、轮询和结果提取。

**关键方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `send_task()` | `async (payload) → task_id` | 向 Coco Agent 提交分析任务，返回任务 ID |
| `poll_task()` | `async (task_id) → raw_response` | 轮询任务状态，指数退避（5s → 20s），直到完成或超时 |
| `extract_result()` | `(raw_response) → (model, metadata)` | 使用 `CocoResponseValidator` 验证并提取结构化结果 |
| `send_validation_task()` | `async (payload) → task_id` | 提交 Task 2 一致性校验任务 |

**轮询策略**:
```
初始间隔: 5s
最大间隔: 20s
退避策略: 指数退避（每次间隔翻倍，上限 20s）
超时控制: 由 CocoSettings.coco_task_timeout 配置
```

**响应模型（Pydantic）**:

| 模型 | 说明 |
|------|------|
| `Task1Response` | Task 1（代码事实提取）的响应模型 |
| `Task2Response` | Task 2（一致性校验）的响应模型 |
| `CodeFactItem` | 单条代码事实（函数签名、逻辑摘要等） |
| `ConsistencyIssueItem` | 单条一致性问题（代码与需求的不一致项） |
| `RelatedSnippetItem` | 相关代码片段引用 |

**异常处理**:
- `CocoTaskError`: Coco 任务级异常（提交失败、轮询超时、响应解析失败）

**依赖**:
- `httpx`: 异步 HTTP 客户端
- `coco_response_validator`: 响应验证（见 §7.4）

### §7.4 `coco_response_validator.py` — Coco 响应容错验证

**核心类**: `CocoResponseValidator`

**职责**: 对 Coco Agent 的原始响应进行 3 层渐进式容错验证，确保即使响应格式异常也能提取有效信息。

**验证流程**:

```
输入: Coco Agent 原始响应 (str/dict)
│
├── Layer 1 — JSON 提取: validate_and_fix() → _extract_json()
│   ├── 成功: 进入 Schema 校验
│   └── 失败: 进入 Layer 3
│
├── Layer 2 — Schema 校验: Pydantic model_validate()
│   ├── 成功: 返回 (BaseModel, metadata={layer: "json_extract"})
│   └── 失败: 进入 Layer 3
│
├── Layer 3a — LLM 部分推理: _llm_partial_infer()
│   ├── 成功: 返回 (BaseModel, metadata={layer: "llm_partial"})
│   └── 失败: 进入 Layer 3b
│
├── Layer 3b — LLM 完整推理: _llm_full_infer()
│   ├── 成功: 返回 (BaseModel, metadata={layer: "llm_full"})
│   └── 失败: 进入 defaults
│
└── Layer 4 — 默认值填充: _fill_defaults()
    └── 返回 (BaseModel with defaults, metadata={layer: "defaults"})
```

**返回格式**: `(BaseModel, metadata)` 元组
- `BaseModel`: 验证后的 Pydantic 模型实例（Task1Response 或 Task2Response）
- `metadata`: 字典，记录响应由哪一层处理成功，用于监控和调试

**设计理念 — 渐进式降级**:
1. **JSON 提取** → 最快路径，零 LLM 调用
2. **Schema 校验** → Pydantic 强类型验证
3. **LLM 部分推理** → 利用 LLM 修复格式异常的 JSON
4. **LLM 完整推理** → 利用 LLM 从非结构化文本中提取结构化数据
5. **默认值填充** → 最终兜底，确保不返回 None

**设计评价**:
- 多层容错是处理外部 API 不稳定响应的最佳实践，每层的 metadata 标注使得降级路径可观测
- LLM 兜底层引入额外延迟和成本，但保证了系统的鲁棒性
- `_fill_defaults()` 作为最终兜底确保调用方永远不会收到 None，简化了下游错误处理

### §7.5 服务层 PR #36 变更总结

**新增文件统计**:

| 维度 | 值 |
|------|-----|
| 新增文件数 | 3 |
| 新增总行数 | ~1,444 |
| 外部依赖 | httpx（异步 HTTP） |
| LLM 依赖 | `coco_response_validator` 的 Layer 3 降级路径需要 LLM 客户端 |

**架构角色**:

```
MR 分析节点 (app/nodes/)
    │
    ├── codebase_tools.py ← Agentic search 工具（LLM function calling）
    │
    ├── coco_client.py ← Coco Agent 交互（任务提交/轮询/结果提取）
    │   │
    │   └── coco_response_validator.py ← 响应容错验证（3 层降级）
    │
    └── CocoSettings (app/config/) ← 连接配置
```

**与现有服务的关系**:
- `codebase_tools.py` 被 MR 分析节点（`app/nodes/mr_analyzer.py`）在 agentic search 循环中调用
- `coco_client.py` 被 Coco 一致性验证节点（`app/nodes/coco_consistency_validator.py`）调用
- 三个新文件与现有服务（§3 中的 14 个文件）无直接依赖关系，保持了良好的模块隔离

**设计模式一致性**:
- `CocoClient` 遵循与 `ProjectContextService` 类似的异步客户端模式
- `CODEBASE_TOOLS` 的 JSON Schema 定义与 LangGraph 工具调用规范一致
- `CocoResponseValidator` 的渐进式降级设计是本项目首次引入的容错模式，可作为后续外部 API 集成的参考
