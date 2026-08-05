# `state.json` schema

The single source of truth an orchestrator reads to resume. It always travels with the commit that
produced it — that pairing is the entire rollback/resume mechanism (see `design-principles.md`).
kestra-build only ever writes the **initial** version of this file — every stage still `pending`, nothing run
yet.

## Top-level

```json
{
  "feature": "<feature-id>",
  "current_stage": ["<id of a stage with no unmet depends_on>", "..."],
  "test_hash": null,
  "stages": { "<stage id>": { ... } }
}
```

- `current_stage` — **always an array**, even when only one stage is ready. This is what lets
  independent stages (e.g. multiple `implement-*` stages with non-overlapping `write_scope`) run
  concurrently without inventing a second field the first time that pattern shows up. At
  generation time this is every stage with an empty `depends_on`.
- `test_hash` — `null` until the `freeze_after` stage passes for the first time; from then on, the
  snapshot hash of the test suite. Every later stage checks this before running; a mismatch halts
  the pipeline. kestra-build always initializes this to `null`.

**No ticket map and no anchor triple here — deliberately.** A sliced fold's `spec_anchor` and
`tickets[]` (`body_sha256`, `ac_hash`, `verified_against`, `verified_at`) live in `workflow.yaml`
instead; see `workflow-schema.md`'s "`spec_anchor` and `tickets`". The reason is the split this file
already embodies: `workflow.yaml` is the derived definition and is immutable for the run's life, while
`state.json` is mutable run state the orchestrator rewrites at **every** commit. Provenance the
orchestrator must never rewrite belongs in the file the orchestrator never rewrites. Don't add a
second copy here for convenience — two copies of a hash is two answers to "did this ticket change?".

`state.json` does gate one fold-time decision, read-only: kestra-build refuses to **re-fold** a run
folder in which any stage's `status` is past `pending`, because overwriting this file mid-run destroys
the resume checkpoints and orphans the commits that were the rollback points. Before F0 overwrites
anything, the run's frozen validator enforces this with
`python3 <run>/validate_workflow.py <run> --refold-guard` (`ticket-fold.md` §4).

## Per-stage state

```json
{
  "status": "pending",       // pending | running | verifying | passed | fixing | reworking | waiting_approval | blocked
  "attempt": 0,
  "seen_diffs": [],            // semantic hashes of prior fix attempts, for no-progress detection
  "seen_failures": [],         // OPTIONAL, orchestrator-populated: normalized exit_criteria failure-output
                                // hashes, diagnostic only (see kestra-run enforcement.md). Never gates a
                                // transition — a future stage-generator must not start reading this field
                                // to decide fixing/reworking; it exists only to inform the reworking report.
  "metrics": {},               // OPTIONAL, orchestrator-populated: { tokens, wall_ms, spawn_type } per
                                // completed attempt. `spawn_type` on generate-tests/implement-* is read by
                                // `validate_workflow.py <run> --separation-guard`, which FAILs on anything
                                // but "fresh"; the rest is informational. Never read by exit_criteria,
                                // write_scope diffing, or the test-hash computation — populated by the
                                // orchestrator itself from data it already holds at commit time (Agent-tool
                                // usage numbers + timestamps), never by an extra subagent or exit_criteria
                                // check. A missing/failed metric means an absent row in the done-stage cost
                                // table, never a stage failure.
  "progress_history": []       // OPTIONAL for exit_criteria.progress: measured attempt/value entries,
                                // beginning with attempt 0 before the first work round; failed attempts append.
}
```

kestra-build initializes every stage to `status: "pending", attempt: 0, seen_diffs: []` — `seen_failures`,
`metrics`, and `progress_history` are populated later by the orchestrator, not by kestra-build, so the
generator may omit them entirely at generation time (an orchestrator that supports them adds the keys
itself on first use).
This holds regardless of where the stage sits in the dependency graph — the orchestrator is what advances
stages, not the generator.

For a stage with `exit_criteria.progress`, attempt 0 is measured from the real criterion before work,
not copied from prose. A later finite value moves only when its distance to the declared target is
strictly smaller than the preceding value; equal, farther, or unmeasured values do not move. Two
consecutive failed non-moves route the stage to `reworking` before the next attempt; passing attempts
do not append a history entry.

---

## Worked example

Matching the `csv-export` workflow in `workflow-schema.md`:

```json
{
  "feature": "csv-export",
  "current_stage": ["spec-review"],
  "test_hash": null,
  "stages": {
    "spec-review": { "status": "pending", "attempt": 0, "seen_diffs": [] },
    "generate-tests": { "status": "pending", "attempt": 0, "seen_diffs": [] },
    "implement-csv-export": { "status": "pending", "attempt": 0, "seen_diffs": [] },
    "verify-acceptance-criteria": { "status": "pending", "attempt": 0, "seen_diffs": [] },
    "review": { "status": "pending", "attempt": 0, "seen_diffs": [] },
    "done": { "status": "pending", "attempt": 0, "seen_diffs": [] }
  }
}
```

## Kill switch (for the orchestrator, not kestra-build)

Not something kestra-build writes, but worth knowing since it lives in the same file: setting any stage's
`status` to `"blocked"` halts every agent that reads this state — that's how a human pauses a run
mid-flight without touching the workflow definition itself.
