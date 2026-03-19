# app/parsers/_ANALYSIS.md — 文档解析器分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `app/parsers/` |
| 文件数 | 4（含 `__init__.py`） |
| 分析文件 | 3 |
| 目录职责 | 文档解析层：将原始文本按格式解析为结构化 `ParsedDocument` |
| 设计模式 | Protocol + Factory — 结构子类型 + 格式路由 |

## §2 文件清单

| # | 文件 | 类型 | 行数(估) | 概要 |
|---|------|------|----------|------|
| 1 | `__init__.py` | - | 0 | 空 |
| 2 | `base.py` | E-接口契约 | ~15 | `DocumentParser` Protocol 定义 |
| 3 | `factory.py` | B-流程编排 | ~20 | 格式路由工厂函数 |
| 4 | `markdown.py` | A-核心算法 | ~60 | Markdown 解析器：按标题拆分章节 |

## §3 逐文件分析

### §3.1 base.py

- **类型**: E-接口契约
- **核心定义**: `DocumentParser` Protocol
  - 方法签名：`parse(content: str) → ParsedDocument`
  - 设计选择：使用 Protocol（结构子类型）而非 ABC（名义子类型）
  - 优势：任何实现了 `parse()` 方法的类自动满足接口，无需显式继承
- **依赖**: 引用 `domain.document_models.ParsedDocument`

### §3.2 factory.py

- **类型**: B-流程编排
- **职责**: 根据文件名后缀路由到对应解析器
- **路由规则**:
  | 后缀 | 解析器 |
  |------|--------|
  | `.md` | `MarkdownParser` |
  | `.markdown` | `MarkdownParser` |
  | `.prd` | `MarkdownParser` |
  | 其他 | `ValueError` |
- **扩展方式**: 添加新格式只需：(1) 实现 `DocumentParser` Protocol 的解析类，(2) 在路由表中添加后缀映射
- **当前局限**: 仅按文件后缀判断，不支持内容类型检测

### §3.3 markdown.py

- **类型**: A-核心算法
- **职责**: 将 Markdown 文本解析为 `ParsedDocument`（标题 + 章节列表）
- **解析算法**:
  1. 逐行扫描文本
  2. 检测 `#` 开头的行作为标题标记
  3. 首个 `#` 行 → 文档标题
  4. 后续 `##` 行 → 新 `DocumentSection` 分界
  5. 每个 section 保存 heading level、标题、内容
- **层级处理**: 记录每个 heading 的 level（# = 1, ## = 2, ### = 3...），供下游按层级过滤
- **边界情况**:
  - 无 `#` 标题 → 整个内容作为单个 section
  - 首个标题前的内容 → 归入前导 section
  - 代码块内的 `#` → **当前未特殊处理**，可能导致误分割

## §4 补充观察

1. **Pipeline 入口定位**: 解析器是整个工作流的第一步，其输出质量直接影响 `context_research` 的研究事实提取。如果章节分割不准确，下游所有节点的输入都会受到影响
2. **Protocol vs ABC 的权衡**: Protocol 的灵活性在当前仅有一种实现的情况下显得过度设计，但为未来扩展（如 Docx、HTML、Confluence 解析器）预留了良好接口
3. **代码块内标题误识别**: `markdown.py` 未处理 ``` 代码块内的 `#` 符号，复杂的技术类 PRD（包含代码示例）可能被错误分割。建议引入状态机跟踪代码块开闭
4. **不支持 frontmatter**: 许多 PRD 系统使用 YAML frontmatter（`---` 包裹），当前会被当作普通内容处理
5. **测试覆盖**: `test_markdown_parser.py` 提供了基础测试，但缺少代码块内标题、深层嵌套标题等边界用例
