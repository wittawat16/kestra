VERDICT: CHANGES_REQUESTED

Reviewed `src/reversals/service.js` against AC-4 and the spec's Runtime Invariants, EC-1/EC-6/EC-10,
and the reversal state machine. Line numbers are relative to the `reverse()` body in the diff.

| Severity | Claim | file:line |
|---|---|---|
| blocking | A provider **timeout** is caught by the same `catch` as a decline and reported as retryable. EC-1 and the state machine require `pending_verification` with **no retry from any path**; this is the double-refund case the invariant exists to prevent. | src/reversals/service.js:6-8 |
| blocking | The comment asserts "provider call did not go through", but the Reality Constraints say the provider does **not** guarantee that a timeout means the reversal did not happen. The code encodes a guarantee the dependency explicitly withholds. | src/reversals/service.js:7 |
| blocking | AC-4 requires the order be left *exactly as it was*. Only the provider call is inside `try`; a failure in `tax`/`inventory`/`ledger`/`loyalty` throws with money already moved and no compensation, leaving a partially-reversed order. | src/reversals/service.js:10-13 |
| blocking | No idempotency-key uniqueness check before the external call. AC-6/EC-6 and the "no order reversed twice for the same key" invariant require returning the existing record; the key is only forwarded to the provider. | src/reversals/service.js:1-5 |
| blocking | `computeAmount(order, scope)` derives the amount from local order state. FR and BR-2 require the amount to come from the provider's own record of prior reversals (`src/reversals/balance.js`), never a local cache. | src/reversals/service.js:3 |
| blocking | No `amount ≤ provider_balance` assertion immediately before the provider call, and no pre-call refusal path (AC-5, EC-2). | src/reversals/service.js:3-5 |
| blocking | `ledger.write` failure propagates as an exception after the money moved. EC-10 requires the reversal be marked `ledger_pending` and alerted at page severity, never rolled back or dropped. | src/reversals/service.js:12 |
| blocking | Legs are written with no assertion that they sum to zero (AC-10, ledger invariant: refuse the write and alert). | src/reversals/service.js:12 |
| blocking | Tax failure aborts *after* the money leg. EC-4/AC-7 require the whole reversal refused with the order untouched; the state machine routes `money_done` + tax unavailable to `compensating`, which does not exist here. | src/reversals/service.js:10 |
| blocking | A loyalty outage throws and prevents `orders.setStatus`, contradicting EC-5/AC-8 (proceed, queue a compensating job). Loyalty is the one recoverable effect and is the only one treated as fatal. | src/reversals/service.js:13 |
| major | Status is set directly to `reversed` with no state-machine transition guard; the declared machine (`validated` → `money_pending` → `money_done` → `tax_done` → `reversed`) and its refuse-and-alert invariant are bypassed entirely. | src/reversals/service.js:14 |
| major | `inventory.release(order.reservationId)` releases the whole order reservation regardless of `scope`, so a partial reversal (AC-9, BR-5) releases stock for lines that were not reversed. Delivered lines must go to `awaiting_return`, not be released. | src/reversals/service.js:11 |
| major | No dual-approval gate; a `pricing_error`/`suspected_fraud`/`regulatory_hold` reversal issues the provider call immediately, violating AC-20. | src/reversals/service.js:4-5 |
| major | No fraud-hold check (AC-23, EC-15), no FX/currency guards (AC-26, AC-27, EC-9/EC-14), and no `reversals.unified` flag read pinned at saga start (AC-28). | src/reversals/service.js:1-14 |
| minor | Comment restates the code while asserting a false claim; per comment discipline it should be deleted rather than reworded. | src/reversals/service.js:7 |
| minor | No notification is emitted at all; AC/FR require exactly one customer notification per reversal. | src/reversals/service.js:14 |

The single highest-value fix: split the provider outcome into declined vs. ambiguous. A decline is
terminal `refused` and legitimately retry-able by the customer; a timeout must park in
`pending_verification` keyed by the idempotency key and be excluded from every retry path. Collapsing
both into one `catch` with `retryable: true` is what turns an unknown-outcome payment into a double
refund, and it is the exact defect AC-4 was written to prevent.

Secondary structural fix: the function has no saga. Every effect after the money leg needs a named
compensation or an explicit terminal marker (`compensating`, `ledger_pending`, queued loyalty job),
which is the whole rationale recorded for chosen approach A.
