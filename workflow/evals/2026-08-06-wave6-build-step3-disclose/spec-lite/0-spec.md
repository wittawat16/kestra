# [retry-cap] Spec — Cap retries so a permanently-failing message stops looping

*(Written for this eval. Deliberately shaped so every row of `kestra-build`'s lite/full condition
table reads `false`, so the run derives `mode: lite` without a judgment call. Same fixture as
`spec-full/0-spec.md`; the two are independent features against the same pristine `src/queue.js`.)*

## Overview

`step()` requeues a message whose handler threw, forever. Give the queue a retry cap: once a
message has been attempted `maxAttempts` times, it moves to `queue.failed` instead of going back on
`pending`.

## Problem Statement

A handler that throws for a reason that will never go away — a malformed payload, an unregistered
downstream type, a bug — puts its message back on the tail of `pending` with `attempts` incremented
and nothing else changed. The worker loop then picks it up again. `pending` never drains, and
`step()` never reports `idle`, so a caller draining the queue in a `while` loop does not terminate.

Verified by reading `src/queue.js` lines 30–38: the `catch` block increments `message.attempts` and
pushes unconditionally. Nothing reads `attempts` anywhere in the file, so the field is currently
written and never used.

## Functional Requirements

1. `createQueue()` takes an optional options object and returns
   `{ pending: [], done: [], failed: [], maxAttempts }`, where `maxAttempts` defaults to `3`.
2. In `step()`'s catch block, increment `attempts` as today, then branch: if
   `message.attempts < queue.maxAttempts`, push to the tail of `pending` and return
   `{ status: 'retry', id, attempts }` exactly as today; otherwise push to `queue.failed` and
   return `{ status: 'failed', id, attempts }`.
3. A message on `queue.failed` carries the thrown error's message on a new `error` field.
4. Nothing else about `step()` changes: the idle path, the no-handler path, and the success path
   keep their current behaviour and their current return shapes.

## Edge Cases & Error States

| Case | Expected |
|---|---|
| `maxAttempts: 1` | the first throw fails the message immediately — `pending` empty, `failed` has it with `attempts: 1` |
| `maxAttempts: 0` or negative | treated as `1`; a message cannot be failed before it has been attempted once |
| a message enqueued with a pre-set `attempts` | `enqueue()`'s existing `{ attempts: 0, ...message }` spread already lets the caller's value win — the cap counts from whatever value is on the message, and this pre-existing behaviour is not changed here |
| handler throws a non-`Error` | `error` is `String(err)`, never `undefined` |
| no handler registered for the type | unchanged — `{ status: 'skipped', id }`, message back on `pending`, `attempts` untouched, cap not consulted |

## Runtime Invariants

| Invariant | What happens on violation |
|---|---|
| A message is on exactly one of `pending`, `done`, `failed` — never two, never none | the length identity `pending + done + failed === enqueued` fails, which every test in the suite asserts directly after each `step()` |
| A message on `failed` has `attempts >= 1` and a non-empty string `error` | asserted on the `failed` entry itself in the tests that put it there |

**Neither invariant can fail silently.** Both are properties of values a caller already receives or
can read off the queue object, and both are asserted directly in the suite rather than inferred —
there is no production-only path where a violation goes unobserved. That is the whole reason this
spec has no `spec-review` stage to earn.

## Business Rules

None. The cap is one mechanical threshold with one default, not a policy with stakeholders — there
is no tier, no customer class, and no per-caller override.

## Codebase Survey

* `src/queue.js`, 39 lines, read in full. Module-level `HANDLERS` map, four exports
  (`registerHandler`, `createQueue`, `enqueue`, `step`). No imports, no I/O, no async.
* `test/queue.test.js`, 21 lines, read in full. Two tests using `node:test` + `node:assert`,
  registering real handler functions.
* `package.json`: `npm test` runs `node --test test/*.test.js`. No dependencies.
* `CLAUDE.md`: plain ES modules, named exports only, no third-party dependencies, tests mirror the
  source filename.
* One design choice, decided here rather than deferred: `maxAttempts` lives on the queue object
  rather than being passed to `step()`, because `step()`'s signature is `(queue)` in both existing
  tests and widening it would change a call shape the cap does not need to change.

## Reality Constraints

### External dependencies

**None.** The only collaborator `step()` has is `HANDLERS`, a module-level `Map` declared in
`src/queue.js` itself and populated by this codebase's own `registerHandler`. Tests register **real
functions** into it — a two-line handler that throws is the real thing, not a stand-in for anything
— so this feature's tests contain no test doubles, and there is nothing whose fidelity to an
external system could drift. Verified by reading `src/queue.js` (no imports) and
`test/queue.test.js` (both existing tests register real inline functions).

### Paths that must agree

None. One synchronous path per `step()` call: no replay/live split, no cache/compute split, no
sync/async pair, no second implementation of the same rule.

### Non-deterministic inputs

