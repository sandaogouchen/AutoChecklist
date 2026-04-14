# AutoChecklist PRD: 项目级 Checklist 模版强制归类

**日期：** 2026-03-19  
**状态：** Draft  
**作者：** Codex  
**适用范围：** AutoChecklist 工作流、本地项目级 checklist 模版文件、Markdown/XMind 输出

## 1. 背景

当前 AutoChecklist 已具备以下能力：

1. 读取本地 PRD Markdown 文档并解析内容。
2. 通过 `context_research -> checkpoint_generator -> draft_writer` 生成 checkpoint 和 testcase。
3. 支持通用 checklist 模版作为 prompt 约束和事后评估基准。

但现有“模版系统”仍有一个核心缺口：生成出的 checkpoint 和 testcase 并不会被稳定地挂接到预定义的项目 checklist 结构中。当前更多是“参考模版生成”，而不是“强制归类到模版节点”。

对于真实项目，测试团队往往已经有稳定的 checklist 树，例如：

```md
Campaign
  Create Campaign
    Basic Info
    Targeting
Ad Group
  Create Ad Group
    Optimize Goal
    Budget
```

使用者期望系统输出的 case 必须挂到这些固定节点下，而不是每次由模型自由发明一棵新的语义树。

因此需要新增一套“项目级 checklist 模版强制归类”能力：

1. 模版由本地文件维护，不走数据库管理。
2. 运行时通过本地文件路径传入。
3. 系统先解析模版树，再要求每个 checkpoint 必须归属到模版中的一个叶子节点。
4. testcase 继承 checkpoint 的模版归属。
5. 最终 checklist 输出以模版树为骨架，不允许生成树结构漂移。

## 2. 问题定义

### 2.1 当前问题

当前流程在“项目固定结构”这个维度上存在以下问题：

1. 生成结果没有稳定的项目级结构锚点，同一项目多次运行的 checklist 树风格可能不同。
2. checkpoint 和 testcase 虽然有 `checkpoint_id` 链路，但没有可靠的模版节点归属字段。
3. 模版合规性更多是事后检查“像不像覆盖了”，而不是在生成阶段“必须归到哪里”。
4. 现有结果树可以被模型自由长出新节点，不利于测试团队长期维护。
5. 项目方已有的 checklist 树无法作为最终输出的唯一合法结构空间。

### 2.2 目标问题陈述

系统需要支持“项目级 checklist 模版文件”，并将其作为生成主链路中的强约束，使得：

1. 每个 checkpoint 必须绑定到模版树的一个叶子节点。
2. 每个 testcase 必须继承该叶子节点归属。
3. 最终 Markdown/XMind 按模版树渲染，而不是按模型自由规划的语义树渲染。
4. 无法高置信度归类时允许选择最相近节点，但必须显式标记低置信度，便于人工复核。

## 3. 产品目标

### 3.1 核心目标

1. 引入项目级 checklist 模版文件输入能力。
2. 将模版归类从“后处理建议”升级为“checkpoint 生成阶段的强约束”。
3. 让 testcase 在生成时天然携带模版路径，而不是事后补挂。
4. 让最终输出树结构严格复用模版树。
5. 在不命中高置信度节点时，支持“最相近路径 + 低置信度标记”的兜底策略。

### 3.2 成功标准

1. 指定 `template_file_path` 的运行中，100% checkpoint 都带有模版叶子归属。
2. 指定 `template_file_path` 的运行中，100% testcase 都继承模版叶子归属。
3. 最终输出中不再出现模版外新增结构节点。
4. 同一份 PRD 在同一项目模版下多次运行时，核心树结构保持稳定。
5. 低置信度归类结果可在输出中被显式识别和筛选。

## 4. 非目标

本期不包含以下内容：

1. 不做项目级 checklist 模版的数据库 CRUD 管理。
2. 不做 UI 配置页面，本期仅支持本地文件输入。
3. 不支持运行时动态扩展模版树。
4. 不做跨项目模版推荐与复用。
5. 不做复杂的模版版本协商机制，本期只消费传入的单个本地文件。

