### Ticket brief — TKT-4: refund-failure handling on cancellation

Slice of the cancellation feature covering the failure path.

Acceptance criterion (Source: S3):
  Given the payment provider's refund call fails
  When cancellation is attempted
  Then the order remains in `paid` status (not partially cancelled) and the customer sees a
  retry-able error

Blocked by: TKT-1 (cancellation entry point), TKT-2 (refund issuance).

## Spec

The full spec for this feature lives at `workflow/runs/order-cancellation-refund/0-spec.md` in this repo. Read it if you need more than the ticket brief above.

## Your task

Write `review-verdict.md` reviewing the implementation below for correctness and safety. First line
exactly `VERDICT: CLEAR` or `VERDICT: CHANGES_REQUESTED`, then a findings table (severity, one-line
claim, file:line). Keep it under 40 lines.

### The diff under review — src/orders/cancellation.js

```javascript
async function cancelOrder(orderId) {
  const order = await orders.get(orderId);
  if (order.status !== 'paid' && order.status !== 'processing') {
    throw new AppError('ORDER_NOT_CANCELLABLE');
  }
  const amount = order.total - order.alreadyRefunded;
  try {
    await paymentProvider.refund({ chargeId: order.chargeId, amount });
  } catch (err) {
    // refund did not go through — leave the order alone so the customer can retry
    throw new AppError('REFUND_FAILED', { retryable: true });
  }
  await inventory.release(order.reservationId);
  await orders.setStatus(orderId, 'cancelled');
}
```
