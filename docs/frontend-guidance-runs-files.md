# 前端从零搭建指导（聚焦 Runs 与文件管理）

本文档用于指导从零开始搭建前端，围绕后端已提供的 **runs 接口**（用例生成）与 **文件管理接口**（上传/列表/下载/删除）做可落地的开发思路说明。

约束：

- 不提供接口文档原文（OpenAPI/字段表格那种）；只说明前端需要怎么用、有哪些坑。
- 不做 UI 设计稿；只讲页面、流程、状态管理与工程落地。

---

## 1. 你要先明确的“产品骨架”

后端当前能力决定了前端最小闭环是：

1) 上传/管理输入文件（得到 `file_id`）

2) 基于 `file_id` 发起一次“用例生成 run”（同步执行，可能较慢）

3) 展示 run 的结果（测试用例、质量报告、检查点统计、迭代摘要等）

因此前端建议按 **文件中心 → 发起 run → run 结果页** 的路径拆页面。

---

## 2. 后端接口的“使用视角总览”（不是接口文档）

### 2.1 文件管理（`/api/v1/files`）

实现位置：`app/api/file_routes.py:13`

- 上传：`POST /api/v1/files`（`multipart/form-data`，字段名固定是 `file`）
  - 返回 `201`，payload 里含 `file_id / file_name / content_type / size_bytes / sha256 / created_at`
  - 前端要把 `file_id` 当成后续 runs 的唯一引用
- 列表：`GET /api/v1/files`
  - 返回文件元数据数组；当前没有分页/过滤/搜索
  - 顺序由后端按 `created_at desc`（再按 `file_id desc`）排列：`app/repositories/file_repository.py:59`
- 详情：`GET /api/v1/files/{file_id}`（不存在返回 `404`）
- 下载内容：`GET /api/v1/files/{file_id}/content`
  - 返回二进制内容；`Content-Disposition` 设置为 `attachment`：`app/api/file_routes.py:62`
  - 前端应按“下载文件”处理，不要直接当 JSON 解析
- 删除：`DELETE /api/v1/files/{file_id}`
  - 成功返回 `204`（无 body），不存在返回 `404`

### 2.2 Runs（用例生成）（`/api/v1/case-generation/runs`）

实现位置：`app/api/routes.py:55`

- 创建 run：`POST /api/v1/case-generation/runs`
  - 注意：这是**同步执行**（后端在这个请求里跑完整工作流），所以请求可能会很慢：`app/services/workflow_service.py:114`
  - 返回 `200`，body 是完整 `CaseGenerationRun`（包含 `run_id / status / test_cases / quality_report / artifacts ...`）
- 查询 run：`GET /api/v1/case-generation/runs/{run_id}`
  - 用于“刷新/回看历史结果”（后端从磁盘/缓存读取 `run_result.json`）
  - 不存在返回 `404`：`app/api/routes.py:64`

**重要现实**：当前没有“runs 列表”接口，所以前端如果要做“历史记录列表”，需要自己存（例如 localStorage）或由后端后续补接口。

---

## 3. 前端要理解的核心数据模型（只讲渲染/交互用到的点）

### 3.1 `StoredFile`（文件元数据）

来源：`app/domain/file_models.py:11`

- `file_id`：后续 runs 里引用文件的唯一标识
- `created_at`：后端以 ISO 字符串返回；前端展示时记得按时区格式化
- `sha256 / size_bytes`：用于展示与“是否重复上传”提示（可选）

### 3.2 `CaseGenerationRequest`（发起 run 的输入）

来源：`app/domain/api_models.py:72`

- `file_id`：必填；也兼容旧字段名 `file_path`（但前端建议统一用 `file_id`）
  - **格式要求**：必须是 32 位十六进制字符串（后端会校验并归一化为小写）：`app/domain/api_models.py:117`
  - **安全边界**：`file_id` 只能来自上传接口返回；不可当作服务器本地路径使用（后端已禁止“路径回退读取”）：`app/services/file_service.py:59`
