VERDICT: CHANGES_REQUESTED

Review of `src/orders/cancellation.js` (line numbers per the diff under review).

| Severity | Finding | file:line |
|---|---|---|
| Blocking | No transaction/saga boundary: refund succeeds, then `inventory.release` or `setStatus` can fail, leaving the exact half-cancelled state Invariant 1 / BR-3 forbid (refunded, not released, still `paid`). No compensation, no post-commit consistency check, no alert. | cancellation.js:8-14 |
| Blocking | A provider timeout is caught and reported as "refund did not go through", but Reality Constraints state the provider does **not** guarantee a timeout means the refund didn't happen. Marking it `retryable: true` with no idempotency key invites a duplicate refund on the customer's retry. The comment asserts a fact the dependency contract denies. | cancellation.js:9-11 |
| Blocking | No idempotency key on the cancellation request (Invariant 2). Nothing is checked before the provider call, so concurrent or retried requests can each issue a refund. | cancellation.js:6-8 |
| Blocking | Already-cancelled order is not a no-op: status `cancelled` falls through the `paid`/`processing` guard and throws `ORDER_NOT_CANCELLABLE` instead of returning the existing cancellation state (AC-5, Edge Case "order already cancelled"). | cancellation.js:3-5 |
| Blocking | Invariant 3 unenforced: `amount` is derived from the local `order.alreadyRefunded` field, not from the provider's prior-refund record, and there is no `assert refund <= total - already_refunded` before issuing. A stale or wrong local value issues an over-refund — the invariant is required to hold "even if upstream state is wrong". Zero/negative `amount` is also unguarded. | cancellation.js:6 |
| Blocking | No concurrency guard (optimistic lock / conditional status write) between the read at line 2 and the write at line 14. The "ship wins" edge case is unenforceable: a shipment created mid-flight is overwritten by `setStatus(orderId, 'cancelled')`, which also bypasses Invariant 4's transition guard (it forces the target status rather than refusing an illegal transition). | cancellation.js:2,14 |
| Major | Provider precondition unchecked: a refund may only be issued against a *settled* charge. Nothing verifies settlement, so unsettled charges produce a provider rejection surfaced to the customer as a generic retryable failure. | cancellation.js:8 |
| Major | Every invariant in the spec requires an alert on violation; no alerting or structured signal exists on any failure path — the caught error is rethrown and the condition is invisible to operators. | cancellation.js:9-11 |
| Minor | `catch (err)` discards `err` entirely, so the provider's failure reason (rejection vs. timeout vs. 5xx) is unrecoverable for triage and for deciding retry safety. | cancellation.js:9 |
| Minor | Comment restates the adjacent `throw` and additionally states an untrue claim; delete rather than reword. | cancellation.js:10 |

Narrower note on the ticket's own AC (S3): on a *definite* provider rejection the order does stay `paid` and the error is retry-able, so the happy-failure case is met. It is the ambiguous-failure case (timeout) and the absent idempotency key that make this AC unsafe as written — the two must be addressed together, since "retryable" is only honest once retries cannot double-refund.
