# tests/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 2 | 分析策略: Test — conftest.py fixture setup, mock strategies

## §1 目录职责

`tests/` 根目录包含测试包初始化文件和**全局共享 fixture 配置**（`conftest.py`）。`conftest.py` 是整个测试套件的核心基础设施，提供两个 Fake LLM 客户端 fixture，分别模拟**高质量**和**低质量** LLM 响应，供 `tests/unit/` 和 `tests/integration/` 中的测试函数使用。

## §2 文件清单

| 序号 | 文件名 | 行数 | 职责概述 |
|------|--------|------|----------|
| 1 | `__init__.py` | 1 | 测试包标识文件（空文件） |
| 2 | `conftest.py` | ~235 | pytest 全局 fixture 配置：FakeLLMClient 和 FakeLLMClientLowQuality |

## §3 文件详细分析

### §3.1 __init__.py

- **路径**: `tests/__init__.py`
- **行数**: 1（空行）
- **职责**: 将 `tests/` 标记为 Python 包，使 pytest 能正确发现和导入测试模块

#### §3.1.1 核心内容

空文件，仅包含一个换行符。

#### §3.1.2 依赖关系

无外部依赖。

#### §3.1.3 关键逻辑 / 数据流

无逻辑。

---

### §3.2 conftest.py

- **路径**: `tests/conftest.py`
- **行数**: ~235
- **职责**: 提供全局 pytest fixtures，核心是两个 Fake LLM 客户端类及其对应的 fixture 函数

#### §3.2.1 核心内容

**类 `FakeLLMClient`** — 高质量 LLM 客户端模拟

提供 `generate_structured(**kwargs)` 方法，根据 `response_model.__name__` 分派返回：

| response_model 名称 | 返回内容 |
|---------------------|----------|
| `ResearchOutput` | 2 个 feature_topics, 1 个 user_scenario, 1 个 constraint, 2 个 ResearchFact（FACT-001 行为类 + FACT-002 约束类），每个 fact 带完整 evidence_refs |
| `CheckpointDraftCollection` | 2 个 checkpoint（"Verify SMS login success flow" + "Verify SMS code expiration"），分别关联 FACT-001 和 FACT-002 |
| `DraftCaseCollection`（默认） | 2 个 TestCase（TC-001 登录成功 + TC-002 过期拒绝），带 checkpoint_id、完整 steps/expected_results/evidence_refs |

**类 `FakeLLMClientLowQuality`** — 低质量 LLM 客户端模拟

用于测试迭代评估回路的回流能力，特征：
- 内部计数器 `_call_count` 跟踪调用次数
- `ResearchOutput`: 3 个 fact，但 FACT-002 和 FACT-003 的 evidence_refs 为空列表
- `CheckpointDraftCollection`: 仅 1 个 checkpoint，只覆盖 FACT-001（故意留下 fact 覆盖缺口）
- `DraftCaseCollection`: 1 个 TestCase，故意缺少 expected_results（空列表）、checkpoint_id（空字符串）、evidence_refs（空列表）

**Fixture 函数**:

```python
@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()

@pytest.fixture
def fake_llm_client_low_quality() -> FakeLLMClientLowQuality:
    return FakeLLMClientLowQuality()
```

两个 fixture 均为**函数级作用域**（默认），每个测试函数获得独立实例。

#### §3.2.2 依赖关系

- **被依赖方**: `tests/unit/` 和 `tests/integration/` 中所有需要 LLM 客户端 mock 的测试函数
- **导入依赖**: 仅 `pytest`（标准测试库）
- **隐式协议依赖**: 两个 Fake 类均实现 `generate_structured(**kwargs)` 接口，与 `app.clients.llm.OpenAICompatibleLLMClient` 保持鸭子类型兼容
- **模型依赖（运行时）**: 返回值依赖 `ResearchOutput`, `CheckpointDraftCollection`, `DraftCaseCollection` 的 Pydantic 模型结构（通过 `model_validate` 构建）

#### §3.2.3 关键逻辑 / 数据流

**Mock 策略**: 基于**行为替换（Behavioral Substitution）** 模式，而非 `unittest.mock.patch`。Fake 类实现与真实 LLM 客户端相同的接口签名，通过 `response_model.__name__` 字符串匹配实现多态分派。

**数据流**:
```
测试函数 --请求fixture--> conftest.py --创建--> FakeLLMClient实例
    |                                              |
    +--注入到 WorkflowService/Node--调用--> generate_structured()
                                              |
                                    检查 response_model.__name__
                                              |
                          ┌───────────────────┼───────────────────┐
                   ResearchOutput    CheckpointDraftCollection   DraftCaseCollection
                          |                   |                       |
                    返回预定义数据        返回预定义数据          返回预定义数据
```

**高/低质量对比设计**:

| 维度 | FakeLLMClient (高质量) | FakeLLMClientLowQuality (低质量) |
|------|----------------------|-------------------------------|
| Fact 数量 | 2（全部带 evidence） | 3（2 个缺 evidence） |
| Checkpoint 覆盖 | 2 个，覆盖全部 fact | 1 个，仅覆盖 FACT-001 |
| TestCase 质量 | 完整 steps + expected_results + evidence | 缺 expected_results + checkpoint_id + evidence |
| 用途 | 验证正常流程 | 触发迭代回流和评估失败路径 |

## §4 目录级依赖关系

```
tests/conftest.py
  ├── 被 tests/unit/test_nodes.py 使用 (fake_llm_client)
  ├── 被 tests/unit/test_checkpoint.py 间接受益
  ├── 被 tests/integration/test_api.py 使用 (fake_llm_client)
  ├── 被 tests/integration/test_workflow.py 使用 (fake_llm_client)
  ├── 被 tests/integration/test_iteration_loop.py 使用 (fake_llm_client_low_quality)
  └── 被 tests/integration/test_project_workflow.py 间接受益
```

## §5 设计模式与架构特征

| 模式/特征 | 体现位置 |
|-----------|----------|
| **Fake Object 模式** | FakeLLMClient/FakeLLMClientLowQuality 替代真实 LLM 客户端 |
| **鸭子类型协议** | Fake 类未继承任何基类，仅通过方法签名兼容 |
| **多态分派** | `response_model.__name__` 字符串匹配实现不同模型的返回逻辑 |
| **测试金字塔基础** | 全局 fixture 支撑 unit 和 integration 两层测试 |
| **对比测试设计** | 高/低质量双 fixture 支撑正常流程和异常回流两类测试场景 |
| **函数级隔离** | 默认 scope 确保每个测试函数获得独立 Fake 实例 |

## §6 潜在关注点

1. **字符串匹配脆弱性**: `response_model.__name__` 匹配依赖类名字符串，如果模型类重命名但 conftest 未同步更新，将静默返回错误数据（落入默认的 DraftCaseCollection 分支）。
2. **Fake 数据硬编码**: 所有返回数据硬编码在类体中，如果领域模型字段变更（如新增必填字段），需要同步更新两个 Fake 类。
3. **`_call_count` 未被消费**: `FakeLLMClientLowQuality` 维护调用计数器，但当前未被任何测试断言引用，也未用于实现 "多轮调用返回不同数据" 的渐进改善行为。这意味着低质量 mock 每轮返回完全相同的数据，可能无法真实模拟 "LLM 在 retry 后改善输出" 的场景。
4. **未覆盖错误响应**: 两个 Fake 类都只模拟成功路径，不模拟 LLM 调用失败（如超时、API 错误）的场景。LLM 错误路径测试需要在具体测试文件中使用 `unittest.mock` 或其他手段。