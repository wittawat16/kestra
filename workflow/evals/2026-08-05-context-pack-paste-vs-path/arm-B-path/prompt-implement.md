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

Write `implementation-notes.md`: how you would implement the backend for this ticket. Cover the
failure paths you would handle, the guards you would install, and for each one the condition it
detects and what happens on violation. Keep it under 40 lines — this is a plan, not code, and the
repo is not wired up.
