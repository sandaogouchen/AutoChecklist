---
name: repo-prd-generator
description: Use when generating a repository-aware PRD from an existing analysis branch, or from a lightweight repository scan when no analysis branch is available, especially for feature scoping, technical planning, or stakeholder-ready requirements drafts.
---

# Repo PRD Generator

## Overview

Generate a full PRD from analysis artifacts instead of rereading the whole codebase. Keep this file concise and load the references for the specific branch of the workflow you are executing.

## Quick Start

1. Read [input contract](references/input-contract.md).
2. Read [analysis consumption](references/analysis-consumption.md) before touching the repo.
3. If the analysis branch is missing or malformed, read [degraded mode](references/degraded-mode.md) and switch to the lightweight scan path.
4. Read [prd structure](references/prd-structure.md) before drafting the document.
5. If `focus_topics` contains `checklist-optimization`, also read [checklist focus](references/checklist-focus.md).

## Workflow

1. Normalize inputs and inspect the target repo plus `analysis_branch`.
2. Prefer `_INDEX.md` plus only the relevant `_ANALYSIS.md` files. Do not bulk-read every analysis file.
3. If the analysis branch is healthy, do not read source files except when the user explicitly asks for that.
4. If the analysis branch is missing or unusable, switch to degraded mode and clearly mark the resulting PRD limits.
5. Draft the PRD using the required structure, citations, and open-question handling rules.
6. Run the documented self-check before returning the deliverable.

## Runtime Notes

- `runtime_mode=auto` means: try GitHub MCP repo reads first, then downgrade to local git and file-system inspection.
- In degraded mode, never fabricate analysis-index citations.
- If `output_format=feishu_doc` but the environment cannot create one, produce markdown and state the limitation explicitly.

## Deliverables

- A complete PRD in Chinese by default
- Clear indication of whether the PRD used analysis-branch mode or degraded mode
- Appendix listing every `_ANALYSIS.md` file read during generation
- Warnings for stale analysis, missing information, or unresolved questions

## Guardrails

- Do not skip the repo-understanding step and jump straight to writing.
- Do not omit non-functional requirements, risks, or open questions.
- Treat 3000 Chinese characters as the floor unless the user explicitly asks for a shorter draft.
- Put unresolved ambiguity in the open-questions section instead of guessing.
