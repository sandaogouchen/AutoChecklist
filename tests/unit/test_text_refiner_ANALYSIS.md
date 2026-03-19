# test_text_refiner.py 分析

## 概述

`tests/unit/test_text_refiner.py` 是 `text_normalizer.py` 中 F2 文本精炼功能（`refine_text` 和 `_merge_redundant_steps`）的单元测试文件。覆盖中英文前缀/后缀去除、关键标识符保护、长度约束和冗余步骤合并等场景。

该文件位于 `tests/unit/` 测试目录，为 F2（文本精炼）功能提供测试保障。

## 依赖关系

- 上游依赖:
  - `pytest`
  - `app.services.text_normalizer.refine_text`
  - `app.services.text_normalizer._merge_redundant_steps`（内部函数，白盒测试）
- 下游消费者: 无（测试文件）

## 核心实现

### TestRefineText 测试类

测试 `refine_text` 基本功能：

**中文前缀去除：**
- `test_zh_prefix_removal_verify`: 「验证用户能够正常登录」→ 不以「验证」开头
- `test_zh_prefix_removal_check`: 「检查页面是否显示正确」→ 不以「检查」开头
- `test_zh_prefix_removal_confirm`: 「确认订单状态已更新」→ 不以「确认」开头

**中文后缀去除：**
- `test_zh_suffix_removal`: 「登录功能是否正常」→ 不以「是否正常」结尾

**英文前缀去除：**
- `test_en_prefix_removal_verify`: "Verify that the button works" → 不以 "Verify that" 开头
- `test_en_prefix_removal_ensure`: "Ensure the page loads" → 不以 "Ensure" 开头

**英文后缀去除：**
- `test_en_suffix_removal`: "The system works as expected" → 不以 "as expected" 结尾

**关键标识符保护：**
- `test_backtick_content_preserved`: 反引号包裹的 `submit_button` 被保留
- `test_url_preserved`: URL `https://example.com/login` 被保留

**长度约束：**
- `test_length_constraint`: 超长文本被截断到 zh step 限制（120 字符）

**边界场景：**
- `test_empty_string`: 空字符串原样返回
- `test_clean_text_unchanged`: 已简洁的文本不被修改

### TestMergeRedundantSteps 测试类

测试 `_merge_redundant_steps` 冗余步骤合并：
- `test_duplicate_steps_merged`: 完全相同的连续步骤被合并
- `test_similar_steps_merged`: 高相似度步骤（基于 SequenceMatcher >= 0.85）被合并，保留较长的那条
- `test_different_steps_kept`: 不同步骤全部保留

## 关联需求

- PRD: Checklist 同前置操作整合与表达精炼优化
- 功能编号: F2（文本精炼 — 测试覆盖）

## 变更历史

- PR #15: 初始创建
