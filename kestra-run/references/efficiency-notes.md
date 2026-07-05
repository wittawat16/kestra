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

## Resume the previous attempt's subagent instead of spawning fresh

A brand-new subagent has to re-read the spec, re-orient on the codebase, and rebuild whatever
understanding the previous attempt already had — pure re-paid cost on every single retry, which is
exactly where cost balloons on a stage with `max_attempts: 5`. Resuming means the follow-up only
needs to carry the failure output and the retry instruction; everything the agent already loaded
stays loaded. This applies to the same stage's own `fixing` retries (and to a `target`-based
re-review — a resumed reviewer already knows what it found the first time, so it naturally checks
specifically whether *those* findings are now resolved instead of re-deriving a whole fresh review
of the entire diff from zero). It does **not** apply across a `reworking` transition — that unlocks
test-writing and changes what's even true about the stage, so start that fresh. If the environment
has no way to resume a specific prior agent, spawning fresh is the fallback, not a mistake.
