# app/knowledge/ Directory Analysis

## §13.1 Directory Overview

The `app/knowledge/` directory implements the **GraphRAG-powered knowledge retrieval system** for AutoChecklist. This subsystem allows the pipeline to enrich test case generation with domain-specific knowledge retrieved from pre-indexed Markdown documents using LightRAG, an open-source Graph RAG (Retrieval-Augmented Generation) library.

The directory contains four modules:

1. **`graphrag_engine.py`** -- The core engine class that wraps LightRAG, managing the full lifecycle: initialization, document indexing, knowledge retrieval, and resource cleanup.
2. **`ingestion.py`** -- Document scanning, validation, and loading from the filesystem, preparing content for indexing.
3. **`models.py`** -- Pydantic domain models for knowledge documents, retrieval results, and system status.
4. **`retriever.py`** -- High-level retrieval interface that constructs queries from parsed PRD documents and formats results for prompt injection.

**Architecture**: The knowledge system is an **optional enhancement** to the main pipeline. When enabled, it injects a `knowledge_retrieval` node into the main workflow graph (§6) between the context loaders and `context_research`. When disabled, the pipeline operates normally without knowledge-augmented context.

**Technology**: LightRAG library, OpenAI-compatible embedding/LLM APIs via httpx, numpy for embedding arrays, Pydantic v2 for data models.

---

## §13.2 File Analysis

### §13.2.1 graphrag_engine.py

**Type**: Type A -- Core Infrastructure  
**Criticality**: **MEDIUM-HIGH**  
**Lines**: ~320  
**Primary Export**: `GraphRAGEngine` class

#### LightRAG Integration Architecture

The `GraphRAGEngine` class wraps a `LightRAG` instance and provides the full lifecycle:

```
initialize() → insert_document() / insert_batch() → query() → finalize()
```

**LightRAG configuration**:
- Working directory: `settings.knowledge_working_dir` (persistent across restarts)
- LLM callback: `_openai_compatible_llm()` (async, via httpx)
- Embedding callback: `_openai_compatible_embedding()` (async, via httpx)
- Embedding dimension: Hardcoded to 1536 (OpenAI default)
- Max embedding token size: 8192

#### LLM/Embedding Callback Adapters

Two async callback functions bridge LightRAG to the project's OpenAI-compatible endpoints:

**`_openai_compatible_llm()`**:
- Constructs chat completion messages from `prompt`, `system_prompt`, and `history_messages`
- Uses `httpx.AsyncClient` to call `{base_url}/chat/completions`
- Temperature: 0.0 for keyword extraction, otherwise `settings.llm_temperature`
- Max tokens: `settings.llm_max_tokens`
- Timeout: `settings.llm_timeout_seconds`

**`_openai_compatible_embedding()`**:
- Calls `{base_url}/embeddings` with the configured embedding model
- Falls back to `settings.llm_model` if no embedding model is specified
- Returns `np.ndarray` of embeddings

**Important design note**: These callbacks create a **new `Settings()` instance** on every invocation rather than using the engine's stored `_settings`. This means they always read the latest environment variables, but it also means configuration changes between calls could cause inconsistencies. Additionally, these callbacks bypass the `LLMClient` (§4) entirely -- they use raw httpx calls without the retry/fallback mechanisms that `LLMClient` provides.

#### Document Indexing

**Single document** (`insert_document()`):
1. Compute MD5 hash of content
2. Generate `doc_id` from hash (or use provided one)
3. Check if already indexed with same hash (skip if unchanged)
4. Call `self._rag.ainsert(content, ids=[doc_id], file_paths=[...])`
5. Create `KnowledgeDocument` metadata
6. Save to in-memory registry and persist to JSON file

**Batch indexing** (`insert_batch()`):
- Iterates over `(KnowledgeDocument, content)` pairs
- Calls `insert_document()` for each, catching exceptions per-document
- Returns list of successfully indexed documents

**Content deduplication**: Uses MD5 hash comparison to skip re-indexing unchanged documents. This is efficient for the common case of restarting the engine with an existing document set.

#### Knowledge Retrieval

The `query()` method:
1. Validates engine readiness
2. Creates `QueryParam(mode=mode)` where mode is one of: `naive`, `local`, `global`, `hybrid`, `mix`
3. Calls `self._rag.aquery(query_text, param=param)`
4. Returns `RetrievalResult` with content, sources (all document IDs), mode, and success flag
5. Catches all exceptions and returns error result (never raises)

**Source tracking limitation**: The current implementation returns ALL document IDs as sources, regardless of which documents actually contributed to the query result. This is a known limitation of the LightRAG integration -- granular source attribution would require additional LightRAG API support.

#### Full Reindex

`reindex_all()`:
1. Finalize current engine (release resources)
2. Delete entire working directory (`shutil.rmtree`)
3. Clear in-memory document registry
4. Re-initialize engine
5. Scan document directory via `ingestion.scan_knowledge_directory()`
6. Batch insert all found documents

