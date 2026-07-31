# [priority-tier] Spec — Tier-based retry policy for the in-memory queue

> Status: READY_FOR_BUILD | Created: 2026-07-31 | Next: kestra-build

---

## Overview
Per-message `tier` (`'paid'` | `'free'`) decides failure handling: paid retries forever (today's
behaviour), free is dropped after one attempt into a new `dropped` list; `stats()` exposes
succeeded-vs-dropped per tier so operators can price the one-shot policy.

## Problem Statement
* Today `step()` treats every handler throw identically — `attempts += 1`, back to `pending` tail,
  forever (`src/queue.js:34-38`). No tier concept exists; `createQueue()` returns `{pending, done}`
  only (verified).
* Free-tier traffic therefore consumes unbounded retry capacity it has no SLA for.
* No per-tier outcome visibility exists — nothing counts anything.
* Goal: free-tier failures cost exactly one attempt and land in an inspectable `dropped` list; paid
  failure behaviour byte-identical to today; `stats(queue)` returns exact per-tier done/dropped
  counts.

## Functional Requirements
* [ ] `createQueue()` returns `{ pending: [], done: [], dropped: [], enqueued: 0 }` — two new keys.
* [ ] `enqueue()` normalizes tier: stored `tier` is `'free'` iff `message.tier === 'free'` (strict),
      else `'paid'`. Normalized value overrides whatever the caller passed.
* [ ] `enqueue()` increments `queue.enqueued`.
* [ ] Given a paid-tier message / When its handler throws / Then `attempts += 1`, message goes to the
      `pending` tail, return `{ status: 'retry', id, attempts }` — unchanged from today.
* [ ] Given a free-tier message / When its handler throws / Then `attempts += 1` (to exactly 1), the
      message is pushed to `queue.dropped`, is **not** returned to `pending`, and `step()` returns
      `{ status: 'dropped', id, attempts: 1 }`.
* [ ] Given a message of either tier / When no handler is registered for its `type` / Then it returns
      to the `pending` tail untouched, `attempts` unchanged, return `{ status: 'skipped', id }` —
      tier is never consulted on this path.
* [ ] Given a message of either tier / When its handler returns normally / Then it goes to
      `queue.done` and returns `{ status: 'ok', id }` — unchanged from today.
* [ ] New export `stats(queue)` → `{ paid: { done, dropped }, free: { done, dropped } }`, derived by
      counting `queue.done` / `queue.dropped`; no stored counters.
* [ ] Existing exports `registerHandler`, `enqueue`, `step`, `createQueue` keep their current names
      and signatures; `stats` is added as a **named** export (repo convention: no default exports).

## Edge Cases & Error States
* **`tier` absent (un-migrated caller):** normalized to `'paid'` at enqueue. Verified the safe path —
  never drops a message from a caller that has not opted in.
* **`tier: undefined` passed explicitly:** normalized to `'paid'`. Note the trap — the repo's existing
  default idiom `{ attempts: 0, ...message }` (`src/queue.js:15`) does **not** cover this: spreading a
  key whose value is explicitly `undefined` *overwrites* the default with `undefined` (verified). The
  normalized `tier` must be applied **after** the spread, not as a pre-spread default.
* **`tier` is `null` / `''` / `'PAID'` / `'Free'` / a number / an object:** all normalize to `'paid'`
  (strict `=== 'free'` is the only free branch). No throw, no warning — a typo costs retries, never a
  silent drop.
* **Caller supplies `attempts`:** survives (spread order, verified — `attempts: 7` stays 7). A
  free-tier message enqueued with `attempts: 5` is dropped on its first failure returning
  `attempts: 6` (verified) — the "exactly one attempt" rule counts attempts *this queue* performed,
  not the field's value. BR-3/AC-5's `attempts: 1` assume the default `attempts: 0`; the invariant
  underneath is "exactly one increment, then terminal", not "the field equals 1".
* **Empty queue:** `{ status: 'idle' }`, no tier logic runs, no conservation check.
* **`stats()` on a fresh queue:** all four counts `0` — never a missing key.
* **Handler throws a non-`Error` (string, `undefined`):** caught identically; tier policy applies
  normally (verified).
