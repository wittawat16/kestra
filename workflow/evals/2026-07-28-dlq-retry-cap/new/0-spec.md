# ☕ [dlq-retry-cap] Spec — Dead-letter path and retry backoff for the queue worker

> **Status:** 🟢 READY_FOR_BUILD | **Created:** 2026-07-28
> **Next:** 🏗️ kestra-build

---

## ☕ Overview
Cap retries at 3 attempts and move exhausted messages to a dead-letter list that keeps the last
error, space retries out with an attempt-based backoff read off an injected clock, and make a
message type with no registered handler impossible to ignore silently.

## 🪵 Problem Statement
* `step()` in `src/queue.js` today pushes any throwing message straight back to the tail of
  `queue.pending` with `attempts += 1` and no cap — a permanently-failing message is retried
  forever, immediately, starving the rest of the queue.
* A message whose `type` has no handler is also pushed back to the tail and reported as
  `{ status: 'skipped' }`, which a worker loop can consume indefinitely with nobody finding out
  that a deploy shipped a message type without its handler.
* No counters exist, so an operator cannot say whether messages are mostly getting through.
* 🎯 **Goal:** after this change, a message fails at most 3 times before landing in `queue.dead`
  with its last error text; retries are delayed by `1000 * 2^(attempts-1)` ms; an unhandled type
  raises to a configured alert sink or throws; and `queue.stats` reports ok / retried /
  deadLettered / skipped counts.

## 🥑 Functional Requirements
* [ ] `createQueue()` returns `{ pending: [], done: [], dead: [], stats: { ok: 0, retried: 0, deadLettered: 0, skipped: 0 } }`.
* [ ] `step(queue, now)` takes an explicit millisecond timestamp as its second parameter, defaulting
      to `Date.now()`. All due-time comparisons use that value and nothing else reads the clock.
* [ ] **Given** a message with `attempts: 0` whose handler throws
      **When** `step(queue, now)` runs
      **Then** the result is `{ status: 'retry', id, attempts: 1 }`
      **And** the message is at the tail of `queue.pending` with `attempts: 1`,
      `lastError: '<err.message>'`, and `nextAttemptAt: now + 1000`
      **And** `queue.stats.retried` is incremented by 1.
* [ ] **Given** a message with `attempts: 1` whose handler throws
      **When** `step(queue, now)` runs
      **Then** `attempts` is 2 and `nextAttemptAt` is `now + 2000`.
* [ ] **Given** a message with `attempts: 2` whose handler throws (its 3rd failure)
      **When** `step(queue, now)` runs
      **Then** the result is `{ status: 'dead', id, attempts: 3 }`
      **And** the message is **not** in `queue.pending`
      **And** `queue.dead` ends with that message carrying `attempts: 3`,
      `lastError: '<err.message>'`, and `deadLetteredAt: now`
      **And** `queue.stats.deadLettered` is incremented by 1.
* [ ] **Given** the head of `queue.pending` has `nextAttemptAt > now`
      **When** `step(queue, now)` runs
      **Then** `step` selects the first message in `queue.pending` order whose `nextAttemptAt` is
      absent or `<= now`, leaving relative order of the remaining messages unchanged.
* [ ] **Given** every message in `queue.pending` has `nextAttemptAt > now`
      **When** `step(queue, now)` runs
      **Then** the result is `{ status: 'waiting', nextDueAt: <min nextAttemptAt> }`
      **And** no message is mutated, moved, or counted.
* [ ] **Given** `queue.pending` is empty
      **When** `step(queue, now)` runs
      **Then** the result is `{ status: 'idle' }` (unchanged from today).
* [ ] **Given** a message whose `type` has no registered handler and an alert sink registered via
      `setUnhandledTypeAlert(fn)`
      **When** `step(queue, now)` runs
      **Then** `fn({ id, type })` is called exactly once
      **And** the result is `{ status: 'skipped', id }`
      **And** the message is back in `queue.pending` with `attempts`, `lastError` and
      `nextAttemptAt` all byte-for-byte unchanged
      **And** `queue.stats.skipped` is incremented by 1.
* [ ] **Given** the same message and **no** alert sink registered
      **When** `step(queue, now)` runs
      **Then** `step` throws `UnhandledMessageTypeError` (exported, `message` includes the type)
      **And** the message is back in `queue.pending` unchanged, so the throw loses no data.
