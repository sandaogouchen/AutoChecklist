# Input Contract

Use these fields when invoking the skill.

If this skill is called by `genfu-change-workflow`, the parent workflow should populate these shared fields from `../../references/repo-profile.md` plus any explicit user overrides. Treat that merged runtime config as the source of truth.

## Shared Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `repo_url` | yes | - | Canonical remote URL. |
| `repo_owner` | yes | - | Use for repository lookups. |
| `repo_name` | yes | - | Use for repository lookups. |
| `source_branch` | yes | - | Source branch for the implementation. |
| `analysis_branch` | no | `analysis` | Analysis branch to consume or sync. |
| `runtime_mode` | no | value from parent/profile | `github_mcp` or `local_git`. |
| `focus_topics` | no | `[]` | Include `checklist-optimization` when needed. |
| `focus_notes` | no | `""` | Repo-specific hints or constraints. |
| `output_language` | no | `zh-CN` | Default explanation language. |

## Parent Workflow Binding

When nested under `genfu-change-workflow`:

- inherit repository defaults from `../../references/repo-profile.md`
- inherit merge behavior from `../../references/runtime-config-template.md`
- do not replace parent-provided `repo_url`, `repo_owner`, `repo_name`, `source_branch`, `analysis_branch`, `focus_topics`, or `focus_notes` with local guesses

## Skill-Specific Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `prd_markdown` | conditional | - | Inline PRD content. Use this or `prd_file_path`. |
| `prd_file_path` | conditional | - | Path to the PRD file. Use this or `prd_markdown`. |
| `create_pr` | no | `true` | If false, stop after local branch or commit preparation. |
| `sync_analysis` | no | `true` | Attempt analysis sync after code changes. |

## Output Contract

- Return the implemented change or an explicit blocked-state report.
- Return a reviewer-facing diff explanation.
- Return an analysis-sync report or a warning that sync was skipped or impossible.
