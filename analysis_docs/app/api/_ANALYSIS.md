# app/api/_ANALYSIS.md — API 路由层分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `app/api/` |
| 文件数 | 3（含 `__init__.py`） |
| 分析文件 | 2 |
| 目录职责 | FastAPI 路由层：REST 端点定义与请求/响应处理 |

## §2 文件清单

| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | `__init__.py` | - | 0 | 空 |
| 2 | `routes.py` | B-流程编排 | ~80 | 用例生成 3 端点 |
| 3 | `project_routes.py` | B-流程编排 | ~60 | 项目上下文 CRUD 5 端点 |

## §3 逐文件分析

### §3.1 routes.py

- **职责**: 定义用例生成核心 API 端点
- **端点清单**:

| 方法 | 路径 | 职责 | 请求体 | 响应体 |
|------|------|------|--------|--------|
| GET | `/healthz` | 健康检查 | — | `{"status": "ok"}` |
| POST | `/api/v1/case-generation/runs` | 创建用例生成任务 | `CaseGenerationRequest` | `CaseGenerationResponse` |
| GET | `/api/v1/case-generation/runs/{run_id}` | 查询任务状态 | — | `CaseGenerationResponse` |

- **执行模式**: 同步阻塞 — POST 端点直接 await 整个工作流完成后返回
  - 优势：实现简单，客户端单次请求获取结果
  - 风险：长 PRD 处理可能超过 HTTP 超时（建议改为后台任务 + 轮询）
- **依赖注入**: 通过 FastAPI `Depends()` 注入 `WorkflowService`、`Settings`、`RunRepository`
- **错误处理**:
  - Pydantic 模型验证：自动 422 响应
  - 运行不存在：手动 HTTPException 404
  - 工作流异常：未捕获，将产生 500

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

1. **路由前缀不一致**: `/api/v1/case-generation/runs` vs `/projects` — 建议统一到 `/api/v1/` 命名空间下，如 `/api/v1/projects`
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
