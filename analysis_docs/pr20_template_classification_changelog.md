# PR #20: 项目级 Checklist 模版强制归类 — 变更分析

> 对应 PR: [#20](https://github.com/sandaogouchen/AutoChecklist/pull/20)
> 分支: `feat/project-template-forced-classification`
> 基线: `88e1848` (Merge PR #17)

## 1. 功能概述

新增项目级 Checklist 模版系统，允许用户提供 YAML 格式的模版文件，系统解析后将模版叶子节点注入 LLM 提示词，引导检查点自动归类到模版树结构中，最终按模版骨架输出 Markdown 报告。

## 2. 架构影响

### 2.1 数据流变更

```
[新增] YAML Template File
         ↓
[新增] template_loader node (主工作流)
         ↓
GlobalState.project_template + template_leaf_targets
         ↓
case_generation_bridge (传入子图)
         ↓
[修改] checkpoint_generator (LLM prompt 注入 + 后处理校验)
         ↓
Checkpoint.template_* 字段
         ↓
[修改] draft_writer (模版字段主继承)
         ↓
[修改] structure_assembler (模版字段兜底继承)
         ↓
TestCase.template_* 字段
         ↓
[修改] markdown_renderer (三级渲染: 模版 > 树 > 扁平)
```

### 2.2 工作流拓扑变更

**变更前**: `input_parser → [project_context_loader] → context_research → case_generation → reflection`

**变更后**: `input_parser → template_loader → [project_context_loader] → context_research → case_generation → reflection`

`template_loader` 始终存在于流水线中，当未提供模版文件路径时返回空增量（no-op）。

## 3. 新增组件

### 3.1 领域模型 (`app/domain/template_models.py`)

| 类 | 职责 |
|----|------|
| `ProjectChecklistTemplateNode` | 递归树节点（Pydantic v2 自引用 + `model_rebuild()`） |
| `ProjectChecklistTemplateMetadata` | 模版元数据（name, version, description） |
| `ProjectChecklistTemplateFile` | 完整模版文件结构 |
| `TemplateLeafTarget` | 拍平后的叶子目标（含完整路径） |

### 3.2 模版服务 (`app/services/template_loader.py`)

| 方法 | 职责 |
|------|------|
| `load(file_path)` | YAML 解析 + 结构映射 |
| `validate_template(template)` | 非空/唯一 ID/至少一叶/类型检查 |
| `flatten_leaves(template)` | 递归树遍历收集叶子 |

### 3.3 工作流节点 (`app/nodes/template_loader.py`)

工厂模式 `build_template_loader_node()` 返回节点函数，签名 `(GlobalState) -> GlobalState`。

## 4. 修改组件影响分析

| 组件 | 变更类型 | 影响范围 |
|------|---------|----------|
| `api_models.py` | 字段追加 | API 层（向后兼容） |
| `checkpoint_models.py` | 字段追加 | 数据模型层 |
| `case_models.py` | 字段追加 | 数据模型层 |
| `state.py` | 字段追加 | 全局/子图状态 |
| `checkpoint_generator.py` | 逻辑新增 | LLM 交互层（核心变更） |
| `draft_writer.py` | 逻辑新增 | 字段继承 |
| `structure_assembler.py` | 逻辑新增 | 兜底继承 |
| `markdown_renderer.py` | 模式新增 | 输出渲染层 |
| `main_workflow.py` | 拓扑变更 | 工作流图 |
| `workflow_service.py` | 透传新增 | 编排层 |
| `pyproject.toml` | 依赖新增 | 构建配置 |

## 5. 关键设计决策

1. **低置信度阈值 0.6**: 硬编码为 `_LOW_CONFIDENCE_THRESHOLD = 0.6`，低于此值的绑定标记为低置信度
2. **两级继承保障**: `draft_writer`（主继承）+ `structure_assembler`（兜底），确保 TestCase 一定能获得模版绑定
3. **三级渲染优先**: `template > tree > flat`，模版模式下按模版骨架递归渲染
4. **安全解析**: 使用 `yaml.safe_load()` 防止代码注入
5. **向后兼容**: `template_file_path` 为 `Optional`，无模版时全链路 no-op

## 6. 已知限制

- 模版叶子数量过大时（100+）LLM prompt 可能过长
- `_render_single_case()` 返回类型标注不准确（`-> str` 应为 `-> None`）
- 无路径穿越防护（依赖部署环境安全性）

## 7. 与现有 PR 的关系

| PR | 状态 | 关系 |
|----|------|------|
| PR #13 (feat/checklist-template-system) | Open | 不同的模版系统方案，本 PR 为独立实现 |
| PR #17 (precondition-grouper-v2) | Merged | 本 PR 基线，`optimized_tree` 特性被保留 |
| PR #20 (本 PR) | Open | 新增模版强制归类系统 |