* [ ] `successRate(queue)` returns `stats.ok / (stats.ok + stats.deadLettered)`, or `null` when that
      denominator is 0.
* [ ] `setUnhandledTypeAlert(fn)` and `UnhandledMessageTypeError` are named exports of
      `src/queue.js`; passing `null` clears the sink.

## 🌤️ Edge Cases & Error States
* **Unregistered `type`:** the message itself is a no-op — nothing about it changes and `attempts`
  is not touched — but the *worker* does not proceed silently: the alert sink fires, or `step`
  throws when no sink is configured. `stats.skipped` still counts the occurrence.
* **Handler throws a non-Error:** `lastError` is `String(err)`, never `undefined`.
* **Handler throws with an empty message:** `lastError` is `''`; the field is still present, since
  its presence is what the dead-letter reader keys on.
* **A message enqueued with an explicit `attempts` >= 3 that then fails:** dead-letters on that
  first failure (the cap is `attempts >= 3` after increment, not "exactly the third call").
* **A message enqueued with a pre-set `nextAttemptAt` in the future:** honored — `enqueue` does not
  clear caller-supplied fields, matching today's `{ attempts: 0, ...message }` spread.
* **All messages backed off:** `{ status: 'waiting', nextDueAt }` rather than `idle`, so a caller
  can distinguish "nothing to do" from "nothing due yet" and sleep instead of spinning.
* **`queue.dead` growth:** unbounded by design; no eviction in this change (see Out of Scope).
* **Reordering:** dead-lettering removes a message from `pending` without disturbing the order of
  the others; the backoff scan skips forward but never reorders.

