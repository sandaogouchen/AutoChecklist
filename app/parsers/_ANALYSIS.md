# app/parsers/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 4 | 分析策略: 业务逻辑 (business logic) + 工具函数 (utility) + 数据处理 (data processing)

## §1 目录职责

`app/parsers/` 是 AutoChecklist 系统的**文档解析层**，负责将外部 PRD 文档（当前为 Markdown 格式）转化为系统内部的结构化表示 `ParsedDocument`。该目录采用**协议 + 工厂**的可扩展架构：

1. **协议定义** (`base.py`): 通过 `Protocol` 定义解析器接口契约，支持鸭子类型
2. **工厂路由** (`factory.py`): 根据文件后缀分发到具体解析器实例
3. **具体解析器** (`markdown.py`): 实现 Markdown/PRD 文件的逐行解析逻辑

该目录是主工作流中 `input_parser` 节点的底层支撑——`input_parser` 节点调用工厂获取解析器，解析器将原始文档转化为 `ParsedDocument`，写入 `GlobalState.parsed_document` 供后续节点消费。

## §2 文件清单

| 文件名 | 行数 | 主要职责 | 分析策略 |
|---|---|---|---|
| `__init__.py` | 1 | 包声明，标识 `app.parsers` 为 Python 子包 | — |
| `base.py` | 30 | 定义 `BaseDocumentParser` Protocol 接口 | 业务逻辑 |
| `factory.py` | 34 | 工厂函数 `get_parser()`，按文件后缀路由到解析器 | 业务逻辑 + 工具函数 |
| `markdown.py` | 117 | `MarkdownParser` 实现，逐行解析 Markdown 文档 | 数据处理 |

## §3 文件详细分析

### §3.1 `__init__.py`

- **路径**: `app/parsers/__init__.py`
- **行数**: 1
- **职责**: 包初始化声明，文档字符串为 `"""文档解析器子包。"""`

#### §3.1.1 核心内容

仅包含模块级文档字符串，无导出符号。作为 Python 包标识文件存在。

#### §3.1.2 依赖关系

无依赖。

#### §3.1.3 关键逻辑 / 数据流

无运行时逻辑。

---

### §3.2 `base.py`

- **路径**: `app/parsers/base.py`
- **行数**: 30
- **职责**: 定义文档解析器的协议接口（`typing.Protocol`），作为所有解析器实现的类型契约

#### §3.2.1 核心内容

**协议类**: `BaseDocumentParser(Protocol)`

```python
class BaseDocumentParser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...
```

该协议定义了**唯一方法** `parse(path: Path) -> ParsedDocument`：
- **输入**: `pathlib.Path` 类型的文件绝对路径
- **输出**: `ParsedDocument` 结构化解析结果

采用 Python 的**结构化子类型**（Structural Subtyping / 鸭子类型）机制——任何实现了 `parse` 方法且签名匹配的类均隐式满足此协议，无需显式继承 `BaseDocumentParser`。

#### §3.2.2 依赖关系

**内部依赖**:
- `app.domain.document_models.ParsedDocument` — 解析结果的领域模型

**外部依赖**:
- `pathlib.Path` — 文件路径抽象
- `typing.Protocol` — Python 协议类型支持

#### §3.2.3 关键逻辑 / 数据流

无运行时逻辑。纯类型定义文件，用于：
1. 类型检查器（mypy / pyright）的静态验证
2. 工厂函数 `get_parser()` 返回值的类型标注
3. 代码文档化——明确所有解析器必须遵循的契约

---

### §3.3 `factory.py`

- **路径**: `app/parsers/factory.py`
- **行数**: 34
- **职责**: 解析器工厂，根据文件后缀路由到对应解析器实例

#### §3.3.1 核心内容

**模块常量**:
```python
SUPPORTED_MARKDOWN_SUFFIXES = {".md", ".markdown", ".prd"}
```

支持的 Markdown 系文件后缀集合，使用 `set` 保证 O(1) 查找性能。

**工厂函数**: `get_parser(path: Path) -> BaseDocumentParser`

路由逻辑：
1. 提取 `path.suffix.lower()` 获取小写后缀
2. 若后缀在 `SUPPORTED_MARKDOWN_SUFFIXES` 中 → 返回 `MarkdownParser()` 新实例
3. 否则 → 抛出 `ValueError(f"Unsupported document type: {path.suffix}")`

**当前路由表**:

