# ☕ [dlq-retry-cap] Spec — Dead-letter path and backoff cap for the retry queue

> **Status:** 🟢 READY_FOR_BUILD | **Created:** 2026-07-28
> **Next:** 🏗️ kestra-build

---

## ☕ Overview
Cap retries at 3 failed attempts, move exhausted messages to a dead-letter list that keeps their last
error, space retries out with an attempt-based backoff read off an injected clock, and make a queue
containing a message with no registered handler impossible to process silently.

## 🪵 Problem Statement
* `step()` in `src/queue.js` re-queues a throwing message forever: `message.attempts += 1` then
  `queue.pending.push(message)`, with no cap, no delay, and no record of the error.
* A message whose `type` has no registered handler is pushed back to the tail and reported as
  `{ status: 'skipped' }` — a return value a worker loop can ignore, so a mis-deployed handler
  produces an endlessly spinning queue and no signal.
* There is no way to see how many messages succeeded versus dead-lettered.
* 🎯 **Goal:** a message fails at most 3 times before landing in `queue.dead` with its last error;
  retries are delayed by an attempt-based backoff; an unhandled message type cannot be processed
  quietly; and success/dead-letter counts are readable off the queue.

## 🥑 Functional Requirements
* [ ] `createQueue()` returns `{ pending: [], done: [], dead: [], stats: { ok: 0, deadLettered: 0 } }`.
* [ ] `step(queue, now)` takes the current wall-clock time in epoch milliseconds as its second
      parameter, defaulting to `Date.now()`. No other function reads the clock.
* [ ] **Given** a message with `attempts: 2` whose handler throws
      **When** `step` runs it
      **Then** `attempts` becomes 3
      **And** the message is appended to `queue.dead`, not `queue.pending`
      **And** the message carries `lastError` set to the thrown error's `message` string
      **And** `queue.stats.deadLettered` increases by 1
      **And** `step` returns `{ status: 'dead', id, attempts: 3 }`.
* [ ] **Given** a message with `attempts: 0` or `1` whose handler throws
      **When** `step` runs it
      **Then** `attempts` is incremented
      **And** `lastError` is set to the thrown error's `message`
      **And** `nextAttemptAt` is set to `now + 100 * 2 ** (attempts - 1)` (100 ms, then 200 ms)
      **And** the message returns to the tail of `queue.pending`
      **And** `step` returns `{ status: 'retry', id, attempts }`.
* [ ] **Given** the head of `pending` has `nextAttemptAt > now`
      **When** `step` runs
      **Then** no handler is called, the message stays at the head of `pending` unmodified, and
      `step` returns `{ status: 'waiting', id, nextAttemptAt }`.
* [ ] **Given** a message whose `type` has no registered handler
      **When** `step` runs
      **Then** the message is returned to the tail of `pending` with `attempts`, `lastError` and
      `nextAttemptAt` all unchanged
      **And** its `type` is recorded in `queue.unhandledTypes`
      **And** `step` refuses to complete quietly — see **Runtime Invariants**.
* [ ] `registerAlertSink(fn)` registers the process-wide sink that receives
      `{ kind: 'unhandled-type', type, id }`. Named export, mirroring `registerHandler`.
* [ ] A successful handler run increments `queue.stats.ok` and pushes to `queue.done` as today.
* [ ] `deadLetterRate(queue)` returns `deadLettered / (ok + deadLettered)`, and `0` when both are 0.

## 🌤️ Edge Cases & Error States
* **No handler registered for the type:** message is left byte-for-byte unchanged (no `attempts`
  bump, no `lastError`, no `nextAttemptAt`) and re-queued at the tail; `type` is added to
  `queue.unhandledTypes`; the alert sink is called, or `step` throws when no sink is registered.
  This is a config fault, never a data fault — the message is never dead-lettered for it.
* **Empty queue:** `step` returns `{ status: 'idle' }`, unchanged from today.
* **Handler throws a non-Error:** `lastError` is `String(thrown)` rather than `thrown.message`, so
  it is always a string.
