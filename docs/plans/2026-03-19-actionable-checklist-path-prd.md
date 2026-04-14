# AutoChecklist PRD: 可操作路径树 Checklist

**日期：** 2026-03-19  
**状态：** Draft  
**作者：** Codex  
**适用范围：** AutoChecklist 工作流、Markdown/XMind 输出、项目上下文注入能力

## 1. 背景

当前 AutoChecklist 已经把 checklist 的层级规划前移到 testcase 草稿生成之前，解决了一部分“树结构漂移”和“后置归并不稳定”的问题。但实际输出仍存在两个明显缺陷：

1. 路径节点过度抽象，很多节点只剩模块名词，例如 `Optimize goal`、`Selection memory`、`Goal options`，测试人员无法直接据此执行操作。
2. 模型对项目中的页面、模块、业务对象归属理解不足，导致层级混乱，例如模块可能被挂到错误的父节点下，或者把同级概念拆成跨层路径。

从实际使用看，测试人员更需要的是“可执行的路径树”，而不是“纯语义归类树”。路径上的每一层不仅要能表达结构归属，还要保留足够的中文操作信息，让用户看到树就知道该怎么测。

## 2. 问题定义

### 2.1 当前问题

当前生成结果主要有以下问题：

1. `business object` 层虽然更清晰，但下钻后的路径节点仍然大量是名词，而不是动作。
2. 原始 testcase 中已经存在的可执行信息，在路径整合阶段被丢失，只在 testcase body 中保留，未进入共享树。
3. 缺少项目级的结构知识，模型只能根据 PRD 片段自由猜测“什么模块属于什么层级”。
4. 树结构缺少“父子合法性约束”，导致部分节点虽然词面相关，但在信息架构上挂错位置。

### 2.2 典型反例

错误形态示例：

```md
## Ad group
### Create ad group page
#### Optimize goal
##### Show on create
```

这种结构虽然表达了归属，但测试人员无法直接从 `Optimize goal -> Show on create` 推导出具体动作。

### 2.3 目标形态

目标输出应更接近以下形式：

```md
## Ad group
### campaign 已处于可创建 ad group 状态
### 用户已进入 `Create Ad Group` 页面
#### 定位 `optimize goal` 模块
##### 检查 `optimize goal` 是否默认可见且可交互
- `optimize goal` 模块在创建阶段显式展示。
- 用户可以主动选择 `optimize goal`，而非仅被动继承。
##### 手动选择一个与默认值不同的 `optimize goal` 选项
##### 点击 `Submit` 提交 ad group
- 提交成功后保存的是用户当前选择的 `optimize goal`。
```

这个形态同时满足：

1. 上层有稳定的业务对象结构。
2. 中下层是测试人员可执行的中文动作。
3. 预期结果仍然能挂在对应操作节点下。

## 3. 产品目标

### 3.1 核心目标

1. 将 checklist 从“语义分组树”升级为“可操作路径树”。
2. 在整合阶段保留原 testcase 中已有的前置条件和操作步骤信息。
3. 为模型补充项目级结构知识，降低层级挂错和概念混层问题。
4. 保持现有 `optimized_tree`、Markdown、XMind 对外契约稳定，避免大规模下游改造。

### 3.2 成功标准

1. 树中 80% 以上的非根路径节点为中文动作短句，而非单纯名词。
2. 给定一个 leaf 路径，测试人员可以直接据此理解要执行的动作，无需回头查看完整 testcase 才知道怎么测。
3. 树中核心模块的父子层级符合项目知识定义，不再频繁出现 `module belongs to wrong parent` 的问题。
4. 原 testcase 中的关键 preconditions 和 steps 不会在整合阶段丢失。
5. Markdown 与 XMind 输出仍继续从 `optimized_tree` 渲染。

## 4. 非目标

本期不追求：

1. 不做通用 DSL 级别的流程编排语言。
2. 不要求所有节点都变成完整自然语言句子，允许保留少量业务对象名词作为稳定结构父节点。
3. 不做全自动项目 ontology 抽取，第一阶段允许项目方人工配置或半结构化输入。
4. 不改变 testcase JSON 的外部结构。

## 5. 目标用户与用户故事

### 5.1 目标用户

1. 需要直接消费 checklist 的 QA / 测试执行人员
2. 需要审核测试覆盖结构的测试策略负责人
3. 需要为项目维护长期上下文的产品/QA owner

### 5.2 用户故事

1. 作为测试执行人员，我希望树上的每个路径节点都表达明确操作，而不是抽象名词，这样我可以直接按树执行测试。
2. 作为测试负责人，我希望树的结构稳定且符合项目模块层级，而不是每次都由模型自由发挥。
3. 作为项目 owner，我希望系统知道 `Campaign`、`Ad group`、`Create Ad Group page`、`optimize goal` 等概念的归属关系。
4. 作为结果使用者，我希望原 testcase 中有价值的步骤信息能被整合进树，而不是只剩归类标签。

