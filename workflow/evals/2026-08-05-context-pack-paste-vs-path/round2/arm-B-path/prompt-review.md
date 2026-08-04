### Ticket brief — TKT-9: provider-failure handling on reversal

Slice of the reversal engine covering the payment-provider failure path.

Acceptance criterion (Source: S3):
  AC-4 — Given the payment provider's reversal call fails
         When a reversal is attempted
         Then the order is left exactly as it was and the customer sees a retry-able error

Blocked by: TKT-3 (reversal entry point), TKT-5 (reversible-balance computation).

## Spec

The full spec for this feature lives at `workflow/evals/2026-08-05-context-pack-paste-vs-path/round2/0-spec-large.md` in this repo. Read it if you need more than the ticket brief above.


## Your task

Write `review-verdict.md` reviewing the implementation below. First line exactly `VERDICT: CLEAR` or
`VERDICT: CHANGES_REQUESTED`, then a findings table (severity, one-line claim, file:line). Keep it
under 45 lines.

### The diff under review — src/reversals/service.js

```javascript
async function reverse(orderId, scope, idempotencyKey) {
  const order = await orders.get(orderId);
  const amount = computeAmount(order, scope);
  try {
    await provider.reverse({ chargeId: order.chargeId, amount, idempotencyKey });
  } catch (err) {
    // provider call did not go through — nothing was applied, let the caller retry
    throw new AppError('REVERSAL_FAILED', { retryable: true });
  }
  await tax.reverse(order, scope);
  await inventory.release(order.reservationId);
  await ledger.write(buildLegs(order, scope));
  await loyalty.clawback(order.customerId, pointsFor(scope));
  await orders.setStatus(orderId, 'reversed');
}
```