* **Handler throws with an empty message:** `lastError` is the empty string, which is still a
  string; no fallback text is invented.
* **A message enqueued with `attempts` already >= 3:** the cap is evaluated on the post-increment
  value, so its next failure dead-letters it immediately; a pre-set `attempts` is never trusted to
  mean the retries actually happened.
* **Clock moves backwards between steps:** a message whose `nextAttemptAt` is in the future simply
  keeps returning `waiting`; nothing throws and nothing is dead-lettered for a clock anomaly.
* **Every pending message is `waiting`:** `step` reports `waiting` for the head and makes no
  progress. The caller is responsible for sleeping; `step` never sleeps or busy-loops.
* **Only one message is dequeued per `step` call**, as today — this change does not introduce a
  loop inside `step`.

## 🛡️ Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; it never proceeds
silently. These are enforced in production, not verified once in a test.)*

| Invariant — what must be true | Detected at runtime by | On violation |
|---|---|---|
| A message with no registered handler never passes through `step` unnoticed | the `if (!handler)` branch in `step`, after re-queueing the message untouched | calls the registered alert sink with `{ kind: 'unhandled-type', type, id }`; if **no sink is registered**, `step` throws `UnhandledMessageTypeError` instead of returning — the worker loop crashes and the operator finds out. There is no path where the branch is taken and the caller learns nothing. |
| `attempts` never exceeds the cap of 3 for any message in `pending` or `dead` | assertion at the end of the failure branch, before the message is placed anywhere | throws `RangeError` naming the message id — a message past the cap still in `pending` means the cap logic is broken and continuing would retry it forever |
| Every message in `queue.dead` has a string `lastError` | assertion on the dead-letter push | throws `TypeError` naming the id — a dead letter with no reason defeats the only reason the list exists |
| `queue.stats.ok + queue.stats.deadLettered` equals `queue.done.length + queue.dead.length` | assertion at the end of every `step` that terminated a message (`ok` or `dead`) | throws `Error` — divergence means `deadLetterRate` is reporting a number the queue contents do not support |

Note the deliberate asymmetry with the first row: the *message* is untouched and the queue moves on,
but the *caller* cannot proceed unaware. Untouched-message and loud-signal are not in tension; the
signal is out-of-band of the message.

## 📜 Business Rules
* **BR-1 — retry cap is 3 total failed attempts, not 3 retries after the first.**
  `Given a message with attempts 2 When its handler throws Then attempts becomes 3 and it is dead-lettered`
  /
  `Given a message with attempts 1 When its handler throws Then attempts becomes 2 and it is re-queued for retry`
* **BR-2 — the no-handler case is a config fault and mutates nothing on the message.**
  `Given a message of type "sms" with attempts 2 and no handler registered for "sms" When step runs Then attempts is still 2, lastError is still absent, and the message is still in pending`
  /
  `Given a message of type "sms" with attempts 2 and a handler registered for "sms" that throws When step runs Then attempts becomes 3 and the message is dead-lettered`
* **BR-3 — backoff is per-attempt and evaluated against the injected clock, not slept on.**
  `Given a message re-queued at now=1000 with attempts 1 When step runs at now=1050 Then it returns waiting and the handler is not called`
  /
  `Given the same message When step runs at now=1100 Then the handler is called`
* **BR-4 — a dead-lettered message is terminal for this feature.** Nothing in this change moves a
  message out of `queue.dead`. Draining is explicitly out of scope.
* 👥 **Stakeholder variations:** operator (reads `queue.dead`, `lastError`, and `deadLetterRate` to
  judge queue health) vs. worker-loop author (reads `step`'s `status` to decide whether to sleep,
  continue, or crash). No role-based behaviour difference inside `step` itself.

