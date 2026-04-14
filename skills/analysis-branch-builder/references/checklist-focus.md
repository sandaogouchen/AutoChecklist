# Checklist Focus

Use this reference only when `focus_topics` contains `checklist-optimization` or the user explicitly asks about checklist/tree quality.

## What to Inspect

Prioritize code or analysis artifacts related to:

- checklist tree construction
- semantic normalization
- path merging or flattening
- template-enforced structure
- rendering into markdown, mind maps, or similar artifacts

If the target repo is AutoChecklist or has the same layout, inspect these files first:

- `app/nodes/checklist_optimizer.py`
- `app/services/semantic_path_normalizer.py`
- `app/services/checklist_merger.py`
- `app/services/template_loader.py`
- `app/services/mandatory_skeleton_builder.py`

## Questions to Answer

- Are path nodes actionable, or are they collapsing into noun-only labels?
- Does semantic normalization over-compress distinct actions into shallow anchors?
- Does template enforcement happen early enough to stabilize structure?
- Can the rendered tree be executed directly by QA without opening each testcase body?
- Are checklist observations captured without breaking the required analysis format?

## Where to Put Findings

- `_ANALYSIS.md`: `补充观察`
- `_INDEX.md`: `改进建议`

Keep these findings observational. Cite file paths plus line ranges or analysis-section references whenever possible.
