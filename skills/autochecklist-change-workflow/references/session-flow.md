# Session Flow

This skill is a conversation-first orchestrator. The user can start with a short goal only.

## Stage 1: Intake

Take the user's short request and normalize it into:

- current problem
- desired outcome
- likely affected checklist or workflow area
- obvious constraints

If the goal is vague, keep asking focused follow-up questions in conversation, but do not ask for repo metadata covered by the fixed defaults.

## Stage 2: Feasibility and Plan Discussion

Before writing the PRD, discuss:

- whether the change is feasible within the current architecture
- likely affected modules
- tradeoffs and risks
- a concrete execution plan at a high level

For AutoChecklist, bias the discussion toward:

- `app/nodes/checklist_optimizer.py`
- `app/services/semantic_path_normalizer.py`
- `app/services/checklist_merger.py`
- `app/services/template_loader.py`
- `app/services/mandatory_skeleton_builder.py`

## Stage 2.5: Plan Hook to User

Once the execution plan is concrete enough to review, stop and send a structured checkpoint to the user before writing the PRD.

That checkpoint should contain:

- feasibility verdict
- likely affected modules
- proposed execution plan
- main risks and tradeoffs
- open questions or assumptions

Treat this as a real review hook, not a decorative summary. Absorb the user's feedback before moving on.

## Stage 3: PRD Generation

Once the direction is stable, call the repo PRD generator with:

- the fixed repo defaults from `repo-defaults.md`
- the refined requirement text from the discussion
- any optional user constraints added as `extra_notes`

Stay in PRD refinement mode until the user explicitly confirms the PRD.

## Stage 4: Automatic Transition to Execution

Treat any explicit PRD confirmation as the handoff trigger, for example:

- "按这个 PRD 做"
- "可以，开始实现"
- "PRD 没问题，继续"

After such confirmation:

1. immediately call the repo PRD executor
2. pass the fixed repo defaults
3. pass the approved PRD as `prd_markdown` or `prd_file_path`
4. keep `create_pr: true`
5. keep `sync_analysis: true`

Do not ask another "是否开始实现" question after PRD approval.

## Stage 5: Execution Self-Feedback Layer

After the execution skill finishes its first-pass implementation and verification, require one more reflection pass before closing.

That pass should:

- actively hunt for likely bugs or regressions
- compare the current implementation effect with the PRD intent
- assess whether the user-visible result matches expectations
- think about what the next evolution of the feature could be

If the self-feedback layer finds must-fix issues, route them back into execution before the session is considered complete.

## Fallbacks

- If `analysis` is missing or stale, the PRD generator and executor already know how to degrade. Do not block on that alone.
- If the PRD contains material ambiguity that would change implementation shape, stop before execution and resolve that ambiguity first.