- `template_name` 与 `template_file_id`：二选一，且 `template_name` 优先：`app/domain/api_models.py:77`
- `reference_xmind_file_id`：可选，用于上传后的 XMind 参考文件
- `options.include_intermediate_artifacts`：是否包含中间产物（前端可作为“高级选项”开关）
- `llm_config`（序列化别名 `model_config`）：允许覆盖模型/温度等（建议默认隐藏）
- `project_id`：可选（如果你后续要接入 `projects` 体系）

### 3.3 `CaseGenerationRun`（run 结果）

来源：`app/domain/api_models.py:115`

- `run_id`：结果页路由的主键
- `status`：`pending/running/evaluating/retrying/succeeded/failed`
  - 由于创建接口是同步执行，**正常情况下返回时多为 `succeeded/failed`**
- `test_cases`：前端渲染核心（表格/树/分组都行）
- `quality_report`：质量/覆盖/建议等信息（建议独立一个 Tab）
- `checkpoint_count`：可用于列表页摘要展示
- `iteration_summary`：用于解释“是否重试、最终阶段、分数”等（适合做一块 run 摘要卡）
- `artifacts`：键是产物名，值是服务器文件路径：`app/services/platform_dispatcher.py:96`
  - **注意：这些路径不是可直接访问的 URL**（除非你后续专门加静态文件服务/下载接口）
  - 前端可以“展示 + 一键复制路径”即可，不要尝试 fetch 这些路径

---

## 4. 页面建议（按优先级）

### 4.1 必做页面/模块

1) **文件中心（Files）**

- 功能：上传、列表、删除、下载、查看元信息
- 关键 UI 状态：上传中/失败重试、列表加载中、删除确认与撤销提示（撤销需要后端支持；当前可不做）
- 列表字段建议：`file_name`、`created_at`、`size_bytes`、`content_type`、`sha256(可折叠)`

2) **发起用例生成（New Run）**

- 功能：选择一个 `file_id`（从文件中心选择或内嵌上传），配置可选参数（模板/参考 XMind/语言/高级选项），点击“生成”
- 提交后跳转：拿到 `run_id` 后跳到 Run 详情页

3) **Run 详情（Run Detail）**

- 以 `run_id` 为路由参数，支持：
  - 初次由创建接口返回直接渲染
  - 刷新/回看时通过 `GET /runs/{run_id}` 拉取
- 建议拆 Tabs：
  - `Test Cases`（主内容）
  - `Quality Report`
  - `Run Summary`（status、iteration_summary、checkpoint_count、error）
  - `Artifacts`（只展示/复制）

### 4.2 可选增强（不影响最小闭环）

- **Run 历史列表（本地实现）**：由于后端暂无 runs 列表，前端可在创建成功时把 `{run_id, file_id, file_name, created_at, status}` 写入 localStorage，并提供“最近 20 条”
- **模板选择器**：结合 `GET /api/v1/templates`（`app/api/routes.py:76`）做下拉；与上传模板文件（二选一）

---

## 5. 关键交互流程怎么落地（建议按这个顺序开发）

### 5.1 文件上传 → 得到 `file_id`

- 上传用 `multipart/form-data`，字段名固定 `file`
- 成功后立即把返回的 `file_id` 写入“当前选择的输入文件”状态，并提示“可用于发起生成”
- 上传失败要区分：网络问题（可重试） vs 4xx（提示用户文件不合法/过大等；目前后端未显式限制，但代理层可能限制）

### 5.2 发起 run（同步慢请求）

后端在一个请求中跑完工作流：`app/services/workflow_service.py:114`，所以前端要把它当“长耗时请求”处理：

