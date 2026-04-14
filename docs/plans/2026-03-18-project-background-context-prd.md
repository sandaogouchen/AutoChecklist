# AutoChecklist PRD: 项目背景知识与项目级 Checklist 模版

**日期：** 2026-03-18  
**状态：** Draft  
**作者：** Codex  
**适用范围：** AutoChecklist API、报告生成工作流、项目配置能力

## 1. 背景

当前 AutoChecklist 以单次运行 (`run`) 为中心，输入主要依赖 `file_path`，系统缺少“项目”这一长期上下文载体。实际使用中，同一个项目往往具有稳定的业务背景、术语、风险点、历史约束，以及固定的 checklist 结构偏好。仅依赖当次 PRD 或文档内容，会导致以下问题：

1. 模型对项目长期背景理解不足，同一项目多轮生成结果风格不稳定。
2. 报告生成缺乏“项目记忆”，无法持续继承项目特征和历史经验。
3. 某些项目有明确的 checklist 结构要求，例如必须覆盖 `A/B/C` 三层模块，但当前系统无法强制或显式引导模型输出这些模块。

因此需要引入 `project_id`，并在项目维度上新增两类能力：

1. **项目背景知识**：支持对项目背景知识的增删改查，并在每轮报告生成时注入上下文，帮助模型理解项目特点。
2. **项目级 Checklist 模版**：支持用户指定项目必须包含的 checklist 模块结构，例如 `A/B/C` 三层。该能力与背景知识同属“项目背景”，但必须独立建模、独立接口、独立生效逻辑。

## 2. 目标

### 2.1 产品目标

1. 为每次运行建立明确的 `project_id` 归属。
2. 支持项目背景知识的结构化 CRUD 管理。
3. 支持项目级 checklist 模版配置，允许用户声明“必须包含的模块”。
4. 在每轮报告生成中自动加载项目背景信息，稳定模型对项目的理解。
5. 在不混淆两类能力的前提下，为后续项目画像、项目规则、项目资产扩展留出空间。

### 2.2 成功标准

1. 新建运行时可以显式关联 `project_id`。
2. 用户可以通过接口完成项目背景知识的新增、查询、编辑、删除。
3. 用户可以通过接口完成项目级 checklist 模版的配置与查询。
4. 每轮报告生成都能读取并注入项目背景快照。
5. 生成结果中能体现 checklist 模版要求，至少保证必须模块被输出或被显式标记缺失。

## 3. 非目标

本期不包含以下内容：

1. 不做跨项目知识复用与推荐。
2. 不做复杂权限系统，仅预留 `created_by` / `updated_by` 等字段。
3. 不做背景知识自动抽取或自动清洗，全部以人工录入和维护为主。
4. 不做通用模板 DSL，本期只支持项目级 checklist 必填模块配置。
5. 不做 UI 设计，本 PRD 聚焦数据模型、接口与工作流行为。

## 4. 核心设计原则

### 4.1 同属项目背景，分开实现

虽然“项目背景知识”和“项目级 checklist 模版”都归属于项目背景，但二者解决的问题不同，必须拆开：

1. **项目背景知识**解决“模型理解项目”的问题，核心是语义补充。
2. **项目级 checklist 模版**解决“输出结构必须满足项目规范”的问题，核心是输出约束。

二者共享 `project_id`，但在以下层面必须分离：

1. 独立数据模型
2. 独立接口
3. 独立校验逻辑
4. 独立注入方式
5. 独立版本管理

### 4.2 兼顾长期可维护性

避免把所有项目上下文都塞进一个大文本字段中，否则后续难以治理、难以审计、难以分层使用。推荐采用“项目实体 + 两类子资源”的结构。

## 5. 目标用户与用户故事

### 5.1 目标用户

1. PM / QA / 测试策略负责人
2. 使用 AutoChecklist 生成项目报告和 checklist 的业务团队
3. 需要稳定复用项目背景的运营或产品支持人员

### 5.2 用户故事