* **Handler is `async` and rejects:** the rejection escapes `step()`'s `try/catch` entirely — the
  message counts as `'ok'`, lands in `done`, and an `unhandledRejection` fires (verified). Tier policy
  never applies. Out of scope to fix; named here so nobody writes a test asserting otherwise.
* **Message pushed directly onto `queue.pending`, bypassing `enqueue()`:** un-normalized `tier`
  reaches `step()` → Runtime Invariant INV-1 (halt), not a silent coercion.
* **Duplicate `id`s:** nothing enforces uniqueness today and nothing will; counts are per-message, not
  per-id.

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| INV-1: every message `step()` processes carries `tier` exactly `'paid'` or `'free'` | explicit `tier !== 'paid' && tier !== 'free'` check in `step()`, placed **after** `pending.shift()` and **before** `HANDLERS.get()` — i.e. outside the handler `try/catch` (verified: a check inside that block would be converted into a `retry` and hidden) | halt — `unshift` the message back to the `pending` head so queue state is unchanged, then `throw new TypeError` naming `id` and the offending tier. Propagates uncaught to the caller; the only caller in this repo is the test runner (verified: `grep -rn "step(" src test` → `src/queue.js:20`, `test/queue.test.js:10,18`), so it surfaces as a failing test. No supervisor exists to swallow it. |
| INV-2: no message is lost — `pending.length + done.length + dropped.length === queue.enqueued` | O(1) check at the end of every non-idle `step()` (all three terminal branches: skipped / ok / retry / dropped) | halt — `throw new Error` naming both numbers. Same propagation as INV-1. |
| INV-3: every message counted by `stats()` carries a recognized tier | explicit tier check inside `stats()`'s accumulation loop, before the counter increment | halt — `throw new TypeError` naming `id` and the tier. Today an unguarded `out[m.tier].done += 1` already halts, but with `Cannot read properties of undefined (reading 'done')` (verified) — it names neither the message nor the field, so the guard is about the operator learning *what* is malformed, not about halting vs. not. |

## Business Rules  *(needs_ba: true)*

* **BR-1 — Tier resolution is strict-equality, at enqueue, once.**
  Given `enqueue(q, { id: 1, type: 't', payload: null, tier: 'free' })` / When the message is stored /
  Then `q.pending[0].tier === 'free'`.
  Counter-example: `tier: 'Free'`, `tier: ''`, `tier: null`, `tier: undefined`, or no `tier` key →
  `q.pending[0].tier === 'paid'` (all verified). Rationale: silently downgrading an un-migrated
  caller to drop-on-failure is the regression nobody asked for; the failure mode of the opposite
  default is only wasted retries.

* **BR-2 — Paid failure behaviour is frozen, not re-derived.**
  Given a `tier: 'paid'` message whose handler throws / When `step()` runs / Then `attempts` is
  incremented, the message returns to the `pending` **tail** (not head), and the return value is
  exactly `{ status: 'retry', id, attempts }`.
  And a second `step()` returns `attempts: 2` — retried indefinitely, no cap.
  Counter-example: a paid message must never appear in `queue.dropped` under any failure count.

* **BR-3 — Free failure is one attempt, terminal.**
  Given a `tier: 'free'` message enqueued with the default `attempts: 0` whose handler throws / When
  `step()` runs / Then `attempts` is incremented exactly once (to 1), the message is appended to
  `queue.dropped`, `queue.pending` no longer contains it, and the
  return value is exactly `{ status: 'dropped', id, attempts: 1 }`.
  And a subsequent `step()` on an otherwise-empty queue returns `{ status: 'idle' }` (verified).
  Counter-example: a free message that *succeeds* goes to `done` like any other — the tier only
  changes the failure branch.

* **BR-4 — The skip path is tier-blind.**
  Given a message with no registered handler for its `type`, of **either** tier / When `step()` runs /
  Then it is pushed back to `pending` with `attempts` unchanged and returns `{ status: 'skipped', id }`
  (verified for both tiers).
  Counter-example: a free-tier message with no handler must **not** be dropped — "no handler yet" is
  not a delivery failure, and dropping it would silently discard traffic during a deploy where the
  handler registers late.

