---
name: kestra-run
description: >
  This skill should be used when the user asks to "run the workflow", "execute this pipeline",
  "run/resume kestra-run", "resume the stage machine from where it left off", "drive kestra-build's
  output to completion", "pick up this stage machine where the orchestrator left off", or points
  at an existing workflow.yaml + state.json pair (produced by kestra-build) and wants it actually
  executed, not just planned. Reads state, spawns a subagent per stage, then mechanically verifies
  each result via real Bash/git commands — never by reading a diff and judging it. Loops
  automatically but always stops at a fixing→reworking escalation, a blocked stage, a test-hash
  mismatch, an anchored requirement-surface mismatch, or (only if the workflow explicitly declares
  one) a human_approval gate; commits per
  stage so every run is resumable. This is
  NOT: generating a workflow.yaml from a spec (that's kestra-build), a fixed-phase agent pipeline
  with no workflow file (chain whatever specialized skills you have yourself for that), or a
  generic CI/CD deployment pipeline runner.
---

# kestra-run — Workflow Orchestrator

Executes a `workflow.yaml` + `state.json` pair that [`kestra-build`](../kestra-build/README.md) already
wrote. kestra-run is the "Hermes" half: it reads state, picks the next stage, gets the work done, and
verifies the result — using real commands, not its own judgment, for every check that matters.

**kestra-run does not generate workflows** (that's kestra-build) **and does not run a fixed phase list**
(there is no fixed-phase orchestrator — chain whatever specialized skills you have by hand). If
there's no `workflow.yaml` yet, say so and point at kestra-build instead of improvising one.

**Suggested model, if spawning this as a subagent with a model to choose:** Sonnet 5. Measured
same-effort against Opus 5 running the same live workflow end to end: the orchestration logic itself
(context-pack composition, mechanical verification, scoped stopping) was identical and correct on
both, and cost came out a wash — this layer showed no model-sensitivity, so the cheaper default is
the sane one. (What a spawned *stage* subagent decides is a separate question — see that stage's own
`model` field in `workflow.yaml`, per kestra-build's guidance.) A suggestion to offer the user, not a
default to pick silently — ask before spawning. Doesn't apply when running inline in an
already-active session.

---

## The one rule everything else follows

**Every enforcement decision must come from an actually-executed command, never from reading a
diff and deciding it looks fine.** This is the whole reason an AI orchestrator is safe to use here:
mechanical checks (`git diff` against globs, `sha256sum` against a stored hash, a test command's
real exit code) can't be talked out of a wrong answer. The moment you substitute "this looks like
it satisfies write_scope" for actually running the comparison, you've reopened the exact
false-positive hole `kestra-build`'s design closes off — except now it's the orchestrator
hallucinating the pass, which is worse than a stage's own code being wrong, because nothing
downstream catches it.

Same standard as any other agent pipeline: **paste the real command + exit code + output** for
every check before treating it as passed. If you can't run the check, the stage is not verified —
say so.

---

## Before you start

1. **Locate the pair.** `workflow.yaml` + `state.json` for a feature-id, usually at
   `workflows/runs/<feature-id>/` or wherever kestra-build wrote them. If you can't find both, stop
   and ask — don't generate a fresh one yourself.
2. **Confirm with the user once, before the first stage runs.** Say which stage(s) `state.json`'s
   `current_stage` array currently lists and what will happen (an agent gets spawned per stage to
   do that stage's work, then each result gets verified and possibly committed). This is the only
   up-front confirmation — once running, the loop advances on its own until a real stop condition
   is hit (see below). Don't ask again per stage; that defeats the point of having an orchestrator.
3. Read `references/enforcement.md` before writing any Bash for the checks below — it has the
   exact commands, not just the idea of them.
4. **Seed one task per stage** with TaskCreate, subject = the stage id, in the same order they
   appear in `workflow.yaml`. This is what makes progress visible without anyone reading the
   transcript — a `fixing` loop can run many spawns before it either passes or escalates, and
   without a standing checklist all of that looks like silence from outside. Set every task's
   initial status from `state.json`: stages already `passed` → `completed`, the stage(s) in
   `current_stage` → `in_progress`, everything else stays `pending` (TaskCreate's default). On a
   fresh run this is just "first stage(s) in_progress, rest pending"; on a resume it reconstructs
   the checklist from `state.json` as it already stands.

## The loop

`current_stage` is always an array — usually one id, but more than one when independent stages
(non-overlapping `write_scope`) are simultaneously ready. Run every stage currently listed in it
through the steps below; independent stages can be worked in parallel since their `write_scope`s
can't collide by construction. Re-derive `current_stage` from `state.json` every time you resume —
don't carry it in your head across a paused run. **The most common instance of this**: `verify` and
`review` both landing in `current_stage` together the moment their shared upstream `implement-*`
stage passes (per kestra-build's default template, both `depends_on` that stage directly, not each
other, since neither has anything to write) — spawn both stages' subagents in the same step instead
of waiting for one to finish before starting the other. See the on-fail handling below for what to
do when one or both of them fail.

1. **Test-hash check, if `state.json.test_hash` is not null.** Recompute the hash of the frozen
   test paths (the `write_scope` of whichever stage had `freeze_after: true`) and compare. **Any
   mismatch is an immediate hard stop** — report it plainly (something rewrote frozen tests) and do
   not proceed. This is not a `fixing`/`reworking` situation; it's a "someone/something violated
   the one invariant everything else depends on" situation. Run this once per loop iteration
   (once per batch), not once per stage in a multi-stage batch — the hash covers a fixed set of
   frozen paths regardless of which stages are running this iteration, so recomputing it per-sibling
   in a `verify`+`review` batch checks the identical thing twice for nothing.

   In the same once-per-batch slot, when `workflow.yaml` carries `spec_anchor`, run the anchored
   surface recipe in `references/enforcement.md`: require all three anchor fields, a reachable
   `raise_commit`, the recorded extractor version, and equality between the current recompute, the
   raise-side recompute, and recorded `surface_hash`. **Any mismatch is a hard stop, never
   `reworking`.** A workflow with no anchor legitimately skips this check.

2. **Do the stage's work, if the stage's `brief` describes any.** This runs *before* the
   `human_approval` check below, regardless of the stage's `exit_criteria.type` — a `human_approval`
   stage whose brief asks for real analysis (e.g. a manual-milestone stage a user explicitly asked
   for) still has to produce that analysis before anyone can approve anything. Reading
   `exit_criteria` first and stopping without doing the brief's work is the exact anti-pattern
   kestra-build's own design warns about: a human eyeballing a raw diff with zero automated pass
   behind it. Only skip this step for a stage whose brief has no real work to describe — a pure
   terminal gate that exists solely to collect sign-off on everything already done.
   To do the work: decide first whether a subagent is even warranted (see the efficiency note
   below) — if it is, spawn one (Agent tool) with a prompt built from the stage's `brief`, its
   `write_scope`, and **the context pack below**. If the stage sets `model`, pass it as the spawn's model
   override; otherwise inherit the orchestrator's own model — don't default a stage to a faster tier
   on your own initiative, the workflow file is the only place that decision is allowed to live (see
   kestra-build's `model` guidance for why it's scoped to `implement-*`). Same for `effort`: if the
   stage sets it, pass it as the spawn's effort override; otherwise inherit the orchestrator's own
   effort level — `effort` and `model` are independent fields, check and pass each on its own, one
   can be set without the other. **Exception for a target-based fix attempt** (a `write_scope: []`
   review/verify stage whose `on_fail.target` names an `implement-*` stage — see step 6): that spawn
   does implement-shaped work inside the target's `write_scope`, so pass the *target* stage's
   `model`/`effort`, not the failing reviewer's (which is usually unset) — otherwise a workflow that
   declares `implement-*` at `effort: low` silently loses that setting on every fix attempt routed
   through a reviewer. If `brief` names a skill as a suggestion, leave that in
   verbatim — the subagent decides whether to use it. Tell the subagent to report back tersely:
   command + exit code + one-line verdict per check it ran, not a narrative essay — you re-verify
   every claim yourself in step 3 regardless, so a long self-justifying writeup has no enforcement
   value and is pure token spend. Also nudge it to batch independent work in parallel tool calls
   within its own turn where there's no real dependency between the pieces (e.g. writing several
   independent test files, or reading several unrelated existing files for context) rather than
   doing them one at a time — this is the same "independent work doesn't need to be serialized"
   idea as the stage-level parallelism above, just applied one level down inside a single stage.
   - **The context pack — hand over what you already know, every spawn, no exceptions.** Its
     provision layer is: the stage's `write_scope` globs; the stage's
     `exit_criteria.run`, already executed by you, with its real exit code and output (or whether an
     `artifact_exists` target is currently present); the diff (`git diff --name-only` + `git diff
     -U0`) against the most recent stage commit that actually touched code (walk back past any
     no-diff commit) — for `implement-*`, also the frozen test suite's file list; the previous
     stage's verdict artifact path and verdict line; anything under `<run-folder>/evidence/` and
     `<run-folder>/harness/` (path + one line each); on a `fixing` retry, the specific findings being
     fixed, not just "it failed"; on a post-`reworking` re-run, always a fresh spawn with a fresh pack
     (never resume across that transition) — scope `review`/`verify` to the rework diff plus shared
     fixtures/ACs, but give `test-review` the full file-by-file treatment since its job is cross-file
     relations a diff-only pack would hide. Omit a field only when it genuinely has no value yet and
     say so explicitly. A pack is context, never permission — never widens `write_scope`.
     If the brief contains a validator-proven embedded `ticket:begin` block and this batch's anchored
     surface check passed, use the slim pack: embedded ticket brief + provision layer, plus the
     `source_spec` path and “surface verified against `<raise_commit>`; read on demand.” Otherwise
     paste the full spec verbatim under its path header; only an oversized spec may fall back to an
     explicitly labelled path-only handoff.
   - **Efficiency note — not every stage needs a fresh subagent.** Run the check directly instead
     of spawning one when a stage's whole job is a mechanical re-check `exit_criteria` already
     covers (empty `write_scope`, no judgment call). Reserve spawns for work a shell command can't
     do itself: writing/changing code, or judgment-requiring analysis. Step 3's independent
     verification always still runs regardless. Full reasoning in `references/efficiency-notes.md`.
   - **The terminal `done` stage is a case of the above**, even with a non-empty `write_scope` —
     write `completion-summary.md` yourself from `state.json`/`git log`/prior verdicts rather than
     spawning an agent to rediscover context you already hold. `references/efficiency-notes.md`.
   - **Wall-clock note — don't re-pay dependency-install cost every stage.** Tell each subagent
     running `generate-tests`/`implement-*`/`verify` to check whether the dependency directory
     already matches the current lockfile (e.g. `node_modules/` newer than `package-lock.json`)
     before installing, and skip if so — install for real only the first time or when the lockfile
     changed. `references/efficiency-notes.md`.

3. **Verify mechanically — in this order, every single time:**
   - `write_scope`: real `git diff --name-only` against the paths in `write_scope` — **except**
     when this attempt is a `fixing` retry of a stage whose own `write_scope: []` and whose
     `on_fail.target` names another stage; in that case check the diff against `target`'s
     `write_scope` instead (that's the whole point of `target` — a review/verify stage judges a
     diff, it doesn't own one). Before the existing revert, copy the already-computed violating
     paths to the fresh external snapshot directory from `references/enforcement.md`, report its
     path, then revert and count the attempt as failed. Keeping it outside the repo prevents the
     evidence from becoming the next attempt's violation. This applies only to a current stage
     attempt, never to the pre-existing dirty tree discovered while resuming.
   - `exit_criteria`: run the actual `run` command (real exit code) or check the actual `artifact`
     path (real file existence). No exceptions for "the subagent said it passed."

4. **If `exit_criteria.type` is `human_approval`:** now that step 2's work (if any) is done and
   step 3's mechanical checks have run, stop here and ask the user directly — show them the diff
   since the last commit, the mechanical check results, and whatever analysis/artifact the stage's
   subagent produced. This always stops, every time, no exceptions — that's what the stage type
   means. Do not auto-approve, and do not treat "the mechanical checks passed" as a substitute for
   the human's sign-off. This type is opt-in now (see kestra-build's "Default HITL posture") — most
   generated workflows won't have any stage of this type, so most runs never hit this step. When a
   stage's `exit_criteria.type` is `command` or `artifact_exists` instead (the new default for
   `spec-review`, `review`, and the terminal stage), it's just steps 3/5/6 like any other stage —
   don't invent a stop here that the workflow file didn't declare.

5. **On pass (non-`human_approval` stages only):** stage → `passed`. If this stage has
   `freeze_after: true`, compute and store the test-hash into `state.json` now. Commit everything
   (code + `state.json` — see `references/enforcement.md` for the exact sequence; no `git tag` per
   stage, the commit itself is the rollback point). **When multiple `write_scope: []` siblings pass
   in the same batch** (the `verify`+`review` case), make one commit naming every stage id that
   passed, instead of one commit per sibling — a `write_scope: []` stage's commit contains only the
   `state.json` update, so there's no per-stage code state a separate commit would need to preserve
   as a rollback point; combining them loses nothing. Make sure the commit message still names every
   stage id individually so a later `git log --grep "stage(<feature-id>): <stage-id> passed"` lookup
   resolves for each one (see `enforcement.md`'s rollback-grep convention). A sibling with a
   non-empty `write_scope` still gets its own commit as before. Remove this stage from `current_stage` and add
   every stage that now has all its dependencies satisfied, then continue the loop automatically.
   Mirror both moves with TaskUpdate: the stage that just passed → `completed`; every newly-ready
   stage entering `current_stage` → `in_progress`. Keep this in the same breath as the state.json
   update — a stale checklist is worse than none, since it actively tells the user the wrong thing.
   If a subagent was spawned for this stage, record its metrics in the same breath as the status
   update: append one line to `<run-folder>/run-log.md` **and** write the same facts into this
   stage's `state.json` entry under `metrics` (see `state-schema.md`) — stage id, its reported token
   count, wall-clock time, whether this attempt was a fresh spawn or a resumed one, and the final
   `attempt` count. Source all of it from data you already hold at commit time (the Agent tool
   result's usage numbers, and timestamps you captured before/after the spawn) — never spawn an
   extra subagent or add an `exit_criteria` check just to fetch it, and never let `metrics` or
   `seen_failures` be read by `exit_criteria`, `write_scope` diffing, or the test-hash computation;
   the rest is informational, with one exception — `spawn_type` on `generate-tests` and
   `implement-*` is a gated fact, so write `fresh` only when it was, and run
   `python3 "$RUN"/validate_workflow.py "$RUN" --separation-guard` before `done` reports the run. This is what makes the `done` stage's per-stage cost table (see
   kestra-build's `done`-stage guidance) real instead of aspirational — nothing else in this loop
   tracks it, so a skipped line means an absent row in that table, never a stage failure. The
   spawn-type/attempt-count columns only mean something across a pause/resume if this was actually
   persisted at the time — a `done` summary spanning a multi-session run that finds no `metrics` for
   an attempt should say "N/A — not tracked for this attempt," not reconstruct a guess.

6. **On fail:** increment `attempt` (on the failing stage's own entry in `state.json`, even when
   `on_fail.target` points elsewhere), hash the (normalized) diff and check it against `seen_diffs`.
   Also record a normalized hash of this attempt's `exit_criteria` failure output into a
   `seen_failures` array alongside `seen_diffs` (normalization recipe in `enforcement.md`, next to
   the semantic-diff hashing it mirrors — strip timestamps/durations/paths the same way). This is
   diagnostic only, no transition changes: `seen_diffs` alone can't catch the case where a too-narrow
   `write_scope` or a broken environment blocks every fix attempt identically — each attempt still
   produces a *different* diff (a different, equally futile edit), so `seen_diffs` never repeats even
   though nothing is converging.
   - **Progress metric, when declared.** The fresh pre-run of `exit_criteria.run` seeds
     `progress_history` with measured attempt `0`. Each failed attempt appends its measured value
     from the orchestrator's own captured output (`"unmeasured"` if extraction fails). Compare each
     entry with its immediate predecessor toward the declared target. Equal, worse, or unmeasured
     is no progress; two consecutive no-progress comparisons escalate through the existing
     `reworking` path before another attempt starts.
   - **If more than one stage in this step's batch failed and shares the same `on_fail.target`**
     (the `verify`+`review` sibling case above is the common one) — **do not spawn two concurrent
     fix attempts on that target**, they'd collide on the same `write_scope`. Combine every failing
     sibling's output into one fix brief, run exactly one fix attempt against `target`, then re-run
     *every* stage that failed (step 2 and step 3 again for each). **Resume both failing siblings'
     subagents concurrently for the re-check**, same as the first pass. Only after both come back
     does the batch as a whole count as passed. A sibling that already passed doesn't need
     re-running. Full reasoning in `references/efficiency-notes.md`.
   - Still under `max_attempts`, and either this is a genuinely new diff, **or** it's a repeat but
     `attempt < escalate_at` (the same diff came back, but not yet often enough to give up on it) →
     stay in `fixing`, record the diff hash, loop back to step 2 with the failure output fed into
     the next attempt's brief. `escalate_at` exists to give a repeated diff a grace window — but note
     that `kestra-build` generates `escalate_at: 2` on every stage it emits, and a diff can only
     repeat starting at attempt 2 (attempt 1 has nothing to compare against yet) — so as generated
     today, a repeat escalates to `reworking` immediately, with no grace retries in between. The
     grace window this paragraph describes only actually exists when a workflow sets `escalate_at` to
     3 or higher; don't assume a generated workflow has one just because this field exists. When
     `on_fail.target` is set (a review/verify stage with `write_scope: []`), the next attempt's
     brief goes to a fix on `target`'s write_scope — hand the subagent the failing stage's own
     output (e.g. `review-verdict.md`'s `CHANGES_REQUESTED` findings) as the thing to address, let
     it edit within `target`'s `write_scope` **at the target stage's own `model`/`effort`** (see
     step 2's exception above — not the failing reviewer's), then re-run the failing stage's own work
     (step 2) and `exit_criteria` (step 3) again — the loop re-checks the *same* stage's
     exit_criteria, it doesn't just trust the fix.
     - **Scope-cap the recheck itself**, for any `on_fail.target`-based retry re-run of
       `test-review`/`review`/a security stage (never `spec-review`'s own self-edit loop, which has
       no `target` and must always re-run its full checklist). Ask the retry pass for exactly two
       things: (a) confirm each prior finding is addressed, (b) check the changed lines — diffed
       against the commit the *last full-scope pass* reviewed, not just this attempt's delta —
       including their indirect effects through shared imports/helpers/fixtures, not just the literal
       changed lines. Unchanged-to-unchanged relations already cleared on an earlier full pass stand
       (step 3's `write_scope` revert already guarantees nothing else changed) — but this scoping
       never applies across a `reworking` transition, which is always a full fresh review. Where a
       blocking finding admits a runnable check, run it yourself while composing the retry pack
       rather than asking the reviewer to re-derive it.
     TaskUpdate the stage's task's `activeForm` to
     something like
     "implement-csv-export — attempt 2/5, retrying after test failure" so a retry loop reads as
     visible progress from outside instead of silence; status stays `in_progress` throughout.
     **Resume the previous attempt's subagent while its transcript is still small; respawn with a
     fresh context pack once it isn't.** Resuming trades tokens for wall clock — measured, ~37%
     faster but ~10% more expensive, because the whole prior transcript is resent every turn — so it
     wins early, when re-orientation would cost more than the transcript does, and loses once the
     transcript is past roughly 150k tokens and the pack can supply the same orientation for a
     fraction of it. This applies to the stage's own `fixing` retries and to `target`-based
     re-reviews; it does **not** apply across a `reworking` transition, which always starts fresh.
     If resuming isn't possible, spawning fresh is the fallback, not a mistake.
     `references/efficiency-notes.md`. Full reasoning in `references/efficiency-notes.md`.
   - `attempts >= max_attempts`, OR the same diff came back **and** `attempt >= escalate_at` (no
     progress, and the grace window for that repeat is spent) → **stop.** This is
     `reworking` — the one transition the design explicitly reserves for a human, and now the *only*
     stop condition that's always present in every generated workflow regardless of what
     `exit_criteria` types it uses. Report clearly: which stage, how many attempts, what kept
     failing, and that the frozen spec/tests are the suspected problem, not the code. When the
     failing check traces through an embedded derived Source line to a spec line marked `⚠`
     inferred, name that inferred line as the prime suspect and do not force the implementation to
     satisfy it. If
     `seen_failures` shows the same normalized failure signature across attempts that produced
     different diffs, add that as a raw signal, not a conclusion — e.g. "N of these M attempts
     produced different diffs but the same failure signature, worth checking whether `write_scope`
     or the environment is structurally blocking a fix" — **never** phrase it as "suspect
     write_scope/environment, not the frozen spec/tests"; the default explanation (the frozen
     spec/tests are wrong) stays live, this is an additional lead, not a replacement for it.
     TaskUpdate the
     task's `activeForm` to name the stop plainly, e.g. "reworking — attempt 5/5 exhausted, needs
     human"; leave status `in_progress` (not `completed` — nothing here finished), so the checklist
     itself flags which item is the one actually blocking the run.

7. **Stop conditions, restated plainly:** a `reworking` escalation (including two consecutive
   no-progress comparisons), a `blocked` stage, a test-hash mismatch, an anchored surface mismatch
   (hard stop, never `reworking`), or — only if this particular
   workflow declares one — a `human_approval` gate. Anything else, keep looping without asking. Any
   of these should leave the stopped stage's task `in_progress` with an `activeForm` explaining why
   — same reasoning as the `reworking` case above, so TaskList always shows where and why a run is
   stuck, not just that it stopped somewhere.

## Resuming

There's no separate "resume mode." `state.json` plus the per-stage commits from `commit-per-stage`
already capture everything needed — read `current_stage` fresh, re-run the test-hash check, and
continue.
If the working tree doesn't match `HEAD` (uncommitted changes sitting around from an interrupted
run), say so before touching anything — don't silently discard someone's in-progress work.

## Hard rules — non-negotiable

- Never treat a subagent's own claim of success as verification. Always independently re-run
  `exit_criteria` yourself after it returns.
- Never skip the test-hash check to save a step, even when nothing seems to have changed.
- Never auto-approve a `human_approval` stage on the rare workflow that has one, and never let
  `fixing` retry past `max_attempts` "just once more" — that's exactly the drift `escalate_at`
  exists to catch. Never invent a `reworking` bounce as a way to *avoid* stopping for the human,
  either — it's the one stop the design always keeps, not a way to route around one.
- Never let a `write_scope` violation through because the diff "looks reasonable" — revert it,
  count it as a failure, move on through the normal `fixing` path.

Full command sequences (write_scope diff check, test-hash compute/compare, commit-per-stage,
semantic-diff hashing for `seen_diffs`) are in `references/enforcement.md` — read it before writing
any of these checks yourself; don't improvise the commands from memory. The full "why" behind every
efficiency shortcut referenced above (skip-the-subagent, install caching, sibling-batch fixing,
resume-over-respawn) is in `references/efficiency-notes.md` — read it before deviating from one of
those directives, not just before following it blind.
