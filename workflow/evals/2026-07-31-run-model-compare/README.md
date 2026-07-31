# Eval — kestra-run, REAL live execution, Sonnet 5 vs Opus 5 vs Haiku 4.5 orchestrator

Same shape as `2026-07-31-run-live-implement-context-pack/` (isolated scratch git repos, real
spawns/commits, scoped to `implement-tier-retry`), but this time the variable is the **orchestrator's
model** (`model: "sonnet"` vs `model: "opus"` on the Agent call), not the prompt. Same canonical
`workflow.yaml` used for both (from `2026-07-31-build-ablation-antipatterns/full-output/`, unchanged),
same seeded 3-commit git history (baseline → generate-tests passed → freeze-tests passed, code-empty
commit — the same no-diff-commit scenario as before). This run also incidentally re-validates
today's earlier fix to `enforcement.md`'s test-hash cwd ambiguity: the seeded `test_hash` this time
was computed with the now-documented repo-root basis, and both orchestrators' own recomputation
matched it cleanly on the first try — no repeat of the earlier cwd-mismatch debugging.

## Orchestration behavior: identical, independently verified

Both correctly walked back past the code-empty `freeze-tests` commit to `generate-tests`'s commit for
the diff, both included the frozen test file's full content, both independently re-verified
`write_scope` and `npm test` rather than trusting the nested subagent, both correctly stopped without
advancing to `verify-acceptance-criteria`/`review`, both flagged the same environment gaps
(`TaskCreate`/`TaskUpdate` unavailable; `source_spec` absent from the scratch repo, worked around by
reading the live reference repo instead) — no orchestration-level divergence this round.

## Where they did diverge: the nested implementation itself

The two orchestrators' nested `implement-tier-retry` subagents resolved the spec's Open Item (a
handler throwing a non-`Error` value) **differently**, even though both were handed the same neutral
brief text ("either halting or falling back to `String(err)` is defensible; state which you picked
and why"):

- **Sonnet's implementation**: `message.error = err.message` — no fallback. A non-`Error` throw
  leaves `error` `undefined`, which then fails the "must be a non-empty string" guard and **halts**
  (Open Item option (a)).
- **Opus's implementation**: `message.error = err?.message || String(err)` — a non-`Error` throw
  still produces a valid string, so `step()` **does not halt** on this case (Open Item option (b)).

Diff confirmed directly (`diff sonnet/final-queue.js opus/final-queue.js`). Both are internally
consistent with their own choice and both pass the frozen 9-test suite (neither test exercises a
non-Error throw — the spec left it explicitly open, so nothing pins it either way).

**Caveat worth being honest about:** this is evidence the two *implementations* diverge, but it does
not cleanly prove the divergence is *caused by* the orchestrator's model override propagating to the
nested spawn, versus the nested spawn defaulting to some other model regardless of the parent's
override. Circumstantial signal supports propagation (Opus's nested spawn took 8 tool calls / 95.8s
vs Sonnet's 4 tool calls / 59.0s for a similar token count — consistent with, though not proof of, a
genuinely different model doing more deliberate work) but this wasn't independently confirmed the way
the top-level orchestrator's own model was.

## Cost

| | Sonnet orchestrator | Opus orchestrator | Haiku orchestrator |
|---|---|---|---|
| Orchestrator (hard) | 172,463 | 168,606 | 145,151 (single synchronous run, no background/resume split) |
| Nested implement subagent | 118,443 (hard — separate notification) | ~121,019 (self-reported, relayed) | ~88,300 (self-reported, relayed) |
| Nested subagent tool calls | 4 | 8 | **88** |
| Total (best estimate) | ~290,906 | ~289,625 | ~233,451 |

Essentially a wash between Sonnet and Opus — unlike the kestra-spec comparison (Opus +14%), roughly
comparable there. Same accounting caveat as the earlier prompt-ablation live round: one child's cost
is harness-confirmed, the other is self-reported prose, so don't read too much precision into any of
these totals, Haiku's included.

**Haiku 4.5 round (2026-07-31, added later, same exact seed/workflow/spec):** cheapest in raw tokens
(~233k vs ~290k for Sonnet/Opus) but needed **~22x more tool calls** in the nested implement
subagent (88 vs Sonnet's 4) and the longest wall-clock (400.9s for the orchestrator alone, plus
whatever the nested spawn itself took within that). Despite the struggle, it converged to a correct
result on the **first attempt** — `state.json` shows `implement-tier-retry: {status: passed, attempt:
1}`, no `fixing` retry was triggered at the orchestrator/stage level. Independently verified (not
self-reported): `npm test` → 9/9 passing, `git diff --name-only` on the final commit touches only
`src/queue.js` + `state.json` (write_scope respected). Orchestration-layer behavior — context-pack
walk-back past the no-diff `freeze-tests` commit, frozen test file list resolution, test-hash
check — was **identical and correct**, matching Sonnet and Opus exactly. On the spec's Open Item,
Haiku picked the same `String(err)` fallback Opus did (differing from Sonnet's halt-only choice) —
n=1, not a pattern to read into.

One thing worth checking before trusting this pattern more broadly, not yet done: whether the
tier-resolution guard pattern all three models converged on independently (compute a normalized
`tier` via `message.tier === 'free' ? 'free' : 'paid'`, then re-check `message.tier !== 'free'`
*inside* the branch that condition already guarantees) is functionally meaningful or vestigial.
Traced through by hand: it's **not** dead code in the way it might look at first glance — it's
unreachable under the *current* derivation, but would actually fire if a future refactor loosened the
derivation (e.g. to case-insensitive matching), which is exactly the scenario the spec's invariant
names as the risk. All three models arrived at the identical defensive pattern independently; noted
here as a neutral observation, not a defect — resist the urge to "fix" it without re-deriving this
reasoning first.

## What this does and doesn't establish

- ✅ kestra-run's own orchestration logic (context-pack walk-back, mechanical verification, scoped
  stopping) behaved identically well on **all three** models, Haiku included — no model-sensitivity
  found in the orchestrator layer itself, on this scenario. This is the strongest evidence yet for
  the skill's own "Suggested model: Sonnet 5" note, and arguably stretches the case for "even Haiku is
  fine here" at the orchestration layer specifically — not for what a spawned stage decides.
- ✅ Confirms today's `enforcement.md` test-hash fix works cleanly across all three models, first try
  each time.
- ⚠️ Real implementation-level divergence found on an intentionally-open spec question — expected,
  since the spec explicitly left it open, but a reminder that "open items" really do get resolved
  differently depending on who's asked, and `review` (not tested this round, scoped stop) is what's
  supposed to catch an unintended inconsistency here, not kestra-run itself.
- ⚠️ Haiku's dramatically higher nested-subagent tool-call count (88 vs single digits) is a real
  efficiency/reliability signal even though it converged correctly this time — a harder feature or a
  larger codebase could plausibly push the same struggle past `max_attempts` where Sonnet/Opus
  wouldn't. This round doesn't test that; it's a single-component, well-specified feature.
- ❌ Model-propagation-to-nested-spawn is inferred, not proven. n=1 scenario, same caveats as every
  round before this.

## Artifacts

- `sonnet/`, `opus/`, `haiku/` — final `queue.js`, commit log, and commit stat from each isolated run
  (full git repos left in scratchpad, not copied here — scratchpad doesn't persist, so only these
  summaries survive if this thread isn't revisited soon)
