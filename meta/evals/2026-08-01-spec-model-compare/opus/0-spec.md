# [price-cache] Spec — Cache pricing lookups + admin "Refresh prices" button

> Status: READY (with blocking Open Items — see bottom) | Created: 2026-08-01 | Next: meta-orc

## Overview
Put a TTL cache in front of `lookupRate()` so a catalog page with N SKUs makes at most N pricing
calls on a cold cache and 0 on a warm one, and give ops a "Refresh prices" button on the admin
catalog page that clears it without a redeploy.

## Acceptance Criteria

**Cache behavior**

* [ ] Given an empty cache, when `lookupRate('A','USD')` is called twice, then `request()` from
      `src/lib/http.js` is invoked exactly once and both calls return the same value.
* [ ] Given a cached entry for `('A','USD')`, when `lookupRate('A','EUR')` is called, then
      `request()` is invoked again — the cache key is the `(sku, currency)` pair, not the SKU alone.
      *(The ask says "once per SKU"; keying on SKU alone would serve USD prices to EUR shoppers.)*
* [ ] Given an empty cache, when `lookupRates(['A','B','A','B'], 'USD')` is called, then `request()`
      is invoked exactly twice.
* [ ] Given a cached entry written at T, when it is read at T + `PRICE_CACHE_TTL_MS` or later, then
      it is treated as a miss and refetched.
* [ ] Given a cached entry written at T, when it is read strictly before T + `PRICE_CACHE_TTL_MS`,
      then it is served from cache with no `request()` call.
* [ ] `PRICE_CACHE_TTL_MS` is read from the environment with a default of 300000 (5 min) when unset;
      a value that is not a positive integer causes startup/module-load to throw rather than
      silently falling back to the default.
* [ ] Tests control expiry by injecting a clock (a `now()` function or equivalent seam), not by
      `setTimeout`/sleeping — the suite must stay deterministic and sub-second.

**Failure handling (this is where a cache most easily makes things worse)**

* [ ] Given the pricing service returns a non-200, when `lookupRate` is called, then it throws (as
      today) **and** nothing is written to the cache — a subsequent call retries the service.
* [ ] Given `request()` rejects (timeout, connection error), when `lookupRate` is called, then the
      rejection propagates **and** nothing is written to the cache.
* [ ] Given `('A','USD')` is cached and `('B','USD')` fails, when `lookupRates(['A','B'],'USD')` is
      called, then the returned promise rejects (unchanged `Promise.all` semantics) and `('A','USD')`
      remains cached.

**Refresh button**

* [ ] Given an ops user on the admin catalog page, when the page renders, then it contains a
      `<form method="post" action="<refresh-route>">` with a submit button labelled "Refresh prices".
* [ ] Given the refresh handler is invoked, when it completes, then the cache is empty (a subsequent
      `lookupRate` for a previously-cached key calls `request()` again) and it returns
      `{ status: 303, body: ... }` redirecting back to the catalog page, per the repo's
      `{ status, body }` handler convention.
* [ ] Given the refresh handler ran, when the catalog page next renders, then it shows a
      confirmation line naming how many entries were cleared (e.g. "Cleared 12 cached prices").
* [ ] The refresh handler clears the whole cache. It does **not** re-fetch prices itself — the next
      page load repopulates on demand.

**Page states** *(see Screen States table)*

* [ ] Given `req.query.skus` is absent or empty, when the catalog page renders, then it shows
      "No SKUs requested" instead of an empty `<table>`, and still shows the Refresh prices button.
* [ ] Given a pricing lookup fails, when the catalog page renders, then it returns
      `{ status: 502, body: <page with an error message and the Refresh prices button> }` rather
      than letting the rejection escape the handler.
      *(Today `catalogPage` has no try/catch — `lookupRates` rejecting propagates out of the handler,
      so the error state is currently undefined behavior. This AC defines it.)*

**Performance (the stated goal)**

* [ ] Given a warm cache, when a 30-SKU catalog page renders, then `request()` is invoked 0 times.
* [ ] Given a cold cache, when a 30-SKU catalog page renders with 30 distinct SKUs, then `request()`
      is invoked exactly 30 times (no amplification, no batching regression).

## Edge Cases & Error States

* **Same SKU repeated in one request:** deduplicated by the cache — `['A','A']` costs one call.
  Concurrent in-flight misses for the same key are **not** required to coalesce (see Out of Scope).
* **Non-200 / timeout:** throws, nothing cached. Negative caching is explicitly excluded.
* **`currency` missing:** `catalogPage` already defaults to `'USD'`; `lookupRate` called directly
  with `undefined` currency keys on the literal `undefined` — acceptable, since `URLSearchParams`
  already serialises it as the string `"undefined"` today. No behavior change.
