VERDICT: CHANGES_REQUESTED

Reviewed `src/orders/cancellation.js` against the TKT-4 acceptance criterion and the spec's Runtime
Invariants, Reality Constraints, and BR-1/2/3. The nominal TKT-4 path (refund throws → order left
`paid`, retryable error) is present, but it holds only under an assumption the spec explicitly says
the provider does not make, and three of four runtime invariants have no guard at all.

| Sev | Finding | file:line |
|-----|---------|-----------|
| 🔴 Blocking | No transaction/saga around refund + inventory release + status set — a crash or a throw from `inventory.release` leaves money refunded with the order still `paid` and stock still reserved. Directly violates Invariant 1 and BR-3. | cancellation.js:203-209 |
| 🔴 Blocking | `inventory.release` and `orders.setStatus` are unguarded: if release throws, the refund is already irreversible and there is no compensation, alert, or halt. This is the exact half-cancelled state the edge case forbids. | cancellation.js:208-209 |
| 🔴 Blocking | The catch treats every provider error as "refund did not go through". Reality Constraints state the provider does **not** guarantee that a timeout means the refund did not happen; the customer-facing `retryable: true` therefore invites a duplicate refund. Timeouts must be resolved against the provider (reconcile/lookup) before being reported as retryable. | cancellation.js:204-206 |
| 🔴 Blocking | No idempotency key on the cancellation request — Invariant 2 has no runtime detection at all, so a retried request issues a second refund. | cancellation.js:196 |
| 🔴 Blocking | Already-cancelled orders throw `ORDER_NOT_CANCELLABLE` instead of returning the existing cancellation state. Spec AC-5 / edge case requires a no-op returning the prior state. | cancellation.js:198-200 |
| 🔴 Blocking | Refund amount is computed from local `order.alreadyRefunded` with no bound assertion. Invariant 3 requires computing from the provider's prior-refund record and asserting `refund ≤ total − already_refunded`, refusing and alerting otherwise — including when local state is wrong (a stale/negative value here issues a bad-amount call). | cancellation.js:201 |
| 🟠 Major | No optimistic lock / status re-check between the initial read and `setStatus`. A shipment created mid-flight loses the "ship wins" race, and the transition guard (Invariant 4) is never re-evaluated at write time. | cancellation.js:197-209 |
| 🟠 Major | No precondition check that the charge is settled; the provider rejects refunds against unsettled charges, and that rejection currently surfaces as a generic retryable `REFUND_FAILED`. | cancellation.js:203 |
| 🟡 Minor | No alerting on any invariant violation — the spec's "On violation" column requires halt **and** alert; every failure path here is a silent throw. | cancellation.js:199,206 |
| 🟡 Minor | The comment asserts a fact the code cannot establish ("refund did not go through"). Delete or correct it once the timeout path is reconciled. | cancellation.js:205 |

No security findings: no injection surface, no secrets, no authn/authz change in this diff. Note
that `cancelOrder(orderId)` takes no caller principal — ownership authorization is presumably
enforced upstream; confirm that before merge, as it is not visible here.
