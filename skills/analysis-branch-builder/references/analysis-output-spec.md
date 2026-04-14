# Analysis Output Spec

Every `_ANALYSIS.md` must follow one stable structure.

## Required Sections

1. Title with the relative directory path
2. Metadata block:
   - analysis time
   - source branch
   - analyzed commit SHA
   - direct source-file count
   - direct child directories
3. `目录职责概述`
4. `文件分析`
5. `本目录内部依赖关系`
6. `对外暴露接口`
7. Optional `补充观察`

Use `_ROOT_ANALYSIS.md` for root-level direct files and keep the same structure.

## Numbering Rules

- `§N`: file number, sorted by filename
- `§N.M`: file-internal analysis item, ordered by code appearance
- `§N.M.K`: class-method or equivalent sub-item

## File-Type Expectations

| Type | Required Detail |
| --- | --- |
| Entry file | Startup flow, assembly, config loading, global error handling, exported app or CLI surface |
| Route or API file | Endpoint table, middleware, validation, error response contract |
| Model or schema | Full field table, relations, indexes, validation rules, methods |
| Service or business logic | Function signature, responsibility, numbered core logic, branches, exceptions, external calls, side effects |
| Config file | Env vars, dependency purpose, script commands, config loading and defaults |
| Utility file | Public signatures, responsibility, usage context |
| Test file | Test names, target module, test type, framework, fixtures or mocks |
| CI/CD config | Trigger, jobs, step purpose, environment requirements, produced artifacts |
| Container or deploy config | Base image, build steps, ports, entry commands, service dependencies |
| Docs | Theme, outline, key information summary |
| Other | File type, purpose, business relevance |

## Constraints

- Do not copy source code into the analysis branch.
- Do not record real secret values.
- Put risk, performance, or pattern commentary only in `补充观察`, and label it as observational.
