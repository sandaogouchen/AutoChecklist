# app/parsers/ Directory Analysis

## §8.1 Directory Overview

The `app/parsers/` directory implements the **document parsing layer** for AutoChecklist. This layer is responsible for converting raw input documents (PRD files, requirement specs) into the structured `ParsedDocument` domain model that the rest of the pipeline consumes.

The directory follows a clean **Protocol + Factory + Implementation** pattern:

1. **`base.py`** -- Defines the `BaseDocumentParser` protocol (interface) that all parsers must satisfy.
2. **`factory.py`** -- Routes file paths to the correct parser implementation based on file extension.
3. **`markdown.py`** -- The primary parser implementation for Markdown-format documents (.md, .markdown, .prd).
4. **`xmind_parser.py`** -- A specialized parser for XMind mind-map files, used for reference structure comparison rather than primary document parsing.

**Architectural Role**: The parser layer is the **first transformation** in the pipeline -- it runs inside the `input_parser` node (the first node in the main workflow, §6). The quality of parsing directly affects all downstream nodes because every subsequent step operates on the `ParsedDocument` output.

**Technology**: Pure Python standard library (no external parsing dependencies for Markdown). `zipfile` and `json` for XMind parsing. Pydantic domain models from `app.domain`.

---

## §8.2 File Analysis

### §8.2.1 base.py

**Type**: Type C -- Interface Definition  
**Criticality**: **LOW** (defines contract, no logic)  
**Lines**: ~25  
**Primary Export**: `BaseDocumentParser` (Protocol)

#### Protocol Design

```python
class BaseDocumentParser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...
```

This uses Python's `typing.Protocol` for structural subtyping (duck typing). Any class implementing a `parse(path: Path) -> ParsedDocument` method satisfies this protocol **without explicit inheritance**. This is the standard Pythonic approach for defining parser interfaces.

The protocol requires:
- **Input**: A `pathlib.Path` representing the document file's absolute path
- **Output**: A `ParsedDocument` (from `app.domain.document_models`) containing sections, metadata, and raw text

**Design implication**: New parser implementations (e.g., for PDF, DOCX, HTML) only need to implement this single method to integrate with the factory and pipeline.

---

### §8.2.2 factory.py

**Type**: Type B -- Routing  
**Criticality**: **MEDIUM**  
**Lines**: ~25  
**Primary Export**: `get_parser()` function

#### Extension-Based Parser Selection

```python
SUPPORTED_MARKDOWN_SUFFIXES = {".md", ".markdown", ".prd"}

def get_parser(path: Path) -> BaseDocumentParser:
    if path.suffix.lower() in SUPPORTED_MARKDOWN_SUFFIXES:
        return MarkdownParser()
    raise ValueError(f"Unsupported document type: {path.suffix}")
```

Key characteristics:
- Case-insensitive suffix matching (`.lower()`)
- `.prd` extension is treated as Markdown -- this is a domain-specific convention for PRD (Product Requirements Document) files
- Returns a **new instance** on each call (stateless parsers, no caching needed)
- Raises `ValueError` for unsupported extensions (not a custom exception type)

#### Extensibility

Adding a new format requires:
1. Implementing a class with `parse(self, path: Path) -> ParsedDocument`
2. Adding the extension(s) to the factory's routing logic
3. No changes to downstream consumers needed (they work with `ParsedDocument`)

Currently, only Markdown is supported. The factory's existence suggests PDF, Word, or other format support was anticipated but not yet implemented.

---

### §8.2.3 markdown.py

**Type**: Type A -- Core Implementation  
**Criticality**: **HIGH**  
**Lines**: ~100  
**Primary Export**: `MarkdownParser` class

#### Parsing Strategy

The `MarkdownParser` uses a **line-by-line scanning approach** rather than a full Markdown AST parser. This is deliberately simple:

1. Read entire file as UTF-8 text
2. Split into lines
3. Scan for lines starting with `#` to identify section boundaries
4. Extract reference links (lines containing `](`)
5. Compute SHA-256 checksum of raw content

#### Section Extraction Algorithm (`_extract_sections`)

