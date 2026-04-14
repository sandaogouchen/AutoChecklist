---
name: autochecklist-change-workflow
description: Use when working on the AutoChecklist repository and the user starts with a short improvement goal, needs feasibility discussion and planning first, wants an explicit user checkpoint after the execution plan, and then wants PRD generation plus implementation to run in one chained workflow with checklist-optimization focus.
---

# AutoChecklist Change Workflow

## Overview

Use this as the AutoChecklist-specific entrypoint. It hardcodes the repository context, defaults to checklist-optimization, inserts a user hook after the execution plan, and chains the PRD stage into the execution stage once the PRD is approved.

## Fixed Context

Always assume the repo defaults from [repo defaults](references/repo-defaults.md). Do not ask for repo URL, owner, branch, or focus unless the user explicitly wants to target a different repository or branch.

## Workflow

1. Read [session flow](references/session-flow.md).
2. Start from the user's short goal only. Expand it into:
   - problem statement
   - feasibility assessment
   - candidate approach
   - concrete execution plan
3. Discuss tradeoffs and open questions in conversation before writing the PRD.
4. After the execution plan is clear, send a structured user hook checkpoint and absorb the user's feedback before generating the PRD.
5. When the direction is stable, use [repo-prd-generator](../repo-prd-generator/SKILL.md) with the fixed repo defaults and the refined requirement.
6. Keep iterating on the PRD until the user confirms it.
7. Once the PRD is confirmed, immediately use [repo-prd-executor](../repo-prd-executor/SKILL.md) with the same fixed defaults and the approved PRD. Do not wait for a second user request. The execution skill must finish with its self-feedback layer before closing.

## What the User Needs to Provide

The user only needs to provide:

- a short goal or desired improvement
- optional constraints, examples, or deadlines

Everything else should be inferred from the fixed repo context and the chained workflow.

## Guardrails

- Stay inside the AutoChecklist repo defaults unless the user explicitly overrides them.
- Default to `checklist-optimization` focus.
- Do not skip the feasibility and planning discussion stage.
- Do not skip the user hook checkpoint after the execution plan is formed.
- Do not auto-start execution before the PRD is explicitly confirmed.
- After confirmation, do not ask again whether to start implementation; transition directly to the execution skill.
- Do not skip the post-implementation self-feedback layer.
