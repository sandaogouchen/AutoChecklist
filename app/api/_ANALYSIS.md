# app/api/ 目录分析

> 生成时间: 2025-01-20 | 源文件数: 3 | 分析策略: Routes/API 策略

## §1 目录职责

`app/api/` 是 AutoChecklist 项目的 HTTP API 路由层，负责定义所有对外暴露的 RESTful 端点。该目录采用 FastAPI 的 `APIRouter` 机制将路由逻辑与应用主体解耦，包含两个核心路由模块：`routes.py` 提供用例生成工作流相关的端点（健康检查、创建/查询生成任务），`project_routes.py` 提供项目上下文的完整 CRUD 操作。所有端点通过 FastAPI 依赖注入从 `app.state` 获取共享服务实例，实现了路由层与业务逻辑层的清晰分离。

## §2 文件清单

| 文件名 | 行数 | 主要职责 | 分析策略 |
|---------|------|----------|----------|
| `__init__.py` | 1 | 包初始化，声明 API 路由子包 | Routes/API 策略 |
| `routes.py` | 70 | 核心业务端点：健康检查、用例生成任务的创建与查询 | Routes/API 策略 |
| `project_routes.py` | 102 | 项目上下文 CRUD 端点：创建、列表、查询、更新、删除 | Routes/API 策略 |

## §3 文件详细分析

### §3.1 `__init__.py`

- **路径**: `app/api/__init__.py`
- **行数**: 1
- **职责**: 包初始化文件，将 `app/api/` 标记为 Python 子包

#### §3.1.1 核心内容

文件仅包含一行模块级文档字符串：

```python
"""API 路由子包。"""
```

该文件不导出任何符号，不执行任何初始化逻辑。其唯一作用是使 `app.api` 成为可导入的 Python 包，方便其他模块通过 `from app.api.routes import router` 等方式引用路由对象。

#### §3.1.2 依赖关系

- 内部依赖: 无
- 外部依赖: 无

#### §3.1.3 关键逻辑 / 数据流

无实质逻辑。

---

### §3.2 `routes.py`

- **路径**: `app/api/routes.py`
- **行数**: 70
- **职责**: 定义核心业务 HTTP 端点，包括健康检查、用例生成任务的创建与结果查询

#### §3.2.1 核心内容

**路由实例化**:

```python
router = APIRouter()
```

创建无前缀的 `APIRouter` 实例，端点路径在装饰器中以完整路径定义。

**依赖注入辅助函数**:

| 函数名 | 参数 | 返回类型 | 职责 |
|--------|------|----------|------|
| `_get_settings(request)` | `Request` | `Settings` | 从 `request.app.state.settings` 获取全局配置 |
| `_get_workflow_service(request)` | `Request` | `WorkflowService` | 从 `request.app.state.workflow_service` 获取工作流服务 |

**端点清单**:

| 方法 | 路径 | 处理函数 | 请求模型 | 响应模型 | 状态码 | 描述 |
|------|------|----------|----------|----------|--------|------|
| `GET` | `/healthz` | `healthz()` | 无 | `dict[str, str]` | 200 | 健康检查，返回服务名称和版本 |
| `POST` | `/api/v1/case-generation/runs` | `create_case_generation_run()` | `CaseGenerationRequest` | `CaseGenerationRun` | 200 | 创建用例生成任务，同步执行 |
| `GET` | `/api/v1/case-generation/runs/{run_id}` | `get_case_generation_run()` | 路径参数 `run_id: str` | `CaseGenerationRun` | 200 / 404 | 根据 run_id 查询任务结果 |

**错误处理**:

- `get_case_generation_run()` 捕获 `FileNotFoundError`，转换为 `HTTPException(status_code=404)`
- 错误详情格式: `"Run not found: {run_id}"`

**API 版本策略**: 使用 URL 路径内嵌版本号 `/api/v1/`，属于 URI 版本控制模式。

#### §3.2.2 依赖关系

- 内部依赖:
  - `app.config.settings.Settings` — 全局配置类
  - `app.domain.api_models.CaseGenerationRequest` — 请求数据模型
  - `app.domain.api_models.CaseGenerationRun` — 响应数据模型
  - `app.services.workflow_service.WorkflowService` — 工作流业务服务
- 外部依赖:
  - `fastapi.APIRouter` — 路由器
  - `fastapi.Depends` — 依赖注入装饰器
  - `fastapi.HTTPException` — HTTP 异常
  - `fastapi.Request` — 请求上下文
  - `__future__.annotations` — 延迟类型注解求值

#### §3.2.3 关键逻辑 / 数据流

