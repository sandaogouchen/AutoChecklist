# Checklist Focus

Use this reference only when `focus_topics` includes `checklist-optimization`.

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

If the target repo matches AutoChecklist, prioritize:

- `app/nodes/checklist_optimizer.py`
- `app/services/semantic_path_normalizer.py`
- `app/services/checklist_merger.py`
- `app/services/template_loader.py`
- `app/services/mandatory_skeleton_builder.py`

## Where to Reflect the Focus

- `背景与目标`
- `功能需求`
- `技术方案概要`
- `风险与依赖`
- `开放问题`

Do not invent a new PRD section just for this focus area.
