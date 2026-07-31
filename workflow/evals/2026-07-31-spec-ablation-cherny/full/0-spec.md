# [queue-cap] Spec — Cap the retry queue's pending size

> Status: READY_FOR_BUILD | Created: 2026-07-31 | Next: kestra-build

---

## Overview
Add a configurable `maxQueueSize` cap to the in-memory retry queue's `pending` array, enforced on
new `enqueue()` calls only, so operators can bound memory/backlog growth and see how often the cap
rejects work.

## Problem Statement
* `enqueue()` currently pushes unconditionally — `pending` can grow without bound.
* Goal: `enqueue()` refuses new messages once `pending.length == maxQueueSize`, tells the caller it
  was refused, and counts refusals — without ever blocking `step()`'s own retry/skip re-entry.

## Functional Requirements
* [ ] `createQueue(options = {})` accepts optional `maxQueueSize` (non-negative integer). Omitted/
  `undefined` → unbounded (`Infinity`), preserving today's behavior for existing callers.
* [ ] `createQueue()` validates `maxQueueSize` synchronously: not a non-negative integer (negative,
  `NaN`, float, non-number) → throw `TypeError` before returning a queue object.
* [ ] `createQueue()`'s returned object gains `rejectedCount: 0` alongside the existing `pending`/
  `done` arrays.
* [ ] `enqueue(queue, message)` — Given `queue.pending.length >= queue.maxQueueSize`, When called,
  Then it does not push `message` anywhere, increments `queue.rejectedCount` by 1, and returns
  `{ status: 'rejected', id: message.id }`.
* [ ] `enqueue(queue, message)` — Given `queue.pending.length < queue.maxQueueSize`, When called,
  Then it pushes `{ attempts: 0, ...message }` to `pending` (unchanged from today) and returns
  `{ status: 'accepted', id: message.id }`. (Return shape changes from today's `undefined` — an
  intentional break; `test/queue.test.js`'s two existing tests never assert on `enqueue()`'s return
  value, so nothing existing breaks. Status vocabulary mirrors `step()`'s own `{status, id, ...}`
  pattern already in `src/queue.js`.)
* [ ] `step()`'s two internal `queue.pending.push(message)` call sites — the no-handler/"skip" path
  and the throwing-handler/"retry" path — stay direct, uncapped array pushes. They must never be
  routed through `enqueue()` or any cap-checked helper, and must never consult `maxQueueSize` or
  touch `rejectedCount`. This is the one behavior this feature must not regress (see Risks).

## Edge Cases & Error States
* **`enqueue()` at the boundary:** `pending.length == maxQueueSize - 1` → accepted, `pending.length`
  becomes `maxQueueSize`. `pending.length == maxQueueSize` → rejected, `pending.length` unchanged.
* **`maxQueueSize: 0`:** every `enqueue()` call is rejected; `rejectedCount` still increments per call.
* **`maxQueueSize` omitted:** unbounded — existing two tests in `test/queue.test.js` keep passing
  unmodified (they call `createQueue()` with no args).
* **Retry re-entry at/above cap:** `step()`'s failed-handler push-back always succeeds regardless of
  `pending.length` vs `maxQueueSize`; `rejectedCount` never increments for it.
* **Skip re-entry at/above cap:** same guarantee as retry — `step()`'s no-handler push-back always
  succeeds, never checked against the cap.
* **Invalid `maxQueueSize`** (negative, `NaN`, non-integer, non-number): `createQueue()` throws
  synchronously; no partially-constructed queue is returned.
* **Rejected message's fate:** discarded entirely — not queued, not auto-retried, not logged or
  persisted anywhere (explicitly out of scope). The `{status:'rejected', id}` return value is the
  only signal the caller gets.

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| `pending.length` never exceeds `queue.maxQueueSize` as a direct result of an `enqueue()` call | `enqueue()`'s pre-push check `pending.length >= maxQueueSize`, evaluated before any mutation | Refuse: message not pushed, `rejectedCount++`, caller told via `{status:'rejected', id}` — never silently dropped nor silently accepted over cap |
| Every message `step()` shifts off `pending` is accounted for exactly once — pushed to `done` (success) or pushed back to `pending` (retry/skip) — and that push-back is never routed through the cap check | `step()`'s own control flow: shift is immediately followed, in the same synchronous call, by exactly one of `done.push`/`pending.push`, with no branch that returns in between and no call into `enqueue()` | Halt: if a future edit breaks this (e.g. refactors the two internal push sites through `enqueue()`), the frozen test suite's message-conservation assertions (AC-RETRY-BYPASS, AC-SKIP-BYPASS below) must fail the build — this is a code-shape guarantee enforced by construction plus tests, not a live production throw, because no external input can violate it independent of the code itself |
| `queue.maxQueueSize`, if provided to `createQueue()`, is a non-negative integer (or omitted, meaning unbounded) | `createQueue()`'s own argument validation at construction time | Halt: `createQueue()` throws `TypeError` synchronously; queue is never constructed with an unusable cap |

