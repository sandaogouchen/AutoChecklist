# app/clients/_ANALYSIS.md — LLM 客户端分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `app/clients/` |
| 文件数 | 2（含 `__init__.py`） |
| 分析文件 | 1 |
| 目录职责 | LLM 客户端抽象层：提供统一的 LLM 交互接口，隔离提供商差异 |

## §2 文件清单

| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | `__init__.py` | - | 0 | 空 |
| 2 | `llm.py` | A-核心算法 | ~200 | LLM 客户端 ABC 与 OpenAI 兼容实现 |

## §3 逐文件分析

### §3.1 llm.py

- **类层级**: `LLMClient`(ABC) → `OpenAICompatibleLLMClient`(具体实现)
- **核心方法**:

| 方法 | 层级 | 职责 | 特殊处理 |
|------|------|------|----------|
| `chat(messages)` | 抽象 | 基础聊天补全 | 由子类实现 HTTP 调用 |
| `parse_json_response(text)` | 具体 | JSON 响应解析 | 三层防御性解析 |
| `generate_structured(messages, model_class)` | 具体 | 结构化输出生成 | Schema 提示注入 + 自动反序列化 |

- **HTTP 客户端选择**: httpx（非 openai SDK）
  - 原因：保持提供商中立性，支持任意 OpenAI-compatible API（如 vLLM、Ollama）
  - 代价：需手动处理 API 协议细节（message 格式、响应解析）

- **JSON 解析三层防御**:
  1. 直接 `json.loads()` — 处理干净的 JSON 输出
  2. 提取 markdown 代码块（` ```json ... ``` `）中的 JSON — 处理 LLM 包装输出
  3. list→dict 自动包装（`{"items": [...]}`）— 处理 LLM 返回裸数组而非对象

- **Schema 注入策略**:
  - 方式：将目标 Pydantic 模型的 JSON Schema 注入系统提示末尾
  - 格式：`"Please respond with a JSON object matching this schema: {schema}"`
  - 权衡：
    - 优势：跨提供商兼容（不依赖 OpenAI 特有的 `response_format` 参数）
    - 劣势：不如原生结构化输出可靠，LLM 可能忽略 Schema 约束

- **配置参数**:
  - `timeout`: 120s（单一超时，未区分 connect/read/write）
  - `temperature`: 来自 Settings（默认 0.3）
  - `max_tokens`: 来自 Settings（默认 16384）

## §4 补充观察

1. **缺乏重试机制**: 网络错误、速率限制（429）、服务器错误（500/503）均无自动重试。建议引入指数退避重试（tenacity 或自定义）
2. **无 Token 计数**: 无法追踪单次/累计 LLM 调用的 token 消耗，不利于成本控制和 prompt 优化
3. **超时粒度不足**: 单一 120s 超时无法区分连接超时（应短）和读取超时（可长）。建议：connect=10s, read=120s, write=30s
4. **可扩展性良好**: ABC 设计允许轻松添加新的 LLM 提供商实现（Anthropic、Azure OpenAI、本地模型等），仅需实现 `chat()` 方法
5. **测试友好**: `FakeLLMClient` 继承 `LLMClient` ABC，可完全替换真实客户端，支持无 API 调用的全流水线测试
6. **流式输出缺失**: 当前为同步请求-响应模式，对长生成任务（如大型 PRD 的完整用例集）用户体验不佳。建议未来添加 SSE/WebSocket 流式支持
