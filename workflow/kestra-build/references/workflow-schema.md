# `workflow.yaml` schema

One file per feature. Read `design-principles.md` before filling in `on_fail` / `freeze_after` —
the fields only make sense in light of *why* they exist.

## Top-level

```yaml
feature: <feature-id>              # kebab-case, matches the spec's feature id
source_spec: <path>                # spec this workflow was derived from
stages: [ ... ]                    # ordered list, see below — order is for readability only,
                                    # actual execution order comes from depends_on
```

## Per-stage fields

| Field | Required | Values | Notes |
|---|---|---|---|
| `id` | yes | unique string | referenced by other stages' `depends_on` and `branches.goto` |
| `depends_on` | yes | list of stage ids | `[]` for the first stage(s); a stage only starts once every dependency is `passed` |
| `brief` | no | free text | plain-language instructions for whatever Claude gets spawned to do this stage's work. **Never a skill name or ID** — see note below |
| `write_scope` | yes | list of glob patterns | paths this stage's diff may touch. `[]` means the stage produces no code diff (e.g. approval gates). Enforced at apply time by the orchestrator — not a promise the AI makes itself |
| `exit_criteria` | yes | object, see below | how the orchestrator decides `verifying` → `passed` vs `fixing` |
| `freeze_after` | no, default `false` | bool | set `true` **only** on the dedicated freeze stage, whose successful completion snapshots the test-hash into `state.json` and commits the freeze point. Exactly one stage per file has this set, and its `write_scope` must be non-empty — the hash is computed from that scope, so an empty one snapshots nothing and the invariant silently doesn't exist. Not the stage that *writes* the tests: that one stays unfrozen so its output can still be reviewed and fixed cheaply (see `design-principles.md`) |
| `on_fail` | yes | object, see below | what happens when `exit_criteria` fails |
| `branches` | no | list, see below | declarative conditional branching — optional, use sparingly |

### `brief`

```yaml
brief: >
  Implement the CSV export endpoint per the frozen spec/tests. An implementation-focused skill,
  if you have one installed, fits this stage well.
```

Skills in Claude Code aren't invoked by ID from the outside — a skill is a description that shows
up in whatever Claude gets spawned to do the work, and *that Claude* decides whether to use it,
the same way skill-triggering works in any normal session. So `brief` is never a `skill:` field
pointing at a specific skill name as a hard dependency — if you write `skill: some-skill` and it
isn't installed wherever this workflow eventually executes, the stage has nothing to fall back to.

kestra-build still gets to use what it knows *right now*: at generation time, kestra-build is itself
running inside a Claude session and can see its own `available_skills`. If something genuinely
relevant is installed (a planning-focused skill for a plan stage, an implementation/verification
skill for an implement/verify stage, a code-review/security-review skill for a review stage), name
it **inside the brief text as a suggestion** — worth trying if it's there, harmless to ignore if it
isn't. The stage's enforcement (`write_scope`, `exit_criteria`, `on_fail`) stays entirely
skill-agnostic; `brief` is the only place that ever mentions a skill by name, and only as a hint.

### `exit_criteria`

```yaml
exit_criteria:
  type: command             # command | artifact_exists | human_approval
  run: "npm test"           # required when type: command — the orchestrator's verifying step
  artifact: "path/to/file"  # required when type: artifact_exists
```

- `command` — orchestrator runs `run`, exit code 0 = pass. When `run` executes a real test suite
  (a `verify` stage, or any stage whose exit_criteria re-runs the frozen tests), prefer the test
  runner's own parallel-execution flag over a plain serial invocation — e.g. `pytest -n auto`
  (pytest-xdist), `jest --maxWorkers=<n>`, `go test -parallel <n>`, `vitest --pool=threads`. This
  still satisfies "one command, one real exit code" (the invariant this field exists to protect) —
  it's not a way to fan the test run out across multiple subagents, which would turn one exit code
  into several that the orchestrator would have to reconcile itself, reopening exactly the
  ambiguity this field is designed to close. Only use this when the target repo's test runner
  actually supports a parallel mode and the corresponding plugin/flag is available — verify that
  before writing it into `run`, the same "check it actually works standalone" discipline as any
  other `exit_criteria.run` command.