This is a destructive operation that rebuilds the entire knowledge graph from scratch.

#### Document Registry Persistence

The engine maintains a JSON file (`indexed_documents.json`) in the working directory that stores `KnowledgeDocument` metadata for all indexed documents. This registry:
- Loads on `initialize()` via `_load_document_registry()`
- Updates after every insert/delete via `_save_document_registry()`
- Enables content-hash-based deduplication across engine restarts
- Uses Pydantic `model_validate()` / `model_dump()` for serialization

---

### §13.2.2 ingestion.py

**Type**: Type B -- Data Loading  
**Criticality**: **MEDIUM**  
**Lines**: ~100  
**Primary Exports**: `scan_knowledge_directory()`, `validate_document_path()`

#### Directory Scanning

`scan_knowledge_directory(docs_dir, max_doc_size_kb=1024)`:
- Recursively scans for `.md` files using `Path.rglob("*.md")`
- Filters: non-empty, under size limit, UTF-8 decodable
- For each valid file: reads content, computes MD5 hash, creates `KnowledgeDocument` metadata
- Returns list of `(KnowledgeDocument, content_text)` tuples
- Sorted by path for deterministic ordering

**Skip conditions** (with warning logs):
- Empty files (0 bytes)
- Oversized files (exceeds `max_doc_size_kb`)
- Non-UTF-8 files (`UnicodeDecodeError`)
- Unreadable files (`OSError`)

#### Single Document Validation

`validate_document_path(file_path, max_doc_size_kb=1024)`:
- Resolves to absolute path
- Validates: exists, `.md` extension, non-empty, under size limit, UTF-8 encoding
- Returns file content as string
- Raises `ValueError` with descriptive messages for each validation failure

This function is called by the API layer (§3.2.3) during document upload.

---

### §13.2.3 models.py

**Type**: Type C -- Data Model  
**Criticality**: **LOW**  
**Lines**: ~40  
**Primary Exports**: `KnowledgeDocument`, `RetrievalResult`, `KnowledgeStatus`

Three Pydantic BaseModel classes:

**`KnowledgeDocument`**:
| Field | Type | Purpose |
|---|---|---|
| `doc_id` | `str` | Unique identifier (MD5-based) |
| `file_name` | `str` | Original filename |
| `file_path` | `str` | Absolute filesystem path |
| `file_size_bytes` | `int` | File size |
| `md5_hash` | `str` | Content hash for deduplication |
| `indexed_at` | `Optional[datetime]` | Indexing timestamp |
| `entity_count` | `int` | Number of extracted entities (default 0) |

**`RetrievalResult`**:
| Field | Type | Purpose |
|---|---|---|
| `content` | `str` | Retrieved knowledge text |
| `sources` | `list[str]` | Source document identifiers |
| `mode` | `str` | Retrieval mode used |
| `success` | `bool` | Whether retrieval succeeded |
| `error_message` | `str` | Error details on failure |

**`KnowledgeStatus`**:
| Field | Type | Purpose |
|---|---|---|
| `enabled` | `bool` | Whether knowledge retrieval is configured |
| `ready` | `bool` | Whether engine is initialized and ready |
| `document_count` | `int` | Number of indexed documents |
| `last_indexed_at` | `Optional[datetime]` | Most recent indexing time |
| `working_dir` | `str` | LightRAG working directory path |

---

### §13.2.4 retriever.py

**Type**: Type B -- Integration Layer  
**Criticality**: **MEDIUM**  
**Lines**: ~100  
**Primary Exports**: `retrieve_knowledge()`, `build_retrieval_query()`, `format_retrieval_result()`

#### Query Construction

`build_retrieval_query(parsed_document)`:
- Extracts document title from `parsed_document.source.title`
- Takes the first 400 characters of `parsed_document.raw_text`
- Concatenates and truncates to 500 characters total
- Returns the query string

The 500-character limit is a precision-over-recall tradeoff -- shorter queries tend to produce more focused results from graph-based retrieval.

#### Result Formatting

`format_retrieval_result(result)`:
- Returns empty string for failed or empty results
- Truncates content to `MAX_KNOWLEDGE_CONTEXT_CHARS` (2000 characters)
- Appends truncation indicator if content was trimmed

The 2000-character limit prevents knowledge context from dominating the LLM's context window in downstream prompts.

#### Complete Retrieval Flow

`retrieve_knowledge(engine, parsed_document, mode="hybrid")`:
1. Check engine readiness (skip if not ready)
2. Build query from parsed document
3. Validate query is non-empty
4. Execute `engine.query(query, mode=mode)`
5. Format result for prompt injection
6. Return `(knowledge_context, knowledge_sources, success)` triple

This function is the interface used by the workflow's `knowledge_retrieval` node (§6).

---

## §13.3 Knowledge System Architecture

### System Flow

