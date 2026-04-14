# Checklist Focus

Use this reference only when `focus_topics` includes `checklist-optimization`.

## What to Prioritize

- actionable checklist path quality
- semantic normalization behavior
- prefix-tree merge logic
- template or mandatory skeleton enforcement
- markdown and XMind rendering consequences

If the repo matches AutoChecklist, inspect these files first:

- `app/nodes/checklist_optimizer.py`
- `app/services/semantic_path_normalizer.py`
- `app/services/checklist_merger.py`
- `app/services/template_loader.py`
- `app/services/mandatory_skeleton_builder.py`

## Implementation Bias

Prefer changes that:

- preserve executable action steps in the shared tree
- prevent noun-only placeholder nodes from dominating the path
- keep template-enforced structure visible early enough in the flow
- maintain renderer compatibility
- make diff explanations easy for QA and reviewers to audit

## Reporting Bias

Call out checklist-specific findings in:

- the architecture overview
- the change plan
- the diff review report
- the analysis-sync report

Do not invent a parallel checklist-only output format.