## 🔭 Solution Architecture
**Chosen approach:** A — extend `src/queue.js` in place with an injected-clock parameter and a
process-wide alert sink, because the fixture is a single 39-line module with no worker loop and no
DI container to hang anything else off.

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **A — extend `src/queue.js`; `step(queue, now)`; module-level `registerAlertSink`, throw when absent** | one file, no new deps, clock is pinnable in tests, mirrors the existing module-level `HANDLERS` map and `registerHandler` convention | the alert sink is process-global mutable state, same as `HANDLERS` already is | ✅ chosen |
| **B — new `src/dlq.js` module wrapping `step`** | keeps `queue.js` untouched | the retry/dead-letter decision *is* the failure branch of `step`; a wrapper cannot see the throw without re-implementing the try/catch, and `CLAUDE.md` maps one source file to one test file, so this doubles the surface for no isolation gain | ❌ rejected — splits one decision across two files |
| **C — `step` throws `UnhandledMessageTypeError` unconditionally on an unhandled type, no sink** | simplest possible loud failure | forces every caller to catch to survive a single mis-deployed type, and gives the operator an exception instead of a structured signal; also silently changes the meaning of the existing `skipped` status | ❌ rejected — chosen approach keeps this behaviour only as the no-sink fallback |

* **Integration contracts:** none — single in-process module, no services, no network.
* **Data model impact:** the queue object gains `dead: []`, `stats: { ok, deadLettered }`, and
  `unhandledTypes` (a `Set`); messages gain optional `lastError` (string) and `nextAttemptAt`
  (epoch ms). No database, no migration. Queues are in-memory and per-process, so no existing
  persisted queue needs upgrading.
* **NFR targets:** `step` stays O(1) per call apart from the existing `Array#shift`; no sleeping, no
  timers, no I/O inside `step`; backoff resolution is 1 ms (integer epoch milliseconds).

## 🔎 Codebase Survey
* **Explored:** `CLAUDE.md`, `package.json`, `src/queue.js` (all 39 lines), `test/queue.test.js`
  (all 20 lines). The whole repo is those four files — there is no worker loop, no logger, no
  config module, and no `src/index.js`.
* **Integrate with:**
  * `HANDLERS` — module-level `Map`, populated by the named export `registerHandler`. The alert
    sink follows this exact pattern (module-level binding + `registerXxx` named export).
  * `step`'s existing shape: `shift()` → handler lookup → `try`/`catch`, returning a
    `{ status, ... }` object. The new statuses (`dead`, `waiting`) extend that same discriminated
    return; `idle`, `ok` and `retry` keep their current meaning.
  * `enqueue` spreads `{ attempts: 0, ...message }`, so a caller-supplied `attempts` wins — this is
    why the cap is checked post-increment (see Edge Cases).
  * Conventions from `CLAUDE.md`: ES modules, named exports only, no default exports, no
    third-party dependencies, `node --test`, `test/<name>.test.js` mirrors `src/<name>.js`.
  * `registerHandler` has no deregister and `HANDLERS` is never cleared, so state leaks between
    tests in the same file — the existing tests already depend on this. Tests for the no-handler
    path must therefore use a type name no other test registers.

## 🌐 Reality Constraints

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|---|---|---|---|
| `HANDLERS` map in `src/queue.js` (own code, but process-global mutable state) | `registerHandler(type, fn)` must have run before a message of that `type` reaches `step`; nothing enforces this, which is precisely the condition the first runtime invariant covers | `Map<string, (payload) => void>`; `HANDLERS.get` returns `undefined` for an unregistered type | that a handler registered in one test is absent in the next — there is no deregister and no clearing, so registrations accumulate for the life of the process |
| Handler functions (supplied by callers) | called with `message.payload` only; the return value is ignored | may return anything; may throw anything, not necessarily an `Error` | that a throw is an `Error`, that `err.message` exists or is a string, that the handler is synchronous (a returned rejected promise would **not** be caught by the existing `try`/`catch` — out of scope here, and named in Risks) |
| `Date.now()` (Node built-in) | read once per `step` call, only as the default value of the `now` parameter | `number`, integer epoch milliseconds | monotonicity — it can jump backwards on an NTP correction; the `waiting` branch is therefore written to tolerate that rather than assert on it |
| `node:test` / `node:assert/strict` (Node built-ins) | none | test runner; `npm test` = `node --test test/*.test.js` | nothing relevant to this feature; there is no fake-timer facility in use, which is the reason the clock is a parameter rather than mocked |