## 5. 目标用户与用户故事

### 5.1 目标用户

1. 需要用固定 checklist 结构审阅结果的 QA / 测试负责人
2. 需要让 AutoChecklist 输出符合项目规范的开发和产品 owner
3. 需要把生成结果持续沉淀到统一树结构中的项目维护者

### 5.2 用户故事

1. 作为测试负责人，我希望把项目固定 checklist 树作为本地文件传入，让系统严格按这棵树组织结果。
2. 作为 QA，我希望每个生成出来的 case 都能明确知道自己属于哪个模版节点，而不是靠人工再归并。
3. 作为结果使用者，我希望最终 Markdown/XMind 直接复用项目模版结构，这样不同轮次输出可以稳定对比。
4. 作为审核人，我希望看到哪些 case 是“低置信度归类”，以便优先人工复核。

## 6. 方案对比

### 6.1 方案 A：先生成 case，再后置归类

优点：

1. 对现有工作流改动较小。
2. 可以作为附加步骤插入。

缺点：

1. 归类和生成分离，容易出现“case 内容描述 A，节点挂到 B”。
2. 归类结果不稳定，本质上仍是后补动作。
3. 无法从源头保证最终输出树结构稳定。

### 6.2 方案 B：checkpoint 阶段强制绑定模版节点

优点：

1. 在 `fact -> checkpoint -> testcase` 全链路中保留模版归属。
2. testcase 不再重新自由分类，只继承 checkpoint 的结果。
3. 最终输出树可以严格以模版树为骨架。
4. 与现有工作流兼容度较高，不需要彻底重写生成流程。

缺点：

1. 需要扩展 checkpoint / testcase 数据模型。
2. 需要新增模版文件解析和匹配逻辑。

### 6.3 方案 C：先以模版树规划，再按节点生成 case

优点：

1. 模版控制力最强。
2. 输出结构最稳定。

缺点：

1. 对现有工作流侵入大。
2. 容易把生成流程变成“按模版填空”，弱化 PRD facts 的主导作用。

### 6.4 结论

采用 **方案 B**。

理由：

1. 能把模版归类变成生成主链路的一等约束。
2. 不会推翻现有 `research -> checkpoint -> testcase` 的总体架构。
3. 最适合当前仓库的演进路径。

## 7. 核心设计原则

### 7.1 模版树是唯一合法结构空间

一旦指定 `template_file_path`，最终结果树必须严格受模版树约束。

具体要求：

1. 只允许挂载到模版中已存在的叶子节点。
2. 不允许运行时生成模版外的新结构节点。
3. 非叶子节点仅作为结构路径，不直接挂 testcase。

### 7.2 归类在 checkpoint 阶段完成

模版归类必须在 checkpoint 生成阶段完成，而不是 testcase 生成后再补做。

具体要求：

1. 每个 checkpoint 都必须有模版叶子归属。
2. testcase 仅继承归属，不再重新判断。
3. 评估、渲染、导出均以 checkpoint 的模版归属为准。

### 7.3 允许低置信度兜底，但不允许无归属

对于无法可靠命中的情况：

1. 允许 LLM 选择“最相近模版叶子”。
2. 必须显式标记 `is_low_confidence = true`。
3. 必须保留简短匹配理由。
4. 不允许出现完全没有模版归属的 checkpoint。

### 7.4 PRD facts 仍然是内容来源

模版负责“挂到哪里”，facts 负责“测什么”。

具体要求：

1. 不允许忽略 PRD 提取出的关键 facts。
2. 不允许只因为模版存在，就生成与 PRD 无关的空洞 case。
3. 模版是结构约束，不是内容替代。

## 8. 输入与模版文件规范

## 8.1 运行输入新增字段

运行请求新增：

- `template_file_path`: 本地项目级 checklist 模版文件绝对路径或相对路径

产品规则：

1. 未提供该字段时，系统保持现有无模版模式。
2. 提供该字段时，系统启用“项目级模版强制归类模式”。
3. 文件不存在、无法解析或不合法时，运行直接失败，不静默降级。

