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

Write `implementation-notes.md`: how you would implement the backend for this ticket. Cover the
failure paths you would handle, the guards you would install, and for each one the condition it
detects and what happens on violation. Keep it under 45 lines — this is a plan, not code, and the
repo is not wired up.
