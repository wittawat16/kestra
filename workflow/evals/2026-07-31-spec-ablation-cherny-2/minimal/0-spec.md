# [priority-tier] Spec — Tier-Based Retry Policy for Queue

> Status: READY_FOR_BUILD | Created: 2026-07-31 | Next: kestra-build

---

## Overview
Add `paid`/`free` message tiers to the retry queue: paid retries forever (today's behavior), free drops after its one attempt into a new `dropped` list, so operators can see per-tier success/drop rates.

## Problem Statement
* Today `step()` treats every message identically: handler throws → `attempts++` → back to tail of `pending`, forever. No concept of tier, no terminal failure state, no per-tier visibility.
* Goal: free-tier messages get exactly one attempt and a visible terminal failure state (`dropped`); paid-tier (including untagged/legacy messages) keeps unlimited retries; operators can query succeeded-vs-dropped counts per tier.

## Functional Requirements
* [ ] `createQueue()` returns `{ pending: [], done: [], dropped: [] }` — adds `dropped` alongside the two existing arrays.
* [ ] `enqueue(queue, message)` normalizes tier: stored `message.tier` is `'free'` only when the input's `tier` is strictly `'free'`; every other value (missing, `undefined`, `null`, any other string) normalizes to `'paid'`.
* [ ] Given a paid-tier message (explicit or defaulted), When its handler throws, Then `step()` increments `attempts`, pushes the message to the tail of `pending`, and returns `{ status: 'retry', id, attempts }` — byte-identical to current behavior.
* [ ] Given a free-tier message, When its handler throws, Then `step()` sets `message.error` (the thrown value's `.message` if it's an `Error`, else `String(err)`), pushes the message to `queue.dropped` (never `pending`), and returns `{ status: 'dropped', id, attempts: 1 }`.
* [ ] Given any message of either tier whose `type` has no registered handler, When `step()` runs, Then the message returns unchanged to the tail of `pending` and `{ status: 'skipped', id }` is returned — tier is never consulted on this path.
* [ ] `getStats(queue)` returns `{ paid: { succeeded: N, dropped: N }, free: { succeeded: N, dropped: N } }`, computed by scanning `queue.done` and `queue.dropped` and tallying by each message's `tier` at call time (not an incrementally-maintained counter).
* [ ] A single choke-point function (`pushDropped` or equivalent) is the only code path that appends to `queue.dropped`; `step()`'s free-tier-failure branch calls it rather than pushing directly (see Runtime Invariants — this is what the two guard rows are checked inside).

## Edge Cases & Error States
* **Malformed/unknown tier value (`tier: 'gold'`, `tier: 123`, `tier: ''`):** normalizes to `'paid'` — same rule as missing tier, per the strict `=== 'free'` check in `enqueue`.
* **Free-tier message, no registered handler for its `type`:** stays in `pending` (skip path) — not dropped. The one-attempt clock starts only when a handler actually runs and throws, never on skip.
* **Free-tier message whose handler succeeds:** goes to `done`, identical to paid — tier only changes the *failure* path.
* **Handler throws a non-`Error` value** (`throw 'boom'`, `throw undefined`, `throw 42`): `message.error` must still end up a defined string (`String(err)` fallback) — must not throw inside the drop path itself.
* **`step()` on an empty `pending`:** `{ status: 'idle' }`, unaffected by any tier logic — unchanged from today.
* **Direct external mutation of `queue.dropped`/`queue.pending`** (caller pushes into the array without going through `enqueue`/`step`): the invariant guard below cannot see this — see Runtime Invariants footnote and Risks.

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| `queue.dropped` never contains a paid-tier message | the choke-point `pushDropped(queue, message)` function re-derives tier independently (`message.tier === 'free'`) and checks it *before* pushing — not trusting the branch that called it | throws `Error` synchronously, propagating out of `step()` — halts the caller's `step()` call, nothing is pushed |
| A message entering `dropped` carries exactly one recorded failure: `attempts === 1` and a non-empty `message.error` string | same `pushDropped` choke point, second check, right after the tier check | throws `Error` synchronously — halts the caller's `step()` call. Catches the out-of-scope case of a dropped message being fed back into `pending` and failing again (attempts would be ≥2) |

**Known limitation, stated not silently assumed:** both guards fire only for messages routed through `step()` → `pushDropped()`. `queue.pending`/`done`/`dropped` are plain public arrays with no encapsulation (confirmed in `src/queue.js` — `createQueue()` returns a raw object; nothing in this codebase prevents `queue.dropped.push(anything)` directly). A caller bypassing `step()` entirely defeats both guards. This is a pre-existing architectural property of the codebase, not a gap introduced by this feature — flagged here rather than left implicit (see Risks & Watch-outs).

## Business Rules

* **BR-1: Paid-tier failure retries indefinitely (unchanged from today).**
  Given a paid-tier message (`tier: 'paid'`, `attempts: 0`) enqueued, When its handler throws, Then `attempts` becomes 1 and the message returns to the tail of `pending`, eligible for another `step()` — repeats without limit on repeated failure.
  Counter-example: Given a free-tier message under the same failure, Then it does *not* return to `pending` — it moves to `dropped` instead (BR-2).

* **BR-2: Free-tier failure is terminal after exactly one attempt.**
  Given a free-tier message (`tier: 'free'`, `attempts: 0`) enqueued, When its handler throws on the first `step()` that processes it, Then the message moves to `dropped` with `attempts: 1` and an `error` field recording the failure — it is never processed again (no config knob to allow more attempts; see Out of Scope).
  Counter-example: Given a free-tier message whose handler *succeeds* on that same first attempt, Then it goes to `done` exactly like a paid message — free tier changes only the failure path, never the success path.

* **BR-3: Missing or unrecognized tier defaults to `'paid'` — the safer default.**
  Given a message enqueued with no `tier` field (an un-migrated caller), When `enqueue()` runs, Then the stored tier is `'paid'` — full unlimited-retry behavior applies on failure, so an un-migrated caller's messages are never silently downgraded to free's drop-on-failure policy.
  Counter-example: Given a message enqueued with `tier: 'free'` explicitly, Then it stays `'free'` — omission defaults to paid, but an explicit `'free'` is always honored, never silently upgraded to paid.

* **BR-4: The no-handler ("skip") path ignores tier entirely.**
  Given any message (paid or free) whose `type` has no registered handler, When `step()` runs, Then the message returns to the tail of `pending` unchanged, `{ status: 'skipped', id }` — identical to pre-feature behavior, no tier check performed.
  Counter-example: a free-tier message with no handler is *not* dropped — skip is not a failure; if a handler for that `type` is registered later, the message still gets its one real attempt then.

* Stakeholder variations:
  * Paid customers — SLA: eventual delivery guaranteed (unlimited retries), unchanged by this feature.
  * Free customers — SLA: none stated beyond one attempt; failure is terminal, not silently retried.
  * Operators — need `getStats()`'s per-tier `succeeded`/`dropped` counts to judge whether free tier's one-shot policy is costing a meaningful failure rate (the idea's stated motivation for this whole feature).
  * Un-migrated callers (no `tier` field yet) — must get paid-tier behavior by default; the regression this rule exists to prevent is a caller silently losing retry coverage because it hasn't been updated to send `tier` yet.

## Codebase Survey
* Explored: `fixture/CLAUDE.md` (conventions: plain ESM, no build step, no TypeScript, `node --test`, no third-party deps, named exports only, `src/x.js` ↔ `test/x.test.js`), `fixture/src/queue.js` (full file, 40 lines — `registerHandler`, `createQueue`, `enqueue`, `step`), `fixture/test/queue.test.js` (2 existing tests), `fixture/package.json` (`"test": "node --test test/*.test.js"`).
* Ran `npm test` in `fixture/` as baseline before writing anything: exit 0, `node v24.15.0`, 2/2 pass (`runs a registered handler`, `retries a throwing handler`) — pasted output below under Reality Constraints verification.
* Integrate with: extend `src/queue.js` in place (no new files — codebase is a single-module library); follow existing named-export convention exactly; add tests to the existing `test/queue.test.js` file, following its existing `test(...)`/`assert` style (Node's built-in `node:test` + `node:assert/strict`, no test framework dependency).
* Current `enqueue`: `queue.pending.push({ attempts: 0, ...message })` — attempts defaults to 0 but is overridable by a caller-supplied `attempts` in `message`; this feature's tier normalization must compose with that (spread first, tier field forced last so it always wins over whatever the caller passed).
* Current `step`'s catch branch: `message.attempts += 1; queue.pending.push(message); return { status: 'retry', ... }` — this is exactly BR-1's paid path; the free path is a new branch alongside it, not a replacement.

## Reality Constraints
*(what the world outside this feature actually does — verified by running/reading, not assumed.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|-----------------------------------|-------------------------|
| Caller-supplied handler fn (registered via `registerHandler(type, fn)`) | must be registered before `step()` processes a message of that `type`, else skip path; called synchronously with `handler(message.payload)`, no timeout | no return value used by `step()` (return is ignored); on success nothing else happens, on failure it may `throw` any JS value, not necessarily an `Error` instance | idempotency on retry, absence of side effects on partial/failed execution, that it throws an `Error` instance (could throw a string/number/undefined), that it completes quickly (no timeout enforced), that `payload` is JSON-serializable |
| Node's built-in `node:test` runner (`npm test` → `node --test test/*.test.js`) | none beyond Node ≥ the version shipping `node:test` (confirmed present: `node v24.15.0`) | test/assert APIs per Node docs | no parallelism guarantee across files affecting shared module-level state (`HANDLERS` map in `queue.js` is module-scoped and shared across tests in the same file — existing tests already rely on unique `type` strings per test to avoid collision; new tests must follow the same pattern) |

### Paths that must agree
* None — single execution path. `step()` is the only function that dequeues a message and applies the retry/drop decision; there is no separate replay/cache/async path in this codebase for this feature to keep in sync with.

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|------------------------------|-----|
| Clock | not touched | `queue.js` reads no timestamp anywhere (confirmed by reading the full 40-line file) — this feature adds none either |
| Randomness | not touched | no RNG use in `queue.js` or in this feature's added logic |
| Network / filesystem | not touched | in-memory only, zero I/O in `queue.js`; CLAUDE.md mandates zero third-party deps |
| Env vars | not touched | no `process.env` read anywhere in `queue.js` |
| Handler execution order across messages of different tiers | floating by design | `step()` is caller-driven (pull one message per call); the caller decides call cadence — this feature does not introduce any ordering guarantee between tiers, only within a single message's own lifecycle |

**Verification run (baseline, before implementation):**
```
$ node --version
v24.15.0
$ npm test
> queue-worker@0.1.0 test
> node --test test/*.test.js

✔ runs a registered handler (0.537667ms)
✔ retries a throwing handler (0.067541ms)
ℹ tests 2
ℹ pass 2
ℹ fail 0
```

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `src/queue.js` | edit | exists (read in full, 40 lines) | add `dropped: []` to `createQueue`; tier normalization in `enqueue`; `pushDropped` choke-point with the two invariant guards; free-tier branch in `step`'s catch clause; new `getStats` export |
| `test/queue.test.js` | edit | exists (read in full, 21 lines) | add tests for: free-tier drop-on-failure, paid-default-on-missing-tier, malformed-tier-defaults-to-paid, no-handler-skip-ignores-tier, `getStats` counts, both invariant-guard throws |

## Dependencies
* None — CLAUDE.md mandates zero third-party dependencies; nothing here needs one (pure control flow + array pushes).

## Acceptance Criteria
* [ ] `createQueue()` → returns object with `pending`, `done`, and `dropped`, each `[]`.
* [ ] Given `enqueue(q, { id: 1, type: 't', payload: null, tier: 'paid' })`, the stored message has `tier === 'paid'`.
* [ ] Given `enqueue(q, { id: 2, type: 't', payload: null, tier: 'free' })`, the stored message has `tier === 'free'`.
* [ ] Given `enqueue(q, { id: 3, type: 't', payload: null })` (no `tier` key at all), the stored message has `tier === 'paid'`.
* [ ] Given `enqueue(q, { id: 4, type: 't', payload: null, tier: 'gold' })`, the stored message has `tier === 'paid'`.
* [ ] Given a paid-tier message whose handler throws, When `step(q)` runs, Then `attempts === 1`, the message is at the tail of `q.pending`, and `q.dropped.length === 0`, and the return is `{ status: 'retry', id, attempts: 1 }`.
* [ ] Given a free-tier message whose handler throws, When `step(q)` runs, Then `q.pending` does not contain it, `q.dropped` contains it with `attempts === 1` and a defined non-empty `error` string, and the return is `{ status: 'dropped', id, attempts: 1 }`.
* [ ] Given a free-tier message whose handler throws a non-`Error` value (e.g. `throw 'boom'`), Then `message.error === 'boom'` (via `String(err)` fallback) and no exception escapes `step()` itself.
* [ ] Given a free-tier message with no registered handler for its `type`, When `step(q)` runs, Then it returns to the tail of `q.pending` unchanged, `q.dropped.length === 0`, return is `{ status: 'skipped', id }`.
* [ ] Given a queue with 2 paid `done`, 1 free `done`, 1 free `dropped`, `getStats(q)` returns `{ paid: { succeeded: 2, dropped: 0 }, free: { succeeded: 1, dropped: 1 } }`.
* [ ] Calling the internal drop choke-point directly with a paid-tier message throws synchronously (invariant guard row 1).
* [ ] Calling the internal drop choke-point directly with a free-tier message whose `attempts !== 1` throws synchronously (invariant guard row 2).
* [ ] The two pre-existing tests in `test/queue.test.js` (`runs a registered handler`, `retries a throwing handler`) still pass unmodified — no regression on paid/default-tier behavior.

## AC Coverage Map
| AC | Covered by (files/steps) |
|----|---------------------------|
| `createQueue()` includes `dropped: []` | `src/queue.js::createQueue`; test: new assertion on `createQueue()` shape |
| Explicit `tier: 'paid'` stored as-is | `src/queue.js::enqueue`; test: new enqueue-normalization test |
| Explicit `tier: 'free'` stored as-is | `src/queue.js::enqueue`; test: new enqueue-normalization test |
| Missing `tier` defaults to `'paid'` (BR-3) | `src/queue.js::enqueue`; test: new default-tier test |
| Malformed `tier` defaults to `'paid'` | `src/queue.js::enqueue`; test: new malformed-tier test |
| Paid failure retries (BR-1) | `src/queue.js::step` catch branch; existing test `retries a throwing handler` + new paid-specific assertion |
| Free failure drops with single error record (BR-2) | `src/queue.js::step` catch branch + `pushDropped`; new test |
| Non-`Error` throw handled on drop path | `src/queue.js::pushDropped` / `step`; new test |
| No-handler skip ignores tier (BR-4) | `src/queue.js::step` skip branch; new test |
| `getStats` per-tier counts | `src/queue.js::getStats`; new test |
| Invariant: dropped never holds paid | `src/queue.js::pushDropped`; new invariant test |
| Invariant: dropped entry has single failure record | `src/queue.js::pushDropped`; new invariant test |
| No regression on existing 2 tests | `test/queue.test.js` (unmodified) — re-run as part of `npm test` |

## Risks & Watch-outs
* `queue.pending`/`done`/`dropped` are plain public arrays, not encapsulated — the two invariant guards only protect the `step()`/`pushDropped()` code path; a caller mutating `queue.dropped` directly bypasses them entirely. Pre-existing architectural property of this codebase, not introduced by this feature (see Runtime Invariants footnote).
* `getStats()` rescans `done` + `dropped` on every call (O(n), no incremental counters) — fine at this codebase's scale; would need revisiting if the queue ever grows large or `getStats` is called in a hot loop. Not a problem for the stated use case (operator queries counts periodically).
* Module-scoped `HANDLERS` map in `queue.js` is shared across all tests in the same test file/process — new tests must use unique `type` strings (as existing tests already do: `'email'`, `'boom'`) to avoid cross-test handler collisions.

## Out of Scope
* Configurable retry count for free tier — it is exactly one attempt, no config knob (explicit in the idea).
* Resurrecting dropped messages back into `pending` — no API for this; the invariant guard (row 2) actively rejects a free-tier message re-entering the drop path with `attempts !== 1`, which is what a resurrection-then-refail would produce.
* Encapsulating `queue.pending`/`done`/`dropped` behind accessor methods to make the invariant guards unbypassable — pre-existing architecture, not this feature's job (flagged under Risks, not fixed here).
* Per-tier `pending`/in-flight counts in `getStats()` — the idea asks only for succeeded vs. dropped.

## Flags
* `needs_ba`: true — real multi-stakeholder business-rule content (paid vs. free SLA, safe-default for un-migrated callers, tier-independence of the skip path); BR-1..BR-4 done inline above, each with example + counter-example.
* `needs_ui`: false — no UI; this is a library, no page/route/modal/form/visible-state change.
* `needs_sa`: false — single component (one file, `src/queue.js`), no competing architectural approaches with lasting consequences, no explicit NFRs stated by the idea.
* `needs_devops`: false — no env vars, no migrations, no feature flags, no infra; purely in-memory data structure with no persistence layer.

## Open Items
* None — every requirement in the idea resolved to a concrete, verified rule above; both out-of-scope items explicitly named by the idea are captured; the one real architectural gap (public, unencapsulated arrays) is disclosed under Runtime Invariants/Risks rather than hidden or silently "fixed" out of scope.