- `artifact_exists` — orchestrator checks the path exists (e.g. a design doc, a generated file).
- `human_approval` — orchestrator stops in `waiting_approval` and waits; a human's explicit
  approval is the only thing that flips it to `passed`. **Opt-in only** — see
  `design-principles.md`'s "Default HITL posture." The generator's default template never emits
  this type; only add it when the user explicitly asks for a manual milestone. Judgment-requiring
  stages (spec sanity, review, security) default to `command` against a verdict artifact instead
  (see the worked example below) — the fix loop and `fixing → reworking` remain the one place a
  human is always in the loop.

### `on_fail`

```yaml
on_fail:
  action: fixing            # fixing | reworking | blocked
  max_attempts: 5            # required when action: fixing
  escalate_at: 3              # required when action: fixing — a repeated diff (no progress) gets
                               # a grace window of retries below this attempt count; once attempt
                               # >= escalate_at, a repeat stops straight to reworking instead of
                               # retrying again, even if max_attempts hasn't been reached yet
  target: implement-x        # required when action: fixing AND this stage's own write_scope is []
                               # (a review/verify-only stage) — names the upstream stage whose
                               # write_scope the fix attempt is allowed to touch. Omit when the
                               # stage has its own non-empty write_scope (fixes apply to itself).
  reason: "short phrase"     # required when action: reworking or blocked — shown to the human
```

- `fixing` — orchestrator lets the stage retry, touching only `write_scope`, up to `max_attempts`.
  Every `fixing` stage must set both `max_attempts` and `escalate_at`; never leave it unbounded.
  A stage whose own `write_scope: []` (review, verify) can still use `action: fixing` — set
  `target` to the upstream implementation stage id. The orchestrator then: checks the fix attempt's
  diff against `target`'s `write_scope` (not this stage's own `[]`), tells the fix subagent what
  this stage's failure output said (e.g. the `CHANGES_REQUESTED` findings), and re-runs *this*
  stage's own work + `exit_criteria` again afterward. `attempt`/`seen_diffs` are still tracked
  against this stage's own entry in `state.json`, same as any other `fixing` stage.
- `reworking` — bounce **up** to spec-review or test-regeneration, unlock test paths, re-freeze,
  reset attempt counters. This is the *only* legal way test paths become writable again after
  `freeze_after` has fired, and the one place the design always stops for a human — see
  `design-principles.md`'s "Default HITL posture."
- `blocked` — terminal, needs a human. Rare in the default template now that `waiting_approval` is
  no longer a default stage; still available for a `human_approval` stage a user explicitly asked
  for, when the answer is "no."

### `branches` (optional — keep declarative)

```yaml
branches:
  - when: { exit_code: 0 }
    goto: implement-happy-path
  - when: { artifact_exists: "design.md" }
    goto: generate-tests-with-ui-cases
```

Conditions may reference only an exit code or an artifact's existence — nothing more expressive.
If a real decision tree is needed beyond that, say so to the user rather than encoding it here.

---

## Worked example

