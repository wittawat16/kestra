# [priority-tier] Spec — Tier-based retry policy for the queue

> Status: READY_FOR_BUILD | Created: 2026-07-31 | Next: kestra-build

---

## Overview
Add per-message `tier` (`'paid'`/`'free'`) to the retry queue: paid retries on failure forever
(today's behavior), free drops to a new `dropped` list after exactly one failed attempt. Give
operators per-tier succeeded/dropped counts so they can judge whether the one-shot free policy is
costing a meaningful failure rate.

## Problem Statement
* Today `step()` (`src/queue.js:20-39`) treats every failing message identically: increment
  `attempts`, push to the tail of `pending`, retry forever. There is no `tier` concept and no way to
  cap retries for a subset of traffic.
* Goal: free-tier messages fail at most once and land in an inspectable `dropped` list; paid-tier
  (and un-migrated, tier-less) messages keep today's indefinite-retry guarantee untouched; operators
  can query succeeded/dropped counts per tier.

## Functional Requirements
* [ ] `enqueue()` accepts an optional `tier` field on the message (`'paid'` | `'free'` | absent) —
  no validation/throw on enqueue; resolution happens lazily in `step()`.
* [ ] A single exported `resolveTier(message)` helper is the one place tier logic lives — returns
  `'free'` only when `message.tier === 'free'`, `'paid'` for everything else (absent, `'paid'`, or
  any unrecognized value). Both the retry/drop decision in `step()` and the reporting function in
  the next bullet call this same helper (see Reality Constraints → Paths that must agree).
* [ ] Given a message whose `resolveTier()` is `'paid'` and its handler throws: Given a paid (or
  tier-less) message whose handler throws, When `step()` processes it, Then `attempts` increments
  and the message is pushed to the tail of `pending` — unchanged from today.
* [ ] Given a message whose `resolveTier()` is `'free'` and its handler throws: Given a free-tier
  message whose handler throws, When `step()` processes it, Then the message (with `attempts`
  incremented to `1` and the thrown error recorded) is pushed to `queue.dropped` instead of
  `pending`, and `step()` returns a new `status: 'dropped'` result.
* [ ] Given a message whose `type` has no registered handler, When `step()` processes it, Then it
  returns to the tail of `pending` untouched (`status: 'skipped'`, no `attempts` change, never
  reaches `dropped`) — identical to today, regardless of `tier`.
* [ ] A new exported `getTierStats(queue)` returns
  `{ paid: { succeeded, dropped }, free: { succeeded, dropped } }`, computed from `queue.done` and
  `queue.dropped` via `resolveTier()` — `paid.dropped` is always `0` (structurally: paid never
  drops).
* [ ] `createQueue()` returns `{ pending: [], done: [], dropped: [] }` (adds `dropped` to the
  existing shape).

## Edge Cases & Error States
* **Message with no `tier` field, handler throws:** treated as `'paid'` — retried indefinitely, never
  dropped. This is the explicit safer default from the source idea (avoids silently regressing an
  un-migrated caller to drop-on-failure).
* **Message with an unrecognized `tier` value** (e.g. `'enterprise'`), handler throws: ⚠️ inferred —
  the source idea only specifies `'paid'`, `'free'`, and absent. Resolved here by applying the same
  stated principle ("the safer default") uniformly: any value other than exactly `'free'` resolves
  to `'paid'`. Flagged in Open Items for a quick confirm since it extrapolates beyond the literal
  source text.
* **No handler registered for `type`:** unaffected by tier in every case, including `tier: 'free'` —
  stays in `pending`, untouched, same as today.
* **Free-tier message already in `dropped`:** terminal. No code path reads from `queue.dropped`;
  it is never re-enqueued, never reprocessed, never contributes a second failure (see Runtime
  Invariant 1). Out of scope: resurrecting it (explicit in source idea).
* **`getTierStats()` on a freshly-created, empty queue:** returns
  `{ paid: { succeeded: 0, dropped: 0 }, free: { succeeded: 0, dropped: 0 } }`.
* **Configurable free-tier retry count:** explicitly out of scope (source idea) — always exactly one
  attempt, no knob.

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.
This is a synchronous, single-process, in-memory library with no live supervisor — "halt" here
concretely means: a frozen test asserting the invariant fails and blocks the commit/merge, which is
the only enforcement mechanism this codebase has. Stated honestly rather than inventing a monitoring
layer that doesn't exist.)*

| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| A message resolved as free-tier that fails is moved to `dropped` and never re-enters `pending` (dropped is terminal) | No function in `src/queue.js` reads from `queue.dropped`; a frozen test enqueues a free-tier failure, then calls `step()` repeatedly on an otherwise-idle queue and asserts the dropped message never reappears in `pending` | Halt: the frozen test fails, blocking merge — this is a real regression, not a style nit |
| `step()`'s tier-resolution decision and `getTierStats()`'s tier categorization always agree on any given message's tier | Both call the single exported `resolveTier(message)` helper — no duplicated ternary/ if-else tier logic anywhere else in the file | Halt: a frozen test constructs messages across all three tier inputs (`'paid'`, `'free'`, absent) and asserts `resolveTier()` output matches both where `step()` routed the message and how `getTierStats()` counted it |
| Every message dequeued via `pending.shift()` is filed into exactly one of `pending` / `dropped` / `done` before `step()` returns — never silently discarded | Exhaustive branch coverage in `step()` (skip / success / paid-retry / free-drop) with a frozen test per branch | Halt: a missing or misordered branch fails the corresponding frozen test; a message vanishing with no trace is the specific failure this guards against |

## Business Rules

* **BR-1: Tier default (missing `tier`).**
  ```
  Given a message enqueued with no `tier` field
  When its handler throws
  Then it is treated as 'paid' — attempts incremented, requeued to the tail of pending
  ```
  Counter-example:
  ```
  Given a message enqueued with tier: 'free'
  When its handler throws
  Then it moves to dropped (not requeued), attempts stays at 1, no further retries
  ```

* **BR-2: Free-tier single-attempt guarantee is structural, not a counter.**
  ```
  Given a free-tier message that has already failed once (now in dropped)
  When any later step() call runs
  Then it is never requeued into pending by any code path — dropped is terminal
  ```
  Counter-example:
  ```
  Given a paid-tier message that has failed N times
  When its handler throws again
  Then it retries again — no attempt ceiling (existing behavior, unchanged)
  ```

* **BR-3: The no-handler "skip" path is tier-blind.**
  ```
  Given a message of a type with no registered handler, tier: 'free'
  When step() processes it
  Then it returns to the tail of pending untouched — no attempts increment, no drop
  ```
  Counter-example:
  ```
  Given a message of a registered type, tier: 'free', whose handler throws
  When step() processes it
  Then it drops (BR-1's counter-example) — because this is a handler failure, not a routing gap
  ```

* **BR-4: Unrecognized tier values.** ⚠️ inferred, not explicit in the source idea — see Edge Cases
  and Open Items.
  ```
  Given a message with tier: 'enterprise' (neither 'paid' nor 'free')
  When its handler throws
  Then it is treated as 'paid' (retried, not dropped) — same safer-default principle as BR-1
  ```

* **Stakeholder variations:**
  - **Paid customers** (external, SLA-bound): expect indefinite retry — must see zero behavior
    change from today.
  - **Free-tier customers**: expect at-most-one attempt, no retry SLA.
  - **Un-migrated callers** (internal, haven't added `tier` yet): silently get paid-tier behavior —
    protective default, but also means they don't get free-tier's cost-saving drop policy either;
    that's expected and correct, not a gap.
  - **Operators** (internal, business stakeholder): need `getTierStats()`'s per-tier
    succeeded/dropped breakdown to judge whether free tier's one-shot policy is costing a meaningful
    failure rate — this is the reporting requirement, not just an internal debugging aid.

## Codebase Survey
* Explored: `fixture/CLAUDE.md`, `fixture/src/queue.js` (full file, 39 lines), `fixture/test/queue.test.js` (full file, 21 lines), `fixture/package.json`.
* Integrate with:
  - `createQueue()` (`src/queue.js:10-12`) — extend returned shape to add `dropped: []`.
  - `step()` (`src/queue.js:20-39`) — extend the `catch` branch (`src/queue.js:34-38`) to branch on
    `resolveTier(message)`; success/skip branches untouched except that success should still be
    counted correctly by `getTierStats()` via `queue.done` (no change needed there beyond what
    `resolveTier` already computes on read).
  - New exports `resolveTier(message)` and `getTierStats(queue)`, following the file's existing
    "named exports, no default exports" convention (per `CLAUDE.md`).
  - Test file: `test/queue.test.js` mirrors `src/queue.js` 1:1 per `CLAUDE.md` convention — no new
    test file; extend this one with the new scenarios.
* New dependencies: none — `CLAUDE.md` mandates zero third-party dependencies; this feature needs
  none (pure logic + a new array field).
* Implementation note (left to `meta-dev`, not elevated to a Solution Architecture section since
  it's a single-function-level choice, not a multi-component or NFR-driven decision): `getTierStats`
  can either scan `done`/`dropped` on every call or maintain incremental counters updated inside
  `step()`. Recommend on-demand scan for simplicity, consistent with the codebase's stated
  minimalism (`CLAUDE.md`: "no third-party dependencies, keep it that way") and because in-memory
  queue sizes here are small — either approach satisfies every AC below.
* Risks: `createQueue()`'s returned object shape changes (`{pending, done}` → `{pending, done,
  dropped}`) — additive, but any external caller that enumerates its keys assuming exactly two would
  need to tolerate the new one; no such caller exists in this repo. The pre-existing async-handler
  gap (`handler(message.payload)` on `src/queue.js:31` is not awaited, so a handler returning a
  rejected Promise is not caught) is unchanged by this feature but applies identically to both tiers
  — worth flagging so free tier's "one attempt" framing isn't mistaken for a stronger completion
  guarantee than the codebase actually provides.

## Reality Constraints

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|-----------------------------------|-------------------------|
| Caller-supplied handler function (via `registerHandler(type, fn)`) | None — called synchronously once per `step()`, on whatever message is at the head of `pending` for that call | `fn(payload)` — no declared return type; a throw is the only signal `step()` currently interprets | Synchronous completion: `step()` (`src/queue.js:31`) calls `handler(message.payload)` without `await`; a handler that returns a rejected Promise instead of throwing synchronously is **not** caught, and the message is incorrectly pushed to `done`. This is a pre-existing gap (verified by reading the code), not introduced by this feature, but it applies to both tiers identically — free tier's "single attempt" claim only covers synchronous throws, same limit paid tier already lived with |

### Paths that must agree
* `step()`'s tier-resolution branch (decides `pending` vs `dropped` placement on failure) ↔
  `getTierStats()`'s tier categorization (used for operator reporting) — equivalent means: both must
  classify the exact same message into the exact same tier bucket for any given `tier` input value.
  May differ: nothing — a mismatch would make the reported stats lie about what actually happened to
  a message. Enforced by routing both through the single exported `resolveTier()` helper (see
  Runtime Invariant 2) rather than duplicating the paid/free ternary in two places.

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-------------------------------|-----|
| Clock | N/A — not read | `src/queue.js` has no timestamp/date logic anywhere, today or after this change |
| Randomness | N/A — not read | no RNG anywhere in the file |
| Timezone / locale | N/A — not read | no date/locale-sensitive formatting |
| Network | N/A — not read | pure in-memory synchronous data structure, verified by reading the full file |
| Filesystem | N/A — not read | no fs calls |
| Env vars | N/A — not read | no `process.env` reads in `src/queue.js` |

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| fixture/src/queue.js | edit | exists (read in full, 39 lines) | add `resolveTier`, `getTierStats`, `dropped` list, tier-aware branch in `step()` |
| fixture/test/queue.test.js | edit | exists (read in full, 21 lines) | add tests for BR-1–BR-4, all Runtime Invariants, all ACs below |

## Dependencies
* New packages: none (`CLAUDE.md` mandates zero third-party dependencies).
* Schema changes: none persisted — the in-memory `queue` object gains a `dropped: []` array field
  returned by `createQueue()`; no migration, nothing serialized to disk in this repo.

## Acceptance Criteria
* [ ] Given a paid-tier message whose handler throws, When `step()` runs it, Then `status: 'retry'`,
  `attempts === 1`, and the message is at the tail of `pending` — unchanged from today. Verified by:
  `npm test` (existing test "retries a throwing handler" already covers the pre-feature case; extend
  with an explicit `tier: 'paid'` variant).
* [ ] Given a free-tier message whose handler throws, When `step()` runs it, Then `status:
  'dropped'`, the message is in `queue.dropped` with `attempts === 1`, and it is absent from
  `queue.pending`.
* [ ] Given a tier-less message whose handler throws, When `step()` runs it, Then behavior is
  identical to the paid-tier AC above (same status/attempts/pending placement).
* [ ] Given a message with `tier: 'enterprise'` whose handler throws, When `step()` runs it, Then it
  is treated as paid (retried, not dropped) — ⚠️ inferred, see Open Items.
* [ ] Given a message of a `type` with no registered handler and `tier: 'free'`, When `step()` runs
  it, Then `status: 'skipped'`, it returns untouched to the tail of `pending`, `attempts` unchanged,
  and it never appears in `dropped`.
* [ ] Given a free-tier message already in `dropped`, When `step()` is called repeatedly on the
  otherwise-idle queue, Then the dropped message never reappears in `pending` and is never
  reprocessed.
* [ ] Given a freshly-created, empty queue, When `getTierStats(queue)` is called, Then it returns
  `{ paid: { succeeded: 0, dropped: 0 }, free: { succeeded: 0, dropped: 0 } }`.
* [ ] Given a mix of paid and free messages that succeed and fail across multiple `step()` calls,
  When `getTierStats(queue)` is called, Then the returned counts exactly match the real outcomes in
  `queue.done`/`queue.dropped`, and `paid.dropped === 0` always.
* [ ] `npm test` (`node --test test/*.test.js`) exits 0 with every new and existing test passing.
  Verified now as the pre-feature baseline: `$ npm test` → 2/2 passing (`runs a registered handler`,
  `retries a throwing handler`), exit 0 — run in `fixture/` on 2026-07-31, confirming the starting
  point this feature builds on.

## AC Coverage Map
| AC | Covered by (files/steps) |
|----|---------------------------|
| Paid-tier retry unchanged | `src/queue.js` `step()` catch branch (paid path) · `test/queue.test.js` |
| Free-tier drop on failure | `src/queue.js` `step()` catch branch (free path) + `dropped` list · `test/queue.test.js` |
| Tier-less message == paid | `src/queue.js` `resolveTier()` default · `test/queue.test.js` |
| Unrecognized tier == paid (⚠️ inferred) | `src/queue.js` `resolveTier()` fallback · `test/queue.test.js` |
| No-handler skip is tier-blind | `src/queue.js` `step()` skip branch (unchanged) · `test/queue.test.js` |
| Dropped is terminal | `src/queue.js` (absence of any `dropped`-reading path) · `test/queue.test.js` (repeated-`step()` assertion) |
| `getTierStats()` on empty queue | `src/queue.js` `getTierStats()` · `test/queue.test.js` |
| `getTierStats()` matches real outcomes | `src/queue.js` `getTierStats()` + `resolveTier()` · `test/queue.test.js` |
| `npm test` exits 0 | `fixture/` `npm test` (baseline verified 2026-07-31; re-run after implementation) |

## Risks & Watch-outs
* `createQueue()`'s object shape gains a third key (`dropped`) — additive only; no existing caller
  in this repo enumerates the shape's keys, verified by reading both `src/queue.js` and
  `test/queue.test.js` in full.
* Pre-existing async-handler-rejection gap (`src/queue.js:31`, `handler()` not awaited) is unchanged
  by this feature and applies identically to both tiers — see Reality Constraints → External
  dependencies. Not this feature's bug to fix, but worth a one-line mention in code review so it
  isn't mistaken for something this feature was supposed to close.
* `resolveTier()` must stay the single place tier logic lives — a future edit that inlines a second
  paid/free check elsewhere would silently reopen the "paths that must agree" gap (Runtime Invariant
  2). Worth a comment-free but structurally obvious single-call-site pattern, not a prose warning
  buried in a comment.

## Out of Scope
* Configurable number of free-tier retry attempts — always exactly one, no config knob (explicit in
  source idea).
* Resurrecting dropped messages back into `pending` — dropped is permanently terminal (explicit in
  source idea).
* Fixing the pre-existing async-handler (unawaited Promise) gap — real, verified, but predates this
  feature and affects both tiers identically; not part of this change's scope.
* Persisting/serializing `dropped` (or any queue state) to disk — this remains a pure in-memory
  library, unchanged.

## Flags
* `needs_ba`: true — genuine multi-stakeholder business rules (paid vs. free vs. un-migrated-caller
  behavior, operator reporting need); see Business Rules section above.
* `needs_ui`: false — no page, route, modal, form, or interactive element; this is a backend
  in-memory library with no UI surface.
* `needs_sa`: false — single component (one file, one in-process data structure), no competing
  architectural approaches with lasting consequences, no explicit NFRs stated by the source idea.
  The one implementation choice (scan-on-demand vs. incremental counters for `getTierStats`) is
  function-level, not architectural, and is left as a recommendation in Codebase Survey rather than
  a full Solution Architecture section.
* `needs_devops`: false — no env vars, no migrations, no feature flags, no infra; a plain library
  change with `npm test` as its only "deploy" gate.

## Open Items
* ⚠️ BR-4 / unrecognized `tier` values (e.g. `'enterprise'`) are not explicitly addressed by the
  source idea — only `'paid'`, `'free'`, and absent are. This spec resolves it by extending the
  idea's own stated "safer default" principle to any non-`'free'` value, but that's an extrapolation
  beyond the literal source text and worth a quick confirm with whoever owns the tier taxonomy
  before this hardens into frozen tests.