1. **健康检查流程**: `GET /healthz` → `_get_settings()` 注入 `Settings` → 返回 `{"status": "ok", "service": ..., "version": ...}`
2. **任务创建流程**: `POST /api/v1/case-generation/runs` → FastAPI 自动解析请求体为 `CaseGenerationRequest` → `_get_workflow_service()` 注入 `WorkflowService` → 调用 `workflow_service.create_run(payload)` → 同步返回 `CaseGenerationRun`
3. **任务查询流程**: `GET /api/v1/case-generation/runs/{run_id}` → 提取路径参数 `run_id` → 调用 `workflow_service.get_run(run_id)` → 成功返回结果 / 失败抛出 404

**重要设计决策**: 任务创建端点采用**同步执行**模式，即 `create_run()` 会阻塞直到整个 LangGraph 工作流完成。这意味着对于大型 PRD 文档，请求可能需要较长时间才能返回。

---

### §3.3 `project_routes.py`

- **路径**: `app/api/project_routes.py`
- **行数**: 102
- **职责**: 提供项目上下文的完整 CRUD RESTful 端点，挂载在 `/projects` 路径下

#### §3.3.1 核心内容

**路由实例化**:

```python
router = APIRouter(prefix="/projects", tags=["projects"])
```

使用 `/projects` 前缀和 `projects` 标签，所有端点自动添加该前缀。

**依赖注入辅助函数**:

| 函数名 | 参数 | 返回类型 | 职责 |
|--------|------|----------|------|
| `_get_project_service(request)` | `Request` | `ProjectContextService` | 从 `request.app.state.project_context_service` 获取项目服务 |

**请求/响应 Schema 定义**:

**`ProjectCreateRequest`** (继承 `BaseModel`):

| 字段 | 类型 | 默认值 | 约束 | 描述 |
|------|------|--------|------|------|
| `name` | `str` | 必填 | `min_length=1, max_length=200` | 项目名称 |
| `description` | `str` | `""` | `max_length=5000` | 项目描述 |
| `project_type` | `ProjectType` | `ProjectType.OTHER` | 枚举 | 项目类型 |
| `regulatory_frameworks` | `list[RegulatoryFramework]` | `[]` | — | 监管框架列表 |
| `tech_stack` | `list[str]` | `[]` | — | 技术栈 |
| `custom_standards` | `list[str]` | `[]` | — | 自定义标准 |
| `metadata` | `dict[str, Any]` | `{}` | — | 扩展元数据 |

**`ProjectUpdateRequest`** (继承 `BaseModel`):

所有字段均为 `Optional`，支持部分更新（PATCH 语义）。字段与 `ProjectCreateRequest` 对应，但默认值均为 `None`。

**端点清单**:

| 方法 | 路径 | 处理函数 | 请求模型 | 状态码 | 描述 |
|------|------|----------|----------|--------|------|
| `POST` | `/projects` | `create_project()` | `ProjectCreateRequest` | 201 | 创建新项目 |
| `GET` | `/projects` | `list_projects()` | 无 | 200 | 列出所有项目 |
| `GET` | `/projects/{project_id}` | `get_project()` | 路径参数 `project_id: str` | 200 / 404 | 查询单个项目 |
| `PATCH` | `/projects/{project_id}` | `update_project()` | `ProjectUpdateRequest` | 200 / 404 | 部分更新项目 |
| `DELETE` | `/projects/{project_id}` | `delete_project()` | 路径参数 `project_id: str` | 204 / 404 | 删除项目 |

**错误处理**:

| 端点 | 异常源 | HTTP 状态码 | 错误详情 |
|------|--------|------------|----------|
| `get_project()` | `svc.get_project()` 返回 `None` | 404 | `"Project not found"` |
| `update_project()` | `svc.update_project()` 抛出 `KeyError` | 404 | `"Project not found"` |
| `delete_project()` | `svc.delete_project()` 返回 `False` | 404 | `"Project not found"` |

**响应序列化**: 所有返回项目对象的端点统一使用 `project.model_dump()` 将 Pydantic 模型转换为字典。`DELETE` 端点成功时返回 `None`（配合 `status_code=204`）。

#### §3.3.2 依赖关系

- 内部依赖:
  - `app.domain.project_models.ProjectType` — 项目类型枚举
  - `app.domain.project_models.RegulatoryFramework` — 监管框架枚举
  - `app.services.project_context_service.ProjectContextService` — 项目上下文业务服务
