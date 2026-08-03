Drive an existing `workflow.yaml` + `state.json` (produced by kestra-build) to completion or the next real stop condition.

Usage: /kestra-run [feature-id]
Example: /kestra-run csv-export

Load `@kestra-run/SKILL.md` and follow it. Then:

1. Locate `workflow.yaml` + `state.json` for the given feature-id (usually
   `workflows/runs/<feature-id>/`). If either is missing, say so and point at `kestra-build` —
   don't generate one yourself.

2. Read `state.json`, report the current stage and what's about to happen (spawn an agent
   for that stage's work, then verify it), and confirm once before starting.

3. Run the loop from `SKILL.md`. On an anchored batch, require the frozen validator and the
   raise/current requirement-surface comparison before work; only its proven ticket block gets the
   slim brief + provision pack with an on-demand spec path. Then spawn → mechanically verify
   (`write_scope` diff, snapshot violations before revert, real `exit_criteria`, test hash) →
   commit-per-stage → advance. Use `references/enforcement.md`; never judge a diff by reading it.

4. Stop automatically (and only) at: `fixing → reworking` (including two consecutive failed
   progress measurements with no movement), `blocked`, a test-hash mismatch, an anchored-surface
   mismatch (hard stop, never reworking), or an explicitly declared `human_approval` gate. Report
   which one and why; otherwise keep looping without asking again.

5. If resuming a previous run, just re-read `current_stage` from `state.json` and continue
   — there's no separate resume mode. If the working tree has uncommitted changes from an
   interrupted run, say so before touching anything.
