# ☕ [order-cancellation-refund] Spec — Order Cancellation & Refund

> **Status:** 🟢 READY_FOR_BUILD | **Created:** 2026-07-25
> **Next:** 🏗️ kestra-build

---

## ☕ Overview
Let customers cancel a paid order before it ships, automatically refunding the payment and
releasing reserved inventory — this is the example spec used to illustrate BDD-style
(Given-When-Then) acceptance criteria for `kestra-spec`/`kestra-build`.

## 🪵 Problem Statement
* Customers currently have to contact support to cancel a paid order; support manually issues
  refunds via the payment provider dashboard, which is slow and error-prone (refund amount typos,
  forgotten inventory release).
* 🎯 **Goal:** Customer can self-serve cancel a paid, not-yet-shipped order and receive an accurate,
  automatic refund within the same request.

## 🥑 Functional Requirements
* [ ] Customer can cancel any order in `paid` or `processing` status from the order detail page.
* [ ] Cancelling a paid order triggers a full refund via the existing payment provider integration.
* [ ] Cancelling releases any reserved inventory back to available stock.
* [ ] **Given** a paid order that has already shipped
      **When** the customer attempts to cancel it
      **Then** the cancellation is rejected with a message directing them to the returns flow instead.
* [ ] **Given** a paid order with a partial refund already issued (e.g. a prior support adjustment)
      **When** the customer cancels the remainder
      **Then** only the remaining uncredited amount is refunded, not the original full total.

## 🌤️ Edge Cases & Error States
* **Payment provider refund call fails (timeout/5xx):** order stays in `paid` status, cancellation
  is not applied, customer sees "refund failed, try again" — never leave the order half-cancelled
  (inventory released but payment not refunded, or vice versa).
* **Order already cancelled:** cancelling again is a no-op that returns the existing cancellation
  state, not a duplicate refund.
* **Concurrent cancel + ship:** if a shipment is created while a cancel request is in flight, the
  cancel must lose — ship wins, customer is routed to returns.

## 🛡️ Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; it never proceeds
silently. These are enforced in production, not verified once in a test.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| Refund and inventory-release either both take effect or neither does | Transaction/saga boundary around the pair; a post-commit consistency check comparing refund state to reservation state | Halt the cancellation, leave the order in `paid`, alert — a half-applied cancellation must never be left in place |
| An order is never refunded twice for the same cancellation | Idempotency key on the cancellation request, checked before any provider call | Refuse the duplicate and return the existing cancellation state; alert if the key was reused with different parameters |
| Refund amount never exceeds the order's uncredited balance | Compute from the provider's prior-refund record, then assert `refund ≤ total − already_refunded` before issuing | Refuse and alert — never issue the call; this bound must hold even if upstream state is wrong |
| Order status transitions only along the allowed path | Guard on the status transition (`paid`/`processing` → `cancelled` only) | Refuse the transition and alert, rather than forcing the target status |

