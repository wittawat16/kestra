VERDICT: CHANGES_REQUESTED

Reviewed `src/reversals/service.js` against AC-4 and the surrounding spec sections it cannot be
judged without (EC-1, the Runtime Invariants table, the Reversal State Machine, and the payment
provider's "does not guarantee" column).

| Severity | Finding | file:line |
|---|---|---|
| Blocking | Timeout is treated as failure. `catch` collapses every provider error into `retryable: true`, but the spec states the provider does **not** guarantee that a timeout means the reversal did not happen. EC-1 requires parking in `pending_verification` keyed by the idempotency key for the reconciler; the state machine's `money_pending --times out--> pending_verification` row carries "**no retry from any path**". As written, an ambiguous outcome is sold to the customer as safe to retry — the double-refund path the invariant exists to close. | service.js:31-33 |
| Blocking | The comment asserts a fact the dependency contract contradicts ("provider call did not go through — nothing was applied"). It is not merely redundant; it encodes the wrong model and will outlive the reviewer. | service.js:32 |
| Blocking | No `amount ≤ provider_balance` assertion immediately before the provider call, using a value read in the same request (Runtime Invariants row 1; AC-5; EC-2 requires refusal *before* any provider call, with the remaining balance in the error). | service.js:28-30 |
| Blocking | `computeAmount(order, scope)` derives the amount from the local order. FR and BR-2 require the reversible balance come from the provider's own record of prior reversals, never a local cache. | service.js:28 |
| Blocking | No idempotency-key uniqueness check before the external call (AC-6, EC-6, Runtime Invariants row 6). The key is forwarded to the provider but a duplicate request still reaches it. | service.js:26-30 |
| Blocking | Tax failure after a successful money movement is unhandled. AC-7/EC-4 require the order left unchanged; the state machine routes `money_done` + tax unavailable to `compensating`. Here a throw from `tax.reverse` leaves money moved, no compensation, no record, order status untouched — violating "leaves the order exactly as it was" in both directions. | service.js:35 |
| Blocking | Ledger failure has no `ledger_pending` marker and no page-severity alert (EC-10, state machine `tax_done --ledger write fails-->`), and there is no legs-sum-to-zero assertion before commit (AC-10, Runtime Invariants row 4). | service.js:37 |
| Blocking | Loyalty failure aborts the whole reversal. EC-5/AC-8 require the reversal to proceed with the clawback queued as a compensating job; here a loyalty outage also prevents `orders.setStatus(..., 'reversed')`. No negative-floor clamp either (EC-21/AC-29). | service.js:38-39 |
| Blocking | No saga/reversal record and no state-machine transitions are persisted. Approach A was chosen precisely so the ambiguous-payment case has somewhere to live; without a persisted state there is nothing for the `pending_verification` reconciler to find. | service.js:26-40 |
| Major | No order lock, so concurrent full-order and per-line reversals (EC-12) and backfill-vs-live contention (EC-22) both race. | service.js:27 |
| Major | `reversals.unified` flag is never read and pinned at saga start (EC-23/AC-28). Fraud-hold deferral of the money leg (EC-15/AC-23) is also absent. | service.js:26 |

**On AC-4 specifically:** the branch does satisfy the "customer sees a retry-able error" half, and for a
clean provider *decline* the order genuinely is left as it was. The defect is that the branch does not
distinguish a decline from a timeout, and AC-4's guarantee is false for the timeout case — money may
have moved while the caller is told to retry.

Minimum to clear: split the catch on the provider client's ambiguous-timeout outcome (the spec's
Files-to-Touch row for `src/payments/provider-client/index.js` says exposing it is in scope), park
ambiguous outcomes in `pending_verification` with no retry, and add the pre-call balance and
idempotency guards. The post-money steps need the saga's compensation shape before this path is safe
to enable, not just try/catch around each call.
