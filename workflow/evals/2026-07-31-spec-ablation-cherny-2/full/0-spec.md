# [priority-tier] Spec — Tier-based retry policy for the queue

> Status: READY_FOR_BUILD | Created: 2026-07-31 | Next: kestra-build

---

## Overview
Enqueued messages carry a `tier` (`'paid'`/`'free'`); on handler failure, paid retries
indefinitely (today's behavior), free drops after its one attempt into a new `dropped` list;
operators get per-tier succeeded/dropped counts.

## Problem Statement
* Today `step()` treats every failure identically: increment `attempts`, requeue to tail of
  `pending`, retry forever. No tier concept exists.
* Goal: paid keeps today's indefinite-retry SLA; free gets exactly one attempt then is moved
  (not requeued) to a new `dropped` list with its failure recorded; operators can read
  succeeded-vs-dropped counts per tier.

## Functional Requirements
* [ ] `createQueue()` returns `{ pending: [], done: [], dropped: [] }` — new `dropped` array
  alongside the existing two.
* [ ] Given a paid-tier message (`tier: 'paid'`) whose handler throws, when `step()` processes
  it, then `attempts` increments by 1, the message returns to the tail of `pending`, and the
  result is `{ status: 'retry', id, tier: 'paid', attempts }` — unchanged behavior, tier now
  echoed in the result.
* [ ] Given a free-tier message (`tier: 'free'`) whose handler throws, when `step()` processes
  it, then the message is removed from `pending`, `attempts` increments by 1, an `error` field
  is set to the thrown error's `.message`, the message is pushed to `queue.dropped` (not
  `pending`), and the result is `{ status: 'dropped', id, tier: 'free', attempts: 1 }`.
* [ ] Given a message with no `tier` field whose handler throws, when `step()` processes it,
  then it is treated exactly as `tier: 'paid'` (retried, never dropped) — missing tier defaults
  to paid.
* [ ] Given a message with an unrecognized `tier` value (e.g. `'gold'`) whose handler throws,
  when `step()` processes it, then it is treated as paid (retried) — the same safer-default
  reasoning extended from "missing" to "anything other than the literal string `'free'`", since
  the idea names only `'paid'`/`'free'` as valid and frames paid as the safe fallback.
* [ ] Given any message (any tier, or missing tier) whose `type` has no registered handler, when
  `step()` processes it, then the message stays in `pending` unchanged and the result is
  `{ status: 'skipped', id }` — tier plays no role in the no-handler path, matching today.
* [ ] Given a free-tier message whose handler succeeds, when `step()` processes it, then it goes
  to `queue.done` exactly as any other tier — tier only branches the *failure* path, never
  success.
* [ ] New export `getMetrics(queue)` returns
  `{ paid: { succeeded: N, dropped: 0 }, free: { succeeded: N, dropped: M } }`, computed by
  scanning `queue.done`/`queue.dropped` at call time (resolving each message's tier the same
  way `step()` does) — not a separately maintained counter, so it cannot drift from the arrays'
  real contents.

## Edge Cases & Error States
* **Free-tier message succeeds on first try:** goes to `done`, same as any tier — no drop, no
  metrics-dropped increment.
* **Free-tier message with unrecognized `tier` string:** treated as paid — see FR above; this is
  an inferred extension of the idea's stated "missing tier -> paid, the safer default" rule to
  any non-`'free'` value, not literal idea text, decided here rather than left ambiguous.
* **No-handler ("skip") path:** unaffected by tier, per idea — explicit FR/AC above; a common bug
  risk is accidentally checking tier before the handler-lookup, which would wrongly drop a
  free-tier message that simply has no handler yet — must not happen.
* **`enqueue()`'s existing `{ attempts: 0, ...message }` spread:** a caller-supplied `attempts`
  field on the incoming message object silently overrides the `0` default (pre-existing
  behavior, `src/queue.js` line 15, unrelated to this feature). The drop decision does not
  depend on the `attempts` value — free tier drops unconditionally on first failure regardless
  of what `attempts` started at — so this quirk cannot cause a free-tier message to dodge or
  duplicate a drop. Not fixed here; out of scope.