- 外部依赖:
  - `fastapi.APIRouter` — 路由器
  - `fastapi.Depends` — 依赖注入
  - `fastapi.HTTPException` — HTTP 异常
  - `fastapi.Request` — 请求上下文
  - `pydantic.BaseModel` — 数据模型基类
  - `pydantic.Field` — 字段约束声明
  - `typing.Any`, `typing.Optional` — 类型提示
  - `__future__.annotations` — 延迟类型注解求值

#### §3.3.3 关键逻辑 / 数据流

1. **创建流程**: `POST /projects` → 解析 `ProjectCreateRequest` → 调用 `svc.create_project(**body.model_dump())` → 返回 `project.model_dump()` (201)
2. **列表流程**: `GET /projects` → 调用 `svc.list_projects()` → 对每个项目调用 `model_dump()` → 返回列表
3. **查询流程**: `GET /projects/{id}` → 调用 `svc.get_project(id)` → `None` 检查 → 返回或 404
4. **更新流程**: `PATCH /projects/{id}` → 解析 `ProjectUpdateRequest` → `body.model_dump(exclude_unset=True)` 仅提取用户显式传入的字段 → 调用 `svc.update_project(id, **updates)` → 捕获 `KeyError` 转 404
5. **删除流程**: `DELETE /projects/{id}` → 调用 `svc.delete_project(id)` → 布尔检查 → 成功返回 `None` (204) / 失败返回 404

**PATCH 语义实现**: 使用 `model_dump(exclude_unset=True)` 确保只有客户端显式发送的字段才会被更新，未发送的字段保持原值。这是标准的 JSON Merge Patch 语义的简化实现。

## §4 目录级依赖关系

**上游依赖（本目录依赖的模块）**:

| 依赖模块 | 依赖内容 | 依赖方式 |
|----------|----------|----------|
| `app.config.settings` | `Settings` | 依赖注入 |
| `app.domain.api_models` | `CaseGenerationRequest`, `CaseGenerationRun` | 请求/响应模型 |
| `app.domain.project_models` | `ProjectType`, `RegulatoryFramework` | 枚举类型 |
| `app.services.workflow_service` | `WorkflowService` | 业务逻辑委托 |
| `app.services.project_context_service` | `ProjectContextService` | 业务逻辑委托 |

**下游依赖（依赖本目录的模块）**:

| 依赖模块 | 依赖内容 | 使用方式 |
|----------|----------|----------|
| `app.main` (推测) | `router` 对象 | 通过 `app.include_router()` 注册路由 |

## §5 设计模式与架构特征

1. **依赖注入模式 (Dependency Injection)**: 所有端点通过 FastAPI 的 `Depends()` 机制获取服务实例，服务实例存储在 `app.state` 上。这种模式实现了控制反转 (IoC)，路由层不直接创建或管理服务生命周期。

2. **薄控制器模式 (Thin Controller)**: 路由处理函数几乎不包含业务逻辑，仅做参数解包和异常转换，真正的业务逻辑委托给 Service 层。

3. **DTO 模式 (Data Transfer Object)**: `ProjectCreateRequest` 和 `ProjectUpdateRequest` 作为请求 DTO，与内部领域模型分离，允许 API 层独立演进。

4. **RESTful 资源模式**: `project_routes.py` 严格遵循 REST 约定——资源路径为名词复数 (`/projects`)，使用标准 HTTP 方法映射 CRUD 操作，状态码符合规范 (201 创建、204 删除、404 未找到)。

5. **URI 版本控制**: `routes.py` 使用 `/api/v1/` 路径前缀进行 API 版本管理。

## §6 潜在关注点

1. **同步阻塞风险**: `create_case_generation_run()` 同步调用 `workflow_service.create_run()`，而 LangGraph 工作流涉及多次 LLM 调用，可能导致请求超时。建议考虑异步执行 + 轮询查询模式，或引入后台任务队列。

2. **缺少分页支持**: `list_projects()` 直接返回所有项目，当项目数量增长时可能影响性能和响应大小。建议添加 `limit`/`offset` 或游标分页参数。

3. **响应模型不一致**: `routes.py` 显式声明 `response_model=CaseGenerationRun`，而 `project_routes.py` 的端点没有声明 `response_model`，直接返回 `model_dump()` 字典。这导致 OpenAPI 文档中项目端点缺少明确的响应 Schema。

4. **异常处理风格不统一**: `routes.py` 捕获 `FileNotFoundError`，`project_routes.py` 分别检查 `None` 返回值和捕获 `KeyError`。建议统一错误处理策略，例如使用自定义异常或中间件。

5. **缺少输入验证中间件**: 没有全局的请求验证中间件或错误处理中间件，依赖 FastAPI 默认的 422 验证错误响应。

6. **缺少认证/授权**: 所有端点均无认证保护，适合内部使用但不适合公开部署。