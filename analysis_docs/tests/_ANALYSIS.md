# tests/_ANALYSIS.md — 测试基础设施分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `tests/` |
| 文件数 | 2（含 `__init__.py`），另有 3 个子目录 |
| 子目录 | `integration/`（4 测试文件）、`unit/`（22 测试文件）、`fixtures/`（测试数据） |
| 目录职责 | 测试基础设施层：全局 pytest 配置、共享 fixtures、Fake LLM 客户端 |

## §2 文件清单

| # | 文件 | 类型 | 概要 |
|---|------|------|------|
| 1 | `__init__.py` | - | 空 |
| 2 | `conftest.py` | J-测试基础设施 | 全局 pytest fixtures 与 Fake LLM 客户端定义 |

## §3 逐文件分析

### §3.1 conftest.py

- **类型**: J-测试基础设施
- **职责**: 定义全局共享的 pytest fixtures 和 Fake LLM 客户端

- **FakeLLMClient（正常质量）**:
  - 继承 `LLMClient` ABC
  - 通过 `model_class` 参数路由到对应的预置响应
  - 覆盖所有 LLM 调用点的结构化输出模型：
    - `ResearchOutput` → 预置研究事实和场景
    - `CheckpointDraft` → 预置检查点草稿
    - `EvaluationReport` → 预置评估报告（overall_score > 0.7, pass_=True）
    - `CanonicalOutlineNode` → 预置 outline 层级
  - 设计优势：单一 fake 客户端覆盖全流水线，无需每个节点独立 mock

- **FakeLLMClientLowQuality（低质量）**:
  - 生成低质量/不合格响应
  - 用途：测试 `IterationController` 的重试决策逻辑
  - 典型场景：evaluation_pass_threshold 未达标 → 触发重试 → 切换到正常客户端 → 通过

- **共享 Fixtures**:
  | Fixture | 类型 | 用途 |
  |---------|------|------|
  | `sample_parsed_document` | `ParsedDocument` | 预解析的 PRD 文档 |
  | `sample_research_output` | `ResearchOutput` | 研究阶段输出 |
  | `sample_checkpoints` | `list[Checkpoint]` | 检查点列表 |
  | `fake_llm_client` | `FakeLLMClient` | 正常质量 LLM 客户端 |
  | `fake_llm_client_low` | `FakeLLMClientLowQuality` | 低质量 LLM 客户端 |

## §4 补充观察

1. **Fake Client 策略优秀**: 通过 `model_class` 路由实现了全面的 LLM mock，避免了真实 API 调用的不确定性和成本
2. **双客户端设计巧妙**: 正常/低质量客户端的组合完美支持迭代控制逻辑的测试（低质量 → 重试 → 正常质量 → 通过）
3. **Fixture 粒度合理**: 从 `parsed_document` → `research_output` → `checkpoints` 逐层构建，每层可独立使用
4. **Fixture 集中管理**: 所有共享 fixture 放在根 `conftest.py`，子目录的 `conftest.py` 仅添加局部 fixture，层次清晰
5. **缺少 Checklist 专用 Fixture**: 缺少 `sample_optimized_tree` 或 `sample_outline_nodes` fixture，checklist 相关测试需各自构建测试数据
