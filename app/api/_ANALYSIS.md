# app/api/_ANALYSIS.md — API 路由层分析
> 分析分支自动生成 · 源分支 `main`
---
## §1 目录概述
| 维度 | 值 |
|------|-----|
| 路径 | `app/api/` |
| 文件数 | 3（含 `__init__.py`） |
| 分析文件 | 2 |
| PR #23 变更 | routes.py 新增 2 个模版端点 |
| 目录职责 | FastAPI 路由层：REST 端点定义与请求/响应处理 |
## §2 文件清单
| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | `__init__.py` | - | 0 | 空 |
| 2 | `routes.py` | B-流程编排 | ~120 | 用例生成 3 端点 + 模版查询 2 端点（PR #23） |
| 3 | `project_routes.py` | B-流程编排 | ~60 | 项目上下文 CRUD 5 端点 |
## §3 逐文件分析
### §3.1 routes.py
- **职责**: 定义用例生成核心 API 端点
- **PR #23 新增依赖**: `logging`, `pathlib.Path`, `ProjectTemplateLoader`, `TemplateValidationError`
- **PR #23 新增模块级对象**: `logger = logging.getLogger(__name__)`
- **端点清单**:
| 方法 | 路径 | 职责 | 请求体 | 响应体 |
|------|------|------|--------|--------|
| GET | `/healthz` | 健康检查 | — | `{"status": "ok"}` |
| POST | `/api/v1/case-generation/runs` | 创建用例生成任务 | `CaseGenerationRequest` | `CaseGenerationResponse` |
| GET | `/api/v1/case-generation/runs/{run_id}` | 查询任务状态 | — | `CaseGenerationResponse` |
| GET | `/api/v1/templates` | 列出可用模版 | — | `list[dict[str, str]]` |
| GET | `/api/v1/templates/{name}` | 获取指定模版详情 | — | `dict` (模版完整 JSON) |
- **执行模式**: 同步阻塞 — POST 端点直接 await 整个工作流完成后返回
- 优势：实现简单，客户端单次请求获取结果
- 风险：长 PRD 处理可能超过 HTTP 超时（建议改为后台任务 + 轮询）
- **依赖注入**: 通过 FastAPI `Depends()` 注入 `WorkflowService`、`Settings`、`RunRepository`
- **错误处理**:
- Pydantic 模型验证：自动 422 响应
- 运行不存在：手动 HTTPException 404
- 工作流异常：未捕获，将产生 500
- **PR #23 新增端点**:
#### GET `/api/v1/templates` — 列出可用模版
| 维度 | 说明 |
|------|------|
| 职责 | 扫描 `templates/` 目录中的 YAML 文件，返回各模版的名称、版本和描述 |
| 依赖注入 | `Settings`（读取 `template_dir` 配置） |
| 实例化 | 每次请求创建新的 `ProjectTemplateLoader()` — 无状态，无性能顾虑 |
| 目录扫描 | `Path(settings.template_dir).glob("*.y*ml")` — 匹配 `.yaml` 和 `.yml` |
| 容错 | 目录不存在时返回空列表 `[]`；单文件加载失败时 `logger.warning()` 并跳过，不中断遍历 |
| 返回字段 | `name`（优先取 `metadata.name`，兜底取文件名 stem）, `version`, `description`, `file_name` |
| 排序 | `sorted()` 按文件名字典序 |
#### GET `/api/v1/templates/{name}` — 获取指定模版详情
| 维度 | 说明 |
|------|------|
| 职责 | 按名称从 `templates/` 目录加载指定模版，返回完整的模版 JSON |
| 路径参数 | `name: str` — 模版名称（不含扩展名），由 `load_by_name()` 自动尝试 `.yaml` / `.yml` |
| 依赖注入 | `Settings`（读取 `template_dir` 配置） |
| 返回值 | `template.model_dump(mode="json")` — 完整的 Pydantic 模型 JSON 序列化 |
| 错误处理 | `FileNotFoundError` → HTTP 404; `TemplateValidationError` → HTTP 422 |
| 安全注意 | `name` 参数未做路径遍历防护（如 `../../etc/passwd`），当前依赖 `load_by_name()` 内的 Path 拼接限制 |
```
请求流:
GET /api/v1/templates/{name}
→ Settings.template_dir
→ ProjectTemplateLoader.load_by_name(name, template_dir)
→ Path(template_dir) / f"{name}.yaml" (或 .yml)
→ YAML 解析 + validate_template()
→ template.model_dump(mode="json")
→ 200 OK
```
### §3.2 project_routes.py
- **职责**: 项目上下文的标准 CRUD 操作
- **端点清单**:
| 方法 | 路径 | 职责 |
|------|------|------|
| GET | `/projects` | 列出所有项目 |
| POST | `/projects` | 创建项目 |
| GET | `/projects/{id}` | 获取项目详情 |
| PUT | `/projects/{id}` | 更新项目 |
| DELETE | `/projects/{id}` | 删除项目 |
- **路由前缀**: `/projects`（注意：与主路由的 `/api/v1/case-generation/` 前缀不一致）
- **依赖**: `ProjectContextService` 通过依赖注入获取
## §4 补充观察
1. **路由前缀不一致**: `/api/v1/case-generation/runs` vs `/projects` vs `/api/v1/templates` — PR #23 的新端点使用了 `/api/v1/templates` 前缀，与 `case-generation` 在同一命名空间层级，但 `/projects` 仍不一致。建议统一到 `/api/v1/` 命名空间下
2. **缺失关注点**:
| 关注点 | 当前状态 | 建议优先级 |
|--------|----------|------------|
| 认证/授权 | 缺失 | 高 |
| 速率限制 | 缺失 | 中 |
| 请求追踪 (trace_id) | 缺失 | 中 |
| CORS 配置 | 缺失 | 低 |
| 分页 | `/projects` 缺失 | 低 |
3. **同步执行风险**: POST `/runs` 同步等待完整工作流执行完毕，复杂 PRD 可能需要数分钟。建议改为：POST 返回 `run_id` + 202 Accepted → 后台异步执行 → GET 轮询状态
4. **API 版本化**: 已有 `/api/v1/` 前缀，版本演进路径清晰
5. **PR #23 模版端点设计评估**:
| 方面 | 评估 | 建议 |
|------|------|------|
| 端点命名 | `/api/v1/templates` — RESTful、版本化，与现有端点一致 | 合格 |
| 每请求实例化 loader | `ProjectTemplateLoader()` 无状态，可接受 | 若模版数量增多，可考虑缓存 |
| 路径遍历风险 | `name` 参数直接拼入文件路径，无 sanitization | 应添加 `name` 白名单校验或路径规范化 |
| 分页缺失 | `list_templates` 无分页参数 | 当前模版数量少，暂可接受；规模增长后需加分页 |
| 认证 | 与其他端点一致，均无认证 | 统一处理，非本 PR 范围 |
6. **模版端点与核心生成端点的关系**:
- `GET /api/v1/templates` 和 `GET /api/v1/templates/{name}` 为只读查询端点，不触发任何生成流程
- `POST /api/v1/case-generation/runs` 的 `CaseGenerationRequest` 可通过 `template_name` 字段引用模版名称
- 预期调用顺序：先 `GET /api/v1/templates` 获取可用列表 → 选择模版 → `POST /runs` 时传入 `template_name`
- 这构成了一个"先查后用"的两步工作流，比直接传文件路径更安全、更用户友好
## §4 PR #24 变更 — 知识库管理 API