* **Unbounded growth:** the cache holds one entry per distinct `(sku, currency)` seen. With a 5-min
  TTL and expired entries evicted on read, an adversary requesting many junk SKUs can still grow it
  between reads — cap the entry count (`PRICE_CACHE_MAX_ENTRIES`, default 5000, evict oldest) rather
  than trusting TTL alone.
* **Unauthenticated refresh:** there is **no auth, session, or CSRF mechanism anywhere in this repo**
  (verified: nothing under `src/` references auth, session, or tokens). A publicly reachable
  cache-clear endpoint is a free cache-buster against the pricing service — one request drops the
  cache, the next page load fans out N calls. See Open Items; the route must not ship reachable
  without whatever gate the deployment already puts in front of `/admin`.

## Screen States  *(needs_ui: true)*

| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|
| Admin catalog page (`catalogPage`) | "No SKUs requested" + Refresh prices button, status 200 | **n/a** — server-rendered single `{status, body}` response; there is no client-side JS in this repo and no partial render, so no loading state can exist. State the same in review rather than treating it as missing. | price table + Refresh prices button (+ "Cleared N cached prices" if arriving from a refresh), status 200 | "Couldn't load prices — try again" + Refresh prices button, status 502 |

No design system (CLAUDE.md states this explicitly). Style with inline styles matching
`renderPage()`'s existing `font-family:system-ui;padding:2rem` baseline — no tokens exist to
reference and none should be invented.

## Codebase Survey

* **Explored (all 4 source files — the repo is this small):** `CLAUDE.md`, `package.json`,
  `src/catalog/rates.js`, `src/admin/catalog-page.js`, `src/admin/layout.js`, `src/lib/http.js`.
  Also searched the whole tree for a router/server/`listen`/`express`/HTTP-method registration and
  for any deploy or env config — **none exists** (see Open Items).
* **Follow these patterns:**
  * All outbound HTTP goes through `request()` in `src/lib/http.js`. The cache wraps `lookupRate`;
    it does **not** touch `http.js`.
  * Handlers return `{ status, body }` and never write to a response object
    (`src/admin/catalog-page.js` is the model).
  * Admin pages render through `renderPage(title, inner)` in `src/admin/layout.js`. That signature
    takes no head/attribute slot, so the form markup goes inside `inner`.
  * ESM (`"type": "module"`), Node built-in test runner (`npm test` → `node --test`).
* **Test runner, verified by running it:** with `"type":"module"` and `node --test` (Node v24.15.0),
  a file at `src/catalog/rates.test.js` is discovered and run — confirmed in a scratch copy of this
  package.json shape, output `✔ discovered … pass 1`. No test files or test config exist in the
  fixture yet; these will be the first.

## Files to Touch

| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `src/catalog/rates.js` | edit | exists (read) | Add the TTL cache around `lookupRate`; export a `clearRateCache()` returning the number of entries cleared. Keep `lookupRates`' `Promise.all` shape. |
| `src/admin/catalog-page.js` | edit | exists (read) | Render the Refresh prices form; add empty-state and error-state branches (try/catch → 502). |
| `src/admin/refresh-prices.js` | new — pattern: `src/admin/catalog-page.js` | n/a (new) | POST handler calling `clearRateCache()`, returning `{ status: 303, ... }`. Same `{status, body}` convention. |
| `src/catalog/rates.test.js` | new — no existing test to pattern after; use `node:test` + `node:assert/strict` | n/a (new) | Cache hit/miss/TTL/key/failure ACs. Discovery verified above. |
| `src/admin/catalog-page.test.js` | new — same | n/a (new) | Empty/success/error page states, button presence. |
| `src/lib/http.js` | **no change** | exists (read) | Named only to state it explicitly: the cache must not live here, or every HTTP call in the service gets cached. |
| `src/admin/layout.js` | **no change expected** | exists (read) | Form markup fits in `inner`. If the implementer finds it doesn't, that's a deviation to raise, not to widen silently. |

## AC Coverage Map

| AC | Covered by |
|----|------------|
| Cache hit / miss / dedupe within one request | `src/catalog/rates.js` · `src/catalog/rates.test.js` |
| Key is `(sku, currency)` | `src/catalog/rates.js` · `src/catalog/rates.test.js` |
| TTL expiry, boundary, injectable clock | `src/catalog/rates.js` · `src/catalog/rates.test.js` |
| `PRICE_CACHE_TTL_MS` default + invalid-value throw | `src/catalog/rates.js` · `src/catalog/rates.test.js` |
| Nothing cached on non-200 / rejection | `src/catalog/rates.js` · `src/catalog/rates.test.js` |
| Partial failure leaves good entries cached | `src/catalog/rates.js` · `src/catalog/rates.test.js` |
| Entry-count cap | `src/catalog/rates.js` · `src/catalog/rates.test.js` |
| Refresh form rendered on page | `src/admin/catalog-page.js` · `src/admin/catalog-page.test.js` |
| Refresh clears cache, returns 303, reports count | `src/admin/refresh-prices.js` · `src/catalog/rates.js` (`clearRateCache`) |
| Empty state | `src/admin/catalog-page.js` · `src/admin/catalog-page.test.js` |
| Error state → 502 | `src/admin/catalog-page.js` · `src/admin/catalog-page.test.js` |
| Warm/cold 30-SKU call counts | `src/catalog/rates.test.js` (counting fake `request`) |