1. 作为项目负责人，我希望先创建或指定 `project_id`，让同一项目的多轮生成共享上下文。
2. 作为 QA，我希望维护项目背景知识，例如业务约束、名词解释、历史事故和测试重点，让模型更懂这个项目。
3. 作为测试负责人，我希望为某个项目指定 checklist 的固定结构，例如必须包含 `A/B/C` 三层模块。
4. 作为报告使用者，我希望每轮生成的报告都自动带入项目背景，不用每次重复写提示词。

## 6. 方案对比

### 方案 A：把所有项目背景放进一个自由文本字段

优点：

1. 实现简单
2. 接口少

缺点：

1. 背景知识与 checklist 模版语义混杂
2. 无法单独治理“必须模块”
3. 后续难以做版本、启停、审计和回放

### 方案 B：项目下挂两个独立子资源

优点：

1. 语义清晰，便于后续扩展
2. 背景理解与结构约束可以分别演进
3. 更适合在工作流中分阶段注入

缺点：

1. 数据模型和接口略多
2. 实现成本高于方案 A

### 结论

采用 **方案 B**。这是本 PRD 的推荐实现方案。

## 7. 功能方案

## 7.1 引入 `project_id`

### 需求描述

系统新增项目维度。每次运行都应可关联到一个项目，项目作为背景知识和 checklist 模版的归属容器。

### 设计要求

1. 新增 `Project` 实体。
2. 运行创建接口增加 `project_id` 字段。
3. 为兼容现有调用，第一阶段可允许 `project_id` 为空；第二阶段升级为必填。
4. 每次运行开始时，系统基于 `project_id` 读取项目背景快照。

### 推荐字段

`Project`

- `project_id`
- `project_name`
- `description`
- `status` (`active` / `archived`)
- `created_at`
- `updated_at`

## 7.2 功能一：项目背景知识 CRUD

### 需求描述

用户可以为某个项目维护多条背景知识。背景知识将作为模型理解项目特性的上下文来源，在每轮报告生成时自动注入。

### 能力范围

1. 新增背景知识
2. 查询背景知识列表
3. 查询单条背景知识详情
4. 编辑背景知识
5. 删除背景知识
6. 启用 / 停用背景知识

### 推荐数据模型

`ProjectBackgroundKnowledge`

- `knowledge_id`
- `project_id`
- `title`
- `content`
- `category`
- `source`
- `status` (`active` / `inactive`)
- `priority`：数值越小优先级越高
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

### 字段说明

1. `title`：知识标题，例如“支付链路特殊约束”。
2. `content`：背景正文，建议为可直接给模型阅读的自然语言内容。
3. `category`：便于筛选，建议支持 `business_rule`、`domain_term`、`risk_history`、`architecture_note`、`test_focus`、`other`。
4. `source`：可记录来源，如 `manual`、`postmortem`、`prd`、`wiki`。
5. `status`：停用后不再参与后续生成。
6. `priority`：用于控制注入顺序，重要知识优先进入上下文。

### 产品规则

1. 同一项目下允许存在多条背景知识。
2. 仅 `active` 状态的背景知识参与运行时注入。
3. 删除为逻辑删除优先；如使用物理删除，需要保证历史运行快照仍可回放。
4. 建议限制单条 `content` 长度，避免无上限膨胀上下文。

## 7.3 功能二：项目级 Checklist 模版

### 需求描述

用户可以为某个项目指定 checklist 输出必须包含的模块结构。例如某项目 checklist 必须包含 `A/B/C` 三层，系统需在生成时将此要求作为显式约束传递给模型。

### 关键说明

该能力虽然同属项目背景，但**不是背景知识条目的一种**，原因如下：

1. 它不是“补充理解”的信息，而是“约束输出结构”的规则。
2. 它需要独立校验是否命中“必须模块”。
3. 它可能存在版本和启停，不适合混入普通知识条目。

### 推荐数据模型

`ProjectChecklistTemplate`

- `template_id`
- `project_id`
- `template_name`
- `description`
- `required_modules`
- `status` (`active` / `inactive`)
- `version`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

其中 `required_modules` 为数组，数组元素建议结构如下：

- `module_key`
- `module_name`
- `module_description`
- `order`
- `required`，本期固定为 `true`

### 示例

