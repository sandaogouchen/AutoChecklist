# templates/_ANALYSIS.md — 模版目录分析

> 分析分支自动生成 · 源分支 `main` · PR #23 新增目录

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `templates/` |
| 文件数 | 1 |
| 分析文件 | 1 |
| 目录职责 | 存放项目级 Checklist 模版 YAML 文件，供 `template_loader` 节点和 `/api/v1/templates` 端点读取 |
| 引入 PR | #23 — Checklist 模版强制层级字段与约束机制 |

## §2 文件清单

| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | `brand_spp_consideration.yaml` | D-数据文件 | ~56 | brand S++ consideration 固定模版，含 2 级强制层级 |

## §3 逐文件分析

### §3.1 brand_spp_consideration.yaml

- **类型**: D-数据文件（YAML 模版）
- **职责**: 定义 brand S++ consideration 场景的标准 Checklist 骨架结构
- **解析入口**: `ProjectTemplateLoader.load()` → `ProjectChecklistTemplateFile`

#### A. Metadata 段

| 字段 | 值 | 说明 |
|------|-----|------|
| `name` | `"brand S++ consideration"` | 模版名称，`load_by_name("brand_spp_consideration")` 通过文件名匹配 |
| `version` | `"1.0.0"` | 语义版本号 |
| `description` | `"brand S++ consideration 固定模版"` | 描述信息 |
| `mandatory_levels` | `[1, 2]` | **强制层级列表**：第 1 层 + 第 2 层节点为强制节点 |

#### B. 节点树结构

```
nodes (depth=1, 强制 ∵ depth ∈ [1,2])
├── doc: 文档信息
│   ├── prd: 需求文档 (depth=2, 强制)
│   │   └── prd-url: 需求文档链接 (depth=3, 非强制)
│   ├── FE-tech-design: 前端技术设计 (depth=2, 强制)
│   ├── BE-tech-design: 后端技术设计 (depth=2, 强制)
│   └── test-plan: 测试方案 (depth=2, 强制)
├── create: 新建
│   ├── campaign: campaign (depth=2, 强制)
│   │   ├── campaign-name: Campaign name (P2, mandatory: true)
│   │   ├── campaign-objective: Campaign objective (P0)
│   │   └── campaign-budget: Campaign budget (P1)
│   ├── adgroup: adgroup (depth=2, 强制)
│   │   ├── adgroup-targeting: Adgroup targeting (P1)
│   │   └── adgroup-bid: Adgroup bid (P0)
│   └── ad: ad (depth=2, 强制)
│       ├── ad-creative: Ad creative (P1)
│       └── ad-landing-page: Ad landing page (P1)
```

#### C. 强制性分析

| 判定规则 | 适用节点 | 节点数 |
|----------|----------|--------|
| depth ∈ mandatory_levels (`[1,2]`) | doc, create (depth=1); prd, FE-tech-design, BE-tech-design, test-plan, campaign, adgroup, ad (depth=2) | 9 |
| mandatory: true (节点级) | campaign-name | 1 |
| 路径连接（强制节点祖先） | 无额外（depth 1-2 已覆盖） | 0 |
| **总强制节点数** | | **10** |
| 非强制叶子节点 | prd-url, campaign-objective, campaign-budget, adgroup-targeting, adgroup-bid, ad-creative, ad-landing-page | 7 |

强制骨架构建后的 `MandatorySkeletonNode` 树：

```
__mandatory_root__ (depth=0, virtual)
├── doc (depth=1, is_mandatory=true)
│   ├── prd (depth=2, is_mandatory=true)
│   ├── FE-tech-design (depth=2, is_mandatory=true)
│   ├── BE-tech-design (depth=2, is_mandatory=true)
│   └── test-plan (depth=2, is_mandatory=true)
└── create (depth=1, is_mandatory=true)
    ├── campaign (depth=2, is_mandatory=true)
    │   └── campaign-name (depth=3, is_mandatory=true ∵ mandatory:true)
    ├── adgroup (depth=2, is_mandatory=true)
    └── ad (depth=2, is_mandatory=true)
```

注意：`prd-url`（depth=3）不在 mandatory_levels 中且 `mandatory: false`，所以不纳入骨架。但 `campaign-name`（depth=3）因 `mandatory: true` 被纳入，其祖先 `campaign`（depth=2）本已在 mandatory_levels 中故无需额外路径连接。

#### D. 字段使用分析

