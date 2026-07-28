# Eval — lite mode, OLD (`a0fd1bf`) vs NEW (`ad1871d`+`20527ac`)

Companion to [`../2026-07-28-dlq-retry-cap/`](../2026-07-28-dlq-retry-cap/README.md), which tested
`mode: full`. This one deliberately targets `mode: lite` — a spec written to trip none of the
full-mode conditions (single component, no test doubles, no non-trivial Runtime Invariants,
`needs_devops: false`) — to see whether the compaction changes still pay off when there's nothing
for most of them to catch.

**Feature:** `chunkByCap(items, cap)` — a pure array-chunking helper, no I/O, no state, no clock.
Spec (`0-spec.md`) was hand-written directly rather than run through `kestra-spec`, since P6
(the spec self-check) was already validated by the `dlq-retry-cap` eval; this run is only testing
whether `kestra-build`/`kestra-run` derive and execute the lite shape correctly. Same fixture repo
(`fixture-ts`, pristine, same base as the sibling eval) — Node/ESM, no third-party deps.

## Results

| Phase | OLD tokens | NEW tokens | Δ |
|---|---|---|---|
| `kestra-build` | 131,273 | 167,975 | **+28.0%** |
| `kestra-run` (3 spawns, no fixing) | 348,828 | 344,292 | −1.3% |
| **Total** | **480,101** | **512,267** | **+6.7%** |

Both versions: chose `mode: lite` correctly, derived the identical 6-stage shape
(`generate-tests → freeze-tests → implement → {verify, review} → done`, `test-review` and
`deploy-readiness` correctly omitted), set no `model` override anywhere, and every stage passed on
attempt 1 with zero fixing/reworking. Correctness is not in question here — only cost.

## The finding: a fixed reading tax on `kestra-build`

This run went the **opposite direction** from `dlq-retry-cap`. There, NEW saved 32.6% because P6
prevented a real implementation bounce. Here, with nothing to prevent (both ran clean), NEW's
`kestra-build` phase alone cost 28% more (167,975 vs 131,273 tokens, 17 vs 11 tool uses) for an
**identical** output — same mode, same 6 stages, same `model` decision.

Most likely cause: `kestra-build/SKILL.md` is genuinely longer after the six compaction changes
(+223 lines) plus the `model` field (+58 lines) — none of which this trivial spec had any use for
(no harness, no evidence, no elaborate verdict shape needed), but `kestra-build` still has to read
the whole file to derive stages. This is a hypothesis inferred from the diff size and the spawn's
own tool-use count, not independently instrumented — worth confirming directly (e.g. comparing
token cost of just the file-read turns) before treating it as settled.

`kestra-run` itself was flat (−1.3%, noise-level) — consistent with the `dlq-retry-cap` finding
that per-spawn execution cost doesn't move much with prose changes; the tax observed here is
specific to `kestra-build`'s one-time read of its own (now longer) SKILL.md.

## Reading the two evals together

- **P6 has a real, measured upside** (528k tokens saved on `dlq-retry-cap`) **and a real, measured
  downside** (37k tokens more per `kestra-build` call, this run) — the six changes are not a free
  win, they're a bet that ambiguous/complex specs are common enough that the downside pays for
  itself. On this pair of tasks it does (−32.6% vs +6.7%, net favorable), but that's two data
  points, not a trend.
- The failure mode to watch for if this file keeps growing: every future compaction/guidance
  addition to `kestra-build/SKILL.md` makes this fixed tax larger, while the payoff only shows up
  on specs complex enough to have a defect worth preventing. A trivial-spec-heavy workload could
  end up net negative even if a complex-spec-heavy workload stays strongly net positive.
- n=1 per mode, same as the sibling eval — two clean data points, not enough to generalize a ratio
  of "how often is a spec complex enough for P6 to pay for the build-phase tax."

## Artifacts

- `0-spec.md` — hand-written spec for `chunkByCap`, deliberately shaped to trigger `mode: lite`
- `old/`, `new/` — `workflow.yaml`, `state.json`, `spawn-log.jsonl`, `review-verdict.md` per version
- Fixture repo is the same pristine base as
  [`../2026-07-28-dlq-retry-cap/fixture/`](../2026-07-28-dlq-retry-cap/fixture/) — not duplicated
  here since nothing in it changed before either build ran