| 文件后缀 | 解析器类 | 说明 |
|---|---|---|
| `.md` | `MarkdownParser` | 标准 Markdown 文件 |
| `.markdown` | `MarkdownParser` | 长后缀 Markdown 文件 |
| `.prd` | `MarkdownParser` | PRD 文档（视为 Markdown 格式） |
| 其他 | — | 抛出 `ValueError` |

#### §3.3.2 依赖关系

**内部依赖**:
- `app.parsers.base.BaseDocumentParser` — 返回类型的协议标注
- `app.parsers.markdown.MarkdownParser` — 当前唯一的具体解析器

**外部依赖**:
- `pathlib.Path`

#### §3.3.3 关键逻辑 / 数据流

```
调用方 (如 input_parser 节点)
    │
    │  get_parser(Path("feature.prd"))
    ▼
factory.py
    │  path.suffix.lower() → ".prd"
    │  ".prd" in SUPPORTED_MARKDOWN_SUFFIXES → True
    ▼
返回 MarkdownParser() 实例
```

**扩展点**: 未来添加新格式（如 PDF、Word）时，需在此函数中增加后缀判断分支并导入对应解析器类。

---

### §3.4 `markdown.py`

- **路径**: `app/parsers/markdown.py`
- **行数**: 117
- **职责**: Markdown 文档解析器，将 `.md`/`.markdown`/`.prd` 文件解析为 `ParsedDocument`

#### §3.4.1 核心内容

**类**: `MarkdownParser`

隐式满足 `BaseDocumentParser` 协议（未显式继承），包含 3 个方法：

**方法 1**: `parse(self, path: Path) -> ParsedDocument`

主入口方法，执行以下步骤：
1. `path.read_text(encoding="utf-8")` 读取文件原始文本
2. `raw_text.splitlines()` 按行拆分
3. 调用 `_extract_sections(lines, default_heading=path.stem)` 提取章节
4. 调用 `_extract_references(lines)` 提取引用链接
5. `hashlib.sha256(raw_text.encode("utf-8")).hexdigest()` 计算内容校验和
6. 组装并返回 `ParsedDocument` 对象

返回的 `ParsedDocument` 结构：

| 字段 | 类型 | 来源 |
|---|---|---|
| `raw_text` | `str` | 原始文件全文 |
| `sections` | `list[DocumentSection]` | `_extract_sections()` 输出 |
| `references` | `list[str]` | `_extract_references()` 输出 |
| `metadata` | `dict` | `{"section_count": len(sections)}` |
| `source` | `DocumentSource` | 路径、类型、标题、校验和 |

**方法 2**: `_extract_sections(self, lines: list[str], default_heading: str) -> list[DocumentSection]`

核心章节提取算法——基于**逐行扫描 + 累积缓冲区**模式：

```
算法流程:
1. 初始化: current_heading=default_heading, current_lines=[], current_start=1
2. 遍历每行 (index从1开始):
   ├── 行以 "#" 开头?
   │   ├── YES: 将缓冲区内容封装为 DocumentSection 并追加到 sections
   │   │        解析新标题层级 (level = "#"字符数)
   │   │        重置缓冲区
   │   └── NO:  将当前行追加到 current_lines 缓冲区
3. 循环结束后: 将最后一个缓冲区封装为 DocumentSection
```

`DocumentSection` 字段：
- `heading`: 标题文本（去除 `#` 前缀）
- `level`: 标题层级（`#` 的数量，如 `##` = 2）
- `content`: 标题下方的正文内容（`"\n".join(current_lines).strip()`）
- `line_start`: 章节起始行号
- `line_end`: 章节结束行号

**方法 3**: `_extract_references(lines: list[str]) -> list[str]` （`@staticmethod`）

使用简单启发式规则提取 Markdown 链接：扫描所有包含 `](` 子串的行，返回去除首尾空白后的行列表。

#### §3.4.2 依赖关系

**内部依赖**:
- `app.domain.document_models.DocumentSection` — 章节数据模型
- `app.domain.document_models.DocumentSource` — 文档来源元数据
- `app.domain.document_models.ParsedDocument` — 解析结果顶层模型

**外部依赖**:
- `hashlib` — SHA-256 校验和计算
- `pathlib.Path` — 文件路径与读取

#### §3.4.3 关键逻辑 / 数据流

**完整解析数据流**:

