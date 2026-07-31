# [queue-cap] Spec — Cap the retry queue's pending size

> Status: READY_FOR_BUILD | Created: 2026-07-31 | Next: kestra-build

---

## Overview
Bound `pending`'s growth via `enqueue()` with a configurable `maxQueueSize`; reject over-cap enqueues visibly; never block `step()`'s retry/skip re-entry.

## Problem Statement
* `enqueue(queue, message)` (`src/queue.js:14-16`) pushes unconditionally — no size limit, no rejection signal, no return value at all.
* Goal: `pending` never grows past `maxQueueSize` via `enqueue()`; a rejected caller can tell; retry/skip re-entry from `step()` is never gated by the cap; operators can read a rejection count off the queue.

## Functional Requirements
* [ ] `createQueue(options)` accepts optional `{ maxQueueSize }`; when omitted/undefined, cap is disabled (unlimited, current behavior preserved).
* [ ] `createQueue()` initializes `queue.maxQueueSize` (from options, or `undefined` if not given) and `queue.rejectedCount = 0`.
* [ ] `enqueue(queue, message)`: Given `queue.maxQueueSize` is a number and `queue.pending.length >= queue.maxQueueSize`, When called, Then it does not push, increments `queue.rejectedCount` by 1, and returns `{ status: 'rejected' }`.
* [ ] `enqueue(queue, message)`: Given `queue.maxQueueSize` is undefined, or `queue.pending.length < queue.maxQueueSize`, When called, Then it pushes `{ attempts: 0, ...message }` onto `pending` as today and returns `{ status: 'enqueued' }`.
* [ ] `step(queue)`'s retry re-entry (`src/queue.js:35-36`) and skip re-entry (`src/queue.js:26`) push directly onto `queue.pending` — never call `enqueue()`, never check `maxQueueSize`, regardless of `pending.length` at the time of the push.
* [ ] `queue.rejectedCount` is readable directly off the queue object returned by `createQueue()` — no new getter/accessor needed (matches existing plain-object style of `queue.pending`/`queue.done`).

## Edge Cases & Error States
* **`enqueue()` at `pending.length === maxQueueSize - 1`:** accepted, `pending.length` becomes `maxQueueSize`.
* **`enqueue()` at `pending.length === maxQueueSize`:** rejected, `pending` unchanged, `rejectedCount` +1.
* **`maxQueueSize: 0`:** every `enqueue()` call is rejected (queue is immediately "full"); `pending` never grows via `enqueue()`. Sharp JS trap: `0` is falsy, so a check written as `if (queue.maxQueueSize)` instead of `if (queue.maxQueueSize !== undefined)` would silently treat cap-0 as "no cap" — must use an explicit `undefined` check.
* **`maxQueueSize` omitted (`createQueue()` or `createQueue({})`):** uncapped — every existing/new `enqueue()` call succeeds, matching current behavior exactly (both existing tests in `test/queue.test.js` must keep passing unmodified).
* **`step()` retry re-entry while `pending` was at cap before `step()` was called:** message is shifted (pending drops to `maxQueueSize - 1`), handler throws, `attempts` increments, message is pushed back (pending returns to `maxQueueSize`) — never rejected, `rejectedCount` unchanged.
* **`step()` skip re-entry (no handler registered) while `pending` was at cap before `step()` was called:** same shift-then-unconditional-push shape as retry; never rejected, `rejectedCount` unchanged.
* **`step()` on empty `pending`:** unaffected by any of the above — still returns `{ status: 'idle' }`.
* **Concurrency:** none — single-threaded synchronous JS, no `async`/`await` anywhere in `queue.js`; a `step()` call's shift-then-push is atomic with respect to any other queue mutation (nothing else can run in between).

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| `pending.length` never exceeds `maxQueueSize` as a result of an `enqueue()` call | `enqueue()` checks `pending.length >= maxQueueSize` *before* mutating `pending`, on every call where `maxQueueSize` is a number | **refuse** — `enqueue()` returns `{status:'rejected'}` and increments `rejectedCount` without touching `pending`; caller finds out synchronously via the return value |
| `step()`'s retry/skip re-entry into `pending` is never subject to `maxQueueSize`, even when `pending.length === maxQueueSize` immediately before `step()` runs | No live runtime check exists for this one — see note | **alert via test suite only**: a dropped retry/skip message produces no error at runtime (silent data loss), so there is no production-time detection point for it in a module this small. Enforcement is structural (the two push-backs in `step()` are direct `queue.pending.push(message)` calls that never route through `enqueue()`) plus a frozen regression test that fills `pending` to `maxQueueSize`, calls `step()` on a throwing/unregistered-type message, and asserts `pending.length` is unchanged and `rejectedCount` is unchanged. Any future edit touching either push site in `step()` must keep this test green — that test *is* the enforcement mechanism, there is nothing else watching this at runtime. |

