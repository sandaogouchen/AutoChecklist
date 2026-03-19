# checklist_merger.py 分析

## 概述

`app/services/checklist_merger.py` 实现了基于 Trie（前缀树）的 Checklist 前置操作合并算法。它将共享公共前置操作/步骤前缀的测试用例合并为树形结构 `list[ChecklistNode]`，是 F1（前置操作合并）功能的核心算法实现。

该文件位于 `app/services/` 业务服务层，接收 `TestCase` 列表作为输入，输出 `ChecklistNode` 树。算法流程为：(1) 拼接 preconditions + steps 为操作序列 → (2) 归一化文本用于比较 → (3) 插入 Trie → (4) Trie 转 ChecklistNode 树 → (5) 单子链剪枝。

## 依赖关系

- 上游依赖:
  - `app.domain.checklist_models.ChecklistNode` — 输出的树节点模型
  - `app.domain.case_models.TestCase` — 输入的测试用例模型（TYPE_CHECKING 导入）
  - 标准库: `re`, `unicodedata`, `uuid`, `dataclasses`
- 下游消费者:
  - `app.nodes.checklist_optimizer` — 在 LangGraph 节点中调用 `ChecklistMerger().merge()`

## 核心实现

### 常量

- `_MAX_DEPTH = 10`: Trie 最大插入深度，防止异常长操作序列导致的过深嵌套

### 内部数据结构

- **`_TerminalInfo`** (dataclass): Trie 叶子节点携带的原始 TestCase 信息，包含 test_case_id、title、remaining_steps、expected_results、priority、category、evidence_refs、checkpoint_id
- **`_TrieNode`** (dataclass): Trie 节点，包含 `children: dict[str, _TrieNode]`（键为归一化文本）、`terminals: list[_TerminalInfo]`（到达该节点的用例信息）、`raw_label: str`（未归一化的原始文本用于展示）

### 归一化函数

- **`_normalize_for_comparison(text)`**: 将文本归一化为可比较的规范形式
  1. 去除序号前缀（`1. `, `2) `, `Step 3: ` 等）— 使用 `_NUMBERING_RE`
  2. `casefold()` 统一大小写
  3. 中英文标点统一 — 使用 `_PUNCTUATION_MAP` (`str.maketrans`)
  4. NFKC Unicode 归一化
  5. strip 首尾空白

### ChecklistMerger 类

- **`merge(test_cases) -> list[ChecklistNode]`**: 公开入口方法
  1. 空输入检查，返回 `[]`
  2. 构建 `_TrieNode` 根节点
  3. 遍历 test_cases，拼接 `preconditions + steps` 后调用 `_insert()`
  4. 调用 `_trie_to_nodes()` 转换为 ChecklistNode 树
  5. 调用 `_prune()` 执行单子链剪枝

- **`_insert(root, ops, case)`**: 将一个 TestCase 的操作序列插入 Trie，受 `_MAX_DEPTH` 限制，超出部分记录为 `remaining_steps`

- **`_trie_to_nodes(trie_node)`**: 递归将 Trie 转为 ChecklistNode 列表。当某个子分支只有一个叶子时，直接提升叶子节点而不创建 group 包装

- **`_prune(nodes)` / `_prune_node(node)`**: 递归剪除单子节点的 group 链。当 group 只有一个子节点且该子节点也是 group 时，合并标题（用 ` → ` 连接）并提升子节点的 children

## 关联需求

- PRD: Checklist 同前置操作整合与表达精炼优化
- 功能编号: F1（前置操作合并 — Trie 树算法）

## 变更历史

- PR #15: 初始创建
