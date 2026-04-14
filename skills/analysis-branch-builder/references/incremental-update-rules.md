# Incremental Update Rules

Use this path only when `_INDEX.md` exists and `analyzed_commit` can be trusted.

## Diff-to-Analysis Mapping

| Source change | Analysis action |
| --- | --- |
| File modified | Regenerate the owning directory analysis file |
| File added | Regenerate the owning directory analysis file and add the new `§N` block |
| File deleted | Regenerate the owning directory analysis file and remove or renumber affected sections |
| New directory | Create a new `_ANALYSIS.md` if the directory has direct analyzable files |
| Directory removed | Delete the corresponding `_ANALYSIS.md` |

## Incremental Workflow

1. Read `_INDEX.md` from `analysis_branch` and extract `analyzed_commit`.
2. Compute the diff from `analyzed_commit..HEAD` on `source_branch`.
3. Group changed files by analysis-file ownership.
4. Regenerate only the affected analysis files.
5. Update `_INDEX.md`:
   - analysis-file index
   - dependency or integration sections if the changes require it
   - `last_updated`, `analyzed_commit`, and counts

## Submission Defaults

- Full rebuild branch: `analysis-rebuild-YYYYMMDD`
- Incremental branch: `analysis-incremental-YYYYMMDD`
- Full rebuild commit: `docs(analysis): full rebuild YYYY-MM-DD`
- Incremental commit: `docs(analysis): incremental update - N dirs affected`

## Escalate Back to Full Rebuild

Use a full rebuild when:

- the analysis branch is missing
- `_INDEX.md` is malformed
- top-level directories were renamed, added, or removed
- incremental updates have drifted too far to trust
- the user explicitly asks for a clean rebuild