| YAML 字段 | 对应 Pydantic 模型字段 | 使用节点数 | 说明 |
|------------|----------------------|-----------|------|
| `id` | `ProjectChecklistTemplateNode.id` | 17 (全部) | 必填，全局唯一 |
| `title` | `ProjectChecklistTemplateNode.title` | 17 (全部) | 必填，节点显示名 |
| `priority` | `ProjectChecklistTemplateNode.priority` | 7 (叶子层) | P0-P2，用于 `original_metadata` 传递 |
| `mandatory` | `ProjectChecklistTemplateNode.mandatory` | 1 | 仅 `campaign-name` 显式标记 |
| `children` | `ProjectChecklistTemplateNode.children` | 5 (非叶子) | 递归嵌套 |
| `description` | `ProjectChecklistTemplateNode.description` | 0 | 本模版未使用 |
| `note` | `ProjectChecklistTemplateNode.note` | 0 | 本模版未使用 |
| `status` | `ProjectChecklistTemplateNode.status` | 0 | 本模版未使用 |

#### E. 树统计

| 指标 | 值 |
|------|-----|
| 总节点数 | 17 |
| 最大深度 | 3 |
| depth=1 节点 | 2 (doc, create) |
| depth=2 节点 | 7 |
| depth=3 叶子 | 8 |
| 叶子节点（含 depth=2 叶子） | 11 |
| 带 priority 的节点 | 7 |
| mandatory: true 的节点 | 1 |

## §4 设计模式分析

### §4.1 YAML 模版约定

```
metadata:
  name: string          # 模版名称
  version: string       # 语义版本号
  description: string   # 描述信息
  mandatory_levels: [int]  # 强制层级列表 (PR #23 新增)

nodes:                  # 节点树
  - id: string          # 唯一标识
    title: string       # 显示名称
    priority: string    # P0-P3 (可选)
    mandatory: bool     # 节点级强制标记 (PR #23 新增, 默认 false)
    description: string # 描述 (可选)
    note: string        # 备注 (可选)
    status: string      # 状态 (可选)
    children: [node]    # 递归子节点
```

约定特征：
- **ID 命名**: 使用 kebab-case（如 `FE-tech-design`、`ad-landing-page`），非 snake_case
- **层级语义**: depth=1 为业务大类（文档、操作类型），depth=2 为功能模块，depth=3 为具体检查项
- **优先级分配**: 仅叶子节点携带 priority，非叶子节点不设优先级
- **mandatory 使用策略**: 优先通过 `mandatory_levels` 批量标记，个别例外节点使用 `mandatory: true`

### §4.2 模版目录扫描机制

```
API/节点请求
  → Settings.template_dir  (默认 "templates")
  → Path(template_dir).glob("*.y*ml")  匹配所有 YAML
  → 逐文件 ProjectTemplateLoader.load()
  → 返回 ProjectChecklistTemplateFile 列表
```

当前 `templates/` 目录仅包含 1 个模版文件。扫描机制支持多模版共存，文件名即为模版的 `load_by_name()` 查找键（stem 部分，不含扩展名）。

### §4.3 文件名与 template_name 的映射

| 文件名 | stem (load_by_name 键) | metadata.name |
|--------|----------------------|---------------|
| `brand_spp_consideration.yaml` | `brand_spp_consideration` | `"brand S++ consideration"` |

注意：`load_by_name()` 使用 **文件名 stem** 而非 `metadata.name` 进行匹配，两者可能不一致。`list_templates` 端点的返回中 `name` 字段优先取 `metadata.name`，这可能导致前端展示的名称与请求 `get_template()` 所需的 `{name}` 参数不匹配。

## §5 补充观察

1. **单模版现状**: 当前仅一个模版文件，强制层级机制的通用性尚未验证。建议后续添加更多场景的模版（如 performance、compliance 等）以验证机制的普适性

2. **mandatory_levels 与 mandatory 字段的冗余**:
   - `mandatory_levels: [1, 2]` 已将 depth 1-2 的所有 9 个节点标记为强制
   - `campaign-name` 的 `mandatory: true` 属于额外标记（depth=3 不在 mandatory_levels 中）
   - 设计意图：两种标记机制互补——批量（按层级）+ 精确（按节点），降低模版编写成本

3. **模版版本化**: 当前 `version: "1.0.0"` 为纯标识字段，无版本兼容性检查逻辑。若同一模版存在多版本（如 `brand_spp_consideration_v2.yaml`），需要额外的版本选择机制

4. **模版与 PRD 的对齐风险**:
   - 模版树定义了固定的 Checklist 骨架（如 "新建 > campaign > Campaign name"）
   - 若 PRD 内容与模版骨架严重不匹配，LLM 生成的 checkpoint 将大量进入 overflow 区域
   - 20% 溢出阈值会触发 warning（`structure_assembler._enforce_mandatory_constraints`），但不会阻断生成

5. **YAML 解析安全**:
   - 模版加载使用 `yaml.safe_load()`，可防御 YAML 反序列化攻击
   - 但模版文件来源（用户上传 vs 预置）决定了安全等级——预置模版安全可控，用户上传模版需额外校验

6. **目录位置**: `templates/` 位于项目根目录，与 `app/`、`data/`、`tests/` 同级。这一位置通过 `Settings.template_dir` 可配置，但默认值假设进程工作目录为项目根目录