```json
{
  "template_name": "ABC 三层检查模版",
  "required_modules": [
    {
      "module_key": "layer_a",
      "module_name": "A层",
      "module_description": "基础能力与输入校验",
      "order": 1,
      "required": true
    },
    {
      "module_key": "layer_b",
      "module_name": "B层",
      "module_description": "核心业务流程",
      "order": 2,
      "required": true
    },
    {
      "module_key": "layer_c",
      "module_name": "C层",
      "module_description": "异常与回退链路",
      "order": 3,
      "required": true
    }
  ]
}
```

### 产品规则

1. 一个项目同一时刻仅允许一个 `active` checklist 模版。
2. 模版修改后应产生新版本，历史运行记录绑定旧版本快照。
3. 若运行时存在 active 模版，则模型提示词中必须显式声明“以下模块必须出现在结果中”。
4. 若结果未覆盖某些必填模块，系统需在报告或质量结果中标记缺失模块。

## 8. 运行时行为设计

## 8.1 报告生成上下文注入

### 目标

在每轮报告生成中，将项目背景知识与 checklist 模版共同纳入上下文，但分两段注入。

### 注入原则

1. **背景知识**以“项目理解上下文”方式注入。
2. **checklist 模版**以“输出结构约束”方式注入。
3. 两类内容不能混写为一个段落，避免模型误解。

### 推荐上下文结构

```text
[Project Context]
Project ID: xxx
Project Name: xxx

[Background Knowledge]
1. ...
2. ...
3. ...

[Checklist Template Requirements]
The output must include the following required modules:
1. A层 - 基础能力与输入校验
2. B层 - 核心业务流程
3. C层 - 异常与回退链路
```

### 生效节点

项目背景快照应在每一轮生成开始前加载，并贯穿以下环节：

1. 需求理解 / 研究
2. checkpoint / checklist 规划
3. 报告生成
4. 迭代回流后的再次生成

### 关键要求

1. **每轮**都重新从快照加载，而不是只在首轮加载。
2. 回流重试时沿用同一份项目快照，保证轮次间一致性。
3. 若中途项目配置被修改，不影响当前运行，下一次运行才读取新版本。

## 8.2 运行快照

为保证可审计和可回放，每次运行需要保存项目背景快照。

推荐新增：

`RunProjectContextSnapshot`

- `project_id`
- `project_name`
- `background_knowledge_items`
- `checklist_template`
- `captured_at`

### 价值

1. 便于排查为什么本次报告生成成这样。
2. 便于回放历史结果。
3. 便于后续做版本对比和效果分析。

## 9. 接口设计

## 9.1 项目接口

### `POST /api/v1/projects`

创建项目。

请求示例：

```json
{
  "project_name": "支付对账项目",
  "description": "面向支付对账链路的 checklist 生成"
}
```

响应示例：

```json
{
  "project_id": "proj_123",
  "project_name": "支付对账项目",
  "description": "面向支付对账链路的 checklist 生成",
  "status": "active"
}
```

### `GET /api/v1/projects/{project_id}`

查询项目详情。

### `PATCH /api/v1/projects/{project_id}`

更新项目基础信息。

## 9.2 项目背景知识接口

### `POST /api/v1/projects/{project_id}/background-knowledge`

新增一条项目背景知识。

请求示例：

```json
{
  "title": "支付状态最终一致性说明",
  "content": "支付成功后账单与流水可能存在短暂延迟，测试时需要考虑异步补偿。",
  "category": "business_rule",
  "source": "manual",
  "priority": 10
}
```

### `GET /api/v1/projects/{project_id}/background-knowledge`

查询项目背景知识列表，支持按 `status`、`category` 过滤。

### `GET /api/v1/projects/{project_id}/background-knowledge/{knowledge_id}`

查询单条背景知识详情。

### `PATCH /api/v1/projects/{project_id}/background-knowledge/{knowledge_id}`

编辑背景知识。

### `DELETE /api/v1/projects/{project_id}/background-knowledge/{knowledge_id}`

删除背景知识。

## 9.3 项目级 Checklist 模版接口

### `PUT /api/v1/projects/{project_id}/checklist-template`

创建或覆盖当前项目的 checklist 模版。

请求示例：

