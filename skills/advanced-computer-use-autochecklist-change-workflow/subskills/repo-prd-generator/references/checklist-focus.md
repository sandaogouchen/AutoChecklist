# Checklist Focus

Use this reference only when `focus_topics` includes `checklist-optimization`.

When nested under `genfu-change-workflow`, read `focus_topics` and `focus_notes` from the merged parent runtime config, which originates from `../../references/repo-profile.md`.

## Problem Framing

Bias the PRD toward these questions:

- Why is the current checklist tree hard to execute?
- Where do semantic merges over-abstract useful steps?
- How should template-enforced structure interact with path planning and rendering?
- How will QA consume the resulting checklist path tree?

## Technical Areas to Cover

- actionable path-tree goals
- semantic normalization rules
- merge and deduplication behavior
- project template and mandatory skeleton enforcement
- markdown or XMind rendering implications
- evaluation metrics for path quality and actionability

If `focus_notes` names specific modules or files, prioritize those first. Otherwise, derive the relevant file set from the target repository instead of assuming a fixed repo layout.

## Where to Reflect the Focus

- `背景与目标`
- `功能需求`
- `技术方案概要`
- `风险与依赖`
- `开放问题`

Do not invent a new PRD section just for this focus area.
