VERDICT: CHANGES_REQUESTED

Reviewed `src/orders/cancellation.js` against the TKT-4 brief and the full spec
(`workflow/runs/order-cancellation-refund/0-spec.md`). The literal AC (order stays `paid`, retryable
error) holds only for an *unambiguous* provider failure; every other invariant in the spec is
unguarded.

| Sev | Finding | Location |
|-----|---------|----------|
| Blocking | A refund timeout is treated as "refund did not go through", but the spec states the provider does **not** guarantee a timeout means the refund didn't happen. Marking it `retryable: true` invites a second refund on the customer's retry. | cancellation.js:34-36 |
| Blocking | No idempotency key on the cancellation/refund call. Invariant "an order is never refunded twice for the same cancellation" requires the key be checked *before* any provider call. | cancellation.js:33 |
| Blocking | No atomicity between refund, `inventory.release`, and `setStatus`. A failure at line 38 or 39 leaves a refunded order still in `paid` with (maybe) released stock — exactly the half-cancelled state the invariant table and BR-3 forbid. No saga/compensation, no post-commit consistency check. | cancellation.js:33-39 |
| Blocking | Missing the pre-call bound assertion `refund ≤ total − already_refunded`. `amount` is computed and sent unchecked, so corrupt upstream state (negative/oversized `alreadyRefunded`) reaches the provider. Spec also requires computing from the provider's prior-refund record, not a local order field. | cancellation.js:31 |
| Blocking | Already-cancelled order falls into `ORDER_NOT_CANCELLABLE` instead of the specified no-op returning existing cancellation state. | cancellation.js:28-30 |
| Blocking | No concurrency guard (optimistic lock/version check) between the status read and the write. The "concurrent cancel + ship — ship wins" rule is unenforceable as written. | cancellation.js:27-39 |
| High | No invariant violation is alerted. Every row in the invariant table requires halt-and-alert; this code only throws to the caller, so a half-applied cancellation is silent to operators. | cancellation.js:32-39 |
| High | Post-shipment rejection returns a generic `ORDER_NOT_CANCELLABLE`, not the Returns-flow redirection the AC requires. Out of this slice's scope but shares the same code path. | cancellation.js:28-30 |
| Medium | The caught `err` is discarded — no cause chaining or logging, so a rejected-unsettled-charge failure is indistinguishable from a timeout in production diagnostics. | cancellation.js:34-36 |
| Low | Comment restates the code below it; the non-obvious part (why the order is deliberately left in `paid`) is what deserves the line. | cancellation.js:35 |

Minimum to clear: idempotency key checked before the provider call, an explicit timeout/unknown-outcome
path that does not advertise a blind retry, the `refund ≤ uncredited balance` assertion, and an atomic
(or compensating) boundary around refund + release + status with an alert on violation.