* **`HANDLERS` is module-level global state**, not per-queue (`src/queue.js` line 4) — new tests
  for tier behavior must register handlers under `type` strings not already used elsewhere in
  `test/queue.test.js` (existing tests use `'email'`, `'boom'`) to avoid cross-test collisions
  in the same process.

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| Every message pushed to `queue.dropped` carries the failure that caused the drop: `attempts >= 1` and a non-empty `error` string | guard immediately before `queue.dropped.push(message)` inside `step()`'s free-tier branch: `if (!message.error) throw new Error(...)` | halt — `step()` throws synchronously instead of pushing an incomplete record; nothing in this codebase wraps `step()` calls in a try/catch (verified: no such wrapper exists in `src/queue.js` or `test/queue.test.js`), so the exception propagates to whatever drives the worker loop |
| Only a literal `tier === 'free'` may result in a drop — every other value (including absent/unrecognized) retries indefinitely | defensive assertion at the top of the free-tier branch: `if (message.tier !== 'free') throw new Error(...)`, guarding against a future refactor loosening the check (e.g. to case-insensitive or truthy) | halt — this is the exact regression the idea explicitly calls unacceptable ("silently downgrading an un-migrated caller's messages... would be a regression nobody asked for"); throwing beats a silent wrong-tier drop |

## Business Rules
* **BR-1 (tier-based failure handling):**
  Given a paid-tier message whose handler throws, when `step()` processes it, then `attempts`
  increments and the message returns to the tail of `pending` with status `'retry'` — indefinite
  retry, unchanged from today.
  Counter-example: given a free-tier message whose handler throws, when `step()` processes it,
  then the message moves to `queue.dropped` (never back to `pending`) with its single failure
  recorded, status `'dropped'`.
* **BR-2 (missing tier defaults to paid):**
  Given a message enqueued with no `tier` field whose handler throws, when `step()` processes
  it, then it is retried exactly like an explicit `tier: 'paid'` message — the safer default,
  since silently downgrading an un-migrated caller to free-tier drop-on-failure would be an
  unrequested regression.
  Counter-example: given the same message but with `tier: 'free'` explicitly set, when `step()`
  processes it, then it is dropped after one failure, not defaulted to paid.
* **BR-3 (no-handler path is tier-independent):**
  Given a message of any tier (or missing tier) whose `type` has no registered handler, when
  `step()` processes it, then the message stays in `pending` unchanged with status `'skipped'`.
  Counter-example: a free-tier message with no handler must NOT be moved to `dropped` — the
  no-handler/"skip" path never looks at `tier` at all, it returns before the try/catch that
  contains the tier branch.
* **BR-4 (per-tier success/drop visibility for operators):**
  Given messages of both tiers processed over time, when an operator calls `getMetrics(queue)`,
  then the result distinguishes paid vs. free succeeded/dropped counts, so operators can tell
  whether the free tier's one-shot policy is costing a meaningful failure rate.
  Counter-example: a metrics shape that lumps both tiers into one combined count does not
  satisfy this rule — per-tier breakdown is the explicit ask.
* Stakeholder variations:
  - Paid customers: expect indefinite retry (SLA-driven), unaffected by this change.
  - Free customers: no retry SLA — exactly one attempt, then dropped; not configurable (out of
    scope per idea).
  - Un-migrated callers (no `tier` field yet): protected by the paid default so this ships
    without silently changing their existing behavior.
  - Operators: need `getMetrics()` to evaluate whether the free-tier policy's failure rate is
    acceptable.

## Codebase Survey
* Explored: `src/queue.js` (full file, 39 lines), `test/queue.test.js` (full file, 21 lines),
  `CLAUDE.md`, `package.json`.
* Integrate with:
  - `src/queue.js` — `createQueue()` (add `dropped: []`), `step()`'s catch block (add tier
    branch + invariant guards), new named export `getMetrics(queue)`.
  - Tier resolution logic is a single ternary reused in two places (`step()`'s catch block and
    `getMetrics()`): `message.tier === 'free' ? 'free' : 'paid'` — same expression in both, so
    a future tier value can't be classified differently by the two call sites. Not extracted
    into a shared named helper here because the codebase has no precedent for small private
    helpers in this file and the expression is one line repeated exactly twice; note this as a
    candidate for extraction if a third call site appears.
  - `getMetrics` derives counts from `queue.done`/`queue.dropped` at call time rather than
    maintaining separate running counters — avoids a second source of truth that could drift
    from the arrays' real contents (e.g. a counter incremented in one code path but not another
    after a future edit). This is the reason no new mutable state is added to `createQueue()`
    beyond the `dropped` array itself.
  - `test/queue.test.js` — existing 2 tests unaffected; `npm test` (`node --test test/*.test.js`)
    verified green before this change (2/2 passing, see below).
  - Conventions followed: named exports only (no default export), ES modules, no third-party
    deps, no TypeScript, tests mirror `src/<name>.js` -> `test/<name>.test.js` (same file, no
    new test file needed).