```
Markdown 文件 (磁盘)
    │
    │ path.read_text("utf-8")
    ▼
raw_text (str)
    │
    ├── splitlines() ──────────────────────────────────────┐
    │                                                       │
    │                                                       ▼
    │                                              _extract_sections(lines)
    │                                                       │
    │                                      逐行扫描，按 "#" 拆分
    │                                                       │
    │                                                       ▼
    │                                              list[DocumentSection]
    │                                                       │
    ├── splitlines() ──────────────────────────────────────┐│
    │                                                       ││
    │                                                       ▼│
    │                                            _extract_references(lines)
    │                                                       ││
    │                                      过滤含 "](" 的行  ││
    │                                                       ▼│
    │                                              list[str]  │
    │                                                       │ │
    ├── sha256(encode("utf-8")).hexdigest() ───► checksum   │ │
    │                                                       │ │
    ▼                                                       ▼ ▼
ParsedDocument(raw_text, sections, references, metadata, source)
```

## §4 目录级依赖关系

```
app/parsers/
    │
    ├──► app/domain/document_models   (ParsedDocument, DocumentSection, DocumentSource)
    │
    └──► Python 标准库
            ├── pathlib.Path
            ├── hashlib
            └── typing.Protocol

被依赖方:
    app/nodes/input_parser  ──►  app/parsers/factory.get_parser()
```

**依赖方向**: `parsers/` 仅依赖 `domain/` 层的数据模型和 Python 标准库，不依赖任何外部第三方包。它被 `nodes/input_parser` 通过工厂函数调用，是工作流的最上游数据入口。

## §5 设计模式与架构特征

| 模式 | 应用位置 | 说明 |
|---|---|---|
| **Protocol 协议接口** (Structural Typing) | `base.py` `BaseDocumentParser` | 使用 `typing.Protocol` 定义解析器契约，支持鸭子类型而非继承式多态 |
| **简单工厂** (Simple Factory) | `factory.py` `get_parser()` | 根据文件后缀返回对应解析器实例，集中管理创建逻辑 |
| **策略模式** (Strategy Pattern) | 整体目录结构 | Protocol + Factory 组合实现运行时策略选择：同一 `parse()` 接口，不同文件类型由不同解析器处理 |
| **累积缓冲区扫描** (Accumulator Scanner) | `markdown.py` `_extract_sections()` | 逐行扫描维护状态缓冲区，遇到分隔标记时刷新——经典的流式文本解析模式 |
| **启发式匹配** (Heuristic Matching) | `markdown.py` `_extract_references()` | 使用 `](` 子串作为 Markdown 链接的简单检测标记，避免引入正则表达式或完整 Markdown AST 解析器 |
| **不可变结果对象** (Immutable Result) | `parse()` 返回 `ParsedDocument` | 解析结果作为值对象返回，后续节点只读消费，不修改解析结果 |

## §6 潜在关注点

1. **引用提取精度**: `_extract_references()` 使用 `](` 作为启发式匹配，可能产生误匹配（如代码块中包含 `](` 的行）或漏匹配（使用尖括号链接 `<url>` 的情况）。对于 PRD 文档的场景通常足够，但在链接密集型文档中可能需要更精确的解析。

2. **单一格式支持**: 当前仅支持 Markdown 系文件（`.md`/`.markdown`/`.prd`）。工厂函数的 `if-raise` 结构在新增格式时需要修改函数体，违反开闭原则。可考虑改为注册表模式（`dict[str, type[Parser]]`）以支持插件式扩展。

3. **大文件性能**: `parse()` 方法使用 `path.read_text()` 一次性读入整个文件到内存，对于超大 PRD 文档可能产生内存压力。`splitlines()` 被调用两次（`_extract_sections` 和 `_extract_references` 各一次），虽然 `lines` 列表被复用，但在 `parse()` 中 `lines = raw_text.splitlines()` 只构建了一次列表并传入两个方法，这一点实现是合理的。

4. **标题解析边界情况**: `_extract_sections()` 将所有以 `#` 开头的行视为标题，未排除代码块（` ``` `）内部的 `#` 字符。若 PRD 文档中包含代码示例（如 Markdown 模板），可能错误地将代码块中的 `#` 注释解析为章节标题。

5. **编码假设**: `parse()` 硬编码使用 `encoding="utf-8"`。在极少数使用其他编码的文档场景下会抛出 `UnicodeDecodeError`，未提供编码检测或回退机制。

6. **空文件处理**: 当输入文件为空时，`_extract_sections()` 中 `if lines:` 保护了最后一个章节的追加逻辑，但 `parse()` 中 `sections[0].heading` 的访问（用于设置 `source.title`）会因 `sections` 为空列表而抛出 `IndexError`。代码中已有 `sections[0].heading if sections else path.stem` 的三元表达式保护。