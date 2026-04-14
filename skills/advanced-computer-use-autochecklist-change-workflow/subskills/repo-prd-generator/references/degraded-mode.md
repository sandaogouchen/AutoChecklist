# Degraded Mode

Use degraded mode only when `analysis_branch` is missing, unreadable, or structurally broken.

## Allowed Read Scope

1. Source-branch root directory, first level only
2. `README.md`
3. Package manager files such as `pyproject.toml`, `package.json`, `requirements.txt`, or `go.mod`
4. The first 80 lines of the main entry file or files

## Required Markers

In degraded mode:

- mark `关联现有代码` as `[需基于分析分支补充]` where citations would normally appear
- mark `涉及改动文件清单` references as `[需基于分析分支补充]`
- add a visible warning that the analysis branch should be built or refreshed

## Hard Rules

- Do not fabricate `§N.M` references.
- Do not pretend the lightweight scan is equivalent to the analysis branch.
- Still produce the full PRD structure; only the citation depth degrades.
