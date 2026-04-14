# Checklist Focus

Use this reference only when `focus_topics` includes `checklist-optimization`.

When nested under `genfu-change-workflow`, read `focus_topics` and `focus_notes` from the merged parent runtime config, which originates from `../../references/repo-profile.md`.

## What to Prioritize

- actionable checklist path quality
- semantic normalization behavior
- prefix-tree merge logic
- template or mandatory skeleton enforcement
- markdown and XMind rendering consequences

If `focus_notes` names specific modules or files, inspect those first. Otherwise, derive the relevant file set from the target repository instead of assuming a fixed repo layout.

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