## 🛡️ Runtime Invariants
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| No message is ever retried a 4th time: nothing in `queue.pending` has `attempts >= 3` after a `step` returns | guard at the end of the failure branch in `step`, after the increment: if `message.attempts >= 3` the only legal path is the dead-letter branch | refuse — `step` throws `RetryCapViolationError` instead of pushing to `pending`; the message stays out of `pending` and in `dead`, so no unbounded retry can start |
| A queue containing a message with no registered handler is never processed unobserved | in the `!handler` branch of `step`: the alert sink is invoked, and its absence is checked before returning | refuse — `step` throws `UnhandledMessageTypeError`, aborting the worker loop; the operator (or the loop's own crash handler) finds out. The message is restored to `pending` first, so the throw is lossless |
| Every dead-letter entry carries a `lastError` string and a numeric `deadLetteredAt` | assertion at the push site into `queue.dead` | halt — `step` throws before the push, rather than writing an entry an operator cannot diagnose |
| `queue.stats.deadLettered === queue.dead.length` and `stats.ok === queue.done.length` | checked at the end of every `step` before returning | halt — `step` throws `StatsDriftError`; a wrong success rate would otherwise be reported as fact |

*Cross-checked against Edge Cases and ACs: the unhandled-type invariant refuses at the **worker**
level while the **message** is an untouched no-op — the two statements are about different subjects
and both hold simultaneously. No invariant fires on a condition an AC declares successful.*

## 📜 Business Rules
* **BR-1 — the cap is 3 failed attempts, counted after increment.**
  `Given` a message at `attempts: 2` `When` its handler throws `Then` `attempts` becomes 3 and it
  moves to `queue.dead` /
  `Given` a message at `attempts: 1` `When` its handler throws `Then` `attempts` becomes 2 and it
  returns to `pending`.
* **BR-2 — backoff is exponential in the attempt count already recorded.**
  `Given` a failure taking `attempts` to N `When` the message is requeued `Then`
  `nextAttemptAt = now + 1000 * 2^(N-1)` (1s, 2s — a 3rd failure dead-letters, so 4s is never used) /
  `Given` a successful handler `When` `step` returns `Then` no `nextAttemptAt` is written at all.
* **BR-3 — a missing handler is a config fault, not a message fault.**
  `Given` `type: 'ghost'` with no handler `When` `step` runs `Then` the message's `attempts` is
  unchanged and it is never dead-lettered /
  `Given` `type: 'boom'` with a throwing handler `When` `step` runs `Then` `attempts` increments and
  the cap eventually applies.
* **BR-4 — a config fault must reach a human.**
  `Given` an alert sink is registered `When` an unhandled type is stepped `Then` the sink is called
  once and the loop may continue /
  `Given` no sink is registered `When` an unhandled type is stepped `Then` `step` throws and the
  loop stops.
* **BR-5 — the success rate excludes in-flight work.**
  `Given` 9 done and 1 dead `When` `successRate` is read `Then` it is `0.9` /
  `Given` 0 done and 0 dead but 5 pending `When` `successRate` is read `Then` it is `null`, not `0`.
* 👥 **Stakeholder variations:** two consumers of this module. The **worker loop** cares about the
  `status` discriminator (`ok` / `retry` / `dead` / `skipped` / `waiting` / `idle`) and about
  `nextDueAt` so it can sleep. The **operator** cares about `queue.dead[].lastError`,
  `queue.dead[].deadLetteredAt`, and `successRate(queue)`. No role-based or locale behavior.

## 🎨 Design Notes
Not applicable — `needs_ui: false`. This module has no user-facing surface; the operator-facing
output is plain data on the queue object, consumed by whatever process embeds it.

## 🔭 Solution Architecture
**Chosen approach:** A — store an absolute `nextAttemptAt` on the message at requeue time and have
`step` scan `pending` for the first due message, with the clock passed in as `step`'s second
parameter.

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A — absolute `nextAttemptAt` on the message; injected `now` param | due-check is one comparison, no clock read inside the comparison path; testable by passing integers, no fake timers; survives being serialized with the message | one extra field on the message shape | ✅ chosen |
| B — store `lastFailedAt` and recompute the delay from `attempts` on every scan | one less concept | recomputes the policy on every read, so a policy change silently retroactively re-times already-queued messages; harder to explain a due time to an operator | ❌ rejected — policy and state get entangled |
| C — real timers (`setTimeout`) to re-admit messages | no scan at all | makes the module stateful/async and unusable from the existing synchronous `step` contract; tests need fake timers, which the repo has no dependency for (built-in runner only) | ❌ rejected — breaks the sync API and the no-dependency rule |

* **Integration contracts:** single module, no services. The contract with callers is the exported
  surface of `src/queue.js`: `createQueue`, `enqueue`, `registerHandler`, `step`,
  `setUnhandledTypeAlert`, `successRate`, `UnhandledMessageTypeError`. `step`'s return is a tagged
  union on `status`; adding `dead` and `waiting` is additive, and `ok`/`retry`/`skipped`/`idle` keep
  their existing shapes so the two existing tests continue to pass unmodified.
* **Data model impact:** message gains optional `lastError: string` and `nextAttemptAt: number`;
  queue gains `dead: []` and `stats: {...}`. In-memory only — no tables, no migration.
* **NFR targets:** `step` stays synchronous and allocation-light; the due-scan is O(n) in
  `pending.length` with n expected in the hundreds, which is acceptable and explicitly not
  optimized here. No wall-clock read anywhere except `step`'s own default argument.

## 🔎 Codebase Survey
* **Explored:** `CLAUDE.md`, `package.json`, `src/queue.js` (39 lines, read in full),
  `test/queue.test.js` (20 lines, read in full). The whole repo is those four files.
* **Integrate with:**
  * Plain ES modules, `"type": "module"`, **named exports only, no default export** (CLAUDE.md).
  * Node's built-in test runner only: `npm test` → `node --test test/*.test.js`. No third-party
    dependencies — so no jest/sinon fake timers, which is why the clock is a parameter.
  * Tests mirror source filenames: `src/queue.js` → `test/queue.test.js`.
  * `HANDLERS` is a **module-level `Map`** shared across all queues and never cleared; the existing
    tests rely on that. New tests must use distinct `type` strings rather than assuming isolation.
  * `enqueue` currently does `queue.pending.push({ attempts: 0, ...message })` — the spread means a
    caller can override `attempts`, which the edge cases above deliberately preserve.

## 🌐 Reality Constraints

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| `Date.now()` (only as `step`'s default arg) | none | `number` — integer ms since epoch | monotonicity: NTP or a manual clock change can move it backwards, so a `nextAttemptAt` may become due early or late; also no sub-ms resolution |
| registered handler `fn(payload)` (caller-supplied, via `registerHandler`) | must be registered before a message of that type is stepped; `HANDLERS` is global and never cleared, so a registration leaks across queues and across tests in one process | return value is ignored; may throw anything | that it throws an `Error` — it may throw a string, `null`, or `undefined`; that it is synchronous — a returned Promise is **not** awaited, so an async rejection is invisible to `step` and counts as `ok`; that it has no side effects on the message object it was handed |
| alert sink `fn({id, type})` (caller-supplied, via `setUnhandledTypeAlert`) | must be set before the first unhandled type is stepped, else `step` throws | return value ignored | that it does not itself throw — if it throws, that exception propagates out of `step` after the message has already been restored to `pending`; that it is delivered anywhere (it may be a no-op the operator never sees) |
| Node built-in test runner (`node --test`) | tests in `test/*.test.js` | — | test-file isolation: all test files may share one process, so module-level `HANDLERS` state is shared |

### Paths that must agree
* `queue.stats.deadLettered` ↔ `queue.dead.length` — **equivalent means:** exactly equal after every
  `step` return · **may differ:** never, within this module; they diverge only if a caller mutates
  `queue.dead` directly, which is out of contract.
* `queue.stats.ok` ↔ `queue.done.length` — **equivalent means:** exactly equal after every `step`
  return · **may differ:** never, same caveat.
* The backoff written at requeue time (`nextAttemptAt`) ↔ the policy `1000 * 2^(attempts-1)` —
  **equivalent means:** for any message in `pending` with `attempts >= 1` and a known requeue
  timestamp, `nextAttemptAt - requeuedAt` equals the policy for that `attempts` · **may differ:**
  a message enqueued by a caller with its own `nextAttemptAt` is exempt (see Edge Cases).

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| clock (`Date.now()`) | 📌 pinned — every test passes an explicit integer `now` to `step` | a test that lets the real clock decide whether a message is due passes or fails by timing; the parameter exists precisely so tests never read the wall clock |
| `step`'s default `now = Date.now()` | 📌 pinned by one dedicated test asserting the default is *used* (two calls with no `now`, asserting a `nextAttemptAt` within a generous bound of the observed `Date.now()`), never used elsewhere | the default is real behavior and must be covered once, but must not leak into the timing-sensitive tests |
| randomness | 🌊 n/a — none introduced; the backoff has no jitter | jitter was not asked for and would make the `nextAttemptAt` ACs unassertable |
| timezone / locale | 🌊 floating | only epoch-ms arithmetic; no formatting or parsing |
| filesystem / network / env | 🌊 n/a — untouched | in-memory module with no I/O and no env vars |
| module-level `HANDLERS` map | 🌊 floating (shared), mitigated by unique `type` strings per test | the repo's existing tests already depend on this global; clearing it would break them, so tests must avoid collisions instead |

## 🗂️ Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `src/queue.js` | edit | ✅ exists (39 lines, read) | all behavior lives here: `createQueue` shape, `step`'s due-scan / dead-letter / alert branches, new `setUnhandledTypeAlert`, `successRate`, and the three error classes |
| `test/queue.test.js` | edit | ✅ exists (20 lines, read) | the repo's mirror convention puts `src/queue.js` tests here and nowhere else; the two existing tests stay as-is and new cases are appended |
| `CLAUDE.md` | none | ✅ exists | conventions unchanged; no new dependency, no new script |

No new files. The whole feature fits the existing two-file layout, and adding a third source file
would break the stated `src/x.js` → `test/x.test.js` mirroring for no benefit.

## 🔗 Dependencies
* None. No new packages (CLAUDE.md forbids them), no schema changes, no migrations, no env vars,
  no feature flags. `1000` (base delay ms) and `3` (attempt cap) are module-level constants in
  `src/queue.js`.

## 🎯 Acceptance Criteria
* [ ] **AC-1** `createQueue()` returns an object with `pending: []`, `done: []`, `dead: []`, and
      `stats: { ok: 0, retried: 0, deadLettered: 0, skipped: 0 }`.
* [ ] **AC-2** **Given** a handler that always throws `new Error('nope')` and one message enqueued
      at `attempts: 0` **When** `step(q, 1000)` runs **Then** it returns
      `{ status: 'retry', id, attempts: 1 }`, `q.pending[0].attempts === 1`,
      `q.pending[0].lastError === 'nope'`, `q.pending[0].nextAttemptAt === 2000`, and
      `q.stats.retried === 1`.
* [ ] **AC-3** **Given** that same message after its first failure **When** `step(q, 2000)` runs
      **Then** `attempts === 2` and `nextAttemptAt === 4000` (`2000 + 2000`).
* [ ] **AC-4** **Given** that message at `attempts: 2` **When** `step(q, 4000)` runs **Then** it
      returns `{ status: 'dead', id, attempts: 3 }`, `q.pending.length === 0`,
      `q.dead.length === 1`, `q.dead[0].attempts === 3`, `q.dead[0].lastError === 'nope'`,
      `q.dead[0].deadLetteredAt === 4000`, and `q.stats.deadLettered === 1`.
* [ ] **AC-5** No 4th attempt is possible: after AC-4, a further `step(q, 999999)` returns
      `{ status: 'idle' }` and `q.dead.length` is still 1.
* [ ] **AC-6** **Given** `pending` is exactly `[A(nextAttemptAt: 5000), B(no nextAttemptAt)]` and
      both types have working handlers **When** `step(q, 1000)` runs **Then** B is handled
      (`status: 'ok'`, `id === B.id`) and `pending` is exactly `[A]`.
* [ ] **AC-7** **Given** `pending` is exactly `[A(nextAttemptAt: 5000), C(nextAttemptAt: 3000)]`
      **When** `step(q, 1000)` runs **Then** it returns `{ status: 'waiting', nextDueAt: 3000 }`,
      `pending` is still exactly `[A, C]` in that order, and every counter in `q.stats` is 0.
* [ ] **AC-8** **Given** a message `{ id: 9, type: 'ghost' }` with no handler and a sink recording
      its calls **When** `step(q, 1000)` runs **Then** the sink was called exactly once with
      `{ id: 9, type: 'ghost' }`, the result is `{ status: 'skipped', id: 9 }`,
      `q.pending.length === 1`, `q.pending[0].attempts === 0`,
      `q.pending[0].nextAttemptAt === undefined`, `q.pending[0].lastError === undefined`, and
      `q.stats.skipped === 1`.
* [ ] **AC-9** **Given** the same message and `setUnhandledTypeAlert(null)` **When** `step(q, 1000)`
      runs **Then** it throws `UnhandledMessageTypeError` whose message contains `'ghost'`, and
      `q.pending.length === 1` with `q.pending[0].attempts === 0`.
* [ ] **AC-10** **Given** a handler that throws the string `'plain'` (not an `Error`) **When**
      `step(q, 1000)` runs **Then** `q.pending[0].lastError === 'plain'`.
* [ ] **AC-11** **Given** 9 messages handled successfully and 1 dead-lettered **Then**
      `successRate(q) === 0.9`; **Given** a fresh queue **Then** `successRate(q) === null`.
* [ ] **AC-12** `stats.ok === done.length` and `stats.deadLettered === dead.length` hold after each
      of a 12-step mixed sequence (successes, retries, one dead-letter, one skip).
* [ ] **AC-13** `step(q)` called with no `now` argument writes a `nextAttemptAt` on a failing
      message that is `>= tBefore + 1000` and `<= tAfter + 1000`, where `tBefore`/`tAfter` bracket
      the call via `Date.now()` — proving the default argument is wired to the real clock.
* [ ] **AC-14** The two pre-existing tests in `test/queue.test.js`
      (`'runs a registered handler'`, `'retries a throwing handler'`) pass **unmodified**, proving
      the `ok`/`retry` shapes stayed backward-compatible.
* [ ] **AC-15** `npm test` (`node --test test/*.test.js`) exits 0.

## 🎯 AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| AC-1 | `src/queue.js` — `createQueue` returns `dead` + `stats` |
| AC-2 | `src/queue.js` — failure branch: increment, `lastError`, `nextAttemptAt`, `stats.retried` |
| AC-3 | `src/queue.js` — backoff formula `1000 * 2 ** (attempts - 1)` |
| AC-4 | `src/queue.js` — cap check `attempts >= 3` → push to `queue.dead` with `deadLetteredAt` |
| AC-5 | `src/queue.js` — dead-lettered message is removed from `pending`, never re-pushed |
| AC-6 | `src/queue.js` — due-scan selects first message with `nextAttemptAt` absent or `<= now` |
| AC-7 | `src/queue.js` — none-due branch returns `{ status: 'waiting', nextDueAt }` with no mutation |
| AC-8 | `src/queue.js` — `!handler` branch: restore message, invoke sink, `stats.skipped` |
| AC-9 | `src/queue.js` — `!handler` branch with no sink: throw `UnhandledMessageTypeError` |
| AC-10 | `src/queue.js` — `lastError = err instanceof Error ? err.message : String(err)` |
| AC-11 | `src/queue.js` — `successRate` export, `null` on zero denominator |
| AC-12 | `src/queue.js` — stats-drift guard at each `step` return (`StatsDriftError`) |
| AC-13 | `src/queue.js` — `step(queue, now = Date.now())` default parameter |
| AC-14 | `test/queue.test.js` — existing two tests left byte-identical; `ok`/`retry` shapes preserved |
| AC-15 | `test/queue.test.js` — all new cases appended in the same file, run by `npm test` |

## ⚠️ Risks & Watch-outs
* **Shared `HANDLERS` map.** Module-global and never cleared, so a `type` string registered in one
  test leaks into every later test in the process. New tests must use unique type names
  (`'boom-cap'`, `'ghost'`, …) rather than reusing `'boom'` or `'email'`, or AC-14's existing tests
  can be perturbed by ordering.
* **The two existing tests are a compatibility fence.** `'retries a throwing handler'` asserts
  `step(q).attempts === 1` and `q.pending.length === 1` while calling `step` with **no** `now` — so
  the default parameter and the `retry` status shape are both load-bearing. Changing either breaks
  a test the implementation stage is not allowed to edit.
* **Async handlers are silently "successful."** A handler returning a rejected Promise is counted
  `ok`, because `step` is synchronous and does not await. This is pre-existing behavior, documented
  above rather than fixed here — but it means `successRate` can overstate success for an async
  caller.
* **`nextAttemptAt` and a non-monotonic clock.** A backwards clock jump delays retries; a forward
  jump releases them early. Acceptable for an in-memory queue, but no test should assert timing
  against the real clock (hence the pinning table).
* **Unbounded `queue.dead`.** A permanently broken handler now accumulates entries in memory
  instead of cycling `pending`. Bounded only by operator intervention, which does not exist yet.
* **`step` now has six possible `status` values.** Any existing caller doing an exhaustive switch
  over `ok`/`retry`/`skipped`/`idle` will fall through on `dead` and `waiting`. No such caller
  exists in this repo, but a consumer outside it would need updating.

## 🚫 Out of Scope
* Draining / requeueing `queue.dead` back into `pending` after a fix — explicitly deferred.
* Eviction, size cap, or persistence for `queue.dead`.
* Jitter on the backoff, per-type retry caps, or per-type backoff policy.
* Async / Promise-aware handlers, and awaiting handler results.
* Any structured logging, metrics export, or dashboard — `queue.stats` and `successRate` are the
  whole observability surface here.
* Clearing or scoping the global `HANDLERS` map.

## 🔀 Flags
* `needs_ba`: **true** — the retry cap's counting semantics, the config-fault-vs-data-fault
  distinction for an unhandled type, and the success-rate denominator are all domain rules a
  developer would otherwise have to guess; enumerated as BR-1…BR-5.
* `needs_ui`: **false** — no page, route, modal, form, or user-visible state. The operator-facing
  output is plain data on the queue object; nothing renders.
* `needs_sa`: **true** — competing approaches with lasting consequences (absolute `nextAttemptAt`
  vs. recomputed delay vs. real timers) plus a hard constraint from the repo's no-dependency,
  synchronous-API rules; resolved in Solution Architecture.
* `needs_devops`: **false** — no env vars, migrations, feature flags, or infra. The cap and base
  delay are in-code constants and the module is in-memory.

## ❓ Open Items
* ⚠️ **OPEN — base backoff delay.** The grilled idea settled on "a backoff based on attempt count,
  read off the wall clock" but never named a base. This spec commits to `1000 * 2^(attempts-1)`
  (1s then 2s) so the ACs are exactly assertable; it is a single module constant and a reviewer may
  want a different base. Changing it after `freeze-tests` costs a `reworking` bounce, so confirm the
  number now if there is any doubt.
* ⚠️ **OPEN — is throwing the right escalation for a missing handler?** The idea says "somebody
  needs to find out," which this spec implements as: alert sink if configured, otherwise throw out
  of `step`. The alternative — always throw, no sink — is simpler but makes a single bad message
  type halt the whole worker permanently. The sink was chosen because it keeps the loop's failure
  policy in the caller's hands, but it does mean a caller can register a no-op sink and get exactly
  the silence the requirement forbids. No mechanism here prevents that.
