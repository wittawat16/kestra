# ☕ [batch-chunk] Spec — chunk a message array into capped batches

> **Status:** 🟢 READY_FOR_BUILD | **Created:** 2026-07-28
> **Next:** 🏗️ kestra-build

---

## ☕ Overview
Add a pure helper, `chunkByCap(items, cap)`, to `src/queue.js`. It splits an array into
consecutive sub-arrays of at most `cap` items each, preserving input order, with no side effects
and no dependency on anything outside its arguments. Intended for a caller that wants to hand a
worker's `pending` array to an external batch API in capped groups — but this function itself
never touches the queue, the clock, or any external system.

## 🪵 Problem Statement
* Nothing in the repo currently splits an array into fixed-size groups; callers would otherwise
  hand-roll a loop each time they need this, with a good chance of getting the last (short) group
  wrong.
* 🎯 **Goal:** one small, pure, exhaustively-testable function other code can rely on.

## 🥑 Functional Requirements
* [ ] `chunkByCap(items, cap)` returns an array of arrays; each inner array has at most `cap`
  elements; concatenating all inner arrays in order reproduces `items` exactly (same order, same
  elements, no copies/drops).
* [ ] The last chunk may be shorter than `cap` — it is never padded.
* [ ] `items` is never mutated by the call.

## 🌤️ Edge Cases & Error States
* **`items` is empty:** returns `[]` (zero chunks, not `[[]]`).
* **`cap` >= `items.length`:** returns a single chunk containing all of `items`.
* **`cap` is not a positive integer** (zero, negative, non-integer, or not a number): throws
  `TypeError` synchronously, before touching `items` — this is a caller bug (bad argument), not a
  runtime condition to guard silently.
* **`items` is not an array:** throws `TypeError` synchronously, same reasoning as above.

## 🛡️ Runtime Invariants
None. This function has no state, no I/O, and no failure mode that could pass unnoticed — every
way it can go wrong (bad `cap`, bad `items`) is a synchronous thrown `TypeError` at the call site,
already covered by the Edge Cases and Acceptance Criteria above. There is no condition here whose
violation could go undetected in production the way a silent state-drift or a swallowed error
would; a caller passing a bad argument gets an immediate, loud, synchronous exception every time.

## 🔎 Codebase Survey
* **Explored:** `src/queue.js` (39 lines — `createQueue`, `enqueue`, `step`, `registerHandler`,
  the `HANDLERS` map), `test/queue.test.js`, `CLAUDE.md`.
* **Integrate with:** `src/queue.js` — CLAUDE.md states one source file maps to one test file
  (`src/queue.js` -> `test/queue.test.js`); `chunkByCap` is added as a new named export in the same
  file rather than a new module, since the fixture has exactly one source/test pair and no existing
  convention for splitting a file by concern.

## 🌐 Reality Constraints

### External dependencies
None — `chunkByCap` reads only its own two arguments and touches no shared state, no clock, no
network, no filesystem.

### Paths that must agree
None — single implementation, no alternate/replay path.

### Non-deterministic inputs
None — no clock, randomness, locale, network, or filesystem read anywhere in this function.

## 🗂️ Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| src/queue.js | edit | ✅ exists (39 lines, read in full) | add `chunkByCap` as a new named export |
| test/queue.test.js | edit | ✅ exists | add tests for `chunkByCap`, appended after the two existing tests |

## 🔗 Dependencies
None — no new packages, no migrations, no infra.

## 🎯 Acceptance Criteria
* [ ] `chunkByCap([1,2,3,4,5], 2)` returns `[[1,2],[3,4],[5]]`
* [ ] `chunkByCap([], 3)` returns `[]`
* [ ] `chunkByCap([1,2], 10)` returns `[[1,2]]`
* [ ] `chunkByCap([1,2,3], 0)` throws `TypeError`
* [ ] `chunkByCap([1,2,3], -1)` throws `TypeError`
* [ ] `chunkByCap([1,2,3], 1.5)` throws `TypeError`
* [ ] `chunkByCap("not an array", 2)` throws `TypeError`
* [ ] calling `chunkByCap` on an array does not mutate that array (reference equality check on
  each original element position after the call)

## 🎯 AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| basic chunking, exact partition | src/queue.js: chunkByCap; test/queue.test.js |
| empty input -> [] | src/queue.js: chunkByCap; test/queue.test.js |
| cap >= length -> one chunk | src/queue.js: chunkByCap; test/queue.test.js |
| invalid cap -> TypeError (3 cases) | src/queue.js: chunkByCap; test/queue.test.js |
| non-array items -> TypeError | src/queue.js: chunkByCap; test/queue.test.js |
| no mutation | src/queue.js: chunkByCap; test/queue.test.js |

## ⚠️ Risks & Watch-outs
None — pure function, no shared state touched, no migration, no concurrency.

## 🚫 Out of Scope
* Wiring `chunkByCap` into `step`/the worker loop itself — this spec is the utility only.
* Async/streaming chunking.

## 🔀 Flags
* `needs_ba`: false — no domain rules, single deterministic behavior
* `needs_ui`: false — no user-facing surface
* `needs_sa`: false — single file, single approach, no NFRs
* `needs_devops`: false — no env vars, migrations, flags, or infra

## ❓ Open Items
None.