## Dependencies
* No new packages — a `Map` plus a clock seam covers it. Do not add an LRU/cache library for this.
* No migrations. Two new env vars — see Flags / `needs_devops`.

## Flags
* `needs_ui`: **true** — a new form + submit button on the admin catalog page, plus three page
  states (empty / success / error) that don't exist today.
* `needs_devops`: **true** — two new env vars (`PRICE_CACHE_TTL_MS`, `PRICE_CACHE_MAX_ENTRIES`) must
  be set or accept documented defaults, and a new POST route must be exposed and gated.
* `tests_first`: **false** — the caller didn't ask for it.
  **Recommendation:** turn it on. Nearly every AC here is a call-count or nothing-was-cached
  assertion, which is exactly the shape an implementation can accidentally satisfy by weakening the
  test after the fact. Written first, the assertions aren't the implementer's to shape.
  Your call, not this spec's.

## Escalation Check

Checked all three triggers. **One fires conditionally, and the condition can't be answered from
this repo — read this before treating the spec as sized correctly:**

* **Silent failure / architectural consequence — fires if the service runs more than one instance.**
  An in-process `Map` cache is per-process. With N instances behind a load balancer, "Refresh
  prices" clears the cache of whichever single instance happened to serve that POST. Ops sees a
  success page; the other N−1 instances keep serving stale prices for up to the full TTL, and
  nothing anywhere reports the discrepancy. That is precisely a condition going false while the
  system carries on — and the fix (shared cache, or invalidation fan-out across instances) is an
  architectural decision with lasting consequence, not an implementation detail. The repo contains
  no Dockerfile, no deploy manifest, no process manager config, and no scaling hints, so I can't
  resolve it by reading — it's the first Open Item.
  * **Single instance** → this spec is the right size; the TTL bounds staleness and the button does
    what it says.
  * **Multiple instances** → stop and escalate to a heavier spec pass. What that pass needs and this
    one can't carry: an approach comparison (shared store vs. pub/sub invalidation vs. accept
    per-instance clearing with a shortened TTL), an integration contract for the chosen store, and a
    runtime-invariant table for "a refresh either reaches every instance or is reported as partial"
    — never "log and continue".
* **Test doubles whose fidelity matters — does not fire.** The tests fake `request()` from
  `src/lib/http.js`, which is this repo's own module with a two-field return shape
  (`{ status, body }`) read directly from source. The interesting assertions are call *counts*
  against that fake, not fidelity to the remote pricing service's semantics. No
  does-not-guarantee matrix is needed for that.
* **2+ services on its own — does not fire** independently of the instance-count question above;
  the pricing service is already an existing dependency and this change adds no new one.

## Out of Scope
* **Request coalescing / stampede protection.** Two concurrent misses for the same key will both
  hit the pricing service. Acceptable at this scale; call it out if the cold-start fan-out after a
  refresh turns out to matter.
* **Negative caching** of failures — explicitly excluded above.
* **Per-SKU invalidation.** The button clears everything. A "clear just this SKU" control is future
  work if ops asks.
* **Cache warming / pre-fetch** after a refresh.
* **Batching the pricing service call** (one request for N SKUs instead of N). That would fix the
  cold-cache cost too, but it needs a pricing-service API this repo doesn't show, so it's a
  separate ask.
* **Cache metrics / hit-rate dashboards.**
* **Any change to `src/lib/http.js`.**

## Open Items

1. **How many instances of this service run in production?** Blocking — decides whether this spec
   is correctly sized or needs the escalation above. See Escalation Check.
2. **Where does the POST route get registered?** There is no router, server, or route table
   anywhere in this repo (searched the whole tree for `route`/`server`/`listen`/`createServer`/
   `express`/HTTP methods — zero matches). `refresh-prices.js` will export a handler matching the
   repo's `{ status, body }` convention, but the wiring that makes it reachable at a URL lives
   outside these four files. The implementer needs to be told the route path and where it's
   mounted, or this ships as a handler nobody can call — and the button's `action` attribute has
   nothing to point at.
3. **What gates `/admin` today?** Nothing in this repo does. A cache-clear endpoint reachable
   without auth is a free cache-buster against the pricing service. If the gate lives in a proxy or
   another repo, say so and this is fine; if there is no gate, that's a real finding to resolve
   before shipping, not after.
4. **Is 5 minutes the right default TTL?** Chosen as a placeholder that bounds staleness without
   making the cache pointless. Ops is the one who knows how often suppliers change prices — the
   button exists precisely because the answer is "unpredictably", so confirm the default rather
   than inheriting it from this spec.
