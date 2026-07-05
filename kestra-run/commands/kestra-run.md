Drive an existing `workflow.yaml` + `state.json` (produced by kestra-build) to completion or the next real stop condition.

Usage: /kestra-run [feature-id]
Example: /kestra-run csv-export

Load `@kestra-run/SKILL.md` and follow it. Then:

1. Locate `workflow.yaml` + `state.json` for the given feature-id (usually
   `workflows/runs/<feature-id>/`). If either is missing, say so and point at `kestra-build` —
   don't generate one yourself.

2. Read `state.json`, report the current stage and what's about to happen (spawn an agent
   for that stage's work, then verify it), and confirm once before starting.

3. Run the loop from `SKILL.md`: spawn → mechanically verify (`write_scope` diff,
   `exit_criteria` exit code, test-hash where relevant) → commit-per-stage → advance.
   Use the exact command sequences in `references/enforcement.md` for every check — never
   judge a diff by reading it.

4. Stop automatically (and only) at: a `fixing → reworking` escalation (the one stop every
   workflow has, guaranteed), a `blocked` stage, a test-hash mismatch, or — only if this
   particular workflow explicitly declares one — a `human_approval` gate. Report clearly which
   one and why. Otherwise keep looping without asking again.

5. If resuming a previous run, just re-read `current_stage` from `state.json` and continue
   — there's no separate resume mode. If the working tree has uncommitted changes from an
   interrupted run, say so before touching anything.
