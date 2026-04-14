---
name: requirement-brainstormer
description: Use when the parent workflow has only a short change goal or rough direction and needs one explicit pass to mine adjacent requirements from the current functionality before PRD generation. Do not use when the user already provided a concrete PRD or equivalent implementation-ready requirement document.
---

# Requirement Brainstormer

## Overview

Inspect the current functionality and surface adjacent improvement opportunities that are close enough to matter for planning, but disciplined enough not to explode scope. When invoked from [genfu-change-workflow](../../SKILL.md), inherit repository defaults and repo-specific hints from [repo profile](../../references/repo-profile.md) through the parent runtime config, and inspect the repository according to `runtime_mode`.
If the parent runtime config already includes a complete repository identity from the default profile, do not ask the user to restate which repository to brainstorm against.

## Quick Start

1. Read [output contract](references/output-contract.md).
2. Confirm the parent workflow does not already have a concrete PRD.
3. Use the merged runtime config from the parent workflow.
4. If the user only asked for broad exploration, treat that as enough to start; do not ask them to choose a brainstorming framework first.
5. Inspect current features, outputs, user flows, and obvious friction points according to `runtime_mode`.
6. Produce a short candidate list with scope labels and a priority recommendation.

## Workflow

1. Start from the current user goal and the repository context from the parent runtime config.
2. Inspect current functionality rather than ideating from scratch.
3. Look for:
   - repeated manual steps
   - missing follow-up actions
   - broken transitions between existing features
   - user-visible friction or ambiguity
   - natural next capabilities implied by current outputs
4. Produce a small set of candidate requirements with brief rationale.
5. Label each candidate as:
   - `include now`
   - `defer`
   - `open question`
6. Add a concise recommended priority order.
7. Return the candidate set in a form the parent workflow can drop into its checkpoint and PRD discussion.

## Guardrails

- Do not run if the user already provided a concrete PRD or equivalent implementation-ready spec.
- Do not ask for repository identity when the parent runtime config already contains `repo_url`, `repo_owner`, and `repo_name`.
- Honor `runtime_mode` from the parent runtime config instead of inventing a different access path.
- Do not spend an extra turn asking the user to pick categories, dimensions, or a starting point when the request is already broad enough to support a bounded first-pass exploration.
- Do not invent roadmap-scale ideas unrelated to the current feature set.
- Do not silently expand scope; every idea must be explicitly labeled.
- Prefer 3-5 strong candidates over a long weak list.
- Treat parent `focus_topics` and `focus_notes` as the highest-priority hints for where to inspect.