## 6. 核心设计原则

### 6.1 结构稳定，动作可执行

树的上层负责稳定结构，下层负责可执行动作。

推荐分工如下：

1. **结构层**：`Campaign`、`Ad group`、`Creative`、`Reporting` 等业务对象
2. **状态/入口层**：如“campaign 已处于可创建 ad group 状态”、“用户已进入 `Create Ad Group` 页面”
3. **操作层**：如“定位 `optimize goal` 模块”、“点击 `Submit` 提交 ad group”
4. **结果层**：对应预期结果

### 6.2 保留原始 testcase 信息

整合阶段不能只消费抽象语义节点，还必须显式吸收原 testcase 中的：

1. 前置条件
2. 页面入口
3. 操作步骤
4. 预期结果

不能因为做共享归并，就把“可执行信息”压缩成无法操作的名词。

### 6.3 项目知识先于自由推断

当项目已经明确知道：

1. 哪些模块属于哪个业务对象
2. 哪些页面属于哪个对象
3. 哪些控件属于哪个页面
4. 哪些状态是前置条件，哪些是页面操作，哪些是结果

则系统应优先使用项目知识，而不是完全依赖模型从 PRD 自由推断。

### 6.4 合法父子关系必须可校验

树结构不能只靠 prompt 约束，还需要有显式校验，例如：

1. `Campaign -> Ad group`
2. `Ad group -> Create Ad Group page`
3. `Create Ad Group page -> optimize goal`
4. `optimize goal -> 检查/选择/提交结果`

若模型给出的层级违反项目规则，系统应纠正或回退。

## 7. 目标输出规范

### 7.1 节点类型

建议将路径树中的节点区分为以下几类：

1. `business_object`
2. `precondition`
3. `page_entry`
4. `operation`
5. `expected_result`

### 7.2 展示规则

1. `business_object` 可以是名词，例如 `Ad group`
2. `precondition` 必须是中文状态句，例如“campaign 已处于可创建 ad group 状态”
3. `page_entry` 必须包含进入页面/模块的动作，例如“用户已进入 `Create Ad Group` 页面”
4. `operation` 必须是可执行动作，例如“定位 `optimize goal` 模块”
5. `expected_result` 继续以叶子形式展示

### 7.3 语言规范

1. 路径节点以中文为主
2. 页面名、字段名、按钮文案等专有名词保留英文原文并用反引号包裹
3. 不允许出现纯英文抽象标签作为展示节点，例如 `Selection memory`
4. 不允许出现无动作语义的空泛名词节点，例如 `Goal options`

## 8. 功能方案

## 8.1 从“纯语义路径”升级为“结构层 + 操作层”双层整合

### 需求描述

当前 planner 生成的节点更像“语义标签”。新方案要求先规划稳定结构层，再把 testcase 中的前置条件与步骤压入对应路径。

### 设计要求

1. 结构层由 planner 负责，确保业务对象稳定。
2. 操作层由 testcase 原始内容整合生成，避免丢失可执行信息。
3. 最终 `optimized_tree` 同时包含结构信息和操作信息。

### 示例

原 testcase：

```md
#### 前置条件
- 用户已登录 CADS advertiser 账号
- campaign 已处于可创建 ad group 状态
- 用户已进入 `Create Ad Group` 页面

#### 步骤
1. 在页面中定位 `optimize goal` 模块。
2. 检查 `optimize goal` 是否默认可见且可交互。
3. 手动选择一个与默认值不同的 `optimize goal` 选项。
4. 点击 `Submit` 提交 ad group。

#### 预期结果
- `optimize goal` 模块在创建阶段显式展示。
- 用户可以主动选择 `optimize goal`，而非仅被动继承。
- 提交成功后保存的是用户当前选择的 `optimize goal`。
```

整合后目标：

```md
## Ad group
### campaign 已处于可创建 ad group 状态
### 用户已进入 `Create Ad Group` 页面
#### 定位 `optimize goal` 模块
##### 检查 `optimize goal` 是否默认可见且可交互
- `optimize goal` 模块在创建阶段显式展示。
- 用户可以主动选择 `optimize goal`，而非仅被动继承。
##### 手动选择一个与默认值不同的 `optimize goal` 选项
##### 点击 `Submit` 提交 ad group
- 提交成功后保存的是用户当前选择的 `optimize goal`。
```

## 8.2 引入项目级结构知识（Project Ontology）

### 需求描述

系统需要知道项目中的核心对象、页面、模块和控件归属关系。

### 推荐知识结构

建议项目级上下文支持以下信息：

