---
name: genfu-change-workflow
description: Use when the user wants to change a repository and either starts with a short goal that needs feasibility discussion, requirement brainstorming, PRD generation, and implementation, or already provides a PRD and wants to skip straight to code understanding and implementation. This skill keeps repository Git configuration editable inside the skill through a repo profile and supports choosing either GitHub MCP or local repository reads at setup time.
---

# genFu Change Workflow

## Overview

Use this as a repo-change workflow entrypoint with an editable in-skill Git config. The current defaults live in [repo profile](references/repo-profile.md), and the repository access mode is chosen there: `github_mcp` or `local_git`.

## Runtime Config Assembly

1. Read [repo profile](references/repo-profile.md).
2. Build one runtime config object for downstream skills:
   - start from the `default_profile` block in the repo profile
   - if the user explicitly provides repo URL, owner, name, branch, focus, or access mode, override the default profile with those values
   - if `repo_url` is present but `repo_owner` or `repo_name` is missing, parse them from the GitHub URL
   - if `default_profile` already contains `repo_url`, `repo_owner`, and `repo_name`, treat the repository context as resolved even when the user did not mention a repo explicitly
3. Treat that merged runtime config as the source of truth when calling:
   - [local requirement-brainstormer](subskills/requirement-brainstormer/SKILL.md)
   - [local repo-prd-generator](subskills/repo-prd-generator/SKILL.md)
   - [local repo-prd-executor](subskills/repo-prd-executor/SKILL.md)

Do not ask for repo metadata when the merged config is already complete.
Honor `runtime_mode` from the merged config:
- `github_mcp`: inspect the repository through GitHub MCP
- `local_git`: inspect the local repository directly

## Access Mode

Choose the repository access mode from `references/repo-profile.md`:

- `github_mcp`: use GitHub MCP for repository, branch, diff, and PR access
- `local_git`: use the local checked-out repository for inspection and implementation

Treat this as an installation/setup choice by default. Only override it from the user message when they explicitly ask to switch access mode.

## Workflow

Choose one of two entry paths after assembling runtime config.

### Path A: Goal-First

Use this path when the user provides:

- a short goal
- a rough idea
- a problem statement
- a desired improvement without an implementation-ready PRD

Flow:

1. Intake: normalize the request into current problem, desired outcome, likely affected feature/workflow, and obvious constraints.
2. Feasibility and plan discussion: discuss architecture fit, likely affected modules or flows, tradeoffs, and a high-level execution plan.
3. Requirement brainstorming: call [local requirement-brainstormer](subskills/requirement-brainstormer/SKILL.md).
4. User checkpoint: present feasibility verdict, likely affected modules/flows, execution plan, brainstormed candidates, scope split, risks, and assumptions.
5. PRD generation: call [local repo-prd-generator](subskills/repo-prd-generator/SKILL.md).
6. PRD confirmation.
7. Execution: call [local repo-prd-executor](subskills/repo-prd-executor/SKILL.md).

If the short goal is simply to explore improvements or new features, run one bounded brainstorm pass immediately and notify the user with findings instead of asking them to pick a brainstorming framework first.

### Path B: PRD-First

Use this path when the user already provides:

- a concrete PRD
- a detailed requirement document
- implementation-ready scope and acceptance criteria

Flow:

1. Intake and validate that the provided PRD is materially actionable.
2. Skip requirement brainstorming and PRD generation.
3. Transition directly into code understanding and implementation through [local repo-prd-executor](subskills/repo-prd-executor/SKILL.md).

## What the User Needs to Provide

The user only needs to provide:

- a short goal or desired improvement
- or an existing PRD / implementation-ready requirement document
- optional constraints, examples, or deadlines
- optional repo overrides when they want to target a different repository or branch
- optional access mode override when they want to switch between `github_mcp` and `local_git`

Everything else should be inferred from the merged runtime config and the chained workflow.
If the user says nothing about the repository, use the default repo from `references/repo-profile.md` automatically.

## Guardrails

- Keep repo defaults and future retargeting knobs in `references/repo-profile.md`.
- Apply user repo overrides on top of the default profile instead of editing workflow text.
- Apply access mode overrides on top of `default_profile.runtime_mode` instead of changing subskill behavior ad hoc.
- If `default_profile` is complete, do not ask the user to confirm or restate the repository before starting work.
- If the user already supplied a concrete PRD, do not force the brainstorming stage or PRD generation stage.
- In the short-goal path, do not skip the feasibility and planning discussion stage.
- In the short-goal path, do not skip the brainstorming stage that mines new requirements from the current functionality.
- When the user asks for broad exploration, do not burn an extra turn asking them to choose categories, dimensions, or a starting angle unless that choice is truly blocking.
- During brainstorming, do not silently bloat scope. Label each idea as "include now", "defer", or "open question".
- In the short-goal path, do not skip the user hook checkpoint after the execution plan and brainstorming pass are formed.
- If the workflow generated the PRD itself, do not auto-start execution before the PRD is explicitly confirmed.
- After confirmation, do not ask again whether to start implementation; transition directly to the execution skill.
- Do not skip the post-implementation self-feedback layer.
