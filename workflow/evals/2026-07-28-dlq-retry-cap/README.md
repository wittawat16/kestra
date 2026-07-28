# Eval — kestra-spec/kestra-build/kestra-run, OLD (`a0fd1bf`) vs NEW (`ad1871d`+`20527ac`)

One end-to-end task, run twice through the full pipeline (spec → build → run) with two versions
of the skill trio, on a fixture chosen specifically to be **not Python** — a small Node/ESM repo
with no third-party dependencies (`fixture/`), so the comparison isn't biased toward whichever
language the trio happens to be best documented for.

**Task:** add a dead-letter/retry-cap path to an in-memory retry queue (`idea-dlq.md`). The idea
was written to plant a real ambiguity — "leave an unhandled-type message untouched" vs "the worker
must never silently keep going" — to see whether `kestra-spec`'s new step-6 self-check (P6) would
resolve it, and whether it would produce output good enough to avoid a costly implementation bounce
later in `kestra-run`.

**OLD** = skill trio as of commit `a0fd1bf` (before the compaction changes).
**NEW** = skill trio as of `ad1871d` (six compaction changes) + `20527ac` (opt-in `model` field).

Each phase's inputs/outputs are under `old/` and `new/`. `fixture/` is the target repo as it stood
before either run (git history stripped — both `old/` and `new/` ran their own copy of it).

## Results

| Phase | OLD tokens | NEW tokens | Δ |
|---|---|---|---|
| `kestra-spec` | 124,201 | 126,494 | +1.8% |
| `kestra-build` | 179,111 | 181,406 | +1.3% |
| `kestra-run` | 1,314,016 | 782,000\* | **−40.5%** |
| **Total** | **1,617,328** | **1,089,900** | **−32.6%** |

\* NEW's raw `kestra-run` spawn log has 8 lines instead of 6 because of an eval-harness mistake
(two stages were accidentally spawned twice due to a background-mode instruction error partway
through the run) — those two duplicate spawns are excluded from the total above as not
representative of the skill's own behavior. Raw log is in `new/spawn-log.jsonl` unedited; the
excluded lines are the first `verify`/`review` pair (before the correction).

## Why kestra-run differs so much: P6, not P1–P5

OLD's `implement-queue-retry` got the retry-cap invariant's control flow wrong on the first
attempt (an unreachable/dead guard), which `review` caught as `CHANGES_REQUESTED`. It took **two**
fixing rounds (`implement` × 2 more, `review` × 2 more re-checks) — 528,419 tokens and ~454s — to
land correctly. NEW's implementation passed clean on attempt 1, no fixing loop at all.

Traced to the spec itself:

- OLD's Runtime Invariant row: *"assertion at the end of the failure branch, before the message is
  placed anywhere"* — doesn't say where, or what the correct outcome is.
- NEW's Runtime Invariant row: *"guard at the end of the failure branch, after the increment: if
  attempts >= 3 the only legal path is the dead-letter branch"* — names the exact site and the one
  legal outcome, then closes with *"Cross-checked against Edge Cases and ACs: ... No invariant
  fires on a condition an AC declares successful."* — the literal output of `kestra-spec`'s new
  step-6 self-check.

Checked this wasn't NEW's `review` being less thorough: `new/review-verdict.md` flags an
analogous-looking dead branch in the same area and correctly classifies it non-blocking (genuine
defensive redundancy, not the load-bearing guard) — same rigor, less to actually catch.

**First-pass-only cost (excluding OLD's fixing loop) was statistically flat**: 785,597 (OLD) vs
782,000 (NEW), <0.5% apart — consistent with the earlier finding that per-spawn cost doesn't move
much with prose changes. The 32.6% overall saving here is real, but it's a demonstration of P6
specifically, not of P1–P5 (context pack, harness contract, evidence reuse, resume/respawn
threshold), which this fixture was too small to exercise (no test doubles needing a mutation
harness, no expensive sweep, no fixing loop on the NEW side to test resume-vs-respawn against).

## What this does and doesn't establish

- ✅ P6 (spec self-check) measurably prevented a real implementation defect and its full retry cost,
  on a non-Python codebase, in an otherwise apples-to-apples comparison.
- ✅ Neither version regressed on defect-catching rigor — `review` in both runs did real,
  file:line-cited verification; NEW just had less to find.
- ❌ P1–P5 remain unvalidated by this run. A second fixture that actually needs a mutation harness,
  an expensive sweep, or a long fixing loop is needed before claiming those save anything.
- ⚠️ n=1. One planted-ambiguity spec producing one bounce is a real data point, not a trend.

## Artifacts

- `idea-dlq.md` — the seed idea handed to `kestra-spec`, with the planted contradiction
- `fixture/` — the target repo both runs started from (Node/ESM, no third-party deps)
- `old/`, `new/` — `0-spec.md`, `workflow.yaml`, `state.json`, `spawn-log.jsonl`, `review-verdict.md`
  for each version