## 8.2 模版文件格式

建议采用 YAML，支持树形多层结构。

示例：

```yaml
metadata:
  name: "Ads Project Checklist"
  version: "1.0.0"
  description: "Ads 项目固定检查树"

nodes:
  - id: "campaign"
    title: "Campaign"
    children:
      - id: "campaign-create"
        title: "Create Campaign"
        children:
          - id: "campaign-create-basic"
            title: "Basic Info"
          - id: "campaign-create-targeting"
            title: "Targeting"

  - id: "adgroup"
    title: "Ad Group"
    children:
      - id: "adgroup-create"
        title: "Create Ad Group"
        children:
          - id: "adgroup-create-optimize-goal"
            title: "Optimize Goal"
          - id: "adgroup-create-budget"
            title: "Budget"
```

## 8.3 模版文件校验规则

### 必填字段

1. `metadata.name`
2. `metadata.version`
3. `nodes`
4. 每个节点的 `id`
5. 每个节点的 `title`

### 结构规则

1. `id` 在整棵树中必须唯一。
2. `title` 允许重复，但不推荐。
3. `children` 允许为空或缺省。
4. 至少要存在一个叶子节点。
5. 不允许循环引用。

### 运行规则

1. 只有叶子节点可作为 checkpoint 的归类目标。
2. 非叶子节点只用于展示路径和父子结构。
3. 模版树解析后需拍平为叶子目标集合，供匹配使用。

## 9. 核心数据结构

## 9.1 新增模版领域模型

建议新增以下模型：

### `ProjectChecklistTemplateFile`

顶层对象，表示解析后的模版文件。

建议字段：

1. `metadata`
2. `nodes`

### `ProjectChecklistTemplateNode`

表示树中的单个节点。

建议字段：

1. `id`
2. `title`
3. `children`

### `TemplateLeafTarget`

表示拍平后的一个叶子目标。

建议字段：

1. `leaf_id`
2. `leaf_title`
3. `path_ids`
4. `path_titles`
5. `path_text`

示例：

```json
{
  "leaf_id": "adgroup-create-optimize-goal",
  "leaf_title": "Optimize Goal",
  "path_ids": ["adgroup", "adgroup-create", "adgroup-create-optimize-goal"],
  "path_titles": ["Ad Group", "Create Ad Group", "Optimize Goal"],
  "path_text": "Ad Group / Create Ad Group / Optimize Goal"
}
```

## 9.2 扩展 Checkpoint 模型

`Checkpoint` 新增字段：

1. `template_leaf_id`
2. `template_path_ids`
3. `template_path_titles`
4. `template_match_confidence`
5. `template_match_reason`
6. `template_match_low_confidence`

语义说明：

1. `template_leaf_id` 是最终归类锚点。
2. `template_path_titles` 用于渲染和展示。
3. `template_match_confidence` 用于排序和人工复核。
4. `template_match_reason` 解释为何命中该节点。
5. `template_match_low_confidence` 标识是否为兜底归类。

## 9.3 扩展 TestCase 模型

`TestCase` 继承以下字段：

1. `template_leaf_id`
2. `template_path_ids`
3. `template_path_titles`
4. `template_match_confidence`
5. `template_match_low_confidence`

产品规则：

1. testcase 不独立判断归类，直接继承 checkpoint 的归类结果。
2. 若一个 testcase 对应多个 checkpoint，本期仍按当前一对一 / 一对少量生成模式处理，不做多归属扩展。

## 10. 工作流设计

## 10.1 总体流程

指定 `template_file_path` 时，工作流演进为：

```md
input_parser
  -> project_template_loader
  -> context_research
  -> checkpoint_generator_with_template_binding
  -> checkpoint_evaluator
  -> evidence_mapper
  -> draft_writer
  -> structure_assembler
  -> reflection
```

其中新增或变化的关键点有：

1. 增加 `project_template_loader`，负责读取并解析本地模版文件。
2. `checkpoint_generator` 在生成 checkpoint 时必须绑定模版叶子。
3. `draft_writer` 生成 testcase 时继承模版路径。
4. 输出阶段按模版路径构造 checklist 树。