```json
{
  "template_name": "ABC 三层检查模版",
  "description": "该项目输出必须覆盖 A/B/C 三层",
  "required_modules": [
    {
      "module_key": "layer_a",
      "module_name": "A层",
      "module_description": "基础能力与输入校验",
      "order": 1,
      "required": true
    },
    {
      "module_key": "layer_b",
      "module_name": "B层",
      "module_description": "核心业务流程",
      "order": 2,
      "required": true
    },
    {
      "module_key": "layer_c",
      "module_name": "C层",
      "module_description": "异常与回退链路",
      "order": 3,
      "required": true
    }
  ]
}
```

### `GET /api/v1/projects/{project_id}/checklist-template`

查询当前生效的 checklist 模版。

### `PATCH /api/v1/projects/{project_id}/checklist-template`

更新当前模版，生成新版本。

### `DELETE /api/v1/projects/{project_id}/checklist-template`

停用当前模版。

## 9.4 运行接口调整

### `POST /api/v1/case-generation/runs`

请求体新增字段：

- `project_id`

请求示例：

```json
{
  "project_id": "proj_123",
  "file_path": "/absolute/path/to/prd.md",
  "language": "zh-CN",
  "model_config": {
    "temperature": 0.2,
    "max_tokens": 1600
  }
}
```

### 行为变化

1. 若存在 `project_id`，系统先加载项目背景快照，再开始本轮生成。
2. 若未传 `project_id`，系统按旧逻辑运行，但不带项目背景能力。
3. 响应中建议补充：
   - `project_id`
   - `project_context_snapshot`
   - `applied_background_knowledge_count`
   - `applied_checklist_template_version`

## 10. 生成与校验规则

## 10.1 背景知识使用规则

1. 按 `priority` 从高到低注入。
2. 仅注入 `active` 条目。
3. 注入内容应保持摘要化、结构化，避免原文冗长堆叠。

## 10.2 Checklist 模版使用规则

1. 结果必须覆盖 `required_modules`。
2. 若模型输出缺失必填模块，需要在质量报告中标记：
   - `missing_required_modules`
3. 若模板要求与 PRD 原始内容冲突，以“保留真实需求 + 标记模板缺口”的方式处理，不应强行伪造内容。

## 10.3 回流规则

1. 迭代回流时沿用首轮锁定的项目背景快照。
2. 若某轮因“缺失必填模块”导致质量不达标，可将其作为回流原因之一。

## 11. 验收标准

### 11.1 功能验收

1. 可创建项目，并获得唯一 `project_id`。
2. 可对项目背景知识完成增删改查。
3. 可为项目设置 checklist 模版，并查询当前生效版本。
4. 创建运行时可指定 `project_id`。
5. 每轮生成均能读取同一份项目背景快照。

### 11.2 结果验收

1. 当项目存在背景知识时，生成结果明显体现项目语境。
2. 当项目存在 checklist 模版时，结果包含所有必填模块，或显式给出缺失模块。
3. 历史运行可以追溯当时使用的背景知识与模版快照。

## 12. 实施建议

建议分两期实施：

### 第一期

1. 引入 `project_id`
2. 完成项目背景知识 CRUD
3. 在运行时注入背景知识

### 第二期

1. 完成项目级 checklist 模版配置
2. 在生成和质量校验中引入必填模块校验
3. 补充运行快照与模板版本追踪

## 13. 风险与开放问题

### 风险

1. 背景知识过多会挤占模型上下文。
2. 模版约束过强可能与真实 PRD 内容冲突。
3. 若项目配置频繁变更，历史结果解释成本会上升。

### 开放问题

1. 项目背景知识是否需要支持富文本或附件引用。
2. checklist 模版是否需要支持“建议模块”和“可选模块”。
3. 项目是否需要支持多份模版并按场景切换。
4. 运行结果是否需要显式回传“哪些背景知识被使用”。

## 14. 最终结论

本需求应以 `project_id` 为主键引入项目维度，并在该维度下新增两类独立能力：

1. **项目背景知识**：负责补充模型对项目特点的理解。
2. **项目级 checklist 模版**：负责约束输出结构，确保必须模块被覆盖。

二者同属项目背景，但必须分开实现。接口上采用“项目主资源 + 两类子资源 + 运行接口补充 `project_id`”的方式最清晰，也最利于后续扩展。