## Codebase Survey
* Explored: `fixture/CLAUDE.md`, `fixture/src/queue.js` (full file, 39 lines), `fixture/test/queue.test.js` (full file, 20 lines), `fixture/package.json`. Ran `npm test` — baseline: 2 passing, 0 failing, exit 0.
* Integrate with: named-exports-only convention (no default exports), plain-object queue shape (`{pending, done}` → extend, don't wrap), Node's built-in `node --test` runner (no third-party test framework), test file mirrors source filename (`src/queue.js` → `test/queue.test.js`, add cases there rather than a new file).

## Reality Constraints
*(what the world outside this feature actually does — verified by running/reading, not assumed.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| none | N/A — `queue.js` is pure in-memory JS, zero imports beyond its own module; `CLAUDE.md` mandates "No third-party dependencies; keep it that way" | N/A | N/A |

### Paths that must agree
* none — single synchronous code path through `enqueue()`/`step()`; no cache/computed pair, no replay/live pair, nothing to keep in sync.

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| clock | N/A — not read | no timestamps anywhere in `queue.js` or this feature |
| randomness | N/A — not read | no RNG use |
| network | N/A — not read | in-memory only |
| filesystem | N/A — not read | in-memory only |
| env | N/A — not read | `maxQueueSize` is a function parameter, not an env var (no `needs_devops`) |

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| src/queue.js | edit | exists (read, 39 lines) | add `maxQueueSize`/`rejectedCount` to `createQueue`; add cap-check + return value to `enqueue`; no code change needed to `step()`'s two push sites, but they must **not** be refactored to route through `enqueue()` (see Risks) |
| test/queue.test.js | edit | exists (read, 20 lines) | add cap-acceptance, cap-rejection, cap-0, uncapped-backward-compat, retry-re-entry-at-cap, and skip-re-entry-at-cap cases, following existing `test()`/`assert` style |

## Dependencies
* none — no new packages; `CLAUDE.md` forbids third-party dependencies.

## Acceptance Criteria
* [ ] AC1 — Given `createQueue({ maxQueueSize: 2 })` with `pending.length === 2` (two prior successful `enqueue()` calls), When `enqueue(queue, {id:3, type:'x', payload:null})` is called, Then it returns `{status:'rejected'}`, `pending.length` stays 2, and `rejectedCount` goes from 0 to 1.
* [ ] AC2 — Given `createQueue({ maxQueueSize: 2 })` with `pending.length === 1`, When `enqueue(queue, {id:2, type:'x', payload:null})` is called, Then it returns `{status:'enqueued'}` and `pending.length` becomes 2.
* [ ] AC3 — Given `createQueue({ maxQueueSize: 1 })`, one message enqueued whose `type` has a throwing handler (pending at cap), When `step(queue)` is called, Then `step()` returns `{status:'retry', attempts:1, ...}`, `pending.length` is 1 afterward, and `rejectedCount` stays 0.
* [ ] AC4 — Given `createQueue({ maxQueueSize: 1 })`, one message enqueued whose `type` has no registered handler (pending at cap), When `step(queue)` is called, Then `step()` returns `{status:'skipped', ...}`, `pending.length` is 1 afterward, and `rejectedCount` stays 0.
* [ ] AC5 — Given `createQueue()` (no options) or `createQueue({})`, When `enqueue()` is called any number of times, Then every call returns `{status:'enqueued'}` and none are ever rejected — existing tests ("runs a registered handler", "retries a throwing handler") keep passing unmodified.
* [ ] AC6 — Given `createQueue({ maxQueueSize: 0 })`, When `enqueue(queue, {id:1, type:'x', payload:null})` is called, Then it returns `{status:'rejected'}`, `pending` stays empty (length 0), and `rejectedCount` becomes 1.
* [ ] AC7 — Given a queue with `rejectedCount` at some value N (from prior rejections), When M further `enqueue()` calls are rejected, Then `rejectedCount` reads exactly N+M directly off the queue object (no separate accessor call needed).

## AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| AC1 | src/queue.js `enqueue()` cap-check branch; test/queue.test.js new "rejects enqueue at cap" case |
| AC2 | src/queue.js `enqueue()` accept branch; test/queue.test.js new "accepts enqueue below cap" case |
| AC3 | src/queue.js `step()` retry push (unchanged, direct push); test/queue.test.js new "retry re-entry bypasses cap" case |
| AC4 | src/queue.js `step()` skip push (unchanged, direct push); test/queue.test.js new "skip re-entry bypasses cap" case |
| AC5 | src/queue.js `createQueue()` default (`maxQueueSize` undefined); test/queue.test.js — existing 2 tests run unmodified + new "uncapped by default" case |
| AC6 | src/queue.js `enqueue()` cap-check with `maxQueueSize: 0`, using `!== undefined` comparison (not truthy check); test/queue.test.js new "maxQueueSize 0 rejects immediately" case |
| AC7 | src/queue.js `queue.rejectedCount` field; test/queue.test.js new "rejectedCount accumulates" case |

## Risks & Watch-outs
* **Falsy-zero trap:** `maxQueueSize: 0` is a valid, meaningful config (immediately-full queue). The cap check must compare `queue.maxQueueSize !== undefined` (or `typeof === 'number'`), never a plain truthy check (`if (queue.maxQueueSize)`), or cap-0 silently becomes "uncapped." Directly covered by AC6.
* **Do-not-unify trap:** `step()`'s retry/skip push-backs must stay as direct `queue.pending.push(message)` calls. Routing them through `enqueue()` for "DRY" breaks two things at once: (1) it re-subjects them to the cap check, violating the retry-exemption invariant, and (2) `enqueue()` always does `{ attempts: 0, ...message }` — reusing it would silently reset a retried message's `attempts` back to 0 every time, a correctness bug independent of the cap. `review` should specifically check these two push sites weren't touched or, if touched, still bypass `enqueue()`.
* **No runtime alert for the retry-exemption invariant** (see Runtime Invariants table) — this is a genuine gap for a codebase this small, not an oversight; flagged so `review`/`test-review` treat the frozen regression test as load-bearing rather than incidental.

## Out of Scope
* Resizing `maxQueueSize` at runtime (no setter/mutator provided; only settable via `createQueue()`).
* Persisting rejected messages anywhere (rejected messages are simply not pushed — caller decides what to do with the original `message` object it still holds).
* Capping `done`, priority ordering, backpressure/async signaling, changes to `registerHandler`.

## Flags
* `needs_ba`: false — no domain/business rules or stakeholder variation; purely a technical capacity/visibility behavior on a single in-memory module.
* `needs_ui`: false — no UI surface; `queue.js` is a backend-only library with no route/page/component involved.
* `needs_sa`: false — single component, single file, no competing architectural approaches with lasting consequences, no NFRs stated beyond "don't silently drop messages."
* `needs_devops`: false — no env vars, no migrations, no feature flags, no infra; `maxQueueSize` is a plain function parameter.

## Open Items
* none — every requirement above traces to a verified read of `src/queue.js`/`test/queue.test.js`, and every AC's exact inputs are named.