No network, filesystem, database, or third-party package is involved.

### Paths that must agree
* `step`'s dead-letter accounting ↔ `queue.stats` / `deadLetterRate(queue)` — **equivalent means:**
  `queue.stats.ok === queue.done.length` and `queue.stats.deadLettered === queue.dead.length` after
  any sequence of `step` calls, so `deadLetterRate` derived from the counters equals the same ratio
  derived by counting the two arrays. · **may differ:** nothing — this is why the fourth runtime
  invariant asserts the identity on every terminating `step` rather than trusting it.
* No replay/live, cached/computed, or sync/async pair exists — `step` is the single path.

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|---|---|---|
| clock (`Date.now()`) | 📌 pinned — every test passes an explicit integer `now` to `step` | backoff comparisons are the feature; a test reading the live clock would pass or fail on machine speed. Exactly one test may exercise the `Date.now()` default, and it must assert only that `nextAttemptAt > 0`, never a specific value. |
| randomness | 📌 pinned — none used | the backoff is deterministic (`100 * 2 ** (attempts - 1)`); no jitter is introduced, deliberately, so tests can assert exact `nextAttemptAt` values |
| timezone / locale | 🌊 floating | only epoch-millisecond integers are compared; no date formatting or parsing anywhere |
| network / filesystem | 🌊 floating — neither is touched | in-memory module with no I/O |
| environment variables | 🌊 floating — none read | the cap and backoff base are module constants, not configuration (see Open Items) |
| `HANDLERS` / alert-sink module state | 📌 pinned per test file — each test registers the handlers and sink it needs under type names unique to that test | registrations persist for the process; sharing a type name across tests would make results order-dependent |

## 🗂️ Files to Touch
| File | Change | Verified? | Why |
|---|---|---|---|
| `src/queue.js` | edit | ✅ exists (39 lines, read in full) | holds `createQueue`, `enqueue`, `step`, `registerHandler`, `HANDLERS` — every change lands here: `dead`/`stats`/`unhandledTypes` on the queue, the `now` parameter, the backoff and cap logic, `registerAlertSink`, `deadLetterRate`, and the four invariant assertions |
| `test/queue.test.js` | edit | ✅ exists (20 lines, read in full) | the only test file, and `CLAUDE.md` mandates `test/<name>.test.js` mirrors `src/<name>.js`, so new tests extend this file rather than adding a new one. Existing tests stay valid: `step(q)` keeps working via the `now` default, and neither existing test asserts on `skipped`. |

No new files. No change to `package.json` (no new dependency, no new script).

## 🔗 Dependencies
* None — no new packages, no schema changes, no migrations, no env vars. `CLAUDE.md` forbids
  third-party dependencies and nothing here needs one.

## 🎯 Acceptance Criteria
* [ ] **Given** a fresh queue **When** `createQueue()` is called **Then** it returns an object with
      `pending`, `done`, `dead` as empty arrays, `stats` equal to `{ ok: 0, deadLettered: 0 }`, and
      an empty `unhandledTypes`.
* [ ] **Given** a message whose handler always throws `new Error('nope')` **When** `step` is called
      three times, each at a `now` past the message's `nextAttemptAt` **Then** the first two calls
      return `status: 'retry'` with `attempts` 1 and 2, the third returns
      `{ status: 'dead', id, attempts: 3 }`, `queue.pending` is empty, `queue.dead` has length 1,
      and that entry has `attempts: 3` and `lastError: 'nope'`.
