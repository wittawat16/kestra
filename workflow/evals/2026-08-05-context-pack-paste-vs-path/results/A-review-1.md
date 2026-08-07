VERDICT: CHANGES_REQUESTED

Review of `src/orders/cancellation.js` against the order-cancellation-refund spec (TKT-4 slice
plus the invariants/constraints the same file must not break).

| Severity | Finding | Location |
|---|---|---|
| Blocking | Refund, inventory release, and status change are three unguarded sequential awaits — no transaction/saga, no compensation. A failure after the refund leaves the order `paid` **and** refunded (money out, order not cancelled), the exact half-applied state Invariant 1 and BR-3 forbid. | cancellation.js:7,12,13 |
| Blocking | The catch assumes a thrown provider error means the refund did not happen and tells the customer to retry. Reality Constraints state a timeout does **not** guarantee the refund didn't go through; a retry then double-refunds. Timeouts must be resolved against the provider (or an idempotency key), not assumed failed. | cancellation.js:8-10 |
| Blocking | No idempotency key on the refund call — Invariant 2 requires one checked *before* any provider call. Nothing here prevents a second refund for the same cancellation on any retry path. | cancellation.js:7 |
| Blocking | `amount` is computed from local `order.alreadyRefunded` with no `refund ≤ total − already_refunded` assertion and no read of the provider's prior-refund record. Invariant 3 requires the bound to hold even when upstream state is wrong; the provider also does not guarantee prior-refund totals are immediately consistent. A stale/negative `alreadyRefunded` issues an over-refund. | cancellation.js:5 |
| Blocking | Cancelling an already-cancelled order throws `ORDER_NOT_CANCELLABLE` instead of returning the existing cancellation state as a no-op (AC 5 / Edge Cases). | cancellation.js:3-4 |
| Blocking | No concurrency guard (optimistic lock / conditional status write) between the initial read and `setStatus`. A shipment created mid-flight loses to the cancel, inverting the spec's "ship wins" rule — and by then the refund has already been issued. | cancellation.js:2,13 |
| Major | No invariant violations are alerted. All four invariants specify halt/refuse **and** alert; the code only throws to the caller, so a violated bound is silent to operators. | cancellation.js:4,10 |
| Major | Shipped/delivered orders get the generic `ORDER_NOT_CANCELLABLE` error, not the Returns-flow message BR-1 and AC 2 require; the caller cannot distinguish "shipped" from any other non-cancellable state. | cancellation.js:3-4 |
| Major | No settled-charge precondition check. The provider rejects refunds against unsettled charges; that rejection currently surfaces as a "retryable" REFUND_FAILED, which will never succeed on retry. | cancellation.js:7 |
| Minor | The original provider error is discarded — no cause, no code, nothing to diagnose a failed refund with. | cancellation.js:9-10 |
| Minor | `inventory.release` is not guarded against the double-release the inventory service treats as an error (relevant on any retry of a partially-applied cancellation). | cancellation.js:12 |

The TKT-4 acceptance criterion is only partly met: a refund rejection does leave the order in
`paid` with a retryable error, but a refund *timeout* can leave the customer charged while the
order reads `paid`, and the retry the error invites is what causes the second charge. Fix the
timeout/idempotency pair and the atomicity boundary together — neither is sound alone.