## 10.2 模版加载阶段

### 目标

在进入 LLM 生成前，先把模版文件解析成可消费的数据结构。

### 处理步骤

1. 读取 `template_file_path`
2. 解析 YAML
3. 校验树结构合法性
4. 拍平叶子节点，生成 `TemplateLeafTarget` 列表
5. 将以下内容写入工作流状态：
   - `project_template`
   - `template_leaf_targets`

### 失败策略

以下情况直接失败：

1. 文件不存在
2. YAML 语法错误
3. 结构校验失败
4. 没有任何叶子节点

## 10.3 Checkpoint 强制归类阶段

### 目标

让每个 checkpoint 在生成时就绑定一个模版叶子路径。

### 推荐实现

1. 继续以 PRD facts 为内容输入。
2. 同时把拍平后的模版叶子路径列表注入 prompt。
3. 要求 LLM 为每个 checkpoint 返回：
   - checkpoint 内容
   - 选中的 `template_leaf_id`
   - 置信度
   - 是否低置信度
   - 匹配理由
4. 后处理阶段验证 `template_leaf_id` 是否存在于叶子目标集合。
5. 如果 LLM 返回非法叶子 ID，则判为生成失败并触发重试或报错。

### 关键约束

1. 一个 checkpoint 只能归属于一个模版叶子。
2. 一个模版叶子可以挂多个 checkpoint。
3. 不允许 checkpoint 归属到非叶子节点。
4. 允许低置信度命中，但必须给出合法叶子。

## 10.4 TestCase 生成阶段

### 目标

testcase 必须继承 checkpoint 的模版归属，不再重新分类。

### 处理方式

1. `draft_writer` 读取 checkpoint 的模版路径。
2. 在 prompt 中把该路径作为强约束传入。
3. 生成出的 testcase 自动写回对应的模版字段。
4. `structure_assembler` 负责兜底补齐这些字段，避免 LLM 丢失。

### 产品规则

1. testcase 标题、步骤、预期结果仍由 checkpoint 和 facts 驱动。
2. 模版路径只决定“属于哪里”，不直接决定“写什么步骤”。

## 10.5 最终树渲染阶段

### 目标

让最终 Markdown/XMind 直接以模版树为骨架渲染。

### 渲染规则

1. 先重建完整模版树。
2. 按 `template_leaf_id` 将 checkpoint / testcase 填充到对应叶子节点下。
3. 没有命中内容的模版节点仍保留在输出中，可标记为空。
4. 不创建模版外节点。

### 展示建议

1. 叶子节点下展示 testcase 列表。
2. 低置信度 testcase 在标题或备注中增加标记，如 `[Low Confidence]`。
3. 对于空叶子，可选择展示“未覆盖”或保持空节点。

## 11. 匹配与归类规则

## 11.1 匹配输入

归类决策建议综合以下信息：

1. checkpoint 标题
2. checkpoint objective
3. fact 描述
4. source section
5. branch_hint
6. 叶子路径文本
7. 叶子父路径上下文

## 11.2 匹配输出

每个 checkpoint 的归类输出至少包含：

1. `template_leaf_id`
2. `template_match_confidence`
3. `template_match_low_confidence`
4. `template_match_reason`

## 11.3 低置信度规则

建议初版采用如下规则：

1. 置信度高于阈值时，标记为正常命中。
2. 置信度低于阈值但仍能选出最相近叶子时，标记为低置信度命中。
3. 不允许输出“无匹配”。

初版阈值建议：

- `confidence >= 0.75`：正常命中
- `confidence < 0.75`：低置信度命中

阈值可在后续实现中参数化。

## 11.4 人工复核信号

以下结果应进入重点复核：

1. `template_match_low_confidence = true`
2. 同一个叶子下聚集了大量语义无关的 checkpoint
3. 某些叶子长期为空且与项目预期不符

## 12. 输出与对外契约

## 12.1 运行请求

`CaseGenerationRequest` 新增：

```json
{
  "file_path": "/abs/path/to/prd.md",
  "template_file_path": "/abs/path/to/project-checklist.yaml"
}
```