* [ ] **Given** the same three-failure sequence **When** it completes **Then** `queue.stats` equals
      `{ ok: 0, deadLettered: 1 }` and no fourth `step` call ever invokes the handler again (assert
      the handler's call count is exactly 3).
* [ ] **Given** a message re-queued after its first failure at `now = 1000`
      **Then** its `nextAttemptAt` is exactly `1100`; after its second failure at `now = 1100`, its
      `nextAttemptAt` is exactly `1300`.
* [ ] **Given** a queue whose only message has `nextAttemptAt = 1100` **When** `step(queue, 1099)`
      is called **Then** it returns `{ status: 'waiting', id, nextAttemptAt: 1100 }`, the handler
      call count is 0, and `queue.pending.length` is still 1 with the same message at index 0.
      **When** `step(queue, 1100)` is then called **Then** the handler is invoked.
* [ ] **Given** a message of a type with no registered handler and an alert sink registered
      **When** `step` runs **Then** it returns `{ status: 'skipped', id }`, the sink was called once
      with `{ kind: 'unhandled-type', type, id }`, `queue.unhandledTypes` contains that type, and
      the message object in `pending` is deep-equal to what was enqueued (`attempts` unchanged, no
      `lastError`, no `nextAttemptAt`).
* [ ] **Given** a message of a type with no registered handler and **no** alert sink registered
      **When** `step` runs **Then** it throws `UnhandledMessageTypeError` whose message names the
      type, and the message is still present in `queue.pending`, unmodified.
* [ ] **Given** a handler that throws a non-`Error` value (e.g. `throw 'plain string'`)
      **When** the message dead-letters **Then** `lastError` is the string `'plain string'`, and
      `typeof lastError === 'string'` holds for every entry in `queue.dead`.
* [ ] **Given** 9 messages that succeed and 1 that fails 3 times **When** all are drained
      **Then** `queue.stats` equals `{ ok: 9, deadLettered: 1 }`, `deadLetterRate(queue)` returns
      `0.1`, `queue.done.length` is 9 and `queue.dead.length` is 1.
* [ ] **Given** a fresh queue with no messages ever processed **When** `deadLetterRate(queue)` is
      called **Then** it returns `0` and does not divide by zero (`Number.isFinite` holds).
* [ ] **Given** an empty queue **When** `step(queue, 0)` is called **Then** it returns
      `{ status: 'idle' }`.
* [ ] **Given** the pre-existing tests in `test/queue.test.js` **When** `npm test` runs
      **Then** both still pass unmodified, calling `step(q)` with no `now` argument.
* [ ] `npm test` exits 0 with no `.skip`/`.only` in `test/queue.test.js`.

## 🎯 AC Coverage Map
| AC | Covered by (files/steps) |
|---|---|
| `createQueue` shape | `src/queue.js` — `createQueue` returns `dead`, `stats`, `unhandledTypes` |
| three failures → dead-lettered with `lastError` | `src/queue.js` — post-increment cap check in the `catch` branch, push to `queue.dead` |
| handler not called a 4th time / `stats` after dead-letter | `src/queue.js` — dead branch does not re-push to `pending`; `stats.deadLettered` increment |
| exact `nextAttemptAt` values 1100 / 1300 | `src/queue.js` — `now + 100 * 2 ** (attempts - 1)` in the retry branch |
| `waiting` before due, runs when due | `src/queue.js` — due-check before `shift()`/handler lookup, returns `waiting` leaving the head in place |
| no-handler with sink: `skipped`, untouched message, `unhandledTypes` | `src/queue.js` — `if (!handler)` branch: re-queue untouched, record type, call sink |
| no-handler without sink: throws `UnhandledMessageTypeError` | `src/queue.js` — same branch, no-sink fallback throw (Runtime Invariant 1) |
| non-`Error` throw → string `lastError` | `src/queue.js` — `String(thrown)` normalization + Runtime Invariant 3 assertion |
| `deadLetterRate` = 0.1 on 9 ok / 1 dead | `src/queue.js` — `deadLetterRate` + `stats` increments; Runtime Invariant 4 keeps them honest |
| `deadLetterRate` = 0 on an untouched queue | `src/queue.js` — zero-denominator guard in `deadLetterRate` |
| empty queue → `idle` | `src/queue.js` — existing `if (!message) return { status: 'idle' }`, preserved |
| pre-existing tests still pass | `src/queue.js` — `now = Date.now()` default parameter; `test/queue.test.js` left as-is |
| `npm test` exits 0, no skips | `test/queue.test.js` — new tests appended to the existing file |

## ⚠️ Risks & Watch-outs
* **Shared file:** every change lands in `src/queue.js`; it is a single write scope, so nothing can
  be parallelised across two implementers here.
* **Process-global registries:** `HANDLERS` has no deregister and the alert sink is a single
  module-level binding, so a sink registered by one test is visible to later tests in the same file.
  The no-sink AC must therefore run before any sink is registered, or the implementation must expose
  a way to clear it — decide in implementation, but do not make the tests order-dependent by
  accident.
* **`enqueue` trusts a caller-supplied `attempts`** (`{ attempts: 0, ...message }`). The cap is
  checked post-increment so a pre-set value cannot bypass it, but a message enqueued with
  `attempts: 99` will dead-letter on its very first failure. That is the intended reading.
* **Async handlers are silently unsupported today** — `try`/`catch` around a synchronous call does
  not catch a rejected promise, so an async handler's failure currently looks like success. This
  change does not fix that and does not make it worse; flagged because the dead-letter path will
  look broken to anyone using an async handler.
* **Backoff is not slept on.** A caller that loops on `step` without sleeping will spin on
  `waiting`. `step` deliberately owns no timer; a worker loop is out of scope.
* **`unhandledTypes` grows unbounded** if a mis-deployed type is retried forever. It is a `Set` of
  type strings, so it is bounded by the number of distinct types, not the message count.

## 🚫 Out of Scope
* Draining `queue.dead` back into `pending` after a fix (explicitly deferred by the sharpened idea).
* A worker loop, sleeping, timers, or any scheduler around `step`.
* Persisting the queue, `dead`, or `stats` anywhere — everything stays in-process memory.
* Async/promise-returning handler support.
* Jitter on the backoff, or a maximum backoff ceiling.
* Making the cap or backoff base configurable (see Open Items).
* Any UI, CLI, or HTTP surface for operators — `deadLetterRate` and `queue.dead` are read
  programmatically.

## 🔀 Flags
* `needs_ba`: **true** — the cap boundary (3 total attempts vs. 3 retries), and the untouched-message
  rule for the no-handler case versus the demand that somebody find out, are domain rules the
  one-line ask left ambiguous. Resolved in **Business Rules** BR-1…BR-4.
* `needs_ui`: **false** — no page, route, modal, form, interactive element, or user-visible
  empty/loading/error state. The operator-facing surface is `queue.dead` and `deadLetterRate()`,
  both plain return values consumed by code. The **Design Notes** section is therefore omitted
  deliberately, not overlooked.
* `needs_sa`: **true** — genuinely competing approaches with lasting consequences (extend `queue.js`
  vs. a wrapper module; unconditional throw vs. alert sink with a throw fallback) plus a clock-source
  decision that determines whether the tests can be hermetic at all. Resolved in
  **Solution Architecture**.
* `needs_devops`: **false** — no env vars, no migrations, no feature flags, no infra. The cap and
  backoff base are module constants; nothing to set before deploy.

## ❓ Open Items
* ⚠️ **OPEN — backoff base constant.** The sharpened idea specifies "a backoff based on attempt
  count, read off the wall clock" but not the magnitude. This spec fixes it at
  `100 * 2 ** (attempts - 1)` ms (100 ms, then 200 ms) so the ACs are exactly testable. That is a
  chosen constant, not a stated requirement — if 100 ms is wrong for the real workload, changing it
  means editing the two exact-value ACs above (`1100` / `1300`) before the tests are frozen. Cheap
  to change now, a `reworking` bounce to change later.
