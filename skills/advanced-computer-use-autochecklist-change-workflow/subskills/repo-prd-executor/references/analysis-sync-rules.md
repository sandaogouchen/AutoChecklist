# Analysis Sync Rules

Use this reference only when `sync_analysis=true`.

## Source Change to Analysis Change

| Source change | Analysis action |
| --- | --- |
| File modified | Regenerate the owning directory analysis file and refresh the affected `§N` sections |
| File added | Add a new `§N` block in the owning directory analysis file |
| File deleted | Remove the matching `§N` block and renumber as needed |
| New directory | Create a new `_ANALYSIS.md` if the directory has direct analyzable files |
| Deleted directory | Delete the corresponding `_ANALYSIS.md` |

## Sync Workflow

1. Build the source-file change list from the final implemented state.
2. Map source changes to analysis-file ownership.
3. Update the affected `_ANALYSIS.md` files using full-depth analysis, not shallow diff summaries.
4. Update `_INDEX.md`:
   - file-index summaries
   - `last_updated`
   - `analyzed_commit`
   - dependency or integration sections if the change requires it

## Branch and PR Defaults

- Sync branch: `analysis-sync-<feature-branch>-YYYYMMDD`
- Commit: `docs(analysis): sync changes from <feature-branch>`
- PR title: `Analysis Sync: <feature-branch> (YYYY-MM-DD)`

## Special Cases

- If `analysis_branch` is missing: skip sync and warn.
- If `_INDEX.md` is missing or malformed: skip sync and recommend a full rebuild.
- If more than 10 directories are affected: complete the sync if possible and recommend a later full rebuild.
- If the change is formatting-only: still refresh analysis if line references or structure changed.

## Hard Rule

Sync analysis from the final source files, not from guessed post-merge behavior or a partial diff interpretation.