Feature: *"add an endpoint that exports a user's data as CSV"* (same example kestra-build's README uses).

```yaml
feature: csv-export
source_spec: workflows/runs/csv-export/0-spec.md

stages:
  - id: spec-review
    depends_on: []
    brief: >
      Review workflows/runs/csv-export/0-spec.md for the defects that are cheap to fix now and
      expensive to fix after tests are frozen. Check that: every acceptance criterion is testable
      without a follow-up question; each Runtime Invariant names what actually happens on violation
      and none of them amount to "log it and continue"; the Reality Constraints subsections are
      either filled in or explicitly marked not-applicable with a reason, in particular what each
      external dependency does NOT guarantee; and none of these contradict each other or the
      acceptance criteria. Anything derived rather than stated by the spec is flagged as inferred in
      the brief above — review the inference itself, don't assume a human already approved it.
      Write the verdict to spec-verdict.md, first line exactly "VERDICT: CLEAR" or
      "VERDICT: CHANGES_REQUESTED", followed by findings.
    write_scope: []
    exit_criteria:
      type: command
      run: "grep -q '^VERDICT: CLEAR$' spec-verdict.md"
    on_fail:
      action: reworking
      reason: "spec has gaps or contradictions — resolve before any test or code exists"

  - id: generate-tests
    depends_on: [spec-review]
    brief: >
      Write tests covering every acceptance criterion in the spec. No implementation exists yet —
      these tests must fail for the right reason (missing feature), not error out. Pin anything the
      spec's Reality Constraints marks as pinned rather than reading it live.
    write_scope: ["test/**"]
    exit_criteria:
      type: command
      run: "npm test -- --listTests csv-export && npx eslint test/csv-export --rule 'no-undef: error'"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2

  # Only generated when the spec's Reality Constraints list external dependencies or a pair of
  # paths that must agree — i.e. when the tests will contain doubles that can drift from reality.
  # A feature that fakes nothing can't have the defects this stage looks for; omit it there.
  # Note it comes BEFORE the freeze: findings here are a bounded fixing loop against
  # generate-tests, whereas the same finding after the freeze would cost a reworking bounce.
  - id: test-review
    depends_on: [generate-tests]
    brief: >
      Read the tests just written against the spec's Reality Constraints and report a table with one
      row per risk (ordering/preconditions, response realism, type/shape drift, path parity, own
      shared logic, non-determinism), each marked applicable or n/a with file:line evidence. Add
      rows this codebase's own conventions imply and say which you added. Judgment only — the
      mechanical checks already ran in generate-tests' exit_criteria; don't re-derive them. Write
      the verdict to test-verdict.md, first line exactly "VERDICT: CLEAR" or
      "VERDICT: CHANGES_REQUESTED", followed by findings.
    write_scope: []
    exit_criteria:
      type: command
      run: "grep -q '^VERDICT: CLEAR$' test-verdict.md"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2
      target: generate-tests

  # The freeze is its own act, deliberately separate from writing the tests. It writes nothing —
  # it owns the test paths solely so the test-hash has something to snapshot, and re-runs the
  # tests' own checks against the exact commit being locked. on_fail is reworking, not fixing:
  # a failure here means something is wrong upstream, and patching it at the freeze point would
  # bypass the review that just approved these tests.
  - id: freeze-tests
    depends_on: [test-review]
    brief: >
      No edits. This stage exists to snapshot and commit the approved test suite as the frozen
      baseline every later stage is held to.
    write_scope: ["test/**"]
    freeze_after: true
    exit_criteria:
      type: command
      run: "npm test -- --listTests csv-export && npx eslint test/csv-export --rule 'no-undef: error'"
    on_fail:
      action: reworking
      reason: "tests no longer pass their own checks at the freeze point — resolve upstream, don't patch here"

  - id: implement-csv-export
    depends_on: [freeze-tests]
    brief: >
      Implement the CSV export endpoint against the frozen tests — do not modify test/**. Also
      install the checks listed under the spec's Runtime Invariants: each one detects its condition
      and halts, refuses, or alerts rather than proceeding. The frozen tests will pass whether or
      not those guards exist — they were derived from anticipated cases, and the guards exist for
      unanticipated ones — so their presence is on you here, not on the test run. An
      implementation-focused skill fits this stage well if you have one installed.
    write_scope: ["src/routes/**", "src/services/csv-export/**"]
    exit_criteria:
      type: command
      run: "npm test -- csv-export"
    on_fail:
      action: fixing
      max_attempts: 5
      escalate_at: 3

  - id: verify-acceptance-criteria
    depends_on: [implement-csv-export]
    brief: >
      Run the full e2e suite and confirm every acceptance criterion in the spec is actually
      met by the implementation, not just that unit tests pass.
    write_scope: []
    exit_criteria:
      type: command
      run: "npm run test:e2e -- csv-export"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2
      target: implement-csv-export

  # Sibling of verify-acceptance-criteria, not its successor — both depend on implement-csv-export
  # directly so kestra-run can run them concurrently (neither writes code: write_scope: [] on both,
  # so there's nothing for them to collide on, and review's diff is already final the moment
  # implement-csv-export passes — it doesn't need verify to finish first).
  - id: review
    depends_on: [implement-csv-export]
    brief: >
      Review the real diff since the last stage commit for correctness, edge cases, and
      injection/authn/secrets risk. Passing tests only prove the spec's own acceptance criteria —
      this stage exists to catch what the spec never thought to test for. Whatever code-review and
      security-review skills you have available both fit this stage well; try them, proceed with a
      direct review if none are available. Write the verdict to review-verdict.md as the first
      line, exactly: "VERDICT: CLEAR" or "VERDICT: CHANGES_REQUESTED", followed by findings.
    write_scope: []
    exit_criteria:
      type: command
      run: "grep -q '^VERDICT: CLEAR$' review-verdict.md"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2
      target: implement-csv-export

  # Conditional — only include this stage when the spec sets needs_devops: true (or otherwise
  # implies env vars / DB migrations / feature flags / infra changes). Omit entirely otherwise.
  # Depends on BOTH siblings, not just review — it needs the full diff to be finished-and-passed,
  # and verify-acceptance-criteria passing is part of that, even though it ran in parallel.
  - id: deploy-readiness
    depends_on: [review, verify-acceptance-criteria]
    brief: >
      Produce a pre-deploy checklist for this diff: env vars, DB migration order + rollback,
      feature flags, infra changes, deploy order, rollback trigger, monitoring. Whatever
      devops-focused skill you have fits this stage well; try it, proceed with a direct checklist
      if not available.
    write_scope: []
    exit_criteria:
      type: artifact_exists
      artifact: "deploy-checklist.md"
    on_fail:
      action: fixing
      max_attempts: 2
      escalate_at: 2

  - id: done
    depends_on: [deploy-readiness]   # or [review, verify-acceptance-criteria] when deploy-readiness was omitted
    brief: >
      Every upstream stage passed. Write a one-page completion-summary.md: what shipped, which
      commits, the review/security verdicts, and (if present) the deploy checklist location.
    write_scope: ["completion-summary.md"]
    exit_criteria:
      type: artifact_exists
      artifact: "completion-summary.md"
    on_fail:
      action: fixing
      max_attempts: 2
      escalate_at: 2
```

Notice: `generate-tests` and `freeze-tests` are the only stages with `write_scope` touching
`test/**`, and `freeze-tests` alone carries `freeze_after: true`. Both sit *before* the freeze
point, which is why owning test paths is legitimate for them — that's how tests get written and
revised while revising them is still a bounded `fixing` loop rather than a `reworking` bounce. Every
stage from the freeze onward is forbidden those paths: if `implement-csv-export`'s diff touches
`test/**`, the orchestrator rejects it regardless of intent. `test-review`,
`verify-acceptance-criteria`, `review`, and `deploy-readiness` all have `write_scope: []` — they
judge or report on work they don't produce. `test-review` still directs fixes through
`on_fail.target: generate-tests`, the same mechanism `review` uses against the implement stage; a
reviewer that could edit what it reviews wouldn't be an independent check at all.

`verify-acceptance-criteria` and `review` both `depends_on: [implement-csv-export]` directly — they
are **siblings, not a chain**. kestra-run's rule for running independent stages in parallel ("their
`write_scope`s can't collide by construction") applies to them directly: both are `[]`, so there's
nothing to collide on, and neither needs the other's result to do its own job. Confirmed by direct
benchmarking: chaining them the "obvious" way (`review: depends_on: [verify-acceptance-criteria]`)
pays for a whole extra sequential subagent round-trip whenever both stages happen to need one, for
no correctness reason — `review`'s diff is already final the instant `implement-csv-export` passes.
Both `on_fail` to `fixing` with `target: implement-csv-export` — findings get a bounded number of
attempts to be addressed in the code, same as any failing check. **If both fail at once**, that's
still exactly one fix attempt on `implement-csv-export` with *both* stages' findings combined into
the brief, not two separate/competing fix attempts touching the same `write_scope` concurrently —
kestra-run's SKILL.md spells out the exact handling for this case. Either or both escalate to
`reworking` only once their own bounded loop is exhausted or stuck repeating the same diff.
`deploy-readiness` (and `done`, when `deploy-readiness` is omitted) waits on **both** siblings, not
just `review` — the full diff isn't actually finished-and-passed until verify has passed too, even
though it ran alongside review rather than after it. No stage in this example stops for a human
unless `reworking` is reached; see `design-principles.md`'s "Default HITL posture" for why that's
now the default, not the exception.
