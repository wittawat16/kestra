VERDICT: CHANGES_REQUESTED

Reviewed against AC-4 and the spec sections it depends on (EC-1, EC-4, EC-5, EC-10, the Runtime
Invariants table, and the Reversal State Machine).

| Sev | Finding | file:line |
|---|---|---|
| blocking | The catch treats every provider error as "nothing was applied". The provider explicitly does **not** guarantee that a timeout means the reversal did not happen (Reality Constraints, payment-provider row). EC-1 requires the ambiguous case be parked in `pending_verification` keyed by the idempotency key for the reconciler; here it is collapsed into a plain failure. | service.js:31–33 |
| blocking | `retryable: true` is returned on that same ambiguous path, so the caller is invited to re-issue a payment whose outcome is unknown — a direct violation of the invariant "A `pending_verification` reversal is never retried by any path" and the state-machine row `money_pending --provider times out--> pending_verification` (**no retry from any path**). This is the double-refund hole. | service.js:33 |
| blocking | The comment asserts as fact ("provider call did not go through — nothing was applied") the exact thing the spec says the dependency will not promise. A false statement of a dependency's guarantee is worse than no comment. | service.js:32 |
| blocking | No `amount ≤ provider_balance` assertion immediately before the provider call, using a value read in the same request (Runtime Invariants row 1; AC-5/EC-2 require refusal *before* any external call). `computeAmount` is local-order-derived, not provider-sourced — BR-2 forbids that. | service.js:27–30 |
| blocking | No idempotency-key uniqueness check before the external call (AC-6, EC-6, invariant "No order is reversed twice for the same idempotency key"). The key is passed through to the provider only, which is not the guard the spec asks for. | service.js:26–30 |
| blocking | After the provider succeeds, the five downstream steps are bare sequential `await`s with no saga, no state transitions, and no compensation. Any of them throwing leaves money moved, the order still not `reversed`, and nothing recorded or alerted — the opposite of "applied together or not at all". | service.js:35–39 |
| blocking | Tax failure must move the reversal to `compensating` and attempt to reverse the money leg (state machine; EC-4/AC-7). Here `tax.reverse` simply throws past the caller. | service.js:35 |
| blocking | Ledger failure must mark `ledger_pending` and alert at page severity, never roll back (EC-10, invariant row 2). Here it throws, un-marked and un-alerted, so the reversal is invisibly incomplete. | service.js:37 |
| blocking | Loyalty unavailability must *not* fail the reversal — EC-5/AC-8 require proceeding and queueing a compensating job. As written a loyalty outage aborts before `setStatus`, so money moved and the order never reaches `reversed`. | service.js:38 |
| high | No assertion that the ledger legs sum to zero before commit (invariant row 4, AC-10). `buildLegs` output is written unchecked. | service.js:37 |
| high | `inventory.release` is called unconditionally for the whole order. Delivered lines must move to `awaiting_return` and only re-enter stock on warehouse receipt, not be released here. | service.js:36 |
| medium | Missing throughout: the `reversals.unified` flag read at saga start (AC-28), the single per-reversal notification (FR/Notification Matrix), and fraud-hold deferral of the money leg (EC-15/AC-23). Status jumps straight to `reversed` with no declared transitions. | service.js:26–40 |

The AC-4 wording ("left exactly as it was … retry-able error") is satisfied only for a clean
provider *decline*. The spec separates decline from timeout deliberately, and this implementation
does not — that separation is the whole point of the branch under review.
