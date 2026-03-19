# checklist_models.py 分析

## 概述

`app/domain/checklist_models.py` 定义了 `ChecklistNode` 递归 Pydantic v2 模型，是 F1（前置操作合并）功能的核心数据结构。该模型使用 `Literal["group", "case"]` 区分中间分组节点和叶子用例节点，通过 `list[ChecklistNode]` 实现任意深度的递归嵌套。由于 Pydantic v2 的递归模型限制，文件末尾显式调用了 `ChecklistNode.model_rebuild()` 完成模型自引用解析。

该文件位于 `app/domain/` 领域模型层，是 Checklist 优化特性（F1-F5）的数据基石。上游由 `ChecklistMerger` 的 Trie 算法生成实例，下游被 `markdown_renderer`、`XMindPayloadBuilder`、`checklist_optimizer` 以及 `state.py`（GlobalState/CaseGenState）消费。

## 依赖关系

- 上游依赖:
  - `pydantic` (`BaseModel`, `Field`)
  - `app.domain.research_models.EvidenceRef` — 复用已有的证据引用模型
  - `typing.Literal` — 用于 node_type 字面量类型约束
- 下游消费者:
  - `app.services.checklist_merger` — Trie 算法生成 ChecklistNode 树
  - `app.nodes.checklist_optimizer` — 间接通过 merger 使用
  - `app.services.markdown_renderer` — 树形渲染消费 ChecklistNode
  - `app.services.xmind_payload_builder` — 树形模式构建 XMind 节点
  - `app.domain.state` — GlobalState 和 CaseGenState 新增 `optimized_tree: list[ChecklistNode]` 字段

## 核心实现

### ChecklistNode (Pydantic BaseModel)

递归树节点模型，关键字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `node_id` | `str` | `""` | 节点唯一标识（group 自动生成 UUID，case 沿用 TestCase.id） |
| `title` | `str` | `""` | group 为公共前置操作描述，case 为用例标题 |
| `node_type` | `Literal["group", "case"]` | `"group"` | 节点类型 |
| `children` | `list[ChecklistNode]` | `[]` | 子节点列表（仅 group 有效） |
| `test_case_ref` | `str` | `""` | 原始 TestCase.id 引用（仅 case） |
| `remaining_steps` | `list[str]` | `[]` | 去掉公共前缀后剩余的操作步骤（仅 case） |
| `expected_results` | `list[str]` | `[]` | 预期结果列表（仅 case） |
| `priority` | `str` | `"P2"` | 优先级 P0-P3 |
| `category` | `str` | `"functional"` | 用例类别 |
| `evidence_refs` | `list[EvidenceRef]` | `[]` | 关联的 PRD 原文证据引用 |
| `checkpoint_id` | `str` | `""` | 所属 checkpoint 标识 |

### model_rebuild() 调用

文件末尾 `ChecklistNode.model_rebuild()` 是 Pydantic v2 处理递归自引用模型的必要步骤。没有此调用，`children: list[ChecklistNode]` 的 JSON Schema 生成和序列化/反序列化会失败。

## 关联需求

- PRD: Checklist 同前置操作整合与表达精炼优化
- 功能编号: F1（前置操作合并 — 核心数据结构）

## 变更历史

- PR #15: 初始创建