The algorithm maintains a state machine with a "current section" accumulator:

```
For each line:
  If line starts with "#":
    1. Save accumulated lines as a DocumentSection
    2. Parse heading level (count of # characters)
    3. Parse heading text (strip # prefix)
    4. Reset accumulator
  Else:
    Append line to current accumulator

After all lines: save final accumulated section
```

**Key behaviors**:
- Heading level is determined by counting `#` characters: `## Heading` = level 2
- Empty heading text falls back to `default_heading` (the filename stem)
- Content between headings is joined with `\n` and stripped
- Line numbers are tracked (`line_start`, `line_end`) for each section
- If the document starts with non-heading text, it is captured under the `default_heading`

**Output structure** (`DocumentSection`):
| Field | Type | Content |
|---|---|---|
| `heading` | `str` | Section title text |
| `level` | `int` | Heading depth (1-6) |
| `content` | `str` | Body text between this heading and the next |
| `line_start` | `int` | Starting line number (1-based) |
| `line_end` | `int` | Ending line number |

#### Reference Extraction

A simple heuristic: any line containing `](` is considered a reference link. This catches:
- `[text](url)` -- standard Markdown links
- `![alt](image)` -- image references
- Links embedded within table cells or list items

The heuristic is imprecise (it could match literal text containing `](`), but for PRD documents this is acceptable since false positives are rare.

#### Document Source Metadata

The parser constructs a `DocumentSource` with:
- `source_path`: String representation of the file path
- `source_type`: Always `"markdown"`
- `title`: First section's heading (or filename stem if no headings)
- `checksum`: SHA-256 of the raw text (for change detection)

#### Limitations

1. **No Markdown AST**: The parser does not understand inline formatting (bold, italic, code), lists, tables, or blockquotes at a structural level. It only recognizes headings as structural boundaries.
2. **No front matter support**: YAML front matter (common in documentation) is not parsed separately.
3. **No nested structure**: All sections are flat (parent-child heading relationships are not tracked). A `## Subsection` under `# Section` produces two independent `DocumentSection` objects.
4. **UTF-8 only**: No encoding detection or fallback.

---

### §8.2.4 xmind_parser.py

**Type**: Type B -- Specialized Parser  
**Criticality**: **MEDIUM**  
**Lines**: ~100  
**Primary Export**: `XMindParser` class, `XMindParseError`, `UnsupportedXMindFormatError`

#### XMind File Format

XMind files (`.xmind`) are ZIP archives containing:
- `content.json` (XMind 8+ format) -- JSON array of sheets, each with a `rootTopic` tree
- `content.xml` (legacy format) -- XML-based structure (not supported)

The parser only supports XMind 8+ format and raises `UnsupportedXMindFormatError` for legacy files.

#### Parse Flow

1. **File validation**: Check existence, then open as ZIP
2. **Format detection**: Check for `content.json` in ZIP entries; if only `content.xml` exists, raise `UnsupportedXMindFormatError`
3. **JSON extraction**: Read and parse `content.json`
4. **Structure validation**: Verify non-empty array with `rootTopic`
5. **Recursive tree construction**: Walk the topic tree via `_parse_topic()`

#### Recursive Topic Parsing (`_parse_topic`)

XMind's internal structure uses:
- `topic["title"]` -- node text
- `topic["children"]["attached"]` -- list of child topics (standard format)
- `topic["children"]` as a direct list -- variant format (handled for compatibility)

The parser constructs an `XMindReferenceNode` tree:
```python
XMindReferenceNode(title=title, children=[...recursive...])
```

#### Error Hierarchy

```
XMindParseError (base)
├── UnsupportedXMindFormatError (legacy format)
└── (generic: corrupt ZIP, missing content.json, invalid JSON, missing rootTopic)
```

All errors include the file path in the message for debugging.

#### Difference from MarkdownParser

The `XMindParser` does NOT follow the `BaseDocumentParser` protocol:
- It takes `file_path: str` (not `Path`)
- It returns `XMindReferenceNode` (not `ParsedDocument`)
- It is not routed through the factory

