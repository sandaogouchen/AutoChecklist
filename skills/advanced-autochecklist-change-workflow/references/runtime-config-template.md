# Runtime Config Rules

Use this file as the runtime config rule sheet for downstream skills. Treat actual values as coming from `repo-profile.md` plus explicit user overrides.

## Required Runtime Fields

The merged runtime config should expose fields shaped like:

```yaml
repo_url: "<from default_profile or user override>"
repo_owner: "<from default_profile, parsed from repo_url, or user override>"
repo_name: "<from default_profile, parsed from repo_url, or user override>"
source_branch: "<from default_profile or user override>"
analysis_branch: "<from default_profile or user override>"
runtime_mode: "<github_mcp or local_git>"
focus_topics: "<from default_profile or user override>"
focus_notes: "<from default_profile or user override>"
output_language: "<from default_profile or user override>"
```

## Merge Rules

1. Start from `default_profile` in `repo-profile.md`.
2. Apply any explicit user overrides.
3. If `repo_url` is present but `repo_owner` or `repo_name` is missing, parse them from the GitHub URL.
4. Keep `analysis_branch: "analysis"` unless the user explicitly changes it.
5. Keep `runtime_mode` from `default_profile` unless the user explicitly changes it.
6. Keep `focus_topics` and `focus_notes` from the profile unless the user explicitly overrides them.
7. If the merged config still lacks `repo_url`, `repo_owner`, or `repo_name`, stop and ask for the missing Git repo information.
8. Honor the merged `runtime_mode`:
   - `github_mcp`: use GitHub MCP
   - `local_git`: use the local repository

## Default Repo Rule

- If `default_profile` already provides `repo_url`, `repo_owner`, and `repo_name`, do not ask the user which repository to use.
- Only ask for repository information when those required fields are still missing after applying defaults plus explicit user overrides.
- If the user says "默认仓库" or gives no repo override at all, use `default_profile` automatically.

## Editing Guidance

- When retargeting this skill later, edit the `default_profile` block in `repo-profile.md`.
- Do not rewrite the workflow when only repository or branch defaults change.
- Keep this file generic so the same merge logic still works after the profile changes.
- Keep this file free of fake empty defaults that could be mistaken for missing repo configuration.

## Downstream Usage

Pass the merged runtime config unchanged into:

- the local `subskills/requirement-brainstormer`
- the local `subskills/repo-prd-generator`
- the local `subskills/repo-prd-executor`