- 提交按钮进入 `loading` 并禁用重复提交（否则会产生多个 run）
- 使用 `AbortController` 支持用户取消（取消只影响前端，不会终止后端已开始的执行）
- 前端 HTTP 客户端超时时间要显式放宽（例如 2~10 分钟，视部署网关而定）
- 如果部署在有反向代理/网关的环境，注意它们的默认超时可能远小于工作流耗时；这会导致前端“超时失败但后端其实可能已经跑完并落盘”
  - 由于目前没有“创建后立即返回 run_id + 后台执行”的异步模式，前端只能通过**提高超时**和**提示用户耐心等待**来规避
  - 另外：当传入的 `file_id/template_file_id/reference_xmind_file_id` 不存在时，后端会返回 `422`（而非 500），前端应提示用户重新选择/上传文件：`app/api/routes.py:60`

### 5.3 Run 详情页刷新/回看

- 页面加载：`GET /api/v1/case-generation/runs/{run_id}`
- 若 `404`：给出“结果不存在/已清理”的错误页，并提供返回入口
- 若 `status=failed`：展示 `error.code` 与 `error.message`（来源：`app/domain/api_models.py:40`）

---

## 6. 前端状态管理与数据组织建议

建议把状态分 3 层：

1) **会话级 UI 状态**：弹窗、loading、toast、当前 tab

2) **资源缓存**（可用 TanStack Query/SWR，也可自己写）：

- `files` 列表缓存（上传/删除后局部更新）
- `run` 详情缓存（按 `run_id` key）

3) **持久化轻量状态**（localStorage）：

- 最近 runs（因为没有后端 runs 列表）
- 最近使用的模板选择/高级配置（可选）

---

## 7. 错误处理要点（按接口行为来写）

### 7.1 文件接口

- `GET/DELETE /files/{file_id}` 返回 `404` 时：统一提示“文件不存在或已删除”，并从本地选中状态里移除该 `file_id`
- `DELETE` 成功是 `204`，不要尝试 `response.json()`：`tests/integration/test_file_api.py:36`
- `GET /content` 是二进制；不要当 JSON 解析

### 7.2 Runs

- 创建 run 失败：
  - HTTP 非 2xx：按 `detail` 提示；必要时引导用户检查输入文件/模板
    - `422`：常见于 `file_id` 非法（不是 32 位 hex）或引用的文件不存在；提示用户重新选择/上传文件，并引导回到文件中心
  - HTTP 200 但 `status=failed`：展示 `error`，并建议用户下载/复制请求参数以便复现
- 模板加载/校验问题可能返回 `422`：`app/api/routes.py:121`

---

## 8. “Artifacts” 的正确使用方式（避免踩坑）

后端会把很多产物写到服务器磁盘，并在 `artifacts` 中返回其路径，比如：

- `test_cases_markdown`、`quality_report`、`checkpoints`、`checkpoint_coverage`、`optimized_tree` 等：`app/services/platform_dispatcher.py:121`

但这些值是 **服务器文件路径**，默认并不可被浏览器下载。

前端建议：

- 作为“可复制信息”展示（复制路径、复制 JSON）
- 导出能力尽量在前端本地实现：例如把 `run.test_cases` 转为 JSON/Markdown 下载，而不要依赖 `artifacts` 路径

---

## 9. 推荐的迭代开发顺序（保证每一步可验收）

1) 文件中心：上传 + 列表 + 删除 + 下载

2) New Run：选择文件 + 提交 run（只传 `file_id`）+ 跳转详情

3) Run Detail：能渲染 `status/test_cases/quality_report/error`；支持刷新（GET by `run_id`）

4) 再做增强：模板选择、参考 XMind、run 本地历史

---

## 10. 后续如果要“做得更像产品”，优先推动的后端补强点（仅建议）

这些不是前端必须做的，但会显著提升用户体验：

- 增加 `GET /api/v1/case-generation/runs`（分页/过滤），让前端能做真正的 runs 列表
- 增加 run 进度查询（例如 `/runs/{id}/state`），让前端可以展示阶段/百分比
- 增加 artifacts 下载代理（例如 `/runs/{id}/artifacts/{name}`），把服务器文件路径变成可下载 URL
