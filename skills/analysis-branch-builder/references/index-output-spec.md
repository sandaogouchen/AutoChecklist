# Index Output Spec

Generate `_INDEX.md` after all analysis documents are ready.

## Required Sections

1. `项目概述`
2. `技术栈`
3. `项目结构总览`
4. `分析文件索引`
5. `模块依赖全景`
6. `外部依赖与集成`
7. `环境变量清单`
8. Optional `改进建议`
9. `元信息`

## Section Rules

- `项目概述`: 3-5 sentences explaining what the project is, the problem it solves, its users, and the main technical direction.
- `技术栈`: table with category, technology, version if known, and purpose.
- `项目结构总览`: tree plus one-line directory responsibilities.
- `分析文件索引`: one row per analysis file with covered source files, distinct summary, and file count.
- `模块依赖全景`: global dependency picture across directories or layers.
- `外部依赖与集成`: external services, storage, APIs, and how they are configured.
- `环境变量清单`: variable name, purpose, required flag, and usage location.
- `改进建议`: observational only; cite analysis sections.

## Required Metadata YAML

```yaml
last_updated: "<ISO 8601>"
analyzed_commit: "<full sha>"
analyzed_branch: "<source branch>"
total_source_files_analyzed: <int>
total_analysis_files_generated: <int>
generation_mode: "full" | "incremental"
```

If the analysis is degraded or partially rebuilt, say so in the prose and keep the metadata honest.