* New dependencies: none (CLAUDE.md: "No third-party dependencies; keep it that way" — this
  feature needs none).
* Risks:
  - Shared file: `src/queue.js` is the only source file — `generate-tests`/`implement` both work
    inside the same file, no cross-file coordination needed, no race condition risk (single
    synchronous worker-loop model, no concurrency in this codebase).
  - `HANDLERS` module-level `Map` is shared global state across the whole test process — new
    tier tests must pick `type` strings distinct from existing tests' (`'email'`, `'boom'`) to
    avoid silent handler-registration collisions (see Edge Cases).
  - Return-shape change: adding `tier` to the `'retry'`/`'dropped'` result objects is additive
    (existing test only asserts `.attempts` and `.status`, not full-object equality) — verified
    by reading `test/queue.test.js` lines 14-20, confirmed no `assert.deepEqual` on the full
    `step()` result that would break.

## Reality Constraints
*(what the world outside this feature actually does — verified by running/reading, not assumed.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|-----------------------------------|-------------------------|
| `HANDLERS` module-level `Map<string, (payload) => void>` (`src/queue.js` line 4) | `registerHandler(type, fn)` must run before any `step()` call processes a message of that `type`, in the same process | plain synchronous function `(payload) => void`; throws to signal failure, no return-value-based error protocol | isolation between test cases in the same process — registrations persist for the process lifetime; does not guarantee a handler is idempotent, side-effect-free, or that it won't throw non-`Error` values (verified: `step()`'s catch binds whatever was thrown to `err` with no type check, so `err.message` on a thrown non-Error, e.g. a thrown string, would be `undefined` — see Open Items) |

### Paths that must agree
* None — single synchronous path per `step()` call, no replay/live, cache/compute, or sync/async
  split anywhere in this codebase (verified: `step()` has no `await`, no callbacks, no branching
  on an execution mode).

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-------------------------------|-----|
| Clock | N/A — not read | feature reads no timestamp anywhere |
| Randomness | N/A — not read | no `Math.random`/UUID generation in this feature |
| Timezone/locale | N/A — not read | no date/locale formatting involved |
| Network | N/A — not read | fully in-memory, no I/O |
| Filesystem | N/A — not read | fully in-memory, no I/O |
| Env vars | N/A — not read | no `process.env` access in `src/queue.js` or this feature |

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `src/queue.js` | edit | exists (39 lines, read in full) | add `dropped: []` to `createQueue()`; tier-branch + invariant guards in `step()`'s catch block; new `getMetrics(queue)` export |
| `test/queue.test.js` | edit | exists (21 lines, read in full) | add tests for paid-retry-with-tier-echo, free-drop, missing-tier-default, unrecognized-tier-default, no-handler-tier-independence, success-path-tier-independence, `getMetrics` — per this repo's convention, one test file mirrors `src/queue.js`, no new file |

## Dependencies
* None — CLAUDE.md mandates zero third-party dependencies; this feature adds none.

## Acceptance Criteria
* [ ] `createQueue()` returns `{ pending: [], done: [], dropped: [] }`.
* [ ] Given a paid-tier message whose handler throws, when `step()` runs, then `attempts`
  increments by 1, message is at the tail of `pending`, result is
  `{ status: 'retry', id, tier: 'paid', attempts: 1 }`.
* [ ] Given a free-tier message whose handler throws, when `step()` runs, then `pending` no
  longer contains it, `queue.dropped` contains it with `attempts: 1` and `error` set to the
  thrown error's message, result is `{ status: 'dropped', id, tier: 'free', attempts: 1 }`.
* [ ] Given a message with no `tier` field whose handler throws, when `step()` runs, then result
  is `{ status: 'retry', id, tier: 'paid', attempts: 1 }` — identical to explicit paid.
* [ ] Given a message with `tier: 'gold'` (unrecognized) whose handler throws, when `step()`
  runs, then result is `{ status: 'retry', id, tier: 'paid', attempts: 1 }`.
