# Output Contract

Return a compact brainstorm result that the parent workflow can paste into the planning checkpoint.
When the user asked for general exploration, return findings directly instead of asking them to choose a brainstorming framework first.

## Required Sections

- `current functionality inspected`
- `candidate requirements`
- `scope split`
- `priority recommendation`
- `main assumptions`

## Candidate Requirement Format

Each candidate should include:

- a short title
- one-sentence rationale grounded in the current functionality
- one scope label:
  - `include now`
  - `defer`
  - `open question`

## Guardrails

- Keep the result concise and reviewable.
- Ground every candidate in observed or inferred current behavior.
- If the parent workflow already has a concrete PRD, skip this skill instead of producing output.
- Prefer delivering one bounded first-pass result over asking the user for another exploratory setup choice.
