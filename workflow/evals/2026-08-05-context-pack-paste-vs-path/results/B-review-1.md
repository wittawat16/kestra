VERDICT: CHANGES_REQUESTED

Reviewed against the ticket brief and `workflow/runs/order-cancellation-refund/0-spec.md`
(Runtime Invariants, Reality Constraints, Edge Cases). Line numbers are relative to the
`cancelOrder` snippet as given.

| Severity | Finding | Location |
|---|---|---|
| Critical | Catch block treats *any* refund error as "refund did not happen". The spec's Reality Constraints state the provider does **not** guarantee that a timeout means the refund didn't go through — on a timeout the order is left `paid` with money already refunded, and the `retryable: true` hint invites a second refund. | cancellation.js:9-12 |
| Critical | No idempotency key anywhere. Invariant 2 requires one checked *before* any provider call; without it a retried cancel (the very path this slice adds) refunds twice. | cancellation.js:8 |
| Critical | No atomicity/compensation across refund → inventory release → status write. Invariant 1 and BR-3 require both or neither; a throw from `inventory.release` or `orders.setStatus` leaves the customer refunded with an order still `paid` and stock still reserved. | cancellation.js:8,13,14 |
| High | Refund bound is never asserted. Invariant 3 requires computing prior refunds from the **provider's** record and asserting `refund ≤ total − already_refunded` before issuing. Code trusts local `order.alreadyRefunded` and issues unconditionally — a stale/negative value produces an over-refund or a nonsensical ≤0 refund call. | cancellation.js:6 |
| High | Already-cancelled orders throw `ORDER_NOT_CANCELLABLE` instead of returning the existing cancellation state. Spec Edge Cases and AC-5 require a no-op with no duplicate refund. | cancellation.js:3-5 |
| Medium | No concurrency guard (optimistic lock / version check) on order status. The spec's "concurrent cancel + ship — ship wins" cannot be enforced; status is read at line 2 and written unconditionally at line 14. | cancellation.js:2,14 |
| Medium | Nothing alerts. Every invariant's on-violation action is halt/refuse **and alert**; the failure path only throws to the caller. | cancellation.js:9-12 |
| Medium | Original provider error is discarded (`err` unused), so a rejected-unsettled-charge (a permanent failure) is reported to the customer as retryable, and post-hoc reconciliation has nothing to work from. | cancellation.js:9-12 |
| Low | Shipped/delivered orders hit the same generic `ORDER_NOT_CANCELLABLE` as any other bad status; BR-1 requires directing the customer to the Returns flow. | cancellation.js:3-5 |
| Low | Inventory release is unguarded against double-release, which the spec records as an error in the inventory service — relevant once retries exist. | cancellation.js:13 |

The comment on line 10 ("refund did not go through") asserts exactly what the spec says the
provider does not guarantee; it should not survive the fix.

Safety: no injection, secret, or authz surface in this diff — but note `cancelOrder(orderId)`
takes no caller identity, so ownership of the order must be enforced upstream. Worth confirming
in the entry-point slice (TKT-1) rather than assumed.
