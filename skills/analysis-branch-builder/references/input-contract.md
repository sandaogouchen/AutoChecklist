# Input Contract

Use these fields when invoking the skill. Normalize missing optional fields to the defaults below unless the repo target itself is ambiguous.

## Shared Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `repo_url` | yes | - | Canonical remote URL. |
| `repo_owner` | yes | - | Use for GitHub MCP lookups. |
| `repo_name` | yes | - | Use for GitHub MCP lookups. |
| `source_branch` | yes | - | Branch whose source tree is analyzed. |
| `analysis_branch` | no | `analysis` | Branch that stores analysis docs. |
| `runtime_mode` | no | `auto` | `auto`, `github_mcp`, or `local_git`. |
| `focus_topics` | no | `[]` | Include `checklist-optimization` for checklist/tree heuristics. |
| `focus_notes` | no | `""` | Extra repo-specific instructions. |
| `output_language` | no | `zh-CN` | Use Chinese unless the user asks otherwise. |

## Skill-Specific Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `build_mode` | no | `full` | `full`, `incremental`, or `auto`. |
| `auto_merge` | no | `true` | Meaningful only when a PR flow is available. |

## Output Contract

- Build or refresh the analysis tree under `analysis_branch`.
- Return a short execution report with:
  - analyzed source commit
  - generated analysis-file count
  - skipped-file count
  - active runtime mode
  - warnings or degraded behavior
- In local-only fallback mode, list any remote actions that remain undone.