> 同步自 PR #24 `feat/graphrag-knowledge-retrieval`

PR #24 新增 `knowledge_routes.py`，提供 6 个知识库管理 REST 端点，挂载于 `/api/v1/knowledge/` 前缀下。

### 新增文件：knowledge_routes.py

- **类型**: A-路由层
- **行数**: ~163
- **路由前缀**: `/api/v1/knowledge`
- **依赖注入**: `_get_engine()` 从 `app.state.graphrag_engine` 获取引擎实例

### 端点清单

| HTTP 方法 | 路径 | 功能 | 请求体 | 响应 |
|-----------|------|------|--------|------|
| POST | `/documents` | 上传并索引单个知识文档 | file_path (str) | KnowledgeDocument |
| GET | `/documents` | 列出所有已索引文档 | - | list[KnowledgeDocument] |
| DELETE | `/documents/{doc_id}` | 删除已索引文档 | - | {"deleted": bool} |
| POST | `/query` | 手动执行知识检索查询 | query (str), mode (str) | RetrievalResult |
| POST | `/reindex` | 全量重建知识索引 | - | {"indexed_count": int} |
| GET | `/status` | 获取知识库状态 | - | KnowledgeStatus |

### 请求/响应模型

文件内定义了两个请求模型：
- `DocumentUploadRequest(file_path: str)` — 上传请求
- `QueryRequest(query: str, mode: str = "hybrid")` — 查询请求

响应模型复用 `app.knowledge.models` 中的领域模型。

### 依赖注入

```python
def _get_engine() -> GraphRAGEngine:
    engine = getattr(app_instance.state, "graphrag_engine", None)
    if engine is None or not engine.is_ready():
        raise HTTPException(status_code=503, detail="知识检索引擎未就绪")
    return engine
```

- 从 FastAPI `app.state` 获取引擎实例，与 lifespan 注入的实例一致
- 引擎未就绪时返回 503 Service Unavailable

### 设计评价

1. **RESTful 完备**: 覆盖文档 CRUD + 检索 + 重建 + 状态查询，API 设计完整
2. **路由隔离**: 独立 `APIRouter`，通过 `app.include_router()` 注册，与现有路由无耦合
3. **错误处理**: 引擎未就绪 → 503，文档校验失败 → 400，符合 HTTP 语义