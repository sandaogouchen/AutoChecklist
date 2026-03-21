# _ANALYSIS.md — app/knowledge/ 知识检索模块分析
> 分析分支自动生成 · 源分支 `feat/graphrag-knowledge-retrieval` (PR #24)
---
## §1 目录概述
| 维度 | 值 |
|------|-----|
| 路径 | `app/knowledge/` |
| 文件数 | 5 |
| 分析文件 | \_\_init\_\_.py, models.py, ingestion.py, graphrag_engine.py, retriever.py |
| 目录职责 | 基于 LightRAG 框架的 GraphRAG 知识文档接入与检索，提供文档扫描/校验、图谱索引构建、多模式语义检索能力 |

## §2 文件清单
| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | \_\_init\_\_.py | - | ~4 | 模块文档字符串，声明包 |
| 2 | models.py | M-模型 | ~45 | 知识检索领域模型：KnowledgeDocument, RetrievalResult, KnowledgeStatus |
| 3 | ingestion.py | S-服务 | ~110 | 知识文档扫描与校验：scan_knowledge_directory, validate_document_path |
| 4 | graphrag_engine.py | S-服务 | ~290 | LightRAG 引擎封装：初始化、索引、检索、生命周期管理 |
| 5 | retriever.py | S-服务 | ~110 | 检索接口封装：查询构造、结果格式化、完整检索流程 |

## §3 逐文件分析

### §3.1 \_\_init\_\_.py
- **类型**: 包标识
- **职责**: 将 `app/knowledge/` 声明为 Python 包，包含模块级文档字符串
- **说明**: 纯结构性文件，无逻辑

### §3.2 models.py
- **类型**: M-领域模型
- **职责**: 定义知识检索子系统的三个核心 Pydantic 数据模型
- **模型清单**:

| 模型 | 用途 | 关键字段 |
|------|------|--------|
| `KnowledgeDocument` | 已索引文档的元数据 | doc_id, file_name, file_path, file_size_bytes, md5_hash, indexed_at, entity_count |
| `RetrievalResult` | 知识检索结果 | content, sources (list[str]), mode, success, error_message |
| `KnowledgeStatus` | 知识库状态信息 | enabled, ready, document_count, last_indexed_at, working_dir |

- **设计特点**:
  - 所有模型继承 `pydantic.BaseModel`，与项目其余领域模型风格一致
  - `KnowledgeDocument.doc_id` 由内容 MD5 哈希前 12 位生成，保证幂等性
  - `RetrievalResult` 内置 `success` + `error_message` 错误信息，支撑降级策略

### §3.3 ingestion.py
- **类型**: S-服务（文档接入）
- **职责**: 从本地目录加载 Markdown 知识文档，提取元数据
- **公开函数**:

| 函数 | 签名 | 职责 |
|------|------|------|
| `scan_knowledge_directory` | `(docs_dir, max_doc_size_kb=1024) → list[tuple[KnowledgeDocument, str]]` | 递归扫描目录下所有 .md 文件，过滤空文件/超大文件/非 UTF-8 |
| `validate_document_path` | `(file_path, max_doc_size_kb=1024) → str` | 校验单个文档路径，返回文件内容，不合法时抛 ValueError |

- **扫描策略**:
  1. 递归 `rglob("*.md")` 遍历目录
  2. 三层过滤：空文件 → 超大文件（默认 >1024KB）→ 非 UTF-8 编码
  3. 基于文件内容计算 MD5 生成 `doc_id`
  4. 返回 `(元数据, 内容文本)` 元组列表，按路径排序
- **容错**: 所有异常均 log warning 后跳过，不中断扫描流程

### §3.4 graphrag_engine.py
- **类型**: S-服务（核心引擎）
- **职责**: 封装 LightRAG 实例的完整生命周期管理
- **核心类**: `GraphRAGEngine`

#### 生命周期方法
| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(settings: Settings)` | 保存配置，初始化内部状态 |
| `initialize` | `async () → None` | 创建 LightRAG 实例、初始化存储、加载文档注册表 |
| `finalize` | `async () → None` | 释放 LightRAG 存储资源 |
| `is_ready` | `() → bool` | 检查引擎是否就绪 |

#### 索引方法
| 方法 | 签名 | 说明 |
|------|------|------|
| `insert_document` | `async (content, metadata) → KnowledgeDocument` | 索引单文档，基于 MD5 哈希跳过未变化文档 |
| `insert_batch` | `async (docs) → list[KnowledgeDocument]` | 批量索引，逐条调用 insert_document |
| `delete_document` | `async (doc_id) → bool` | 删除已索引文档 |
| `reindex_all` | `async (docs_dir) → int` | 全量重建索引：清理 → 重新初始化 → 重新扫描 |

#### 检索方法
| 方法 | 签名 | 说明 |
|------|------|------|
| `query` | `async (query_text, mode="hybrid") → RetrievalResult` | 执行知识检索，支持 naive/local/global/hybrid/mix 五种模式 |

#### LLM/Embedding 适配器
| 函数 | 说明 |
|------|------|
| `_openai_compatible_llm` | 通过 httpx 调用 OpenAI-compatible chat/completions 端点，复用 Settings 中的 LLM 配置 |
| `_openai_compatible_embedding` | 通过 httpx 调用 /v1/embeddings 端点，模型优先使用 `knowledge_embedding_model` |

- **文档注册表持久化**: 通过 `indexed_documents.json` 文件持久化已索引文档的元数据，避免重复索引
- **幂等性**: `insert_document` 基于内容 MD5 哈希判断文档是否已索引且未变化

### §3.5 retriever.py
- **类型**: S-服务（检索接口）
- **职责**: 提供查询构造和结果格式化，将 GraphRAG 原始结果转换为可注入 LLM prompt 的文本
- **公开函数**:

| 函数 | 签名 | 职责 |
|------|------|------|
| `build_retrieval_query` | `(parsed_document: ParsedDocument) → str` | 从 PRD 提取标题 + 正文前 400 字符，截断到 500 字符 |
| `format_retrieval_result` | `(result: RetrievalResult) → str` | 将检索结果截断到 2000 字符，失败/空结果返回空字符串 |
| `retrieve_knowledge` | `async (engine, parsed_document, mode) → (str, list[str], bool)` | 完整检索流程：构造查询 → 调用引擎 → 格式化结果 |

- **返回三元组**: `(knowledge_context, knowledge_sources, success)` — 与 GlobalState 的三个新字段一一对应
- **降级策略**: 引擎未就绪时返回 `("", [], False)`；查询为空时返回 `("", [], True)`

## §4 模块依赖与设计模式

### 内部依赖
```
models.py ← ingestion.py (KnowledgeDocument)
models.py ← graphrag_engine.py (KnowledgeDocument, RetrievalResult, KnowledgeStatus)
models.py ← retriever.py (RetrievalResult)
graphrag_engine.py ← retriever.py (GraphRAGEngine)
ingestion.py ← graphrag_engine.py.reindex_all (scan_knowledge_directory)
```

### 外部依赖
| 依赖 | 引入方 | 说明 |
|------|--------|------|
| `lightrag` (LightRAG, QueryParam, EmbeddingFunc) | graphrag_engine.py | 核心 GraphRAG 框架 |
| `numpy` | graphrag_engine.py | Embedding 向量数组 |
| `httpx` | graphrag_engine.py | OpenAI-compatible API 调用 |
| `app.config.settings.Settings` | graphrag_engine.py | 读取 LLM/知识检索配置 |
| `app.domain.document_models.ParsedDocument` | retriever.py | PRD 文档模型 |

### 设计模式
1. **引擎封装模式**: `GraphRAGEngine` 将第三方 LightRAG 完全封装，对外仅暴露 async 接口
2. **适配器模式**: `_openai_compatible_llm` / `_openai_compatible_embedding` 将 LightRAG 回调桥接到项目 LLM 配置
3. **注册表持久化**: 通过 JSON 文件维护文档元数据，支撑幂等索引和文档管理
4. **优雅降级**: 所有检索失败均返回空结果，不抛异常，不阻塞主工作流

## §5 补充观察

1. **完全解耦**: knowledge 模块与工作流核心无直接依赖——通过 `retriever.py` 返回三元组写入 GlobalState，由节点层桥接
2. **可配置性强**: 7 个 `knowledge_*` 配置字段覆盖开关、路径、检索模式、top_k、模型、文件大小等维度
3. **幂等索引**: 基于 MD5 哈希的跳重机制避免重复索引，适合增量场景
4. **适配器复用项目 LLM**: 不引入额外 LLM 客户端，复用 Settings 中的 API 配置，降低配置复杂度
5. **硬编码 embedding 维度**: `embedding_dim=1536` 硬编码为 OpenAI 默认值，若切换非 OpenAI 模型需修改
6. **单线程批量索引**: `insert_batch` 逐条 await 而非并发，大量文档时可能较慢