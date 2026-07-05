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

## Per-stage state

```json
{
  "status": "pending",       // pending | running | verifying | passed | fixing | reworking | waiting_approval | blocked
  "attempt": 0,
  "seen_diffs": []             // semantic hashes of prior fix attempts, for no-progress detection
}
```

kestra-build initializes every stage to `status: "pending", attempt: 0, seen_diffs: []`, regardless of where
it sits in the dependency graph — the orchestrator is what advances stages, not the generator.

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