## Codebase Survey
* Explored: `CLAUDE.md` (plain ESM, no build step, Node's built-in test runner, named exports only,
  no third-party deps, `src/<name>.js` ↔ `test/<name>.test.js`), `src/queue.js` (all 39 lines),
  `test/queue.test.js` (all 21 lines), `package.json` (`"test": "node --test test/*.test.js"`).
  Ran `npm test` now: 2/2 passing (`runs a registered handler`, `retries a throwing handler`) —
  baseline confirmed green before this feature touches anything.
* Integrate with: `src/queue.js`'s existing conventions — plain object state (no classes), named
  exports, operations return `{status, id, ...}` shape (see `step()`'s `idle`/`ok`/`skipped`/`retry`
  statuses) — `enqueue()`'s new return value follows the same vocabulary style (`accepted`/
  `rejected`). Tests follow `test/queue.test.js`'s existing flat `node:test` + `node:assert/strict`
  style, one `registerHandler`/`createQueue`/assert block per `test(...)`.
* **The exact lines this feature must not disturb:** `src/queue.js:26` (`queue.pending.push(message)`
  in the no-handler/skip branch) and `src/queue.js:36` (`queue.pending.push(message)` in the
  catch/retry branch). Both currently push directly with no size check — that absence of a check is
  exactly what today's code already gets right by construction. The cap-check must be added *only*
  to the top of `enqueue()` (a separate function, called only by external callers) — not factored
  into a shared push helper that these two sites would also call.

## Reality Constraints
### External dependencies
None. `src/queue.js` imports nothing, calls no network/DB/filesystem/timer API anywhere in
`createQueue`/`enqueue`/`step`. Registered handlers (via `registerHandler`) are arbitrary
caller-supplied synchronous functions run in-process — not an external service, and this feature
doesn't change their contract (handlers still receive `message.payload`, still signal failure only
via throw).

### Paths that must agree
None — single path. `enqueue()` and `step()` are the only two functions that touch `pending`; there
is no cached/computed duplicate of pending's contents and no replay/live split to keep in sync.

### Non-deterministic inputs
None read by this feature. `createQueue`/`enqueue`/`step` read no clock, no RNG, no timezone/locale,
no network, no filesystem, no env var — `id`/`type`/`payload` are caller-supplied deterministic
values, and `maxQueueSize` is a caller-supplied config number. All tests can run fully synchronously
with no fake timers/clocks needed.

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| src/queue.js | edit | exists (read in full — 39 lines) | add `maxQueueSize`/`rejectedCount` to `createQueue()`; add cap-check + rejected/accepted return to `enqueue()`; leave `step()`'s two internal push sites (lines 26, 36) untouched |
| test/queue.test.js | edit | exists (read in full — 21 lines) | add cap/rejection/bypass/validation tests, following the file's existing `test(...)` + `node:assert/strict` style; the two existing tests must keep passing unmodified |

## Dependencies
None — no new packages (CLAUDE.md: "No third-party dependencies; keep it that way"), no schema/
migration, no config file.

## Acceptance Criteria
* [ ] **AC-DEFAULT-UNBOUNDED:** Given `createQueue()` with no options, When 150 messages are
  enqueued via `enqueue()`, Then all 150 return `{status:'accepted', id}` and `pending.length` is 150.
* [ ] **AC-CAP-BOUNDARY:** Given `createQueue({maxQueueSize: 1})`, When `enqueue()` is called once,
  Then it returns `{status:'accepted', id}` and `pending.length` is 1; When `enqueue()` is called a
  second time, Then it returns `{status:'rejected', id}`, `pending.length` stays 1, and the rejected
  message's `id` never appears in `pending`.
* [ ] **AC-REJECTED-COUNT:** Given `createQueue({maxQueueSize: 2})` already at cap, When `enqueue()`
  is called 3 more times, Then all 3 return `{status:'rejected', ...}` and `queue.rejectedCount`
  equals 3.