* [ ] Given any message (any/no tier) whose `type` has no registered handler, when `step()` runs,
  then `pending` is unchanged in length/order and result is `{ status: 'skipped', id }`.
* [ ] Given a free-tier message whose handler succeeds, when `step()` runs, then it is in
  `queue.done` and `queue.dropped` is unaffected.
* [ ] `getMetrics(queue)` on a queue with 2 paid successes, 1 free success, 1 free drop returns
  `{ paid: { succeeded: 2, dropped: 0 }, free: { succeeded: 1, dropped: 1 } }`.
* [ ] `npm test` (`node --test test/*.test.js`) exits 0 with all tests (existing 2 + new) passing.

## AC Coverage Map
| AC | Covered by (files/steps) |
|----|---------------------------|
| `createQueue()` returns `dropped: []` | `src/queue.js` `createQueue()` edit; new test asserting shape |
| paid-tier retry (explicit) | `src/queue.js` `step()` catch-block paid branch; new test |
| free-tier drop | `src/queue.js` `step()` catch-block free branch; new test |
| missing-tier defaults to paid | `src/queue.js` tier-resolution ternary; new test |
| unrecognized-tier defaults to paid | same ternary; new test |
| no-handler path tier-independent | `src/queue.js` `step()` handler-lookup branch (unchanged, precedes tier logic); new test |
| success path tier-independent | `src/queue.js` `step()` try-block (unchanged); new test |
| `getMetrics()` per-tier counts | `src/queue.js` new `getMetrics()` export; new test |
| `npm test` exits 0 | repo's existing `npm test` script (`package.json`), run as part of verify |

## Risks & Watch-outs
* `HANDLERS` global-registry collision across tests — pick unique `type` strings for new tests.
* Adding `tier`/`error` fields to result/message objects is additive only — do not change
  existing field names or remove any (`id`, `status`, `attempts` on results; `attempts`, and
  whatever the caller put on the message, on messages) to avoid breaking the 2 existing tests.
* `getMetrics()` must re-derive from arrays, never maintain a separate counter — the drift risk
  named in Codebase Survey.

## Out of Scope
* Configurable retry count for free tier (idea: "it's exactly one attempt, no config knob").
* Resurrecting `dropped` messages back into `pending`.
* Any UI/dashboard rendering of the metrics — `getMetrics()` returns data only, no
  visualization/route.
* Fixing the pre-existing `enqueue()` `{ attempts: 0, ...message }` override quirk (Edge Cases).

## Flags
* `needs_ba`: true — genuine multi-stakeholder business-rule content (paid vs. free tier
  policy, safer-default-on-missing-field reasoning, operator-facing metrics ask) with real
  branching behavior, not just a data-shape change; Business Rules section above is real, not a
  stub.
* `needs_ui`: false — no new/changed page, route, modal, form, or visible UI state; this is an
  in-memory library with no UI layer anywhere in this codebase.
* `needs_sa`: false — single component, single file (`src/queue.js`), no competing
  architectural approaches with lasting consequences, no explicit NFRs (latency/throughput/
  compliance) named in the idea. The one real design choice here (derive `getMetrics()` from
  arrays vs. maintain running counters) is recorded in Codebase Survey rather than a full
  Solution Architecture section, since it's a single-file, no-alternatives-with-real-trade-offs
  decision, not a 2+-service or NFR-driven one.
* `needs_devops`: false — no env vars, migrations, feature flags, or infra involved; pure
  in-memory data structure change.

## Open Items
* A handler that throws a non-`Error` value (e.g. `throw 'boom'` or `throw { code: 1 }`) would
  make `err.message` `undefined`, so a dropped message's `error` field could be `undefined`
  instead of a string — this would itself trip Runtime Invariant #1 (non-empty `error` string)
  and halt. The existing test suite's one throwing handler (`'boom'`) throws a real `Error`, and
  nothing in this codebase's history suggests handlers throw non-Error values, so this is left
  as a genuine edge case for `implement`/`generate-tests` to decide: either (a) accept the halt
  as correct (a handler throwing a non-Error is itself a bug worth surfacing loudly), or
  (b) coerce with `String(err)` as a fallback when `err.message` is absent. Not resolved here
  because the idea gives no guidance on non-Error throws and either choice is defensible —
  flagging rather than guessing.