## 🌐 Reality Constraints
*(what the world outside this feature actually does — the standard its test doubles get judged
against.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| Payment provider | A refund can only be issued against a settled charge; refunds against an unsettled charge are rejected | Provider-native identifier types and money as minor-unit integers — confirm both against the SDK rather than assuming strings/floats | That a refund call is idempotent by default; that prior-refund totals are immediately consistent after a write; that a timeout means the refund did *not* happen |
| Inventory service | Reservation must exist before it can be released; releasing twice is an error | Reservation identifiers and quantities as the service defines them | That release is synchronous, or that a released quantity is immediately visible as available |

### Paths that must agree
* None — single cancellation path. *(If a batch/admin cancellation path is added later, it and the
  customer path must agree on BR-1/2/3 and would need a parity check.)*

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| Clock | 📌 pinned | Shipment-status and settlement checks are time-relative; a live clock makes the same test pass or fail depending on when it runs |
| Provider-assigned identifiers | 📌 pinned | Assertions must not depend on values the provider generates per call |
| Provider latency / timeout | 🌊 floating, but the timeout path must be exercised explicitly | The edge case requires proving a failed refund leaves the order untouched, which needs a deliberately induced failure rather than a lucky one |

## 📜 Business Rules  *(needs_ba: true)*

* **BR-1 — Only pre-shipment orders are self-service cancellable.**
  ```
  Given an order in "paid" or "processing" status (not yet shipped)
  When the customer requests cancellation
  Then the order is cancelled and a full refund is issued
  ```
  ```
  Given an order in "shipped" or "delivered" status
  When the customer requests cancellation
  Then the request is rejected with "already shipped — use Returns instead"
  ```

* **BR-2 — Refund amount reflects prior adjustments, never the original total blindly.**
  ```
  Given a paid order with no prior refunds, total $120
  When the customer cancels
  Then a refund of $120 is issued
  ```
  ```
  Given a paid order, total $120, with a $30 support-issued partial refund already applied
  When the customer cancels the remainder
  Then a refund of $90 is issued (not $120)
  ```

* **BR-3 — Cancellation always releases reserved inventory, refund or not.**
  ```
  Given a paid order holding a reserved-stock line item
  When the order is successfully cancelled
  Then the reserved quantity is released back to available stock in the same transaction as the
  refund — a refund without inventory release (or vice versa) is treated as a failed cancellation
  ```

* 👥 **Stakeholder variations:**
  * Support agents can force-cancel a shipped order (bypasses BR-1) — out of scope for this spec,
    tracked separately; self-service customers cannot.

## 🔎 Codebase Survey
* **Explored:** *(illustrative spec — no real codebase attached; a real spec would list the actual
  order/payment/inventory modules read and verified here before listing files to touch)*
* **Integrate with:** existing order-status state machine and payment-provider refund client,
  wherever this codebase already defines them.

## 🗂️ Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| *(n/a — example spec)* | — | — | Files to Touch requires a real repo; skipped here since this spec isn't wired to an actual codebase. |

## 🔗 Dependencies
* none new — reuses existing payment-provider refund API and inventory-release path.

## 🎯 Acceptance Criteria
* [ ] **Given** a paid, not-yet-shipped order
      **When** the customer cancels it
      **Then** the order status becomes `cancelled`, a full refund is issued, and reserved inventory
      is released — all in one atomic operation
* [ ] **Given** a paid order that has already shipped
      **When** the customer attempts to cancel it
      **Then** the request is rejected and the customer is shown the Returns flow instead
* [ ] **Given** a paid order with a $30 prior partial refund on a $120 total
      **When** the customer cancels the remainder
      **Then** exactly $90 is refunded
* [ ] **Given** the payment provider's refund call fails
      **When** cancellation is attempted
      **Then** the order remains in `paid` status (not partially cancelled) and the customer sees a
      retry-able error
* [ ] Cancelling an already-cancelled order is a no-op — no duplicate refund is issued

## 🎯 AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| Pre-shipment cancel → refund + inventory release | BR-1, BR-3 |
| Post-shipment cancel rejected | BR-1 |
| Partial-refund-aware cancel amount | BR-2 |
| Refund-call failure leaves order untouched | Edge Cases — payment provider failure |
| Duplicate cancel is no-op | Edge Cases — order already cancelled |

## ⚠️ Risks & Watch-outs
* Refund + inventory-release must be atomic (single transaction or saga with compensation) — a
  crash between the two steps is exactly the "half-cancelled" state BR-3 and the edge cases forbid.
* Race between cancel and ship needs a concurrency guard (e.g. optimistic lock on order status) —
  without it "ship wins" isn't actually enforceable.

## 🚫 Out of Scope
* Support-agent force-cancel of shipped orders (mentioned under stakeholder variations, tracked as
  a separate feature).
* Partial-item cancellation (cancelling only some line items of a multi-item order).

## 🔀 Flags
* `needs_ba`: true — refund-amount and shipment-status rules are exactly the kind of thing a vague
  spec gets wrong; enumerated as BR-1/2/3 above.
* `needs_ui`: true — order detail page needs a Cancel action, a confirmation step, and a
  rejected/error state for the post-shipment case. *(Design Notes omitted here since this is an
  illustrative spec, not a real one — a real spec would fill in the Design Notes section per
  kestra-spec's template.)*
* `needs_sa`: false — single service, no competing architectural approaches.
* `needs_devops`: false — no new env vars, migrations, or flags.

## ❓ Open Items
* none
