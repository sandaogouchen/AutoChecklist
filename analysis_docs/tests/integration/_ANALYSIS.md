# tests/integration/_ANALYSIS.md — 集成测试分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `tests/integration/` |
| 文件数 | 5（含 `__init__.py`） |
| 分析文件 | 4 |
| 目录职责 | 端到端集成测试：验证多组件协作的正确性 |

## §2 文件清单

| # | 文件 | 类型 | 测试范围 | 概要 |
|---|------|------|----------|------|
| 1 | `__init__.py` | - | - | 空 |
| 2 | `test_api.py` | J-测试 | API 层 | FastAPI TestClient 端点测试 |
| 3 | `test_workflow.py` | J-测试 | 全流水线 | 端到端工作流 + FakeLLMClient |
| 4 | `test_iteration_loop.py` | J-测试 | 迭代控制 | 多轮评估重试逻辑 |
| 5 | `test_project_workflow.py` | J-测试 | 项目上下文 | 带 ProjectContext 的工作流 |

## §3 逐文件分析

### §3.1 test_api.py

- **测试框架**: FastAPI `TestClient`（同步包装异步端点）
- **覆盖端点**:
  - `GET /healthz` → 验证 200 + `{"status": "ok"}`
  - `POST /api/v1/case-generation/runs` → 验证请求接受、工作流触发、响应格式
  - `GET /api/v1/case-generation/runs/{id}` → 验证结果查询
- **依赖注入覆写**: 通过 `app.dependency_overrides` 注入 `FakeLLMClient`
- **断言重点**: HTTP 状态码、响应 JSON 结构、关键字段存在性

### §3.2 test_workflow.py

- **测试范围**: PRD 输入 → 完整 LangGraph 工作流 → 测试用例输出
- **隔离策略**: 使用 `FakeLLMClient` 替换所有 LLM 调用
- **验证内容**:
  - 工作流正常完成（无异常抛出）
  - 输出包含 `test_cases` 列表
  - 测试用例包含必要字段（title, steps, expected_results）
  - `optimized_tree` 非空（outline 生成成功）

### §3.3 test_iteration_loop.py

- **测试范围**: `IterationController` 的多轮评估决策
- **测试策略**: 模拟低质量 → 高质量的渐进改善
  - 第 1 轮：`FakeLLMClientLowQuality` → 评估不通过 → 重试决策
  - 第 2 轮：`FakeLLMClient` → 评估通过 → 完成
- **验证内容**:
  - 迭代次数符合预期
  - `RetryDecision` 正确（retry → pass）
  - `IterationRecord` 正确记录每轮结果

### §3.4 test_project_workflow.py

- **测试范围**: 带项目上下文的完整工作流
- **特殊处理**: 预先创建 `ProjectContext`，验证其被正确注入到工作流中
- **验证内容**: 项目特定规则影响用例生成

## §4 补充观察

1. **关键路径覆盖完整**: API → Workflow → Iteration 三个维度的集成测试提供了良好的质量保障
2. **⚠️ Checklist 整合缺乏集成测试**: 这是最显著的测试空白
   - 无测试验证 `checkpoint_outline_planner` 生成的 outline 质量
   - 无测试验证 outline 结构对 `draft_writer` 用例组织的影响
   - 无测试验证 `structure_assembler` 的 expected_results 挂载正确性
   - 无测试验证 `PreconditionGrouper` 的分组效果
   - **建议**: 添加 `test_checklist_integration.py` 覆盖 outline 规划 → 用例生成 → 结构组装的端到端链路
3. **测试执行速度**: 使用 Fake 客户端使集成测试可在毫秒级完成，无外部依赖
4. **缺少失败路径测试**: 未测试工作流中间节点失败时的错误传播和降级行为
