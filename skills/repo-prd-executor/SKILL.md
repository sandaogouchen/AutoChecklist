---
name: repo-prd-executor
description: Use when implementing a PRD against a repository with a required feature-branch and PR workflow, a reviewer-facing diff explanation, a post-implementation self-feedback review, and optional synchronization of the repository analysis branch after code changes.
---

# Repo PRD Executor

## Overview

Execute a PRD against a live repository while keeping four outputs aligned: the code change, the self-feedback review, the reviewer-facing change report, and the optional analysis-branch sync. Load only the references needed for the current execution phase.

## Quick Start

1. Read [input contract](references/input-contract.md).
2. Read [execution flow](references/execution-flow.md) before changing any files.
3. Read [diff review report](references/diff-review-report.md) before summarizing changes for reviewers.
4. Read [self-feedback loop](references/self-feedback-loop.md) before finalizing the implementation.
5. If `sync_analysis=true`, read [analysis sync rules](references/analysis-sync-rules.md) before writing the sync report.
6. If `focus_topics` contains `checklist-optimization`, also read [checklist focus](references/checklist-focus.md).

## Workflow

1. Load the PRD and understand the current repo first. Prefer analysis-branch artifacts when available, then fall back to source files.
2. Produce a concise architecture overview and a concrete change plan before editing.
3. Implement the planned code changes without bypassing existing conventions or breaking unrelated behavior.
4. Verify the change with the project-appropriate checks.
5. Run the self-feedback loop before finalizing:
   - hunt for likely bugs
   - compare actual behavior with PRD intent
   - evaluate whether the current effect matches expectations
   - note reasonable evolution directions
6. Create the feature-branch commit and PR when the environment supports it. In local fallback mode, stop with an explicit handoff if a remote PR cannot be created.
7. Build the reviewer-facing report from the actual diff, not from memory.
8. If requested and feasible, sync the analysis branch from the final source state.

## Runtime Notes

- Prefer GitHub MCP for branch, PR, merge, and diff APIs.
- In local mode, use git branches, commits, and `git diff`; do not claim PR creation or merge completion unless those actions really happened.
- If the PRD conflicts with current code or leaves a material ambiguity, stop and surface the conflict instead of guessing.

## Deliverables

- Implemented code change or explicit blocked-state report
- Self-feedback summary with must-fix issues, confirmed expectations, and evolution notes
- Reviewer-facing diff explanation
- Analysis-sync report when enabled
- Verification summary with any residual risks

## Guardrails

- Do not write code before reading current code or analysis artifacts.
- Do not skip the self-feedback loop after initial verification.
- Do not push directly to `main` or another protected branch.
- Base every reviewer explanation on the real diff.
- Base every analysis-sync update on the final source tree, not on guessed post-merge state.