* [ ] **AC-RETRY-BYPASS:** Given `createQueue({maxQueueSize: 2})` with exactly 2 pending messages,
  the head message registered to a handler that throws, When `step()` is called, Then it returns
  `{status:'retry', id, attempts:1}`, `pending.length` is 2 again (same message reappears at the
  tail, identified by `id`), and `queue.rejectedCount` is unchanged (0).
* [ ] **AC-SKIP-BYPASS:** Given `createQueue({maxQueueSize: 1})` with exactly 1 pending message whose
  `type` has no registered handler, When `step()` is called, Then it returns `{status:'skipped', id}`,
  `pending.length` is 1 again (same message, same `id`), and `queue.rejectedCount` is unchanged (0).
* [ ] **AC-ZERO-CAP:** Given `createQueue({maxQueueSize: 0})`, When `enqueue()` is called, Then it
  returns `{status:'rejected', id}` and `pending.length` stays 0.
* [ ] **AC-INVALID-CAP:** Given `createQueue({maxQueueSize: -1})` (repeat for `NaN` and `1.5`), When
  called, Then it throws `TypeError` synchronously and no queue object is returned.
* [ ] **AC-SUCCESS-REGRESSION:** Given a queue with a message whose handler succeeds, When `step()`
  is called, Then `pending.length` decreases by 1, the message moves to `done`, and
  `queue.rejectedCount` is untouched (unchanged from before the call).
* [ ] **AC-EXISTING-TESTS:** `npm test` — the two pre-existing tests (`runs a registered handler`,
  `retries a throwing handler`) still pass unmodified (baseline verified green above).

## AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| AC-DEFAULT-UNBOUNDED | src/queue.js `createQueue` default-cap logic; test/queue.test.js new test |
| AC-CAP-BOUNDARY | src/queue.js `enqueue` cap check; test/queue.test.js new test |
| AC-REJECTED-COUNT | src/queue.js `enqueue` `rejectedCount++`; test/queue.test.js new test |
| AC-RETRY-BYPASS | src/queue.js `step()` catch-branch push (line 36, untouched); test/queue.test.js new test |
| AC-SKIP-BYPASS | src/queue.js `step()` no-handler-branch push (line 26, untouched); test/queue.test.js new test |
| AC-ZERO-CAP | src/queue.js `enqueue` cap check with `maxQueueSize:0`; test/queue.test.js new test |
| AC-INVALID-CAP | src/queue.js `createQueue` validation; test/queue.test.js new test |
| AC-SUCCESS-REGRESSION | src/queue.js `step()` success branch (unchanged); test/queue.test.js new test |
| AC-EXISTING-TESTS | test/queue.test.js (unmodified existing 2 tests) |

## Risks & Watch-outs
* **The one real risk in this feature:** an implementer adds the cap check to `enqueue()` and then,
  for DRY-ness, factors `pending.push` into a shared helper that `step()`'s skip/retry branches also
  call — reintroducing exactly the bug this spec exists to prevent (a retry silently rejected the
  moment `pending` is at cap). Keep `enqueue()`'s cap check local to `enqueue()`; leave
  `src/queue.js:26` and `:36` as direct, unchecked `pending.push` calls.
* `enqueue()`'s return value changes from `undefined` to `{status, id}` — a breaking change to its
  return contract. No consumer in this repo relies on the old `undefined` return (only
  `test/queue.test.js` calls it, and it never asserts on the return value), so nothing here breaks,
  but flag it in case a future external consumer exists.
* `rejectedCount` is a plain mutable field on the queue object (matching `pending`/`done`'s existing
  style — no classes, no private state anywhere in this codebase) — nothing stops external code from
  mutating/resetting it directly. Accepted as consistent with existing conventions, not a defect.

## Out of Scope
* Resizing `maxQueueSize` at runtime after `createQueue()`.
* Persisting rejected messages anywhere (no dead-letter queue, no logging requirement).

## Flags
* `needs_ba`: false — no multi-stakeholder business rules; behavior is fully pinned by the
  post-grilling idea doc, mechanical single-module change.
* `needs_ui`: false — no page/route/modal/form/visible state; pure in-memory library code.
* `needs_sa`: false — single file, single process, no competing services or explicit NFRs; the
  enqueue-return-shape choice is a small API-design call, documented above, not a system-architecture
  decision.
* `needs_devops`: false — no env vars, migrations, feature flags, or infra; `maxQueueSize` is an
  in-process config value passed to `createQueue()` by its caller.

## Open Items
None.
