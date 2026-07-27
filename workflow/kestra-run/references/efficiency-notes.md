# Efficiency notes — why these shortcuts are safe

SKILL.md states each of these as a short directive. This file holds the full reasoning behind
each one — read it if the directive alone isn't enough context to apply it correctly, or before
deviating from it.

## Not every stage needs a fresh subagent

If a stage's entire job reduces to re-running the same mechanical check `exit_criteria` already
checks (empty `write_scope`, no judgment call, nothing beyond a command you're about to run
yourself in step 3 anyway), just run it directly instead of spawning a subagent to run it first.
Reserve subagent spawns for stages that need something a shell command can't produce on its own:
writing/changing code, or judgment-requiring analysis (security review, exploratory verification a
frozen test doesn't cover). This is about cutting *redundant* LLM round-trips, not about skipping
independent verification — step 3 still runs unconditionally either way, so this never reopens the
self-cert hole the design exists to close.

## The terminal `done` stage is a case of the above

Even though its `write_scope` isn't empty. Writing `completion-summary.md` needs synthesis (what
shipped, which commits, the verdicts), but the orchestrator already holds every fact that summary
needs: `state.json`, the full `git log`, and every stage's verdict artifact, all from actually
running the pipeline. A fresh subagent has none of that and would have to re-derive it from
scratch by re-reading the same files the orchestrator already read. Write the summary directly;
don't spawn an agent to rediscover context you already hold.

## Wall-clock note — don't re-pay dependency-install cost every stage

A fresh subagent spawned for `generate-tests`, `implement-*`, or `verify` has no memory of whether
a prior stage already ran `npm install`/`pip install`/etc. in this same repo, so left to its own
judgment it may re-run the install defensively "just in case" — a real wall-clock cost (real
network/disk time, not token cost) paid again for nothing when the lockfile hasn't changed. Tell
each such subagent, as part of its brief or a standing note: check whether the dependency
directory already exists and matches the current lockfile (e.g. `node_modules/` present and newer
than `package-lock.json`) before installing, and skip the install if so. This is purely about not
repeating unchanged setup work — it must still install for real the first time, and again any time
the lockfile actually changed.

## Combining fix attempts across failing siblings

If more than one stage in a batch failed and shares the same `on_fail.target` (the `verify`+
`review` sibling case is the common one), do not spawn two concurrent fix attempts on that target.
They'd both be trying to edit the same `write_scope` at once, which is exactly the collision
independent-stage parallelism is supposed to be impossible by construction; two simultaneous fixes
racing each other reopens that. Instead, collect every failing sibling's output (e.g. both
`review-verdict.md`'s findings *and* the failing e2e output) into one combined fix brief, run
exactly one fix attempt against `target`, then re-run *every* stage that failed (not just one) —
step 2 and step 3 again for each. Resume both failing siblings' subagents concurrently for the
re-check, same as the first pass — the fix is one shared thing to verify against, but each
sibling's own re-verification is still independent of the other, so there's no more reason to
serialize the re-check than the original pass. Only after both come back does the batch as a whole
count as passed. A sibling that already passed in this batch doesn't need re-running; only the
ones that failed.

## Run artifacts: build the harness once, and keep expensive evidence

Two things a run tends to produce over and over because no stage can see what another stage did:

- **A throwaway harness** — the thing that applies mutants and reports which ones the suite caught,
  or compares two paths, or sweeps an input space. Measured on a real run, four agents each wrote
  their own, and the expense was never the writing; it was each one re-discovering which config
  files a sandbox copy of the repo needs before the suite runs there at all.
- **Expensive evidence** — a sweep, a benchmark, a large enumeration. Same run: a 200,001-case
  sweep performed twice by two stages that couldn't see each other.

Both live in the run folder — `<run-folder>/harness/` and `<run-folder>/evidence/` — and both get
named in every subsequent spawn's context pack (path plus one line on what's there). Deliberately
*not* shipped inside this skill: a harness has to be written in some language, and the setup
knowledge it encodes is specific to this repo, so it belongs next to `state.json` rather than in a
skill that has to work in any stack.

The reuse rules that keep this from becoming a liability: an `evidence/` file is valid only for the
commit it was computed against, so a stage reusing one after the code moved must re-run it; and a
stage may not clear a finding on the strength of an artifact it neither verified nor reproduced.
Reuse is there to skip *recomputation*, never to skip *judgment*.

## Resume vs. respawn — a trade, not a default

The earlier guidance here was "resume over respawn, full stop." Measured, that's wrong as an
absolute. Resuming `generate-tests` for a fixing round took 138.7 s against 221.6 s for the original
fresh spawn — 37% less wall clock — but cost 170,964 tokens against 154,868, about 10% more, because
resuming resends the entire prior transcript on every turn. The same shape held for both other
resumed spawns in that run: they had by far the highest tokens-per-turn (up to 29,910, against
~12,000 for a fresh spawn).

So it buys wall clock with tokens, and which side wins depends on how big the transcript already is:

- **Transcript still small → resume.** The re-orientation you'd otherwise re-pay costs more than the
  transcript does, and a resumed reviewer naturally checks whether *its own* findings were addressed
  rather than re-deriving a whole review from zero.
- **Transcript large (roughly past 150k tokens) → respawn with the context pack.** Past that point
  every turn is dragging a transcript heavier than the pack that would replace it, and the pack
  supplies exactly what resuming was protecting: the current state, what changed, and the specific
  findings to address. A fresh agent with the pack is not the uninformed agent the old advice was
  written against.

Two cases are not judgment calls: **never** carry a transcript across a `reworking` transition —
that unlocks test-writing and changes what's even true about the stage, so start fresh — and if the
environment has no way to resume a specific prior agent, respawning is the fallback, not a mistake.
