---
name: analysis-branch-builder
description: Use when building, rebuilding, or incrementally refreshing a repository analysis branch with mirrored directory-level `_ANALYSIS.md` files and a root `_INDEX.md`, especially before repo-aware PRD generation, architecture review, or implementation planning.
---

# Analysis Branch Builder

## Overview

Build or refresh an `analysis` branch that mirrors the source tree with analysis documents instead of source files. Keep this file high-level and load the reference files only for the active branch of the workflow.

## Quick Start

1. Read [input contract](references/input-contract.md) and normalize missing optional fields to documented defaults.
2. Detect runtime:
   - Use GitHub MCP if `runtime_mode=github_mcp` or GitHub repo tools are available.
   - Use local git if `runtime_mode=local_git` or MCP is unavailable.
   - In `auto`, try MCP first and downgrade silently.
3. Choose workflow:
   - Read [file filter rules](references/file-filter-rules.md) and [analysis output spec](references/analysis-output-spec.md) for `full`.
   - Read [incremental update rules](references/incremental-update-rules.md) for `incremental` or `auto` after branch inspection.
   - Read [index output spec](references/index-output-spec.md) before writing `_INDEX.md`.
4. If `focus_topics` contains `checklist-optimization`, also read [checklist focus](references/checklist-focus.md).
5. Finish the build, branch/PR actions, and execution report in one run unless blocked by missing permissions.

## Workflow

1. Inspect `source_branch`, `analysis_branch`, and the branch state needed to decide `full` vs `incremental`.
2. Use `full` when the analysis branch is missing, `_INDEX.md` is missing or malformed, or `build_mode=full`.
3. Use `incremental` only when `_INDEX.md` exists and `analyzed_commit` can be trusted.
4. Scan the source tree with the documented filters and attribution rules. Never copy source files into the analysis branch.
5. Generate `_ROOT_ANALYSIS.md` and per-directory `_ANALYSIS.md` files with the required numbering, metadata, and type-specific detail.
6. Generate or update `_INDEX.md` last so it reflects the final set of analysis documents.
7. Submit changes:
   - MCP path: create branch, push files, open PR, merge when allowed.
   - Local path: create local branch and commits; if remote PR creation is unavailable, stop with an explicit handoff block.

## Runtime Notes

- Prefer GitHub MCP for remote reads, PRs, merges, and branch creation.
- In local mode, use git history, `git diff`, and file-system reads. Do not claim remote actions succeeded unless they were actually executed.
- Never read `.env` or record real secrets. Only analyze `.env.example`.

## Deliverables

- Mirrored analysis tree with `_ROOT_ANALYSIS.md` and directory `_ANALYSIS.md` files
- Root `_INDEX.md`
- Build report with source commit, analysis branch, file counts, skipped-file counts, and degradation notes

## Guardrails

- Keep source-branch reads to the minimum required for the active mode.
- Preserve the required `§N`, `§N.M`, and `§N.M.K` numbering.
- Put checklist/tree-quality commentary only in documented observational sections.
- If the repo shape exceeds the documented limits, follow the fallback rules from the references instead of inventing a new format.