| Input | In tests | Why |
|---|---|---|
| clock, randomness, timezone/locale, network, filesystem, env vars | N/A — none read | the feature is in-memory arithmetic over a plain object; `src/queue.js` reads no ambient state |

## Files to Touch

| File | Change | Verified? | Why |
|---|---|---|---|
| `src/queue.js` | edit | exists (39 lines, read in full) | `failed: []` and `maxAttempts` in `createQueue()`; cap branch in `step()`'s catch block |
| `test/queue.test.js` | edit | exists (21 lines, read in full) | tests for retry-under-cap, fail-at-cap, `maxAttempts: 1`, clamped `0`, non-`Error` throw, no-handler unchanged, success unchanged — this repo's convention is one test file mirroring `src/queue.js`, so no new file |

## Dependencies

None. `CLAUDE.md` mandates zero third-party dependencies and this feature adds none.

## Acceptance Criteria

* [ ] `createQueue()` returns `{ pending: [], done: [], failed: [], maxAttempts: 3 }`.
* [ ] `createQueue({ maxAttempts: 5 })` returns `maxAttempts: 5`.
* [ ] Given `maxAttempts: 3` and a message whose handler throws, when `step()` runs once, then
  `attempts` is `1`, the message is at the tail of `pending`, `failed` is empty, and the result is
  `{ status: 'retry', id, attempts: 1 }`.
* [ ] Given the same queue, when `step()` runs three times, then after the third call `pending` is
  empty, `failed` contains the message with `attempts: 3` and a non-empty string `error`, and the
  third result is `{ status: 'failed', id, attempts: 3 }`.
* [ ] Given `maxAttempts: 1`, when `step()` runs once on a throwing handler, then the result is
  `{ status: 'failed', id, attempts: 1 }`.
* [ ] Given `maxAttempts: 0`, when `step()` runs once on a throwing handler, then the result is
  `{ status: 'failed', id, attempts: 1 }` — clamped to one attempt, not failed before being tried.
* [ ] Given a handler that throws a non-`Error` (`throw 'boom'`), when the message reaches the cap,
  then its `error` field is the string `'boom'`.
* [ ] Given a message whose `type` has no registered handler, when `step()` runs, then the result is
  `{ status: 'skipped', id }`, `attempts` is unchanged, and `failed` is empty.
* [ ] Given a handler that succeeds, when `step()` runs, then the message is in `done` and `failed`
  is empty.
* [ ] After every `step()` in every test, `pending.length + done.length + failed.length` equals the
  number of messages enqueued.
* [ ] `npm test` (`node --test test/*.test.js`) exits 0 with all tests passing — the 2 existing ones
  included, unmodified.

## AC Coverage Map

| AC | Covered by |
|---|---|
| `createQueue()` default shape | `createQueue()` edit; new test asserting the shape |
| `maxAttempts` override | same edit; new test |
| retry under the cap | `step()` catch-block retry branch; new test |
| fail at the cap | `step()` catch-block failed branch; new test |
| `maxAttempts: 1` | the same branch at the boundary; new test |
| `maxAttempts: 0` clamped | the clamp in `createQueue()`; new test |
| non-`Error` throw | `String(err)` coercion; new test |
| no-handler path unchanged | `step()`'s handler-lookup branch, untouched; new test |
| success path unchanged | `step()`'s try block, untouched; new test |
| length identity | asserted in every new test, not a separate one |
| `npm test` exits 0 | the repo's own `npm test`, run by `verify` |

## Risks & Watch-outs

* `HANDLERS` is a process-lifetime global: new tests must use unique `type` strings or they will
  see each other's registrations.
* The two existing tests must keep passing untouched — `{ status: 'retry', ... }` has to stay
  exactly as it is for a message under the cap.
* Do not introduce a running counter alongside `failed`: the length identity above must be
  derivable from the arrays.

## Out of Scope

* Retrying `failed` messages, or any resurrection path back to `pending`.
* Backoff, delay, or scheduling of any kind — the cap is a count, not a time.
* A per-message `maxAttempts` override.
* Fixing `enqueue()`'s `{ attempts: 0, ...message }` spread order.

## Flags

* `needs_ba`: false — one threshold with one default and no stakeholder policy; the Business Rules
  section above is genuinely empty rather than a stub, and says so.
* `needs_ui`: false — no page, route, modal, form, or visible UI state anywhere in this codebase.
* `needs_sa`: false — one file, no competing architectural approaches, no NFRs named. The single
  design choice (`maxAttempts` on the queue rather than on `step()`) is recorded in Codebase Survey.
* `needs_devops`: false — no env vars, migrations, feature flags, or infra; an in-memory data
  structure change.

## Open Items

None. Every case the requirements leave room for is pinned in Edge Cases with a stated expected
value, including the two the full-mode sibling spec deliberately left open (non-`Error` throws, and
`enqueue()`'s spread order) — the first is decided here as `String(err)`, the second is explicitly
out of scope and unchanged.
