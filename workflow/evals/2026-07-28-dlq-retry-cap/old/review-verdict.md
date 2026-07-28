VERDICT: CLEAR

## Findings

| Severity | Claim | file:line |
|---|---|---|
| info (non-blocking) | Invariant 2's assertion is reachable code (executes on every requeue-to-pending) but its guard condition is logically unsatisfiable under the current control flow — see trace below. This is a legitimate defense-in-depth placement, not the same defect as the earlier dead-code finding, so it is not blocking. | src/queue.js:142-147 |

## 1. Is Invariant 2's new inline assertion genuinely reachable code (not dead)? Where does it sit relative to the dead-letter branch?

Reachable, not dead — confirmed by reading the actual uncommitted diff (`git diff HEAD -- src/queue.js`), not the prior review's stale notes about a `> RETRY_CAP` pre-decision throw (that check no longer exists in this diff; the note below in "Note on this file's prior contents" explains the discrepancy).

Trace of `step`'s catch block (src/queue.js:108-151):
- `message.attempts += 1; message.lastError = normalizeError(err);` (109-110)
- Dead-letter branch: `if (message.attempts >= RETRY_CAP)` (112) — asserts `lastError` is a string (116-120), pushes to `queue.dead`, updates stats, **returns** (124). This branch executes and returns *before* line 127 for every message whose post-increment `attempts >= RETRY_CAP`.
- Only when that `if` is false does control reach `message.nextAttemptAt = ...` (127) and then Invariant 2's check at 142-147, immediately before `queue.pending.push(message)` (149).

The assertion at 142 genuinely executes on every requeue-to-pending call — it is not an unreachable statement. However, because line 112 already tested the exact same value (`message.attempts`, unmutated between 112 and 142) and returned when it was `>= RETRY_CAP`, the condition at 142 can never be true under the code as currently written: reaching line 142 already implies `message.attempts < RETRY_CAP`. It functions as a guard against a *future* edit that decouples the two checks (e.g. inserts an extra increment between 112 and 149, or reorders the branches) rather than one that fires under any input today. That is an intentional, disclosed defensive-assertion pattern (the code comment at 130-141 says exactly this), and it satisfies the spec's literal requirement ("assertion... before the message is placed anywhere in pending") without contradicting any Edge Case or AC — not a cosmetic no-op like a console.log.

## 2. Does a message pre-seeded with attempts >= 3 now dead-letter immediately, per spec, rather than throw?

Confirmed by hand-trace and empirically. `enqueue` spreads `{ attempts: 0, ...message }`, so a caller-supplied `attempts: 3` survives. On first failure: `message.attempts` becomes 4 (109), `lastError` set (110), then the dead-letter branch (112) sees `4 >= 3` → true → asserts `lastError` is a string (it is) → pushes to `queue.dead`, increments `stats.deadLettered`, returns `{status:'dead', id, attempts:4}`. Control never reaches line 127 or the Invariant-2 throw at 142-147, so nothing throws.

Empirical confirmation (throwaway `node -e`, no files created/modified other than this verdict):
```
registerHandler('preseed', () => { throw new Error('boom'); });
enqueue(q, { id: 999, type: 'preseed', payload: null, attempts: 3 });
step(q, 0)
→ RESULT: {"status":"dead","id":999,"attempts":4}
→ dead: [{"attempts":4,"id":999,"type":"preseed","payload":null,"lastError":"boom"}]
→ pending: []
```
No `RangeError`. This matches the spec's Edge Case ("A message enqueued with `attempts` already >= 3: ... its next failure dead-letters it immediately") and the corresponding AC. **The edge-case regression from fix attempt 1 is resolved.**

## 3. Re-confirmation of previously-clear items

- **lastError normalization (src/queue.js:64-67, 110):** `normalizeError` is called exactly once per catch, at line 110, before either the dead-letter branch or the retry branch reads `message.lastError`. Both paths (dead-letter push at 121, retry requeue at 149) see the already-normalized string. No path sets `lastError` from the raw thrown value. Unchanged from prior review.
- **`waiting` branch tolerates a clock moving backwards (src/queue.js:79-82):** plain `>` comparison against `now`; no arithmetic that could throw, no assumption of monotonicity. A `now` smaller than a previous call simply makes more messages report `waiting`. Unchanged from prior review.
- **No unrequested deregister for HANDLERS or the alert sink:** `registerHandler` (19-21) and `registerAlertSink` (23-25) are unchanged — still simple `Map#set` / assignment, no clear/delete/unset added anywhere in the diff.
- **`step()` dequeues exactly one message per call:** exactly one `queue.pending.shift()` call (73), no loop around it. The `waiting` branch's `unshift` (80) puts the same message back rather than pulling another.
- **Invariant 1 (unhandled type, src/queue.js:91-99):** unchanged — alerts the sink if registered, throws `UnhandledMessageTypeError` otherwise. Real throw/alert, not a log.
- **Invariant 3 (dead-letter lastError must be a string, src/queue.js:113-120):** unchanged — real `throw TypeError` guard at the push site.
- **Invariant 4 (stats/array agreement, src/queue.js:48-62):** unchanged — real `throw Error` guard, called after every terminating `step` (106, 123).

## Note on this file's prior contents

`review-verdict.md` already existed in the working tree (untracked) when this re-review started, containing a `CHANGES_REQUESTED` verdict describing a check at `> RETRY_CAP` positioned *before* the dead-letter branch. That does not match `git diff HEAD -- src/queue.js` for the current working-tree state, which shows Invariant 2 at `>= RETRY_CAP`, positioned *after* the dead-letter branch, exactly as this task's brief described fix attempt 2. That stale verdict appears to be from reviewing an earlier, superseded state of the diff. This verdict reflects the actual current `src/queue.js`, confirmed by `git diff` and hand-tracing.

## Test status
`npm test` — 12/12 passing, exit 0 (already confirmed independently by the orchestrator; not re-run here since write_scope is `[]` and no code has changed since that confirmation).