1. **对象层级**
   - `Campaign -> Ad group`
   - `Ad group -> Create Ad Group page`
   - `Creative -> Create creative page`

2. **页面归属**
   - `Create Ad Group page` 属于 `Ad group`
   - `Ad group optimization goal page` 属于 `Ad group`

3. **模块归属**
   - `optimize goal` 属于 `Create Ad Group page`
   - `TTMS account binding` 属于 consideration mode 相关配置

4. **别名映射**
   - `Create ad group page`
   - `Create Ad Group`
   - `ad group creation page`
   这些都应归一到同一 canonical node

### 产品规则

1. 项目 ontology 应优先于 LLM 自由推断。
2. 若 checkpoint 路径与 ontology 冲突，应优先修正到 ontology 定义的父节点下。
3. ontology 缺失时才允许模型退回通用推断。

## 8.3 增加父子合法性约束与回退

### 需求描述

需要在树构建后校验节点挂载是否符合项目层级规则。

### 规则示例

1. `optimize goal` 不能直接挂在 `Campaign` 下
2. `Create Ad Group page` 不应被挂在 `Creative` 下
3. `TTMS account` 不能作为 `optimize goal` 的叶子操作节点

### 回退策略

1. 若节点无法合法挂载到当前父节点，则尝试上移到最近合法祖先
2. 若仍无法确定，则降级为 testcase leaf，不进入共享树
3. 记录质量告警，便于排查 ontology 缺口

## 8.4 保留并归并 testcase 原始操作信息

### 需求描述

当多条 testcase 共享相同操作前缀时，应归并为共享路径；不共享时应保留各自分支。

### 归并原则

1. 完全相同的前置条件可合并
2. 语义等价的操作短句可归一后合并
3. 不允许把不同操作硬合并成一个抽象名词节点
4. 不允许把关键动作“吞掉”只保留结果

### 归并例子

允许合并：

1. “进入 `Create Ad Group` 页面”
2. “用户已进入 `Create Ad Group` 页面”

不应合并为纯名词：

1. `Create Ad Group page`

## 8.5 渲染层保持兼容

### 需求描述

Markdown 和 XMind 继续消费 `optimized_tree`，但展示节点需要以动作短句为主。

### 要求

1. Markdown 树模式继续使用当前 `optimized_tree` 入口
2. XMind 树模式继续使用当前 `optimized_tree` 入口
3. 不改 `test_cases.md` 文件名
4. 不改 `optimized_tree` 外部字段名

## 9. 数据与流程建议

建议将工作流分成四步：

1. **结构规划**
   - 先生成业务对象、页面、核心模块的稳定骨架

2. **项目知识修正**
   - 使用 project ontology 对骨架做父子关系修正

3. **操作信息整合**
   - 将 testcase 的 preconditions + steps 映射到骨架对应分支

4. **结果挂载**
   - 将 expected_results 挂到最贴近的操作节点下

## 10. 验收标准

以下场景必须满足：

1. 给定包含完整操作步骤的 testcase，整合后树中仍能看到关键前置条件和操作步骤。
2. 树中不再出现大量难以执行的纯英文名词节点。
3. `Ad group`、`Campaign`、`Creative` 等核心对象层级稳定。
4. 页面、模块、控件能挂在正确父节点下。
5. 预期结果仍然能正确附着在相应操作节点下。

## 11. 风险与权衡

### 风险 1：路径变长

加入前置条件和操作信息后，树会更深、更长。

应对：

1. 对结构层和操作层做明确分层
2. 控制单节点文案长度，避免冗长句子

### 风险 2：项目知识维护成本

引入 ontology 后，需要项目方维护结构知识。

应对：

1. 第一阶段允许从背景知识中半结构化导入
2. 后续再演进为独立配置能力

### 风险 3：不同 testcase 文案不统一，难以合并

应对：

1. 对操作短句做规范化
2. 增加 alias 和 semantic key 归一

## 12. 里程碑建议

### Phase 1

1. 路径节点改成中文动作短句
2. 在整合阶段保留 preconditions + steps
3. 继续兼容现有 `optimized_tree` 渲染链路

### Phase 2

1. 引入项目级 ontology
2. 加入父子合法性校验与修正

### Phase 3

1. 增加质量报告，标记“路径丢失动作”“节点挂错层级”“ontology 缺失”
2. 提供项目级可维护的结构知识配置能力

## 13. 结论

本期的核心不是继续做“更强的语义归类”，而是把 checklist 从“概念树”升级为“可执行路径树”。

最终目标是：

1. 上层结构稳定
2. 中层路径可操作
3. 下层结果可验证
4. 项目知识可注入
5. 输出形态可被测试人员直接消费

只有这样，树结构优化才不仅“看起来更整齐”，而是真正提升测试执行效率与结果可信度。
