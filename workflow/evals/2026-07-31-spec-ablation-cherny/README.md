# Eval — kestra-spec, FULL prose vs. Cherny-style ABLATED (minimal) prompt

Not an OLD-vs-NEW commit comparison like the other evals in this folder — a **prompt-ablation**
test, prompted by Boris Cherny's "press delete" philosophy (write a minimal goal + guardrails,
trust the model, only add back instructions for mistakes it actually makes). Same idea, same
fixture, same model, two prompt variants:

- **`full/`** — the real `kestra-spec/SKILL.md`, pasted verbatim (~320 lines: full step-by-step
  process, rationale paragraphs, the a/b/c/d Reality-Constraints framing, the itemized 5-point
  step-6 self-check, the Mindset section).
- **`minimal/`** — a ~40-line distillation: one goal sentence, six bullet instructions (no
  step-by-step process, no rationale, no Mindset section, step-6 self-check compressed to one
  bullet), the same guardrails in one paragraph, and the **same output template verbatim** (kept
  because it's a hard interface contract with `kestra-build`, not narrative — Cherny's ablation
  targets over-specified *process*, not a downstream schema).

Task: `idea-queue-cap.md` — add a `maxQueueSize` cap to `enqueue()` on the same in-memory retry
queue fixture used by `2026-07-28-dlq-retry-cap/` (`fixture/`, copied fresh, Node/ESM, no deps).
The idea's own wording ("must never be blocked by the cap, even if pending is already exactly at
the cap") assumes retries can push `pending` over the cap — planted to see whether either variant
would notice this doesn't actually happen (a `step()` retry always shifts one message off `pending`
before pushing it back, so it's size-neutral, never growing) and reframe the real risk as a future
maintenance regression rather than a live overshoot.

## Results

| | FULL | MINIMAL | Δ |
|---|---|---|---|
| Subagent tokens | 143,246 | 139,514 | −2.6% |
| Wall time | 268s | 274s | +2.2% |
| Tool calls | 9 | 9 | 0 |

Token/time cost was statistically flat — consistent with this repo's earlier finding
(`2026-07-28-dlq-retry-cap/README.md`) that per-spawn cost doesn't move much with prose changes.
**Cutting ~85% of the instruction text did not cut cost.** If there's a token-savings lever in this
skill, it isn't prompt length.

## Stopping-rule checklist (graded against kestra-spec's own 8-item Stopping Rule)

| Item | FULL | MINIMAL |
|---|---|---|
| Every AC testable without follow-up | ✅ 9 ACs, exact inputs | ✅ 7 ACs, exact inputs |
| Flagged sections have real content | ✅ N/A (all flags false) | ✅ N/A (all flags false) |
| Files to Touch verified to exist | ✅ both files read in full | ✅ both files read in full |
| Every AC maps to a coverage-map row | ✅ 9/9 | ✅ 7/7 |
| Runtime Invariants name on-violation, none "log and continue" | ✅ 3 invariants, refuse/halt/halt | ✅ 2 invariants, refuse / honestly-flagged-no-runtime-detection |
| Reality Constraints filled or N/A+reason | ✅ prose | ✅ tabular, more literally per-row |
| Step 6 self-check actually run (not just read internally) | ✅ ran `npm test`, read all 4 fixture files | ✅ ran `npm test`, read all 4 fixture files |
| No silent gaps — unresolved → Open Items | ✅ "None" | ✅ "None" |

**Both variants pass all 8 items identically.** No checklist-level quality regression from the
ablation.

## Where they actually differed

- **MINIMAL caught a sharper bug than FULL.** Both flagged "don't unify `step()`'s push-backs
  through `enqueue()` for DRY" as the one real risk. FULL's Risks section states one consequence
  (retries would get wrongly capped). MINIMAL's Risks section states **two** — the same capping
  bug, *plus* that `enqueue()` always does `{attempts: 0, ...message}`, so unifying would silently
  reset a retried message's `attempts` back to 0 on every retry, a correctness bug independent of
  the cap. FULL never mentions this second consequence anywhere. This is the opposite of what
  hobbling-by-over-specification would predict — the shorter prompt produced the more original
  catch here, not a shallower one.
- **FULL repeats itself; MINIMAL doesn't.** FULL restates the "don't route step()'s pushes through
  enqueue()" point four separate times (Functional Requirements #6, Runtime Invariants row 2,
  Codebase Survey, Risks). MINIMAL states it once, in Risks, with the extra attempts-reset detail
  folded in. Same fact, a quarter of the restatement cost to a downstream reader — and `kestra-run`'s
  context pack pastes this file into *every* later stage spawn, so FULL's repetition is a real,
  recurring tax, not a one-time stylistic issue.
- **Step 6 compressed to one bullet still fired.** The earlier `2026-07-28-dlq-retry-cap` eval found
  step 6's itemized self-check (P6) was the single highest-value section in the whole skill —
  measurably prevented a real implementation defect. MINIMAL compressed its 5-item checklist to one
  sentence ("check your own invariants against your own edge cases/ACs for contradictions... confirm
  every claim came from actually reading or running something"). MINIMAL still ran `npm test`, still
  read every fixture file before writing a line, and its Runtime Invariants table shows the same
  cross-check discipline as FULL's (both independently converged on "this specific invariant has no
  live runtime detection point — say so honestly" for the retry-exemption row). **What P6 needed was
  the instruction to self-check, not five paragraphs describing what self-checking looks like.**

## What this does and doesn't establish

- ✅ On this fixture, with this model, cutting the process-narrative/rationale/Mindset prose down to
  goal + guardrails produced an output that passes every mechanical stopping-rule item identically,
  at flat cost, with no observable quality loss — and one section (Risks) that was arguably better.
- ❌ **Doesn't test the flagged-work sections** (`needs_ba`/`needs_ui`/`needs_sa` step-3 content).
  Every flag came out `false` on both runs, so step 3's detailed per-flag instructions (BR
  examples/counter-examples, component audits, 2-3 SA approaches) never actually fired in either
  variant. That's this skill's largest remaining chunk of unverified prose — a UI- or BA-heavy idea
  is the next fixture needed before trimming those sections.
- ❌ **n=1, one model, one fixture.** A single planted-risk idea producing one comparison is a data
  point, not a trend — same caveat the dlq eval flagged about itself.
- ❌ Doesn't test downstream cost (`kestra-build`/`kestra-run` off of either spec) — both specs look
  build-ready by inspection, but neither was actually run through the rest of the pipeline to confirm
  MINIMAL's spec doesn't cost more later from something FULL's prose would have caught.

## Artifacts

- `idea-queue-cap.md` — the seed idea, with the planted (and, per both agents' own analysis, false)
  overshoot premise
- `minimal-prompt.md` — the ablated instruction set used for the MINIMAL run
- `fixture/` — the target repo both runs read (fresh copy of `2026-07-28-dlq-retry-cap/fixture/`)
- `full/0-spec.md`, `minimal/0-spec.md` — the two produced specs
