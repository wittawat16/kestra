VERDICT: CHANGES_REQUESTED

Scope: AC-4 (provider-failure path) in `src/reversals/service.js`, reviewed against
`0-spec-large.md` (EC-1, EC-2, EC-5, EC-10, Runtime Invariants, Reality Constraints).

| Sev | Finding | file:line |
|---|---|---|
| blocking | Timeout is treated as failure. The catch collapses every provider error into `REVERSAL_FAILED {retryable:true}`, but the spec's dependency table states the provider does **not** guarantee "a timeout means the reversal did not happen", and EC-1 requires an unknown outcome to park as `pending_verification` keyed by the idempotency key, with **no retry from any path** until the reconciler settles it. As written, a timed-out reversal is advertised to the customer as retry-able — the exact double-refund path invariant "A `pending_verification` reversal is never retried by any path" exists to prevent. | service.js:31-34 |
| blocking | Comment asserts a fact the code cannot know. `// provider call did not go through — nothing was applied` is false for the timeout case and encodes the wrong mental model into the file. | service.js:32 |
| blocking | Missing balance invariant guard. No `amount ≤ provider_balance` assertion immediately before the provider call using a value read in the same request; EC-2 requires refusal *before* any provider call with the remaining balance in the error. `computeAmount` is local-state-derived (BR-2: balance comes from the provider, never local state). | service.js:28-30 |
| blocking | Missing idempotency-key uniqueness check before any external call. Invariant requires refusing the duplicate and returning the existing record (EC-6); the key is only passed through to the provider. | service.js:26-30 |
| blocking | No `ledger_pending` handling. If `ledger.write` throws after the provider succeeded, the money has moved and this function simply propagates — EC-10 requires marking `ledger_pending` and paging, never rolling back or dropping. Same exposure for `tax.reverse`/`inventory.release` failing post-money. | service.js:35-39 |
| blocking | No state-machine transitions. The declared machine (`money_pending` → `money_done` / `refused` / `pending_verification`) is bypassed entirely; the order jumps straight to `'reversed'` at the end, so a partially-applied reversal is either invisible or falsely terminal. | service.js:39 |
| major | Tax is not transactionally bound to the money movement. The invariant requires a transaction boundary spanning the tax call and the reversal record, halting with the order untouched on failure (EC-4); here tax runs after the money has already moved. | service.js:35 |
| major | Loyalty clawback is inline and unguarded. EC-5 requires it queued as a compensating job (loyalty unavailability must not fail the reversal), and EC-21 requires clamping at the negative floor. A throw here leaves money moved and status un-set. | service.js:38 |
| minor | No customer notification. AC-4 requires the customer to see a retry-able error; the function only throws an internal `AppError`, and the one-notification-per-reversal requirement is unimplemented. | service.js:33 |
| minor | Order lock absent (EC-12/EC-22: first to acquire the order lock wins) — concurrent full-order and per-line reversals can both pass `computeAmount`. | service.js:26-27 |

Recommended shape: guard (idempotency key → lock → provider-read balance assertion) before any
external call; classify provider errors into *declined* (→ `refused`, nothing applied, retry-able
error to customer) vs *ambiguous/timeout* (→ `pending_verification`, explicitly **not** retry-able);
apply downstream effects only after a confirmed provider record, with `ledger_pending` and a queued
loyalty compensation for post-money failures.