```
[Filesystem]                    [LightRAG Engine]              [Workflow Pipeline]
     │                               │                               │
     ├─ .md files ────────────────►│                               │
     │   (scan_knowledge_directory)  │                               │
     │                               ├─ Entity extraction            │
     │                               ├─ Relationship extraction       │
     │                               ├─ Graph construction            │
     │                               ├─ Embedding generation          │
     │                               │                               │
     │                               │◄── query (from retriever) ────┤
     │                               │                               │
     │                               ├── Graph traversal              │
     │                               ├── LLM synthesis                │
     │                               │                               │
     │                               ├── RetrievalResult ───────────►│
     │                               │   (formatted context)          │
     │                               │                       knowledge_retrieval node
```

### Retrieval Modes

LightRAG supports five retrieval modes, each with different quality/performance tradeoffs:

| Mode | Description | Best For |
|---|---|---|
| `naive` | Direct vector similarity search | Simple keyword-like queries |
| `local` | Entity-centric graph traversal | Specific concept lookups |
| `global` | Community-level summarization | Broad topic understanding |
| `hybrid` | Combination of local + global | General-purpose (default) |
| `mix` | All modes combined | Maximum recall at cost of latency |

### Integration Points

1. **API Layer** (§3.2.3): CRUD operations for documents, manual query endpoint, reindex trigger
2. **Workflow Graph** (§6.2.1): Optional `knowledge_retrieval` node injected into main pipeline
3. **Configuration**: `Settings` controls `enable_knowledge_retrieval`, `knowledge_working_dir`, `knowledge_max_doc_size_kb`, `knowledge_embedding_model`, `knowledge_docs_dir`

### Persistence Model

The knowledge system has a **dual persistence** approach:
- **LightRAG internal storage**: Graph database and vector indices in the working directory (managed by LightRAG)
- **Document registry**: `indexed_documents.json` in the same directory (managed by `GraphRAGEngine`)

Both are filesystem-based, which means:
- Data survives process restarts but not container rebuilds (unless volume-mounted)
- No concurrent write safety beyond what LightRAG provides internally
- Full reindex is the recovery mechanism for corruption

---

## §13.4 Key Findings

1. **Separate LLM path**: The GraphRAG engine uses raw httpx calls for LLM/embedding interactions, completely bypassing the `LLMClient` (§4) with its retry/fallback mechanisms. This means knowledge retrieval calls have **no retry logic, no exponential backoff, no model fallback**. A transient API error during indexing or retrieval fails immediately.

2. **Settings re-instantiation**: The LLM and embedding callbacks create `Settings()` on every invocation rather than closing over the engine's stored settings. This could lead to inconsistent behavior if environment variables change during runtime.

3. **Hardcoded embedding dimension**: The embedding dimension is hardcoded to 1536 (OpenAI's default). If a non-OpenAI embedding model with a different dimension is used, this would cause silent dimensional mismatch errors.

4. **Coarse source attribution**: `query()` returns ALL document IDs as sources regardless of actual contribution. This makes it impossible for downstream nodes to determine which specific knowledge documents influenced the retrieval result.

5. **Content size limits are reasonable**: The 1024 KB document size limit and 2000-character retrieval context limit are appropriate for preventing oversized inputs from dominating the pipeline's context budget.

6. **No incremental index updates**: Modifying a document requires re-indexing it entirely. There is no diff-based update mechanism, though the MD5 deduplication prevents unnecessary re-indexing of unchanged documents.

7. **Async-only engine**: The `GraphRAGEngine` is fully async, which is appropriate for its FastAPI integration but creates a boundary with the synchronous `LLMClient` and synchronous workflow nodes. The knowledge retrieval node in the workflow likely needs an async-to-sync bridge.

8. **Destructive reindex**: `reindex_all()` deletes the entire working directory and rebuilds from scratch. There is no incremental rebuild or backup mechanism. In production, this could cause brief unavailability of the knowledge feature.

---

## §13.5 Cross-References

| Reference | Target | Relationship |
|---|---|---|
| `GraphRAGEngine` used by | `app/api/knowledge_routes.py` (§3.2.3) | API endpoint dependency |
| `retrieve_knowledge()` used by | Workflow `knowledge_retrieval` node (§6) | Pipeline integration |
| `ParsedDocument` | `app/domain/document_models.py` | Input to query construction |
| `Settings` | `app/config/settings.py` | Configuration source |
| LightRAG | External dependency (`lightrag` package) | Graph RAG library |
| OpenAI-compatible API | External service | LLM and embedding provider |
| `LLMClient` (§4) | `app/clients/llm.py` | NOT used (separate httpx path) |
| `validate_document_path` used by | `app/api/knowledge_routes.py` (§3.2.3) | Upload validation |
| `KnowledgeStatus` used by | `app/api/knowledge_routes.py` (§3.2.3) | Status endpoint response model |
| `scan_knowledge_directory` used by | `GraphRAGEngine.reindex_all()` | Bulk document loading |