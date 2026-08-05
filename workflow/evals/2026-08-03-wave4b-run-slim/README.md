# Eval — Wave 4b: kestra-run slim pack, pre-spawn surface check, clause-2 progress stop

**Ticket:** `arkaphat/arkaphat-builder#38` · **Date:** 2026-08-03 · **Verdict: PASS — 18/18
assertions, `run-legs.sh` exit 0.**

kestra-run is prose-driven — there is no orchestrator binary to test. What this eval grades is
therefore the *commands* the new prose mandates: every leg executes the exact recipe text from
`workflow/kestra-run/references/enforcement.md` against a real git repo and records the real exit
code. A reviewer re-runs everything with one command:

```
sh workflow/evals/2026-08-03-wave4b-run-slim/fixtures/run-legs.sh          # writes ../logs/
KX_ROOT=/tmp/elsewhere sh …/run-legs.sh                                    # any clean root works
```

## 0. Fixture

The Wave-4a build-fold fixture (an anchored sliced fold: `spec_anchor` triple + three tickets with
embedded `ticket:begin` briefs) materialized into a real git repo under `$KX_ROOT/repo` — the spec
committed first so `raise_commit` is a real, reachable commit; the anchor's `raise_commit`,
`surface_hash`, and every `verified_against` rewritten to that commit with the run folder's own
`requirement_surface.py` (`logs/00-fixture.log`). Nothing is simulated: `git cat-file -e`,
`git show <raise>:<spec>`, and both surface recomputes run for real.

## 1–5b. The pre-spawn surface check, every arm (`logs/01…05b-*.log`)

| Leg | Tree state | Expected | Measured |
|---|---|---|---|
| 1 | clean | proceed | `SURFACE OK: working == raised == recorded == 2f2e17ed…` exit 0 |
| 2 | one AC cell edited in `## AC Coverage Map` | MISMATCH, hard stop | `MISMATCH: surface moved — working 88c02e19… vs raised 2f2e17ed…` exit 1; restore ⇒ OK again |
| 3 | `raise_commit` = 40×`deadbeef` slice | MISMATCH, fail-closed | `MISMATCH: raise_commit unreachable in this repo` exit 1 |
| 4 | `surface_hash` key deleted | MISMATCH before any command | `MISMATCH: partial anchor — surface_hash missing or malformed` exit 1 — **and** the fold-side view agrees: `python3 <run>/validate_workflow.py <run>` FAILs the partial anchor, exit 1 |
| 5 | recorded `extractor_version: 2` vs run copy `1` | MISMATCH, not comparable | `MISMATCH: extractor_version differs (recorded 2 vs run copy 1)` exit 1 |
| 5b | recorded `surface_hash` edited to 64×`a` (arm 4 — recomputes agree, record doesn't) | MISMATCH | `MISMATCH: recorded surface_hash disagrees with the recompute at raise_commit — the anchor was edited` exit 1 |

*(Leg 2's hash values are per-fixture-build; re-runs produce the same equal/unequal outcomes with
that run's own hashes.)*

**F1 — measured extractor-boundary residual.** The first version of leg 2 edited a Given-When-Then
bullet in `## Acceptance Criteria` and then appended a new AC bullet — the hash did not move either
time (`2f2e17ed…` both sides, ASSERT FAIL). That is the extractor's *deliberate* boundary (#24's
five sections; the Coverage Map is the canonical paraphrase, the bullets are out), not a defect —
but it means the pre-spawn check does not detect out-of-surface prose drift. Recorded as a named
residual in `enforcement.md`'s surface-check section rather than silently fixed in the leg.

## 6. The slim pack (`logs/06-slim-pack.log`)

Pack composed for `implement-csv-writer` exactly per the recipe: stage block (embedded ticket,
verbatim) + provision layer (write_scope, pre-run `exit_criteria` with its real exit code, diff
line, evidence/harness lines) + the spec as **path + freshness line only**. Four assertions:

* pack **carries** `ticket:begin 01-csv-writer` (the slice's own requirement text) — OK
* pack **carries** `write_scope` and the pre-run exit code — OK
* pack **carries** "surface verified fresh this batch against `<raise>` — read sections on demand" — OK
* pack **does not contain** the sentinel line `"The object store does not guarantee
  read-after-write…"` — a `## Reality Constraints` line that exists in `0-spec.md` (control assert
  proves it) and appears nowhere in `workflow.yaml` — proving the spec body was not pasted. — OK

That is AC-1's "verifiably brief+provision only": the positive contents are asserted present, and a
spec-only sentinel is asserted absent, both by `grep` against the composed pack file.

## 7. Progress clause 2 (`logs/07-progress-clause2.log`)

Three failed attempts all reporting `2 failing, 1 passed`; the number extracted with the
`enforcement.md` grep recipe, appended to `progress_history` in the fixture's real `state.json`,
and compared per "moved = strictly improved toward the target":

```
attempt 2: value=2 prev=2 moved=False consecutive_no_progress=1
attempt 3: value=2 prev=2 moved=False consecutive_no_progress=2
ESCALATE: reworking — two consecutive attempt rounds without the number moving (clause 2)
```

exit 3 on exactly the second stalled round — not the first, and without waiting for
`max_attempts`. The persisted field is printed back from `state.json` afterwards:
`[{'attempt': 1, 'value': '2'}, {'attempt': 2, 'value': '2'}, {'attempt': 3, 'value': '2'}]`.

## 8. Snapshot-before-revert (`logs/08-snapshot-revert.log`)

An untracked out-of-scope file (`src/stray.py`) snapshotted to
`<run>/evidence/scope-violations/implement-csv-writer-attempt-1/src/stray.py`, then reverted with
the untracked-file recipe (`rm -f`). Asserted: the evidence copy exists, the worktree copy is gone,
`git status --porcelain -- src/` is empty.

## 9. Upstream regression (`logs/09-upstream-regression.log`)

`test_requirement_surface.py` 12 tests OK exit 0 · `test_validate_workflow_anchor.py` 42 tests OK
exit 0 · `validate_workflow.py workflow/runs/order-cancellation-refund` → 1 WARN (no
`spec_anchor`) + `PASS — 11 stages, structurally sound.` exit 0 — unchanged behavior.

## Artifacts

| File | What it is |
|---|---|
| [`fixtures/run-legs.sh`](fixtures/run-legs.sh) | **the whole eval, one command**, legs 0–9 → `logs/` |
| [`logs/00-fixture.log`](logs/00-fixture.log) … [`logs/09-upstream-regression.log`](logs/09-upstream-regression.log) | literal output + exit codes per leg |
| [`logs/verdict.log`](logs/verdict.log) | all 17 assertions, `assertion failures: 0` |
