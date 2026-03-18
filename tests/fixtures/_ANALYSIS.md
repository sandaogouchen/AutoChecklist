# tests/fixtures/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 1 | 分析策略: Test fixture / documentation — describe the sample PRD content and its role in testing

## §1 目录职责

`tests/fixtures/` 目录存放测试使用的**静态输入文件**，作为工作流端到端测试的标准化输入源。当前仅包含一个样例 PRD（产品需求文档）Markdown 文件，为解析器、工作流节点和 API 集成测试提供一致且可控的文档输入。

## §2 文件清单

| 序号 | 文件名 | 行数 | 职责概述 |
|------|--------|------|----------|
| 1 | `sample_prd.md` | 12 | 样例 PRD 文档：描述一个简单的手机号 SMS 登录流程需求 |

## §3 文件详细分析

### §3.1 sample_prd.md

- **路径**: `tests/fixtures/sample_prd.md`
- **行数**: 12
- **职责**: 提供最小化但结构完整的 PRD 文档，作为所有解析和生成测试的标准输入

#### §3.1.1 核心内容

文档完整内容：

```markdown
# Login Flow

## User Story

As a returning user, I want to sign in with my phone number.

## Acceptance Criteria

- Users can request an SMS code.
- Expired SMS codes are rejected.
- Successful login redirects to the dashboard.
```

**文档结构分析**:

| 元素 | 内容 | 在 Markdown 中的级别 |
|------|------|---------------------|
| 主标题 | "Login Flow" | H1 (`#`) |
| 二级标题 1 | "User Story" | H2 (`##`) |
| 用户故事文本 | "As a returning user, I want to sign in with my phone number." | 段落 |
| 二级标题 2 | "Acceptance Criteria" | H2 (`##`) |
| 验收条件 1 | "Users can request an SMS code." | 无序列表项 |
| 验收条件 2 | "Expired SMS codes are rejected." | 无序列表项 |
| 验收条件 3 | "Successful login redirects to the dashboard." | 无序列表项 |

**业务场景涵盖**:
- **正向路径**: 用户请求 SMS 验证码并成功登录，跳转到 dashboard
- **异常路径**: 过期 SMS 验证码被拒绝
- **隐含约束**: SMS 验证码有有效期（与 conftest.py 中 FakeLLMClient 返回的 "5 minutes" 约束对应）

#### §3.1.2 依赖关系

**被以下测试文件引用**:

| 测试文件 | 引用方式 | 用途 |
|----------|----------|------|
| `tests/unit/test_markdown_parser.py` | `Path("tests/fixtures/sample_prd.md")` | 验证 MarkdownParser 能提取 sections，首个 heading 为 "Login Flow" |
| `tests/integration/test_workflow.py` | `Path("tests/fixtures/sample_prd.md")` | 端到端工作流测试的输入文件 |
| `tests/integration/test_api.py` | `Path("tests/fixtures/sample_prd.md").resolve()` | API 端点集成测试的请求 payload |
| `tests/integration/test_iteration_loop.py` | `Path("tests/fixtures/sample_prd.md").resolve()` | 迭代回路测试的输入文件 |

**与 conftest.py 的数据一致性**:

`conftest.py` 中 `FakeLLMClient` 返回的模拟数据与 `sample_prd.md` 的内容紧密对应：

| sample_prd.md 内容 | FakeLLMClient 模拟数据 |
|--------------------|-----------------------|
| "Login Flow" 标题 | `feature_topics=["Login"]` |
| "sign in with my phone number" | `user_scenarios=["User logs in with SMS code"]` |
| "Expired SMS codes are rejected" | `constraints=["SMS code expires in 5 minutes"]` |
| "Acceptance Criteria" 章节 | `evidence_refs` 中 `section_title="Acceptance Criteria"` |
| "Successful login redirects to the dashboard" | TC-001 的 `expected_results=["User reaches the dashboard"]` |

#### §3.1.3 关键逻辑 / 数据流

```
sample_prd.md
    |
    ├──> MarkdownParser.parse() ──> ParsedDocument (sections: Login Flow, User Story, Acceptance Criteria)
    |
    ├──> InputParserNode (工作流) ──> 传递给 ContextResearchNode
    |                                      |
    |                                FakeLLMClient.generate_structured()
    |                                      |
    |                                ResearchOutput (facts, scenarios, constraints)
    |
    └──> API 端点 (POST /api/v1/case-generation/runs)
              |
              └──> 完整工作流执行 ──> CaseGenerationRun 响应
```

**作为测试基准的设计意图**: 文件刻意保持极简（12 行），使得：
1. 解析结果可预测（固定 3 个 sections）
2. 生成的测试用例数量可控（FakeLLMClient 返回固定 2 个 TestCase）
3. 测试断言可以精确匹配具体文本（如 `sections[0].heading == "Login Flow"`）

## §4 目录级依赖关系

```
tests/fixtures/sample_prd.md
    │
    ├── tests/unit/test_markdown_parser.py (解析器测试输入)
    ├── tests/integration/test_workflow.py (工作流测试输入)
    ├── tests/integration/test_api.py (API 测试输入)
    ├── tests/integration/test_iteration_loop.py (迭代回路测试输入)
    │
    └── tests/conftest.py (FakeLLMClient 返回数据与此文件内容语义对齐)
```

## §5 设计模式与架构特征

| 模式/特征 | 体现位置 |
|-----------|----------|
| **Golden File 模式** | 固定输入文件作为所有测试的标准化基准 |
| **最小化 Fixture** | 12 行文档覆盖 H1/H2/段落/列表四种 Markdown 元素 |
| **数据一致性契约** | sample_prd.md 内容与 conftest.py 模拟数据语义对齐 |
| **路径约定** | 测试代码通过相对路径 `tests/fixtures/sample_prd.md` 引用 |

## §6 潜在关注点

1. **单一 Fixture 文件**: 目前仅有一个 `sample_prd.md`，缺少覆盖以下场景的 fixture 文件：
   - 空文档或仅含标题的文档
   - 深层嵌套标题（H3/H4/H5）
   - 包含代码块、表格、图片引用的复杂 Markdown
   - 非 UTF-8 编码或含特殊字符的文档
   - 大型文档（性能测试）
2. **路径硬编码**: 测试文件通过硬编码相对路径引用 fixture，如果项目目录结构变更或 pytest 的工作目录改变，可能导致 `FileNotFoundError`。部分测试使用 `.resolve()` 转为绝对路径缓解此问题。
3. **Fixture 与 Mock 数据耦合**: `sample_prd.md` 的内容变更需要同步更新 `conftest.py` 中 FakeLLMClient 的返回数据，否则测试中的语义一致性假设将失效。