This is intentional: XMind files serve as **reference structures** for coverage comparison (via the `xmind_reference_loader` node in §6), not as primary input documents. They represent the expected test case hierarchy, not the requirements being parsed.

---

## §8.3 Parser Architecture

### Design Pattern Summary

```
BaseDocumentParser (Protocol)
    │
    ├── MarkdownParser          (implements parse(Path) -> ParsedDocument)
    │     └── used by factory
    │
    └── [future parsers]        (PDF, DOCX, etc.)

XMindParser (separate hierarchy)
    └── parse(str) -> XMindReferenceNode
        └── used by xmind_reference_loader node

get_parser(Path) -> BaseDocumentParser     (factory function)
```

### Data Flow

```
Raw File (.md/.prd)
    │
    ├── get_parser(path) → MarkdownParser
    │
    └── MarkdownParser.parse(path)
        │
        ├── _extract_sections() → [DocumentSection, ...]
        ├── _extract_references() → [str, ...]
        ├── SHA-256 checksum
        │
        └── ParsedDocument
              ├── raw_text: str
              ├── sections: [DocumentSection]
              ├── references: [str]
              ├── metadata: {"section_count": N}
              └── source: DocumentSource
```

### Integration in Pipeline

The parser layer feeds into the very first pipeline node:
```
input_parser node → get_parser() → parser.parse() → ParsedDocument → GlobalState["parsed_document"]
```

Every subsequent node (context_research, scenario_planner, checkpoint_generator, etc.) reads from `parsed_document`. The section structure determines how the LLM analyzes the requirements, which directly impacts checkpoint and test case quality.

---

## §8.4 Key Findings

1. **Minimal Markdown parsing**: The parser intentionally avoids using a full Markdown AST library (like `markdown-it` or `mistletoe`). This makes it simple and dependency-free but means it cannot reason about inline formatting, nested lists, tables, or other structural elements. For PRD documents that use tables to define requirements, this could result in loss of structure.

2. **Flat section model**: The lack of hierarchical section tracking (parent-child heading relationships) means a document with nested headings produces a flat list. Downstream LLM nodes must infer hierarchy from heading levels, which adds cognitive load to the LLM prompts.

3. **XMind parser protocol mismatch**: The `XMindParser` intentionally does not conform to `BaseDocumentParser`, which is a conscious design choice reflecting its different role (reference structure vs. primary input). However, this creates two separate parser hierarchies in the same directory, which could confuse new developers.

4. **Factory is Markdown-only**: Despite the factory pattern suggesting extensibility, only Markdown is currently supported. The `.prd` extension mapping to Markdown is a pragmatic choice for the current use case.

5. **No content preprocessing**: The Markdown parser does not strip HTML tags, normalize whitespace, or handle special characters. If PRD documents contain embedded HTML (common in some documentation tools), these elements pass through as raw text.

6. **SHA-256 checksum for change detection**: The content checksum in `DocumentSource` enables cache invalidation and change detection, but no current code path uses it for caching. It may be intended for future incremental processing.

7. **Robust XMind error handling**: The XMind parser has thorough error handling for format detection, ZIP corruption, JSON parsing, and structure validation. This is important because XMind files come from external tools with varying format versions.

---

## §8.5 Cross-References

| Reference | Target | Relationship |
|---|---|---|
| `ParsedDocument` | `app/domain/document_models.py` | Output model for MarkdownParser |
| `DocumentSection` | `app/domain/document_models.py` | Section data structure |
| `DocumentSource` | `app/domain/document_models.py` | Source metadata |
| `XMindReferenceNode` | `app/domain/xmind_reference_models.py` | Output model for XMindParser |
| `input_parser_node` | `app/nodes/input_parser.py` | Calls `get_parser()` and `parser.parse()` |
| `get_parser()` used in | Main workflow (§6) via `input_parser` node | First pipeline step |
| `XMindParser` used by | `xmind_reference_loader` node (§6) | Reference structure loading |
| `build_retrieval_query()` | `app/knowledge/retriever.py` (§13) | Consumes `ParsedDocument` for query construction |
| Template-related parsing | `app/services/template_loader.py` | Separate YAML parsing (not in parsers/) |