* **BR-5 — `dropped` is terminal within this feature.**
  Given a message in `queue.dropped` / When any number of `step()` calls run / Then it is never moved
  back to `pending`, `done`, or re-attempted. No API to resurrect it (see Out of Scope).

* **BR-6 — Operator visibility is counts, not verdicts.**
  Given a queue that has processed 1 paid success, 1 free success, 1 free failure / When
  `stats(queue)` is called / Then it returns exactly
  `{ paid: { done: 1, dropped: 0 }, free: { done: 1, dropped: 1 } }` (verified).
  Counter-example: `stats()` does not compute a failure *rate* — the rate is one division at the call
  site and `0/0` has no settled answer here.

* Stakeholder variations:
  | Stakeholder | Cares about | Behaviour difference |
  |---|---|---|
  | Paid customer | eventual-delivery SLA | unbounded retries; drop is unreachable for them (BR-2) |
  | Free customer | none contractual | exactly one attempt, then `dropped` (BR-3) |
  | Un-migrated caller (no `tier`) | not regressing | treated as paid (BR-1) |
  | Operator | is one-shot costing us delivery? | `stats()` per-tier done/dropped (BR-6) |
  | Handler author | nothing — cannot see tier | handlers receive `message.payload` only, never the message (verified `src/queue.js:31`); tier is a queue-level policy, not a handler input |

## Codebase Survey
* Explored (read in full): `workflow/evals/2026-07-31-spec-model-compare/fixture/CLAUDE.md`,
  `.../fixture/package.json`, `.../fixture/src/queue.js` (39 lines),
  `.../fixture/test/queue.test.js` (20 lines). `src/` and `test/` contain nothing else (verified by
  `ls -laR`).
* Integrate with:
  * ES modules, **named exports only, no default exports** (CLAUDE.md) — `stats` follows.
  * No build step, no TypeScript, **no third-party dependencies — keep it that way** (CLAUDE.md).
  * Node's built-in test runner only: `npm test` → `node --test test/*.test.js` (package.json,
    verified exit 0 on Node v24.15.0).
  * Test file mirrors source filename (CLAUDE.md): `src/queue.js` → `test/queue.test.js`. **All new
    tests go in that one existing file** — do not create `test/tier.test.js`.
  * Existing idiom for defaults is the object spread at `src/queue.js:15` — reuse it, with the
    normalized `tier` applied after the spread (see Edge Cases).
  * `step()`'s existing structure: `shift()` → falsy guard → handler lookup + skip branch → `try`
    around handler call only. New tier checks slot in as a third guard before the lookup.

## Solution Architecture  *(needs_sa: true)*
Chosen approach: **A — normalize tier at enqueue; branch on it in `step()`'s catch; derive stats by
scanning `done`/`dropped`** — every downstream reader sees an already-valid tier, and derived counts
cannot drift from the arrays they describe.

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A — normalize at `enqueue`, derive stats from arrays | one normalization site; `step()` and `stats()` both see a two-valued field; counts are a pure function of state, so no drift is representable | O(n) per `stats()` call; `dropped` grows unbounded in memory | **chosen** — n is a small in-memory queue, and unbounded `dropped` is the point (operators inspect it) |
| B — normalize lazily inside `step()` | no change to `enqueue`/stored shape | `pending` then holds un-normalized tiers, so every future reader must re-normalize; INV-1 becomes unstateable (there is no "already valid" moment) | rejected — pushes the same decision into every call site |
| C — maintain incremented counters on the queue (`queue.stats.free.dropped++`) | O(1) reads | two representations of one fact; a missed increment is silent and undetectable after the fact — exactly the drift class INV-2 exists to catch | rejected — buys O(1) on a lookup nobody has said is hot |
| D — throw on an unrecognized `tier` at enqueue | typos surface immediately | contradicts the settled "safer default" rule (BR-1) and breaks every un-migrated caller at once | rejected — the settled decision is coerce-to-paid |

