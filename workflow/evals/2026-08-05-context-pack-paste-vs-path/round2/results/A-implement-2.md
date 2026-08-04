# TKT-9 — provider-failure handling on reversal (AC-4)

## Shape
`src/reversals/service.js` saga, `money_pending` step only. Money is the first and only
non-compensatable leg, so nothing downstream is dispatched until the provider returns a
definite outcome. `src/payments/provider-client/index.js` gains a three-way outcome —
`confirmed | declined | ambiguous` — instead of throwing one error shape, because the
capture path shares that client and a changed error shape breaks checkout.

## The distinction the AC hides
"The provider's reversal call fails" is two outcomes, not one:
* **Declined** (definite no) → `money_pending → refused`, order untouched, retry-able error
  to the customer. This is AC-4.
* **Timed out / connection lost** (unknown) → `money_pending → pending_verification` (EC-1).
  Not a failure, not retry-able, no error the customer can act on beyond "we're checking."
  Mapping a timeout onto AC-4's retry-able error is how a double refund happens.

## Failure paths handled
| Path | Handling |
|---|---|
| Provider declines | Terminal `refused` carrying the decline reason; zero downstream calls issued |
| Provider times out / ambiguous | `pending_verification` keyed by idempotency key; reconciler (`jobs/reconcile/pending-verification.js`) re-queries; closes to `money_done` on record match, `refused` after the window |
| Provider unreachable pre-call | Same as timeout only if the request may have left the process; a connection refused before send is a clean decline |
| Provider returns 2xx with no reversal record | Treated as ambiguous, not success — the state machine requires the record in the same response |
| Post-decline late settlement | Refusal stands (EC-13); customer re-requests |

## Guards
| Guard | Condition detected | On violation |
|---|---|---|
| Balance bound, read in-request | `amount > provider_balance` immediately before the call | Refuse, alert, no call issued (AC-5 / EC-2) |
| Idempotency-key uniqueness | Key already has a reversal record | Return existing record; if same key + different params, refuse and alert (EC-6) |
| No-retry on `pending_verification` | Any path — retry worker or request handler — attempting a reversal whose state is `pending_verification` | Refuse and alert; never re-issue |
| State-transition guard | Transition not in the declared machine (e.g. `refused → money_pending`) | Refuse the transition and alert; never force the target state |
| Downstream-dispatch gate | Any tax/stock/loyalty/ledger call attempted while state ≠ `money_done` | Halt the saga, alert — the order must be left exactly as it was |
| Flag snapshot | `reversals.unified` re-read mid-saga | Refuse the read; the value captured at saga start is authoritative (EC-28) |

None of these log-and-continue: each refuses or halts, and the reversal stays visibly
incomplete rather than being marked done.

## Notes
* Order mutation happens only after `money_done`, so "left exactly as it was" is structural,
  not a rollback — there is nothing to undo on the decline path.
* Saga helper in `src/lib/saga/` assumes every step is compensatable; the money step must be
  registered as terminal-on-failure or its default compensation will attempt a re-call.
* Finance/`pending_verification` notifications fire on entry; the customer is notified only on
  refusal or on resolution (Notification Matrix).
