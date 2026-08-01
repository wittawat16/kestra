# [pricing-cache] Spec — Cache pricing lookups + manual refresh on the admin catalog page

> Status: READY | Created: 2026-08-01 | Next: meta-orc (or meta-designer / meta-dev)

## Overview
Catalog page loads currently call the pricing service once per SKU (no caching), so a 30-SKU page
makes 30 sequential-cost lookups; add an in-memory TTL cache in front of `lookupRate` so repeat
lookups skip the network call, and add a "Refresh prices" button on the admin catalog page so ops
can force-clear the cache after a supplier price change without a redeploy.

## Acceptance Criteria
* [ ] Given a SKU+currency pair not yet in the cache (or previously cached but expired), when
  `lookupRate` is called for it, then exactly one pricing-service call is made and, on success, the
  result is stored in the cache keyed by `(sku, currency)`.
* [ ] Given a SKU+currency pair already cached and unexpired, when `lookupRate` is called for it
  again, then zero pricing-service calls are made and the cached value is returned.
* [ ] Given a catalog page load for N SKUs where all N are already cached and unexpired, when the
  page renders, then `lookupRates` makes zero pricing-service calls total.
* [ ] The cache key includes currency — a cached `(sku, "USD")` entry is a cache miss for
  `(sku, "EUR")`.
* [ ] Given the pricing service returns a non-200 status or throws for an uncached SKU, when
  `lookupRate` is called, then it throws exactly as it does today (`pricing lookup failed: <status>`
  or the underlying error) and nothing is written to the cache for that key.
* [ ] Each cache entry expires after 5 minutes from when it was written (default TTL — see Reality
  Constraints for rationale); an expired entry is treated as a miss and re-fetched on next lookup.
* [ ] Given ops clicks "Refresh prices" on the admin catalog page, when the request completes, then
  every entry in the pricing cache is cleared (not just entries for SKUs currently on screen), and
  the next `lookupRate`/`lookupRates` call for any SKU is a cache miss.
* [ ] Given the admin catalog page renders (any SKU list), when the HTML is returned, then it
  includes a "Refresh prices" control that posts to the refresh handler — present in the empty,
  success, and error states alike (ops needs it precisely when prices look wrong).