* Integration contracts:
  * `step()` gains a fourth return `status` value, `'dropped'`. Callers that `switch` on status and
    have no `default` branch will silently ignore it. No such caller exists in this repo (verified:
    only `test/queue.test.js` calls `step()`), but it is a breaking change for any out-of-repo worker
    loop.
  * `createQueue()` gains keys `dropped` and `enqueued`. Any caller doing a `deepEqual` on a whole
    queue object breaks; the two existing tests do not (verified — they assert on
    `q.pending.length` and on `step()`'s return, and both pass unchanged against a prototype,
    `npm test` exit 0).
  * `stats(queue)` is new; no existing caller.
* Data model impact: in-memory only, no persistence, no migration. Queue shape
  `{ pending, done, dropped, enqueued }`; message shape gains a normalized `tier` string.
* NFR targets: none stated and none invented. `stats()` is O(done + dropped); `step()` stays O(1)
  plus the O(1) conservation check.

## Reality Constraints
*(verified by running/reading, not assumed — probe scripts run against the real fixture and against a
throwaway prototype in a scratch dir; the fixture itself was not modified.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| `HANDLERS` module-level `Map` + `registerHandler` (`src/queue.js:4-8`) | a type must be registered before a `step()` that pulls it, else the skip path | `Map<string, Function>`; `registerHandler` returns `undefined` | **no per-queue or per-test isolation** — one Map shared by every `createQueue()` in the process (verified: two queues, one registration, both `ok`); **no unregister/reset export exists**; re-registering a type silently overwrites (verified); no arity/async validation of `fn` |
| Caller-supplied handler `fn` | invoked as `handler(message.payload)` — receives the payload only, never the message, so it cannot read or set `tier` (verified) | return value ignored entirely | **not guaranteed synchronous** — an `async` handler's rejection escapes the `try/catch`, the message is recorded `'ok'` into `done`, and `unhandledRejection` fires (verified); **not guaranteed to throw an `Error`** — a thrown string is caught identically (verified); no guarantee it is pure or does not mutate `payload` |
| Message object supplied by the caller to `enqueue` | none | stored as `{ attempts: 0, ...message }` — arbitrary extra keys pass through untouched (verified: a `bogus` key survives) | **no `id` uniqueness**, no schema validation, no type checking; a caller-supplied `attempts` **overrides** the default `0` (verified: `attempts: 7` stays 7); a caller-supplied `tier` must therefore be overridden *after* the spread, not before |
| `node:test` + `node:assert/strict` via `npm test` (`node --test test/*.test.js`, Node v24.15.0) | glob is `test/*.test.js` — a new test file outside that pattern is silently not run | exit 0 on pass (verified, both fixture and prototype) | **no test isolation within a file** — all tests in `test/queue.test.js` share one process and therefore one `HANDLERS` map; no automatic module-state reset between tests |

### Paths that must agree
* `step()`'s returned `status` stream ↔ `stats(queue)` — equivalent means: over one queue's whole
  lifetime, per tier, `count(status === 'ok') === stats.<tier>.done` and
  `count(status === 'dropped') === stats.<tier>.dropped` · may differ: a caller that starts tallying
  mid-run, or one that restarts (state is in-memory only), sees fewer than `stats()`, which is
  cumulative from `createQueue()`.
* Caller's own message object reference ↔ the object in `queue.dropped` / `queue.done` — equivalent
  means: identical object, not a copy (verified: `queue.dropped[0] === the enqueued object` after a
  free-tier failure) · may differ: nothing may differ — which is the hazard, since `attempts` is
  mutated **in place**, so a caller holding the reference observes the increment.

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| Module-level `HANDLERS` map | floating — **cannot be pinned, no reset export exists** | mitigation is mandatory: every test must use a `type` string unique to that test (the existing file already does: `'email'`, `'boom'`). A test reusing another's `type` silently inherits its handler. |
| Clock / date | N/A — not read | no timestamps, no TTL, no backoff anywhere in the feature (verified: `src/queue.js` contains no `Date`/`setTimeout`) |
| Randomness | N/A — not read | `id`s are caller-supplied, nothing generates one |
| Network / filesystem / env vars | N/A — not read | in-memory, zero dependencies, no `process.env` access |
| Iteration order | pinned by construction | arrays with `push`/`shift` only; `stats()` iterates arrays, never an object's keys |

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `workflow/evals/2026-07-31-spec-model-compare/fixture/src/queue.js` | edit | exists (read, 39 lines) | `createQueue` (+`dropped`,+`enqueued`), `enqueue` (tier normalization + `enqueued++`), `step` (INV-1 guard, free-drop branch, INV-2 check), new `stats` export |
| `workflow/evals/2026-07-31-spec-model-compare/fixture/test/queue.test.js` | edit | exists (read, 20 lines) | CLAUDE.md mandates one test file mirroring the source filename — all new tests append here; the two existing tests stay byte-identical (verified they pass unchanged) |

## Dependencies
* None. No new packages (CLAUDE.md forbids third-party deps), no schema changes, no migrations, no
  env vars, no feature flags.

## Acceptance Criteria
* [ ] AC-1: `createQueue()` returns an object whose keys are exactly
      `['pending','done','dropped','enqueued']` with values `[], [], [], 0`.
* [ ] AC-2: Given `enqueue(q, {id:1,type:'t',payload:null,tier:'free'})` / When stored / Then
      `q.pending[0].tier === 'free'` and `q.enqueued === 1`.
* [ ] AC-3: For each of `undefined` (explicit), `null`, `''`, `'PAID'`, `'Free'`, `'gold'`, `0`, `{}`,
      and a message with no `tier` key at all — after `enqueue`, `q.pending[0].tier === 'paid'`.
      (All nine cases verified against a prototype.)
* [ ] AC-4: Given a paid message whose handler throws / When `step()` runs / Then it returns exactly
      `{status:'retry', id, attempts:1}`, `q.pending.length === 1`, `q.dropped.length === 0`; and a
      second `step()` returns `attempts: 2`.
* [ ] AC-5: Given a free message whose handler throws / When `step()` runs / Then it returns exactly
      `{status:'dropped', id, attempts:1}`, `q.pending.length === 0`, `q.dropped.length === 1`,
      `q.dropped[0].attempts === 1`; and a following `step()` returns `{status:'idle'}`.
* [ ] AC-6: Given a message with no registered handler, for `tier:'free'` **and** `tier:'paid'` /
      When `step()` runs / Then it returns exactly `{status:'skipped', id}`, `q.pending.length === 1`,
      `q.pending[0].attempts === 0`, `q.dropped.length === 0`.
* [ ] AC-7: Given a free message whose handler returns normally / When `step()` runs / Then it returns
      `{status:'ok', id}` and the message is in `q.done`, not `q.dropped`.
* [ ] AC-8: Given a queue with 1 paid success, 1 free success, 1 free failure / When `stats(q)` /
      Then it deep-equals `{paid:{done:1,dropped:0}, free:{done:1,dropped:1}}`.
* [ ] AC-9: `stats(createQueue())` deep-equals `{paid:{done:0,dropped:0}, free:{done:0,dropped:0}}`.
* [ ] AC-10 (INV-1): Given a message pushed directly onto `q.pending` with `tier:'gold'` and
      `q.enqueued = 1` / When `step()` runs / Then it throws `TypeError`, and `q.pending` still holds
      that one message (state unchanged by the failed step).
* [ ] AC-11 (INV-1 placement): the INV-1 throw is **not** converted into a `retry` — with a
      `tier:'gold'` message whose registered handler also throws, `step()` still throws out of the
      function rather than returning `{status:'retry'}`.
* [ ] AC-12 (INV-2): Given a queue where `q.enqueued` is tampered to 99 with one real message / When
      `step()` runs / Then it throws an `Error` whose message names both counts.
* [ ] AC-13 (INV-3): Given `q.done` containing `{id:1, tier:'gold'}` / When `stats(q)` runs / Then it
      throws a `TypeError` naming the id and the tier — not `Cannot read properties of undefined`.
* [ ] AC-14: The two pre-existing tests in `test/queue.test.js` are unmodified and still pass;
      `npm test` exits 0. (Verified against a prototype: exit 0, both tests pass, test file
      byte-identical.)
* [ ] AC-15: `grep` of `src/queue.js` shows no `import`/`require` of any third-party module and no
      default export (CLAUDE.md constraints).

## AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| AC-1 | `src/queue.js` → `createQueue()` |
| AC-2, AC-3 | `src/queue.js` → `enqueue()` tier normalization applied after the object spread |
| AC-4 | `src/queue.js` → `step()` catch branch, paid path (existing code, unchanged) |
| AC-5 | `src/queue.js` → `step()` catch branch, new free path pushing to `queue.dropped` |
| AC-6 | `src/queue.js` → `step()` no-handler branch (existing code, left tier-blind) |
| AC-7 | `src/queue.js` → `step()` try branch (existing code, unchanged) |
| AC-8, AC-9 | `src/queue.js` → new `stats()` export |
| AC-10, AC-11 | `src/queue.js` → `step()` INV-1 guard placed after `shift()`, before `HANDLERS.get()`, outside `try` |
| AC-12 | `src/queue.js` → INV-2 conservation check at the end of every non-idle `step()` |
| AC-13 | `src/queue.js` → INV-3 tier guard inside `stats()`'s accumulation loop |
| AC-14 | `test/queue.test.js` → existing tests untouched; new tests appended below them |
| AC-15 | `src/queue.js` → no new imports; `export function stats` (named) |
| all ACs | `test/queue.test.js` → one `test()` per AC, unique `type` string per test (see Non-deterministic inputs) |

## Risks & Watch-outs
* **The spread-order trap.** The obvious implementation `{ attempts: 0, tier: 'paid', ...message }`
  is wrong: an explicit `tier: undefined` overwrites the default with `undefined` (verified), which
  then trips INV-1 at `step()` time rather than defaulting to paid. Normalize after the spread.
* **INV-1 guard placement.** Inside `step()`'s `try` block the throw becomes a `retry` return and the
  invariant is silently defeated (AC-11 exists to catch exactly this).
* **Shared file.** `src/queue.js` carries every change — tier logic, `dropped`, `stats`, all three
  invariants. Any parallel implement stage would collide on it; keep it one write scope.
* **Test-file pollution.** One `HANDLERS` map for the whole file, no reset export. A new test reusing
  `'email'` or `'boom'` inherits the existing tests' handlers and can pass for the wrong reason.
* **Async handlers.** Any test that uses an `async` handler to simulate failure will observe
  `status: 'ok'` and a message in `done` (verified) — a test written that way would encode the
  opposite of BR-3. Failure fixtures must throw synchronously.
* **`dropped` grows unbounded.** Deliberate (operators inspect it), but it is an in-memory leak by
  design for a long-running process.
* **`'dropped'` is a new `status` value.** Out-of-repo `switch` statements without a `default` will
  ignore it silently.

## Out of Scope
* Configurable free-tier retry count — exactly one attempt, no knob.
* Resurrecting messages from `dropped` back into `pending` (BR-5 is terminal).
* A computed failure *rate* in `stats()` — counts only; `0/0` has no settled answer.
* Per-tier `pending` counts in `stats()` — done/dropped only, as asked.
* Fixing the async-handler hole (rejections bypassing the tier policy) — documented, not repaired.
* Per-queue handler registries / a `resetHandlers()` export — the global `HANDLERS` map stays as-is.
* Persistence, TTL, backoff, dead-letter export, or any reporting surface outside the process.

## Flags
* `needs_ba`: true — multi-stakeholder policy (paid SLA vs. free no-SLA vs. un-migrated callers vs.
  operators), and the tier-resolution/skip-path rules are domain decisions, not implementation ones.
* `needs_ui`: false — no page, route, modal, form, interactive element, or visible state; `stats()`
  is a library function returning a plain object, and this repo has no UI, CLI, or HTTP surface
  (verified: `src/` contains only `queue.js`).
* `needs_sa`: true — competing approaches with lasting consequences on the persisted queue shape
  (where tier is normalized; stored vs. derived counters), resolved in Solution Architecture above.
* `needs_devops`: false — no env vars, migrations, feature flags, or infra; in-memory, zero
  dependencies, no deploy surface.

## Open Items
* How operators actually *consume* `stats()`. This repo has no CLI, HTTP, or log surface (verified:
  `src/` contains only `queue.js`), so this spec delivers the function and nothing that renders it.
  If operators need the numbers out-of-process, that is a separate feature — flagged rather than
  invented here.
