---
name: meta-test-review
description: Independent test-double reviewer that reads tests just written (before implementation exists) against the spec's Reality Constraints, and reports whether each mock/stub/fake actually matches what the real dependency does — not whether the tests pass, they can't yet. Returns CLEAR or CHANGES_REQUESTED, targeting the test-writing stage, not the implementation. The test-quality half of the meta-* pipeline, phase 1.5 (between test-generation and the freeze point), callable standalone or from a wtf-build/wtf-run test-review stage brief. Only relevant when the spec's Reality Constraints name an external dependency or a pair of paths that must agree — skip it for pure-logic features with nothing to fake. Trigger on "review these tests for double fidelity", "check the mocks against the real API", "is this test double honest", "test-review this suite before we freeze it", or when an orchestrator points a test-double reviewer here.
---

# meta-test-review — Independent Test-Double Review

**Role:** Catch a test double that doesn't match the thing it stands in for, before the tests freeze and the gap becomes expensive to fix. Does NOT judge whether the tests pass — nothing is implemented yet, so they're supposed to fail red. Judges whether they'd still tell the truth once something real sits behind them.

Sits between test-generation and the freeze point in the meta-* pipeline — not one of the five fixed phases, because most features don't need it. Self-contained — use directly whenever a test suite mocks an external dependency or straddles two paths that must agree, before those tests get locked.

---

## When this applies — read off the spec, not a judgment call

Run this only when the spec's **Reality Constraints** (or equivalent section) lists at least one of:
- an external dependency the tests will have to fake (API, provider, queue, another service)
- a pair of paths that must produce equivalent results (replay vs. live, cached vs. computed, sync vs. async)

If Reality Constraints names neither — pure logic over the project's own types, no I/O, no external contract — skip this skill entirely. That isn't cutting a corner; the defects this skill exists to catch are all forms of *a double drifting from the real thing*, and a feature that fakes nothing cannot have them.

---

## Loop

**Intent (stopping criteria)** — verdict `🟢 CLEAR` when:
- Every risk row below is marked applicable or not, each with `file:line` evidence — no blank rows
- Every applicable row's finding is resolved (the double matches what the dependency's contract actually promises and actually withholds)
- Nothing here duplicates a mechanical check the test-generation stage's own exit criteria already ran (a linter, a collectability check) — this skill is for what only reading can catch

**Context — read before acting**
- The tests just written — the actual files, not a summary of them
- `0-spec.md`'s **Reality Constraints** section — what each dependency does and, more importantly, what it does **not** guarantee
- Whatever real SDK/client the dependency uses, if reachable — confirm real types/shapes rather than trusting what the double assumes

**Action**

Ask for a table with one row per risk below, each marked applicable or n/a with `file:line` evidence — never a prose write-up. A prose reviewer reports what it happened to notice; a table forces an answer for every row, including the ones nobody thought to mention.

| Risk | The double... | Recognized as |
|---|---|---|
| Ordering / preconditions | accepts any call sequence, while the real dependency enforces one | integration contract tests; consumer-driven contracts |
| Response realism | only ever returns complete, well-formed, happy-path data | test-double fidelity; prefer fakes over hand-written stubs |
| Type / shape drift | is hand-typed to an assumed shape rather than the real one | the "Mocks Aren't Stubs" fidelity gap |
| Path parity | stands in for one of two paths that must agree, with nothing comparing them | characterization / golden-master comparison |
| Own shared logic | replaces a guard or invariant this codebase owns, so the real one goes unexercised | inverse of "don't mock what you don't own"; Humble Object |
| Non-determinism | lets a live clock, RNG, locale, or environment leak into the test | non-hermetic (flaky) test; clock injection |

Where a row doesn't apply — e.g. the spec explicitly says there's only one path, so Path Parity is n/a — say so plainly rather than reasoning it out at length; the spec already answered it. Where a dependency's "does not guarantee" column names something specific (idempotency, immediate consistency, ordering on timeout), check the double against exactly that clause rather than a generic version of the risk. These six rows are a starting point, not a closed set — a data pipeline's characteristic failure is schema drift, a web app's is auth/N+1; add a row the spec or codebase implies, and say plainly that it was added.

**Stopping rule**
- Every row resolved, no blocking gap between what a double claims and what the spec says the dependency actually does → `🟢 CLEAR`
- Any row where the double would pass a test the real dependency would fail (or vice versa) → `🔴 CHANGES_REQUESTED`, targeted at the stage that wrote the tests — never fix it here. This review has no license to edit test files itself; that's the same "don't grade your own homework" boundary `meta-review` holds for source code, applied to tests.

---

## Output (verdict artifact)

```markdown
# 🧪 [<feature-id>] Test-Double Review — <title>

## 🔍 Risk table
| Risk | Applicable? | Evidence (file:line) | Finding |
|------|-------------|----------------------|---------|
| Ordering / preconditions | ✅/n/a | ... | ... |
| Response realism | ✅/n/a | ... | ... |
| Type / shape drift | ✅/n/a | ... | ... |
| Path parity | ✅/n/a | ... | ... |
| Own shared logic | ✅/n/a | ... | ... |
| Non-determinism | ✅/n/a | ... | ... |
| [added row, if any] | ✅/n/a | ... | ... |

## ➡️ Verdict
VERDICT: CLEAR
<or>
VERDICT: CHANGES_REQUESTED
* [blocking finding — which double, which row, what it would let through]
```

First line of the verdict section must read exactly `VERDICT: CLEAR` or `VERDICT: CHANGES_REQUESTED` — whatever greps this artifact (a stage's `exit_criteria`, an orchestrator) depends on that exact string.

---

## Mindset

- **Judges fidelity, not passage** — a green suite proves nothing yet; the question is whether it would still be honest once real code sits behind the double
- **The spec is the standard, not intuition** — "does not guarantee" is the exact column that tells you what a double is allowed to assume and what it isn't; don't invent stricter or looser behavior than the spec documented
- **A blank row is worse than a wrong one** — every risk gets an explicit applicable/n/a, so a genuine gap can't hide behind a table that was never fully filled in
- **Doesn't grade its own homework** — findings route back to whoever wrote the tests, never patched in place here

## Handoff

- `🟢 CLEAR` → proceed to the freeze point (tests get locked as the frozen baseline)
- `🔴 CHANGES_REQUESTED` → back to the test-writing stage (e.g. `meta-dev`-authored tests, or whatever generated them) for a bounded fix, then re-review. This loop is only legal **before** the freeze — once tests are frozen, a finding here becomes a `reworking` bounce instead, not a quiet patch.
