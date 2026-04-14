# Analysis Consumption

Prefer analysis artifacts over direct source reads whenever the analysis branch is healthy.

## Primary Path

1. Read `_INDEX.md` from `analysis_branch`.
2. Check `last_updated`:
   - if within 30 days, use normally
   - if older than 30 days, continue but add a stale-analysis warning at the end of the PRD
3. Use the requirement text to choose only the relevant `_ANALYSIS.md` files.
4. Read those analysis files and cite them with `path/_ANALYSIS.md#§N.M`.

## Relevance Heuristics

- Entry or startup changes: root analysis plus the app entry directory
- API or endpoint changes: API, routes, controllers
- Data model changes: models, schemas, entities
- Business logic: services, handlers, use cases
- Deployment or ops: root analysis, CI/CD, deploy directories

## Checklist Focus Heuristics

When `focus_topics` includes `checklist-optimization`, prioritize analysis or source artifacts covering:

- checklist optimizer nodes
- semantic path normalization
- checklist merge behavior
- project template loading or mandatory structure
- markdown or mind-map rendering

## Hard Rule

Do not read every `_ANALYSIS.md` file by default. Use `_INDEX.md` to decide what is relevant.