* [ ] Given the refresh action completes, when the response renders, then the ops user sees
  confirmation (the catalog page re-rendered with freshly-fetched prices, or an explicit "prices
  refreshed" success message — see Screen States) rather than a silent no-feedback response.

## Edge Cases & Error States
* **Empty SKU list (`req.query.skus` is `[]`/undefined):** unchanged from today — `lookupRates`
  resolves to `[]`, table renders with zero rows, cache is untouched. The Refresh button still
  renders (ops may want to clear stale entries from a previous, larger SKU list).
* **Pricing service error on a cold/expired key:** propagate the existing `Error` unchanged; do not
  cache a failed lookup (a transient outage must not "poison" the cache with a missing entry that
  then silently gets treated as unrelated — it simply isn't written, so the next call retries).
* **Concurrent requests for the same uncached key (thundering herd):** out of scope for this pass —
  two page loads racing on the same cold SKU may both call the pricing service and both write the
  same value; this is self-correcting (both writes agree) and adds no risk beyond today's
  per-request cost. Request coalescing/de-dup is explicitly deferred (see Out of Scope).
* **Refresh racing an in-flight catalog lookup:** if a lookup started just before `clear()` writes
  its (pre-refresh) value just after, that one entry can briefly survive the refresh. Accepted for
  v1 — the window is a single in-flight request's duration, and either the next TTL expiry (≤5 min)
  or the next manual refresh self-heals it. Not treated as a defect; called out here so it isn't
  independently "discovered" during implementation.
* **Refresh clicked when cache is already empty:** no-op, still returns the success response.
* **How pricing-service failures surface to the browser today:** no router/error-handling
  middleware exists anywhere in this codebase slice (verified — see Codebase Survey), so what HTTP
  response an uncaught `Error` from `catalogPage`/the refresh handler currently produces is not
  discoverable from the code alone. This spec does not change that behavior; it's flagged in Open
  Items rather than guessed at.

## Screen States  *(needs_ui: true)*
| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|
| Admin catalog page (SKU table + Refresh button) | Zero-SKU query renders an empty `<table>` with the Refresh button still visible | N/A — page is synchronously server-rendered per request with no client-side JS (per `CLAUDE.md`: "plain server-rendered HTML with inline styles"); the browser's own full-page-navigation indicator is the only "loading" affordance, so there is no separate state to design | Table rows render `sku`/`amount` per today's markup, Refresh button visible above/below the table | A pricing-service failure on an uncached SKU throws before the page can render (existing, unchanged behavior — see Edge Cases); no new error UI is introduced for this path since the underlying failure isn't observable from this codebase slice |
| Refresh action (POST target) | N/A — always operates on "whatever is cached right now," never conditioned on a data set that could be empty in a UI sense | N/A — same full-page-navigation reasoning as above | Redirects/re-renders back to the catalog page with a "prices refreshed" confirmation (exact wording implementer's call — no design system to match) | If clearing the cache itself throws (extremely unlikely — it's a `Map.clear()`), return a 500-shaped `{status, body}` per the handler convention rather than an uncaught throw, so this one new failure mode doesn't reproduce the pre-existing unhandled-error gap noted above |

## Codebase Survey
* Explored: `CLAUDE.md`, `package.json`, `src/catalog/rates.js`, `src/admin/catalog-page.js`,
  `src/admin/layout.js`, `src/lib/http.js`. Searched the whole repo (`grep`/`find`) for a router,
  server entrypoint (`createServer`/`.listen(`), and any existing test files — **none exist**. The
  repo as given is four source files with no wiring between an HTTP server and these handlers.
* Follow these patterns:
  * `src/lib/http.js` is the only sanctioned path to an outbound call (`CLAUDE.md` convention) — the
    cache wraps `lookupRate`, it does not bypass `request()`.
  * Handlers return `{ status, body }` and never touch a response object directly
    (`src/admin/catalog-page.js` is the existing example) — the new refresh handler follows the same
    shape.
  * `src/admin/layout.js`'s `renderPage(title, inner)` is the one rendering helper for admin pages —
    reuse it for the refreshed page, don't hand-roll a second HTML wrapper.
  * `src/catalog/rates.js` uses plain named function exports, no classes — the new cache module
    follows the same style (there's no existing cache in the repo to pattern-match against
    otherwise).

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `src/catalog/rate-cache.js` | new | no existing cache module in repo; new file follows `src/catalog/rates.js`'s plain-named-export style | TTL cache: `get(sku, currency)`, `set(sku, currency, value)`, `clear()` |
| `src/catalog/rates.js` | edit | exists (read in full above) | `lookupRate` checks the cache before calling `request()`; caches only on success; export a `clearPricingCache()` (or re-export `rate-cache.js`'s `clear`) for the refresh handler to call |
| `src/admin/catalog-page.js` | edit | exists (read in full above) | render the "Refresh prices" control (a `<form method="post">`, per the no-client-JS convention) alongside the table |
| `src/admin/refresh-prices.js` | new | no existing handler to fully pattern-match (only one handler exists today); follows `src/admin/catalog-page.js`'s `{status, body}` shape and its use of `renderPage` | POST handler: clears the pricing cache, re-renders the catalog page (or a confirmation) |

## AC Coverage Map
| AC | Covered by |
|----|------------|
| Cold/expired key → one pricing call, cache on success | `src/catalog/rate-cache.js`, `src/catalog/rates.js` |
| Warm key → zero pricing calls | `src/catalog/rate-cache.js`, `src/catalog/rates.js` |
| N-SKU page, all warm → zero calls total | `src/catalog/rates.js` (`lookupRates`) |
| Cache key includes currency | `src/catalog/rate-cache.js` |
| Failure on uncached key → throws unchanged, not cached | `src/catalog/rates.js` |
| 5-minute default TTL | `src/catalog/rate-cache.js` |
| Refresh clears entire cache | `src/admin/refresh-prices.js`, `src/catalog/rate-cache.js` |
| Refresh control present in every render (empty/success/error) | `src/admin/catalog-page.js` |
| Refresh completion gives visible confirmation | `src/admin/refresh-prices.js` |

## Dependencies
* none — in-memory `Map`-based cache, no new package, no new infra (e.g. no Redis).

## Flags
* `needs_ui`: true — new interactive "Refresh prices" button/control on `src/admin/catalog-page.js`.
* `needs_devops`: false — TTL is a hardcoded default (5 minutes), not an env var/flag; no migration,
  no infra change. (If ops later wants the TTL tunable without a redeploy, that's a follow-up that
  *would* flip this flag — noted, not assumed here.)
* `tests_first`: false — not requested by the caller.

## Escalation Check
* **Silent failure:** considered — an unbounded/never-expiring cache serving stale prices forever
  would qualify, which is exactly why this spec pins a 5-minute default TTL rather than leaving the
  cache to expire only on manual refresh (see the AC above and the TTL rationale below). With a TTL
  in place, staleness is bounded and self-correcting, not silent-forever, so this doesn't rise to
  `kestra-spec`'s runtime-invariant bar. If a future ask needs a *guaranteed* staleness ceiling with
  alerting on breach, that would cross the line — not the case here.
* **Test-double fidelity:** the pricing service is already faked out through `src/lib/http.js` for
  any existing/future tests; this feature doesn't add a new external dependency or a second path
  that must agree with a first (there's exactly one lookup path, cached or not) — no reality-
  constraints matrix needed.
* **2+ services / lasting architecture decision:** none — one service, one new in-process module, no
  new integration contract.
* → None of the three escalation triggers fire. `meta-spec`'s scope is sufficient; no escalation to
  `kestra-spec`.

## Out of Scope
* Request coalescing/de-duplication for concurrent cold lookups on the same key (see Edge Cases).
* Per-SKU (as opposed to whole-cache) refresh/invalidation — the ask was a blunt "clear it all"
  control for ops, not a scalpel.
* Making the TTL configurable via env var/flag — hardcoded default for this pass (see Flags).
* Any new router/server-wiring work — this codebase slice has none to begin with, and adding one is
  outside what was asked (see Open Items).

## Open Items
* **How the refresh POST route gets registered/reachable is unverifiable from this codebase slice**
  — there is no router or server entrypoint anywhere in the repo (confirmed by grep/find across the
  whole tree). `src/admin/refresh-prices.js` is specified as a handler with the same `{status,
  body}` shape as the existing `catalogPage` handler, but wiring it to an actual URL/route requires
  whatever routing layer exists outside this slice — the implementer needs to locate or ask about
  it before this can be end-to-end tested.
* **How an uncaught pricing-service error currently surfaces to the browser** is likewise
  unverifiable (no router/error-middleware in this slice) — pre-existing gap, unchanged by this
  spec, flagged rather than guessed at (see Edge Cases' last row).
* Exact wording/markup of the "prices refreshed" confirmation — no design system exists
  (`CLAUDE.md`: "plain server-rendered HTML with inline styles"), so this is an implementer
  judgment call within the Screen States constraints above, not a spec gap.