兼容策略：

1. `template_file_path` 为可选字段。
2. 不传时保持旧行为。

## 12.2 运行结果

运行结果中的 `test_cases`、`checkpoints`、中间工件建议新增模版归属字段。

## 12.3 Markdown/XMind

输出契约变化：

1. 树骨架来源从“自由规划的结果树”切换为“模版树”。
2. 节点顺序遵循模版文件中的定义顺序。
3. 低置信度标记需要在展示层保留。

## 13. 评估与验收

## 13.1 新增评估维度

建议在现有结构化评估中新增以下维度：

1. `template_binding_coverage`
   - 所有 checkpoint 是否都绑定了合法模版叶子
2. `template_leaf_case_coverage`
   - 被命中的叶子数 / 总叶子数
3. `low_confidence_rate`
   - 低置信度 checkpoint 占比

## 13.2 验收标准

本期通过标准建议为：

1. 指定模版文件的运行中，所有 checkpoint 都有合法 `template_leaf_id`
2. 所有 testcase 都继承模版路径字段
3. 最终 Markdown/XMind 中不存在模版外结构节点
4. 非法模版文件会被明确拦截
5. 低置信度结果可被清楚展示

## 13.3 测试范围

建议覆盖以下测试：

1. 模版文件解析成功
2. 模版文件非法结构失败
3. 模版树拍平结果正确
4. checkpoint 绑定合法叶子
5. testcase 继承模版路径
6. 最终树只使用模版节点
7. 低置信度标记透传到输出
8. 无模版模式向后兼容

## 14. 风险与权衡

### 14.1 主要风险

1. 模版树设计过细时，LLM 归类难度会升高，低置信度比例可能偏高。
2. 模版树设计过粗时，结构稳定了，但对测试执行的帮助不足。
3. 强制绑定后，某些 PRD facts 可能被迫挂到“最相近而不完美”的叶子下。

### 14.2 缓解策略

1. 通过低置信度标记把不确定性显式暴露，而不是隐藏。
2. 允许项目方逐步迭代模版树，而不是一次性追求完美。
3. 在评估中持续统计空叶子、低置信度叶子和过载叶子。

## 15. 分阶段落地建议

### Phase 1：最小可用版本

1. 新增 `template_file_path`
2. 支持模版文件解析和叶子拍平
3. checkpoint 强制绑定模版叶子
4. testcase 继承模版路径
5. Markdown 输出按模版树渲染

### Phase 2：质量增强

1. 增加低置信度标记展示
2. 增加模板绑定评估维度
3. 支持空叶子覆盖分析

### Phase 3：可维护性增强

1. 支持模版文件 lint/validate 命令
2. 支持模版变更后的影响分析
3. 支持更细粒度的匹配解释和调试信息

## 16. 开放问题

本期建议先按以下默认答案实现，不阻塞主流程：

1. **是否允许挂到非叶子节点**
   - 结论：不允许。

2. **无法高置信度命中时是否中断生成**
   - 结论：不中断，挂到最相近叶子并标记低置信度。

3. **模版文件是否支持 JSON**
   - 结论：本期仅支持 YAML。

4. **是否保留当前通用模版系统**
   - 结论：保留；项目级 checklist 模版是新增能力，不替换现有通用模版 prompt 约束能力。

## 17. 结论

本 PRD 建议引入“本地项目级 checklist 模版文件 + checkpoint 阶段强制归类”的新能力。

核心结论如下：

1. 模版文件通过 `template_file_path` 传入，本地解析，不走数据库。
2. 模版采用树形多层 YAML，叶子节点是唯一合法归类目标。
3. 每个 checkpoint 必须绑定一个模版叶子，testcase 继承该绑定结果。
4. 最终 Markdown/XMind 以模版树为骨架渲染，不再允许自由生长结构节点。
5. 低置信度归类允许存在，但必须显式标记并可人工复核。

该方案能在保留现有工作流总体结构的前提下，显著提升项目输出结构的稳定性、可维护性和可审阅性。
