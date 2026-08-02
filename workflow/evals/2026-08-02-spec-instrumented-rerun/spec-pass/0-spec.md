# [operator-console] Spec — Live operator console for the retry queue

> Status: READY_FOR_BUILD | Created: 2026-08-02 | Next: kestra-build

> Provenance key (every intent line this raise ADDS carries one): `US-n` = user story n of
> `0-spec-verbatim.md` · `ID§x` = ticket Implementation Decisions subsection · `TD` = Testing
> Decisions · `FN` = Further Notes · `OOS` = ticket Out of Scope · `PS` = Problem Statement ·
> `⚠ inferred` = originated by this pass, no ticket line behind it · `verified:<probe>` = confirmed
> by running code in step 4, not read-and-reasoned. Verbatim intent layer preserved at
> `/tmp/eval33/spec-pass/0-spec-verbatim.md` (sha256 `6fdcee78…d090f4`, identical to the vetted
> ticket).

> Delimiter precondition: section delimiters are stable. Splitting this file on `^## ` yields exactly
> the template sections and nothing else — no line inside any requirement-surface section body begins
> with `## `. Subsection headings use `### `, which does not match the delimiter. The file contains
> zero fenced code blocks, so no fence can hide a `##` (checked: fence-open count is 0).

---

## Overview

Loopback-bound, stdlib-only HTTP console over the in-memory retry queue: health-at-a-glance, message
list + detail, one mutation (requeue-to-head), and an unmistakable lost-contact state — so a paged
on-call operator answers "draining or stuck, and which message" from a phone without a REPL (PS).

## External Interface

The seam this feature is exercised at, and the only surface tests may drive:

* **Primary (new): HTTP boundary.** Console server started on an ephemeral loopback port; driven by
  the platform `fetch`; assertions on status code, `Location` header, operator-visible *text* in the
  body, and the state of the queue object afterwards (TD seam 2).
  * `GET /` — console page: health summary + filter controls + message list, fully server-rendered
    (ID§HTTP surface).
  * `GET /fragment?list=<pending|done|all>&type=<t>` — summary + list markup only; the poll target
    (ID§HTTP surface).
  * `GET /message?id=<id>` — detail page (ID§HTTP surface).
  * `GET /requeue?id=<id>` — confirmation page; reachable only for a message currently in `pending`
    (ID§HTTP surface, US-22, US-25).
  * `POST /requeue` (body `id=<id>`) — performs the move, then `303` → `/?outcome=<moved|completed|
    missing>&id=<id>`; the redirect *is* the refresh (ID§HTTP surface, US-28).
    `verified:probe-d` — platform `fetch` follows `303` and converts POST→GET, final URL carries the
    query, so the outcome is assertable end-to-end without a client.
  * anything else — `404` rendered in the console's own styling (ID§HTTP surface, US-27).
* **Secondary (existing, reused not extended): queue-module seam.** Direct calls to the exported
  functions of `src/queue.js`, exactly as `test/queue.test.js` does today — covers only the three
  additive queue changes (TD seam 1, FN§seam count). No new exports are added to make anything
  testable.
* **Deliberately absent seams** (TD): fragment renderer, escaping helper, summary builder, style
  baseline, DOM/browser. All are reached through HTTP responses only. Anything pushing toward a
  third seam is a design smell first (FN§seam count).
* **Not an interface:** the console's internal render/escape/style functions are module-private and
  unexported (ID§Modules).

## Problem Statement

* Current: queue state is observable only by `console.log`-ing the queue object from the script
  driving `step()`; requires source, laptop, daylight (PS).
* Current: `step()` catches a handler throw and discards it — nothing records *why* a message keeps
  retrying, only that `attempts` rose. `verified:probe-a` (A4: message after a failed step carries
  `attempts,id,type,payload` and no error field of any name).
* Current: no lever to advance one message; the only tool is a process restart, which loses the
  whole in-memory queue (PS).
* Goal: an on-call operator on a phone reaches the drain-or-stuck verdict in ~2 s, names the message
  eating the worker, and can move one message to the head — with a stale screen that can never be
  mistaken for a calm one (PS, US-6, US-32, US-33).

## Functional Requirements

Health summary (whole-queue, no interaction, no scroll)

* [ ] Console page shows, above everything and without interaction: pending count (US-1), done count
      (US-2), count of distinct `type`s in `pending` (US-3), highest `attempts` in `pending` (US-4),
      wait duration of the oldest pending message (US-5).
* [ ] All five figures computed over the full `pending`/`done` arrays — never over the filtered or
      row-capped subset (US-7).
* [ ] Summary block fits above the fold at 375 px width with no scrolling and no taps (US-6, US-47).
* [ ] Summary and rows in one response are read in a single synchronous pass over the live queue, so
      they describe the same moment (US-45, ID§Chosen-1). `verified:probe-b` — zero HTTP requests are
      served while `step()` runs (B2: 0 observations during a 705 ms synchronous handler), so no
      request can observe the queue mid-`step()`.

Message list

* [ ] Lists every message in `pending` and `done` with id, type, attempts, and which list it is in
      (US-8).
* [ ] Pending rows in queue order, head first — the top row is literally what `step()` takes next
      (US-9). `verified:probe-f` (F3: `pending[0]` is the message the next `shift()` returns).
* [ ] List filter accepts `pending` | `done` | `all`; any other value falls back to `all` and is not
      echoed into the page (US-10, ID§Semantics).
* [ ] Type filter offers only the `type` values present in the queue at render time, derived in the
      same pass as the summary (US-11, US-12).
* [ ] Rows capped at `ROW_CAP = 200`; when matches exceed the cap the page prints "showing the first
      200 of M matching" with M the true full match count (US-13; cap value ⚠ inferred — ticket says
      "a fixed number", names none). Truncation notice only — no pager controls, no page-through
      (ID§Semantics, OOS).
* [ ] A one-tap control clears any active filter and returns the unfiltered list (US-14).

Detail view

* [ ] Each row links to the message detail for its id (US-15).
* [ ] Detail shows id, type, attempts, which list the message is in, and the payload rendered as
      readable text (US-16, ID§Semantics).
* [ ] Detail shows the message text of the most recent error the handler threw (US-17), explicitly
      labelled as the most recent one and stamped with when it was recorded (US-18).
* [ ] Returning from detail restores the list with the previous filter still applied — the back link
      carries the filter query (US-20).

Requeue

* [ ] Requeue moves the first `pending` message whose stringified id matches, from its index to
      index 0 (US-21, ID§Semantics). `verified:probe-f` (F3: `[0,1,2,3,4]` → `[3,0,1,2,4]`).
* [ ] `pending.length`, `attempts`, and the enqueue time are unchanged by a requeue, and the relative
      order of every other message is unchanged (US-23, US-24, ID§Semantics). `verified:probe-f` (F3:
      all four assertions true).
* [ ] A `GET /requeue` confirmation page stands between the row and the mutation; the mutation
      happens only on the `POST` (US-22).
* [ ] The requeue control is not rendered at all for a message in `done` — not rendered-then-refused
      (US-25); `GET /requeue?id=<done id>` renders the already-completed answer rather than a
      confirm button.
* [ ] Exactly three outcomes: `moved`; `already completed` (id found in `done`); `no such message`
      (id in neither list). Already-completed is reported plainly as a normal outcome, not an error
      (US-26, US-27, ID§Semantics). `verified:probe-f` (F3 tail: `no-such-message` and
      `already-completed` both produced).
* [ ] The outcome and the refreshed queue arrive together via the `303` redirect, with no manual
      refresh (US-28).
* [ ] Requeue is the only mutation the console can perform; no route mutates anything else (US-30,
      OOS).

Freshness and lost contact

* [ ] The page polls `GET /fragment` every `POLL_MS = 3000` and swaps the returned markup into one
      container (US-31, ID§Chosen-2).
* [ ] Staleness is a client-side determination from the last *successful* poll:
      age > `STALE_MS = 10000` (≈3 missed polls) switches the page to the STALE state
      (US-32, US-34, ID§Chosen-2; both numbers ⚠ inferred — ticket fixes neither, see OI-5).
* [ ] STALE state is visually unmistakable and cannot be confused with a healthy empty queue: distinct
      glyph + text label + the counts marked untrusted (US-32, US-33).
* [ ] Time since the last successful poll is shown numerically (US-34).
* [ ] Polling suspends while `document.hidden` and fires immediately on `visibilitychange` to visible;
      because the last-success timestamp aged while hidden, the page renders STALE on wake until a
      poll actually succeeds (US-35, ID§Chosen-2).
* [ ] A background poll never replaces the DOM while a confirmation page is open — the confirm page
      is a separate document with no poll loop, and the poll swaps only the fragment container on the
      console page (US-36).
* [ ] `POLL_MS` and `STALE_MS` are named constants declared once, in one place (ID§Semantics).

States, accessibility, safety

* [ ] A queue with `pending.length === 0 && done.length === 0` renders "no message has ever been
      enqueued", distinct from a drained queue (US-37). `verified:probe-f` (F2: fresh `0/0` vs drained
      `0/1`; F1: no `step()` path drops a message, so the two are never confusable).
* [ ] A filter matching nothing renders "no message matches this filter" plus the clear-filter control
      — never the empty-queue text (US-38).
* [ ] Any in-flight action shows a visible in-progress indication (US-39).
* [ ] A server-side failure renders an explicit error state in the console's own styling — never a
      blank or half-drawn screen (US-40).
* [ ] Healthy / stale / error / success are each distinguishable without colour: text label + distinct
      glyph, colour as reinforcement only (US-41).
* [ ] Every interpolated value — id, type, attempts, payload text, error text, timestamps, and any
      echoed filter value — passes through one escaping helper covering `& < > " '` (US-42,
      ID§Semantics). `verified:probe-c` (C4: the hostile sequence does not survive escaping).
* [ ] Payload rendering: objects/arrays as pretty-printed JSON; primitives as text; `null` and
      `undefined` as explicit literal markers, not blanks; anything that fails to serialize as an
      explicit unserializable marker; anything over `PAYLOAD_MAX = 4000` chars truncated with a notice
      (US-19, ID§Semantics; length ⚠ inferred). Three distinct failure shapes must be handled, not one
      — `verified:probe-c` (C3: circular and BigInt **throw** `TypeError`; a bare `undefined` and a
      function **return `undefined`** without throwing; a `Map` and a symbol-valued property serialize
      *lossily* to `{}` without throwing). A try/catch alone catches only the first shape.
* [ ] Console binds the loopback interface itself; no host option is accepted (US-46, ID§Modules).
      `verified:probe-d` (D1: bound to `127.0.0.1`, a request to this host's LAN address on the same
      port is `ECONNREFUSED`).
* [ ] The console adds no work to `step()` and never calls it; the order messages leave `pending` is
      unchanged except by an explicit requeue (US-29, US-43).
* [ ] Health summary stays responsive at 10,000 pending messages (US-44). `verified:probe-c` (C5:
      single-pass summary over 10k = 0.35 ms/call; 200-row render = 0.16 ms / 8.3 KB, vs 10k-row
      render = 5.2 ms / 431 KB — the cap is a payload-size guard, not a CPU one).

Queue module — additive only (ID§Modules)

* [ ] `step()` records onto the message the text of the error a handler throws, plus when it was
      recorded, replacing any previously recorded one; only the most recent is kept; a thrown
      non-`Error` is coerced to text rather than dropped (US-49, ID§Modules).
* [ ] The retained error travels with the message into `done` if a later attempt succeeds; the detail
      view labels it most-recent and shows which list the message is in, so a completed message
      carrying an old error reads correctly (ID§Semantics). `verified:probe-c` (C2: the message object
      is moved by reference into `done`, so any field added on the retry path survives the later
      success).
* [ ] `step()` records a **last-step record** — message id, start time, duration, outcome — and
      *retains* it after the message leaves the handler, rather than clearing an in-flight mark
      (US-49-adjacent; **corrects** ID§Chosen-1 Accepted-consequence, see Reality Constraints and
      OI-4). `verified:probe-b` — an in-flight mark cleared on handler exit is observable by **no**
      HTTP request ever (B4/B5: three polls fired during a 705 ms block were all served *after* it, at
      +712/+715/+719 ms, each reading `inFlight: null`).
* [ ] `enqueue()` stamps an enqueue time when the caller did not supply one, applied *before* the
      caller's fields are merged, so a caller-supplied enqueue time or `attempts` still wins (US-50,
      ID§Modules). `verified:probe-a` (A1: `{ attempts: 0, ...message }` — caller's `attempts: 7` and
      `enqueuedAt: 123` both survive; today's behaviour is preserved and tests get a dependency-free
      way to control message age).
* [ ] Enqueue time is set once and never moved: neither a retry re-push nor a requeue resets it, so
      "oldest pending wait" measures how long a message has been failing to get through
      (ID§Semantics).
* [ ] No change to processing order, to any existing return-value shape, or to what the two current
      tests assert (ID§Modules). `verified:baseline` — `npm test` green before any change (2 pass, 0
      fail).

Contract

* [ ] The console module's documented contract states that the host process must not block the event
      loop between steps (US-52, ID§Modules). No worker-loop module is added (OOS).

## Edge Cases & Error States

* **Duplicate ids:** ids are caller-supplied and unenforced; every lookup resolves to the first match
  scanning `pending` from the head, then `done`; two messages sharing an id are indistinguishable in
  the list (ID§Semantics, FN). `verified:probe-a` (A5: `enqueue` accepts both, first match wins).
* **Numeric id vs URL text:** ids from a URL are compared as strings against `String(stored.id)`
  (ID§Semantics). `verified:probe-a` (A6: `1 === '1'` is false, `String(1) === '1'` is true) —
  without the coercion every requeue of a numerically-ided message would answer "no such message".
* **Message completed between render and tap:** the `POST` finds the id in `done` → outcome
  `already completed`, queue untouched, reported as the ordinary race it is (US-26).
* **Unknown id:** outcome `no such message`, `404`-styled answer, queue untouched (US-27).
* **Unrecognised list filter value:** falls back to `all`, and the bad value is never echoed into the
  page (ID§Semantics) — this is also the escaping fallback for a hostile `?list=` value.
* **Unknown route:** `404` in the console's own styling, not Node's default (ID§HTTP surface).
* **Mid-render throw:** the full body string is built before anything is written, so the failure
  becomes a clean `500` error page instead of a torn fragment (ID§HTTP surface).
* **Unserializable / oversized / absent payload:** explicit markers, never a blank and never a thrown
  page — three distinct shapes, see the payload FR above (US-19).
* **Handler with no registered type:** message returns to the tail *without* incrementing `attempts`,
  so it circulates forever; the console shows a message that never leaves `pending` with attempts
  stuck at 0 — now diagnosable, not fixed here (FN, OOS). `verified:probe-a` (A2: three consecutive
  `step()`s all return `skipped`, attempts stays 0, `done` stays empty).
* **Async handler that rejects:** invoked synchronously and not awaited, so the rejection escapes;
  the message lands in `done` despite failing and carries no retained error — the console shows it as
  completed because that is what the queue believes (FN). `verified:probe-a`/`probe-e` (A3: status
  `ok`, `done.length` 1). **Additional, not in the ticket:** under Node 22 defaults an unhandled
  rejection with no listener **terminates the process** (`verified:probe-e`, exit code 1) — which
  kills the console with the worker, so the operator sees the STALE state rather than an error page.
  ⚠ inferred (consequence, not a fix — fixing async handling is OOS).
* **10,000-message backlog:** summary stays whole-queue and single-pass; the list is capped with a
  truthful notice (US-13, US-44).
* **Server closed / worker dead:** every poll fails, last-success age crosses `STALE_MS`, page enters
  STALE (US-32).

## Runtime Invariants

*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*

| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| Requeue conserves `pending`: length unchanged, and the moved object is the same object now at index 0 (US-24) | In the `POST /requeue` handler: capture `pending.length` and the resolved message reference before `splice`; after `unshift` compare `pending.length === before` and `pending[0] === ref` | **Refuse** — `500` error page in console styling, no `303`, no `moved` outcome shown to the operator |
| The server is listening on a loopback address only (US-46) | After `listen` resolves, read `server.address().address`; require it in `{127.0.0.1, ::1}` | **Refuse to run** — `server.close()` and reject the start promise, so the process never serves a non-loopback console |
| The screen never presents queue data as current once the last successful poll is older than `STALE_MS` (US-32, US-33, US-35) | Client tick compares `Date.now() - lastPollSuccessAt` against `STALE_MS` on every interval and on `visibilitychange` | **Refuse the calm presentation** — switch to STALE: glyph + text label, counts marked untrusted, last-heard age shown |
| No response body is written partially (ID§HTTP surface) | Every route builds its complete body string and only then calls `writeHead`/`end`; one wrapper try/catch around the build | **Halt that response** — `500` error page built the same way; no half-written body reaches the browser |
| Health counts describe the whole queue, never the rendered subset (US-7, US-13) | Fragment builder asserts `summary.pending === queue.pending.length`, `summary.done === queue.done.length`, `renderedRows <= ROW_CAP`, and that the "of M" figure equals the unsliced filtered length | **Refuse** — `500` rather than emit a summary that could be read as a filtered subset |

Deliberately **not** listed here, because no honest runtime check exists — enforced as ACs with
test-level detection instead, rather than written as an invariant nobody can trip:

* "The console never calls `step()`" (US-29, US-43) → AC-27, detected by a test that replaces the
  exported `step` with a recording double and sweeps every route.
* "Every interpolated value is escaped" (US-42) → AC-25, detected by the hostile-message sweep. A
  runtime check cannot see the interpolation a developer forgot to route through the helper.

## Business Rules  *(needs_ba: false — see Flags)*

Not applicable. The ticket settles every domain rule the console needs (requeue semantics, the three
outcomes, id resolution, enqueue-time immutability, filter whitelisting, error retention) and both
stakeholder roles — on-call operator and maintainer — are spoken for across all 52 stories. Per the
bounce discipline, the residual silences are **numeric thresholds, not rules**, and are recorded in
Open Items (OI-5, OI-6) rather than authored as business rules here.

## Design Notes  *(needs_ui: true)*

Read before naming anything: `/tmp/eval33/fixture/CLAUDE.md` (read in full — no build step, ES
modules, named exports, no third-party dependencies) and the full source tree
(`find` → exactly four files: `package.json`, `CLAUDE.md`, `src/queue.js`, `test/queue.test.js`).
**There is no CSS, no component, no token, no design system, and no markup of any kind in this repo
today** — verified, not assumed. So the audit below has no reuse column to fill honestly, and the
console must establish the baseline itself, written down once and reused (US-48).

### Component Audit

| Component | Reuse? | Token ref | Notes |
|-----------|--------|-----------|-------|
| `StatusBanner` | new | `--oc-ok` / `--oc-warn` / `--oc-bad`, `--oc-space-2` | No existing UI in repo to reuse. Carries the LIVE/STALE/ERROR/MOVED glyph + text label pair (US-41); the one element the stale determination writes to |
| `SummaryGrid` | new | `--oc-space-2`, `--oc-fg`, `--oc-muted` | Five figures (US-1..5); CSS grid, 2 cols at 375 px, 5 cols at desk width; must fit above the fold at 375 px (US-6) |
| `FilterBar` | new | `--oc-tap`, `--oc-rule` | List filter + type filter + clear-filter control (US-10, US-11, US-14); plain `<form method="get">`, no JS |
| `MessageTable` | new | `--oc-rule`, `--oc-muted`, `--oc-tap` | id / type / attempts / list (US-8); each row an `<a>` to detail (US-15); truncation notice as the last row (US-13) |
| `DetailPanel` | new | `--oc-space-3`, `--oc-muted` | Full message + payload block + most-recent-error block with its timestamp (US-16..18) |
| `PayloadBlock` | new | `--oc-mono`, `--oc-muted` | `<pre>`; renders the JSON / primitive / literal-marker / unserializable-marker / truncation-notice cases (US-19) |
| `ConfirmPanel` | new | `--oc-tap`, `--oc-bad` | Separate document, no poll loop, so a background refresh cannot move it under a thumb (US-22, US-36) |
| `EmptyState` | new | `--oc-muted` | Two distinct texts: never-enqueued vs filter-matched-nothing (US-37, US-38) |
| `ErrorState` | new | `--oc-bad` | `500` and `404` bodies in console styling (US-27, US-40) |

No component is exported (ID§Modules) — they are internal string-returning functions, named here so
the build stages share a vocabulary, not so tests can reach them.

### Token Mapping

No design system — hardcoded baseline, declared once in a single `:root` block inside the console
module and reused by every view (US-48):

* page background / foreground: `--oc-bg` `#111` / `--oc-fg` `#eee` (dark-first — the operator is in
  the dark, US-41)
* de-emphasised text: `--oc-muted` `#9a9a9a`
* rules and table borders: `--oc-rule` `#333`
* healthy: `--oc-ok` `#4caf50` · stale: `--oc-warn` `#ffb300` · failure: `--oc-bad` `#ef5350`
  — every one paired with a glyph + label, colour never load-bearing (US-41)
* spacing scale: `--oc-space-1` `4px` / `--oc-space-2` `8px` / `--oc-space-3` `16px`
* minimum tap target: `--oc-tap` `44px` (phone, 3am, US-22, US-39)
* text: `--oc-font` system sans stack · `--oc-mono` system mono stack (payload block)
* content max width: `--oc-maxw` `900px` (desk width; unconstrained below it, US-47)

Glyph vocabulary (the non-colour channel, US-41): LIVE `●` · STALE `▲` · ERROR `✕` · MOVED `✓` ·
COMPLETED `◍` · TRUNCATED `…`.

### Screen States

| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|
| Console page `/` | Never-enqueued: "no message has ever been enqueued" + LIVE banner (US-37). Drained: counts `0 pending / N done` — never the never-enqueued text | **Impossible by design, stated not skipped:** fully server-rendered, so first paint is real data and no artificial loading state exists (ID§HTTP surface) | Summary + filters + capped list, LIVE banner, last-heard age | `500` page in console styling, ERROR banner, no partial body (US-40) |
| Fragment region (polled) | Filter-matched-nothing: "no message matches this filter" + clear-filter control (US-38) | In-progress indication on the banner while a poll is outstanding (US-39) | Swapped markup, banner LIVE, last-heard age reset | Poll failed: previous markup left in place, banner flips to STALE with the ageing last-heard figure — the failure state is *not* an empty list (US-32, US-33) |
| Detail `/message` | Payload absent → explicit `undefined`/`null` literal marker, not a blank (US-19). No retained error → "no error recorded for this message" | **Impossible by design:** server-rendered, no client fetch on this route | Full message + payload + most-recent-error block with timestamp and list membership (US-16..18) | Unknown id → `404`-styled "no such message" (US-27) |
| Confirm `/requeue` (GET) | n/a — the page exists only for a resolvable id | **Impossible by design:** server-rendered, no poll loop on this document (US-36) | Message summary + confirm button (`POST`) + cancel back to the list with the filter preserved (US-22, US-20) | Id in `done` → already-completed answer, no confirm button rendered at all (US-25). Unknown id → `404`-styled (US-27) |
| Not-found / error | n/a | n/a | n/a | `404` and `500` both in console styling with the ERROR glyph + label (US-27, US-40) |

Design ACs (component + token + state + viewport) are folded into Acceptance Criteria as AC-29..AC-33.

## Solution Architecture  *(needs_sa: true)*

Three decisions. The first two are the ticket's, restated as approach tables so the build stages
inherit the reasoning rather than the conclusion; the third is genuinely open in the ticket and is
decided here on execution evidence.

**Decision 1 — how the console gets at queue state.** Chosen: **A, direct reference, same process**
(ID§Chosen-1).

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A — direct reference to the live queue, read per request | Requeue is a plain array `splice`/`unshift`; torn-view problem cannot arise (Node single-threaded, `step()` synchronous); zero cost on `step()`; queue keeps its `{pending, done}` shape | Console cannot respond while a synchronous handler blocks the loop | **chosen** — the only option that satisfies requeue *and* same-moment consistency at once |
| B — queue grows an event/subscription hook, console keeps a derived read-model | Console could survive some decoupling | Puts cost on the hot path (US-43); *introduces* the torn-view risk US-45 guards against; adds an observer registry and lifecycle to the queue | rejected — contradicts US-43 and US-45 |
| C — worker writes a snapshot file, separate console process reads it | Console survives worker death | Requeue needs an IPC command channel, which makes "outcome visible immediately" (US-28) unsatisfiable; serializing 10k messages per step is not a small cost (US-43, US-44) | rejected — breaks US-28 and US-43 |

**Decision 2 — how the screen stays current.** Chosen: **A, client polls for a server-rendered
fragment** (ID§Chosen-2).

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A — poll a fragment endpoint, swap markup into one container | Staleness becomes a client-side determination — the only side that survives the server being gone (US-32); sleeping phone needs no special handling (US-35); rendering exists once, escaping has one home, client never builds markup from queue data | Fixed-interval latency; a small hand-written script stays untested (TD accepted risk) | **chosen** |
| B — Server-Sent Events | Lower latency | Server has nothing to push *from* under decision 1 — would reopen it or need an internal timer; needs hand-written reconnect + heartbeat, i.e. *more* client JS | rejected — reopens decision 1 |
| C — whole-page reload on a timer | Trivial | Hostile mid-interaction: drops the filter, the detail view, or an open confirmation (US-36); a failed reload surrenders the screen to the browser's error page (US-40) | rejected |

**Decision 3 — representing "which message was eating the worker".** The ticket's module surface says
`step()` "marks which message is in flight … and clears the mark when the message leaves the handler
by either path", and its Accepted-consequence paragraph relies on that mark to make "the first
successful poll after the handler returns name the message that was eating the worker". Those two
sentences cannot both hold. `verified:probe-b`: during a 705 ms synchronous handler, **zero** requests
were served; all three polls landed after it (+712/+715/+719 ms) and each read the mark as `null`. A
mark cleared on handler exit is observable by no HTTP request, ever — it is dead data.

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A — retain a **last-step record** (`id`, `startedAt`, `durationMs`, `outcome`), overwritten each step | Delivers exactly the mitigation the ticket promises; observable on the first poll after the block; O(1) per step, one object write, no hot-path cost (US-43) | One extra retained field on the queue object | **chosen** — smallest change that makes the ticket's own stated mitigation true |
| B — keep the mark, clear it on handler exit (as literally written) | Matches the ticket's module-surface wording | Provably unobservable (`probe-b`); ships a field no view can ever display | rejected — dead data |
| C — drop the concept entirely; rely on retained error + `attempts` | Least change to `queue.js`; no story requires an in-flight concept (none of US-1..52 mentions it) | Loses the "names the message that was eating the worker" mitigation the ticket accepted a real consequence on the strength of | rejected — silently drops a promised behaviour |

Consequence still accepted, unchanged: an in-process console cannot respond *while* the worker is
blocked; the operator sees STALE during the block, then the last-step record after it (ID§Chosen-1).

* **Integration contracts:**
  * `src/console.js` → `src/queue.js`: reads `queue.pending`, `queue.done`, `queue.lastStep`; writes
    `queue.pending` only, only via requeue's `splice`+`unshift`. It does **not** import `step`,
    `enqueue`, or `registerHandler` (US-29, US-30).
  * `src/console.js` public surface: one named export, `startConsole(queue, { port = 0, now = Date.now
    } = {})` → `Promise<http.Server>`, resolving once listening, returning the server so the caller can
    `close()` it (ID§Modules). No host option — loopback is bound in code (US-46). Render/escape/style
    are private (ID§Modules).
  * Host-process contract: must yield to the event loop between `step()` calls (US-52).
* **Data model impact:** no database, no migration. Three additive fields on the in-memory message /
  queue objects: `message.lastError = { message, at }`, `message.enqueuedAt`, `queue.lastStep =
  { id, startedAt, durationMs, outcome }`. No existing field changes meaning; no return-value shape
  changes (ID§Modules).
* **NFR targets:**
  * Health summary over 10,000 pending: one pass, no nested scan (US-44). Measured headroom
    `verified:probe-c` — 0.35 ms per summary at 10k, so the smoke ceiling of 250 ms per `/fragment`
    response is ~700× headroom and cannot be mistaken for a benchmark (TD).
  * Zero added work in `step()` beyond O(1) field writes (US-43).
  * Response payload at 10k with `ROW_CAP = 200`: ~8 KB vs ~431 KB uncapped `verified:probe-c` — the
    cap is what keeps a phone on cellular usable, and it is a payload-size guard, not a CPU one.
  * Fault tolerance: no non-loopback listener ever (US-46); no partial response body ever
    (ID§HTTP surface).

## Codebase Survey

* Explored (read in full, whole repo — four files): `/tmp/eval33/fixture/package.json`,
  `/tmp/eval33/fixture/CLAUDE.md`, `/tmp/eval33/fixture/src/queue.js`,
  `/tmp/eval33/fixture/test/queue.test.js`. `find` confirms no other file exists — no CSS, no UI, no
  config, no CI.
* Runtime: Node `v22.22.1` — `verified` — so the platform `fetch`, `AbortSignal.timeout`, and
  `node:test` are all available without a dependency (TD, FN§no-dependency rule).
* Baseline: `npm test` → `node --test test/*.test.js` → 2 pass / 0 fail — `verified`. The glob already
  picks up a new `test/*.test.js` file, so `package.json` needs no change.
* Integrate with / conventions to follow: ES modules, `"type": "module"`; **named exports, no default
  export**; source in `src/`, test filename mirrors source filename; `node:test` + `node:assert/strict`;
  one behaviour per `test()`; direct module imports; plain closures as test doubles — the existing
  "runs a registered handler" test collects calls into an array, and that is this repo's whole
  substitute for a mocking library (CLAUDE.md, TD§prior art).
* Known hazard inherited: `HANDLERS` is a module-global `Map` never reset between tests, and the
  existing tests already leak registrations across files. New tests use distinct type names rather
  than adding a reset function — adding one purely for tests would widen the production surface for
  the test's convenience (TD§hazards). `verified:probe-a` — registrations made in one probe persisted
  for the whole process.

## Reality Constraints

*(what the world outside this feature actually does — verified by running/reading, not assumed.)*

### External dependencies

| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| `src/queue.js` `step()` | Must be driven by a host loop that yields between calls (US-52); runs the handler **synchronously** and does not await it | `{status:'idle'}` \| `{status:'skipped',id}` \| `{status:'ok',id}` \| `{status:'retry',id,attempts}` — `verified:probe-a` | That a message in `done` succeeded (an async rejection still lands it in `done` — `probe-a` A3); that `attempts` rises on every failure (a missing handler re-queues at attempts 0 — A2); that the process survives a handler's async rejection (Node 22 default terminates it, exit 1 — `probe-e`) |
| `src/queue.js` `enqueue()` | None | Pushes `{ attempts: 0, ...message }`; caller fields win over the default — `verified:probe-a` A1 | Id uniqueness; any id type; presence of `type`, `payload`, or a registered handler — `verified:probe-a` A5 |
| `node:http` `server.listen(0, '127.0.0.1')` | `address()` valid only after the `listening` event | `{address:'127.0.0.1', family:'IPv4', port:<ephemeral>}` — `verified:probe-d` D1/D3 | A stable port across runs (a fresh ephemeral each time — D3); that an unclosed server lets the test runner exit (`probe-d` D4: the handle stays live until `close()`) |
| platform `fetch` (Node 22 global) | — | Follows `303` and rewrites POST→GET; `res.redirected` true; `res.url` carries the final query — `verified:probe-d` D2. `redirect:'manual'` exposes status `303` + raw `Location` — D2 | Not to follow redirects by default — a test asserting the `Location` header **must** pass `redirect:'manual'`, or it will assert against the followed page instead |
| `JSON.stringify` (payload rendering) | — | String for objects/arrays/primitives — `verified:probe-c` C3 | A string at all: `undefined` and functions **return `undefined`** without throwing; circular values and `BigInt` **throw `TypeError`**; `Map`/`Set` and symbol-valued props serialize *lossily* to `{}` with no signal. Three shapes, not one |

### Paths that must agree

* `GET /` (server-rendered first paint) ↔ `GET /fragment` (poll target) — **equivalent means:** for
  the same queue state and the same `list`/`type` filters, the five summary figures, the row set, the
  row order, and the truncation notice are identical, because both call the same summary + row
  builders. **May differ:** the fragment omits the page chrome (`<html>`, style block, filter form,
  poll script) and the last-heard-age figure, which is client-owned (ID§Chosen-2, US-45).
* Confirm page (`GET /requeue`) ↔ requeue outcome (`POST /requeue`) — **equivalent means:** the
  confirm page is offered only when the id resolves in `pending`, and the `POST` re-resolves the same
  id by the same first-match-from-head rule. **May legitimately differ:** the worker may complete the
  message in the gap, so the confirm page can say "will move" and the `POST` answer "already
  completed" — this divergence is the specified race, not a bug (US-26).
* Requeued `pending` ↔ pre-requeue `pending` — **equivalent means:** same multiset of message objects,
  same `length`, same `attempts` and `enqueuedAt` per message, same relative order of every
  non-moved message. **May differ:** the index of exactly one message, which becomes 0 —
  `verified:probe-f` F3 (US-24).

### Non-deterministic inputs

| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| Clock (`Date.now`) — oldest-pending wait, error timestamp, last-step timing | **pinned** — injected via `startConsole(queue, { now })`; message age controlled by supplying `enqueuedAt` at enqueue, which the spread order permits (`verified:probe-a` A1) | Any wall-clock assertion is otherwise flaky (TD§hazards) |
| TCP port | **floating, deliberately** — port `0` everywhere, never a fixed port; the test reads `server.address().port` | A fixed port collides with a parallel run or a leftover process; `verified:probe-d` D3 shows each bind takes a distinct ephemeral port |
| Elapsed wall time in the 10k smoke check | **floating** — a generous ceiling, asserted only as a guard against an accidental quadratic pass; explicitly **not** a benchmark and must not be tightened into one (TD§hazards) | Machine-dependent; measured headroom is ~700× (`verified:probe-c` C5) |
| Network | **loopback only** — `127.0.0.1`, real sockets, no external host (US-46) | The seam under test *is* real HTTP (TD seam 2); `verified:probe-d` D1 shows a LAN address is refused |
| Handler registry (`HANDLERS`, module-global, never reset) | **floating and shared** — mitigated by giving every new test a distinct `type` name | Adding a reset export would widen the production surface for the test's convenience (TD§hazards); `verified:probe-a` — registrations persist process-wide |
| Filesystem | **not used** — the console reads and writes no file (ID§Chosen-1 rejects the snapshot option; OOS rejects persistence) | — |
| Randomness, timezone, locale | **not used** — no random source; all timestamps rendered as elapsed durations and raw epoch ms, never locale-formatted, so no `Intl`/TZ dependency enters | Locale-formatted output would make assertions machine-dependent. ⚠ inferred (the ticket does not address formatting) |

## Files to Touch

| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `/tmp/eval33/fixture/src/queue.js` | edit | **exists** (read in full, 39 lines) | Three additive changes: retained `lastError`, retained `lastStep` record, `enqueuedAt` default applied before the caller spread (US-49, US-50, Decision 3) |
| `/tmp/eval33/fixture/src/console.js` | new | follows pattern at `/tmp/eval33/fixture/src/queue.js` (ES module, named export only, no default, stdlib imports only) | The one new module: routing, summary, rendering, escaping, style baseline, requeue (ID§Modules). Name ⚠ inferred — ticket names no file, see OI-7 |
| `/tmp/eval33/fixture/test/queue.test.js` | edit | **exists** (read in full, 20 lines) | Existing queue seam reused for the three queue changes; new `test()` blocks in the existing style, distinct type names (TD seam 1, TD§hazards) |
| `/tmp/eval33/fixture/test/console.test.js` | new | follows pattern at `/tmp/eval33/fixture/test/queue.test.js` (`node:test` + `node:assert/strict`, one behaviour per `test()`, closures as doubles); filename mirrors `src/console.js` per CLAUDE.md | The one new seam: ephemeral-port server + platform `fetch` (TD seam 2) |
| `/tmp/eval33/fixture/package.json` | **no change** | **exists**; `"test": "node --test test/*.test.js"` — glob already matches a new test file (`verified`) | Named to close the question, not to be edited |

## Dependencies

* New packages: **none** — `node:http`, `node:test`, `node:assert/strict`, and the platform `fetch`
  cover everything (FN§no-dependency rule, CLAUDE.md). `verified` on Node v22.22.1.
* Schema changes / migrations: none — in-memory only (OOS§persistence).

## Acceptance Criteria

* [ ] **AC-1** Given a queue with 3 pending and 2 done, When `GET /`, Then the body contains the
      pending count 3 and the done count 2 as text.
* [ ] **AC-2** Given pending messages of types `a`,`a`,`b`, When `GET /`, Then the distinct-type
      figure reads 2.
* [ ] **AC-3** Given pending messages with `attempts` 0, 4, 2, When `GET /`, Then the highest-attempts
      figure reads 4.
* [ ] **AC-4** Given injected `now = 10_000` and a pending message with `enqueuedAt = 4_000`, When
      `GET /`, Then the oldest-pending-wait figure reads 6 s (deterministic, no wall clock).
* [ ] **AC-5** Given 500 pending of which 10 are type `x`, When `GET /fragment?list=pending&type=x`,
      Then the five summary figures still describe all 500 pending, not the 10 shown.
* [ ] **AC-6** Given pending `[m1,m2,m3]`, When `GET /`, Then `m1`'s row precedes `m2`'s and `m3`'s in
      the body, and `pending[0]` is `m1`.
* [ ] **AC-7** Given `?list=done`, Then only done rows appear; given `?list=<junk>`, Then all rows
      appear and the literal junk string does not appear anywhere in the body.
* [ ] **AC-8** Given pending types `a`,`b` and done type `c`, When `GET /`, Then the type filter
      offers exactly `a`,`b`,`c` and no other value.
* [ ] **AC-9** Given 250 matching messages and `ROW_CAP = 200`, When `GET /`, Then exactly 200 rows
      render and the body contains "first 200" and "250".
* [ ] **AC-10** Given `?list=done&type=a`, When the clear-filter control's href is followed, Then the
      response is the unfiltered list.
* [ ] **AC-11** Given a message `m` in `pending`, When `GET /message?id=<m.id>`, Then the body
      contains its id, type, attempts, and the word `pending`.
* [ ] **AC-12** Given payload `{a:1}`, Then the detail body contains the pretty-printed JSON text;
      given payload `null`, Then it contains an explicit `null` marker, not an empty cell.
* [ ] **AC-13** Given a handler that threw `new Error('disk full')` and a later successful attempt,
      When the message's detail is fetched from `done`, Then the body contains `disk full`, a
      most-recent-error label, and a recorded-at timestamp.
* [ ] **AC-14** Given a circular payload, a `BigInt` payload, and a `undefined` payload, When each
      detail page is fetched, Then each returns `200` with a distinct explicit marker and none
      returns `500` — three shapes, one per case (`verified:probe-c` C3).
* [ ] **AC-15** Given a payload longer than `PAYLOAD_MAX`, Then the body contains a truncation notice
      and does not contain the tail of the payload.
* [ ] **AC-16** Given `GET /message?id=<id>&list=done&type=a`, Then the back link's href carries
      `list=done` and `type=a`.
* [ ] **AC-17** Given pending `[a,b,c]`, When `POST /requeue` with `id=c`, Then `pending` is
      `[c,a,b]`, `pending.length` is 3, and `c.attempts` and `c.enqueuedAt` are unchanged.
* [ ] **AC-18** Given the same, Then the response follows a `303` to `/?outcome=moved&id=c`, and with
      `redirect:'manual'` the status is `303` and `Location` is that path (`verified:probe-d` D2).
* [ ] **AC-19** Given `id` present only in `done`, When `POST /requeue`, Then the outcome is
      `already completed`, `pending` and `done` are byte-identical to before, and the body text reads
      as a normal outcome, not an error.
* [ ] **AC-20** Given an id in neither list, When `POST /requeue`, Then the outcome is `no such
      message` and neither list changes.
* [ ] **AC-21** Given a message in `done`, When `GET /requeue?id=<id>`, Then the body contains no
      confirm/submit control and states the message already completed.
* [ ] **AC-22** Given a message in `pending`, When `GET /requeue?id=<id>`, Then the body contains a
      confirm control targeting `POST /requeue`, And `pending` is unchanged by the `GET`.
* [ ] **AC-23** Given a stored numeric id `7`, When `POST /requeue` with the URL text `7`, Then the
      outcome is `moved` — not `no such message` (`verified:probe-a` A6).
* [ ] **AC-24** Given two pending messages sharing id `dup`, When `POST /requeue` with `dup`, Then the
      one nearer the head moves and `pending.length` is unchanged.
* [ ] **AC-25** Given a message whose `type`, `payload`, and `id` each contain `<script>` and `"` and
      `'`, When `GET /`, `GET /fragment`, `GET /message`, and `GET /requeue` are each fetched, Then
      no response body contains the raw sequence `<script` (`verified:probe-c` C4).
* [ ] **AC-26** Given `startConsole(queue)`, Then `server.address().address` is a loopback address,
      And a request to a non-loopback address of this host on the same port is refused
      (`verified:probe-d` D1).
* [ ] **AC-27** Given the exported `step` replaced by a recording double, When every route is fetched
      once, Then the double records zero calls, And `pending`'s order is unchanged across the sweep
      (US-29, US-43).
* [ ] **AC-28** Given 10,000 pending messages across 12 types, When `GET /fragment` is fetched, Then
      the five figures are correct, at most `ROW_CAP` rows render, and the response completes in under
      **250 ms** — a guard against an accidental quadratic pass, explicitly not a benchmark and not to
      be tightened into one (TD§hazards). The number is a ceiling with ~700× measured headroom, not a
      target: `verified:probe-c` C5 measured 0.35 ms per summary at 10k.
* [ ] **AC-29** *(design)* Given `GET /`, Then the emitted document declares, in its single `:root`
      style block, a `SummaryGrid` rule of 2 columns at the default (phone-first) tier carrying all
      five figures, And `StatusBanner` precedes `SummaryGrid` in document order, which precedes
      `FilterBar` and `MessageTable` (US-6, US-47). **Assertable at the HTTP seam as emitted CSS and
      document order only** — the rendered pixel height at 375 px is *not* automatically verified,
      because a DOM/browser seam is a third-party dependency this repo forbids (TD, OOS); it is a
      review-by-eye item, recorded here rather than left implied.
* [ ] **AC-30** *(design)* Given `GET /`, Then the emitted style block declares a desk-width tier
      (min-width breakpoint) placing the five figures in one row inside `--oc-maxw`, with
      `StatusBanner` still first in document order at both tiers (US-47). Same seam limitation as
      AC-29: emitted CSS and order are asserted; rendered layout is review-by-eye.
* [ ] **AC-31** *(design)* Given each of LIVE / STALE / ERROR / MOVED, Then `StatusBanner` emits a
      distinct text label **and** a distinct glyph, and the body carries that pairing with no state
      distinguished by a `--oc-ok`/`--oc-warn`/`--oc-bad` value alone (US-41).
* [ ] **AC-32** *(design)* Given `pending` and `done` both empty and nothing ever enqueued, Then the
      body contains the never-enqueued text; given a filter matching nothing over a non-empty queue,
      Then the body contains the no-match text plus the clear-filter control, and neither text ever
      appears in the other case (US-37, US-38) (`verified:probe-f` F2).
* [ ] **AC-33** *(design)* Given every view, Then the emitted CSS declares a min-height of `--oc-tap`
      for every interactive control selector, And the `:root` token block appears exactly once per
      document (string count 1) across `/`, `/message`, `/requeue`, and the 404/500 bodies (US-48).
* [ ] **AC-34** Given a handler that throws a non-`Error` (a string), When `step()` runs, Then the
      message carries a `lastError.message` with that text coerced to string, and `attempts` is 1.
* [ ] **AC-35** Given `enqueue(q, {id:1,type:'t',payload:1,attempts:7,enqueuedAt:123})`, Then the
      stored message has `attempts` 7 and `enqueuedAt` 123 — the caller wins over both defaults
      (`verified:probe-a` A1).
* [ ] **AC-36** Given a handler that blocks 50 ms then returns, When `step()` runs, Then
      `queue.lastStep` afterwards names that message id, its start time, a duration ≥ 50, and outcome
      `ok` — the record is **retained**, not cleared (Decision 3, `verified:probe-b`).
* [ ] **AC-37** Given the console module, Then it exports exactly one name, `startConsole`, and the
      render/escape/style functions are not exported (ID§Modules).
* [ ] **AC-38** Given any route throws mid-render, Then the response is a `500` in console styling
      with the ERROR label and a complete body — never a truncated one (US-40).

## AC Coverage Map

| AC | Source | Covered by (files/steps) |
|----|--------|--------------------------|
| AC-1 | US-1, US-2 | `src/console.js` summary builder → `test/console.test.js` |
| AC-2 | US-3 | `src/console.js` summary builder (Set over `pending`) → `test/console.test.js` |
| AC-3 | US-4 | `src/console.js` summary builder → `test/console.test.js` |
| AC-4 | US-5, US-50 | `src/queue.js` `enqueuedAt`; `src/console.js` summary + injected `now` → `test/console.test.js` |
| AC-5 | US-7 | `src/console.js` fragment builder (summary takes the queue, rows take the slice) → `test/console.test.js` |
| AC-6 | US-9 | `src/console.js` row builder (no sort) → `test/console.test.js` |
| AC-7 | US-10, ID§Semantics | `src/console.js` filter whitelist → `test/console.test.js` |
| AC-8 | US-11, US-12 | `src/console.js` type-option builder → `test/console.test.js` |
| AC-9 | US-13 | `src/console.js` `ROW_CAP` + truncation notice → `test/console.test.js` |
| AC-10 | US-14 | `src/console.js` `FilterBar` clear control → `test/console.test.js` |
| AC-11 | US-8, US-15 | `src/console.js` detail route → `test/console.test.js` |
| AC-12 | US-16, US-19 | `src/console.js` `PayloadBlock` → `test/console.test.js` |
| AC-13 | US-17, US-18, US-49, ID§Semantics | `src/queue.js` `lastError`; `src/console.js` `DetailPanel` → `test/console.test.js` |
| AC-14 | US-19 | `src/console.js` `PayloadBlock` three-shape guard → `test/console.test.js` |
| AC-15 | US-19 | `src/console.js` `PAYLOAD_MAX` truncation → `test/console.test.js` |
| AC-16 | US-20 | `src/console.js` detail back link → `test/console.test.js` |
| AC-17 | US-21, US-23, US-24 | `src/console.js` requeue move → `test/console.test.js` |
| AC-18 | US-28 | `src/console.js` `POST` → `303` → `test/console.test.js` (`redirect:'manual'`) |
| AC-19 | US-26 | `src/console.js` outcome resolution → `test/console.test.js` |
| AC-20 | US-27 | `src/console.js` outcome resolution → `test/console.test.js` |
| AC-21 | US-25 | `src/console.js` confirm route guard → `test/console.test.js` |
| AC-22 | US-22 | `src/console.js` confirm route → `test/console.test.js` |
| AC-23 | ID§Semantics (id-as-string) | `src/console.js` id resolver → `test/console.test.js` |
| AC-24 | ID§Semantics (first match from head), FN | `src/console.js` id resolver → `test/console.test.js` |
| AC-25 | US-42 | `src/console.js` single escaping helper → `test/console.test.js` hostile sweep |
| AC-26 | US-46 | `src/console.js` `startConsole` loopback bind + address assert → `test/console.test.js` |
| AC-27 | US-29, US-30, US-43 | `src/console.js` (no `step` import) → `test/console.test.js` recording double |
| AC-28 | US-44, US-45 | `src/console.js` single-pass summary → `test/console.test.js` 10k smoke |
| AC-29 | US-6, US-47 | `src/console.js` `SummaryGrid` + `:root` tokens → `test/console.test.js` (markup/CSS text assertions only) |
| AC-30 | US-47 | `src/console.js` `SummaryGrid` desk breakpoint → `test/console.test.js` |
| AC-31 | US-41 | `src/console.js` `StatusBanner` glyph+label pairs → `test/console.test.js` |
| AC-32 | US-37, US-38 | `src/console.js` `EmptyState` two texts → `test/console.test.js` |
| AC-33 | US-48, US-22, US-39 | `src/console.js` `:root` token block, emitted once → `test/console.test.js` |
| AC-34 | US-49, ID§Modules (non-`Error` coercion) | `src/queue.js` catch branch → `test/queue.test.js` |
| AC-35 | US-50, ID§Modules (default-before-merge) | `src/queue.js` `enqueue` spread order → `test/queue.test.js` |
| AC-36 | ID§Chosen-1 Accepted-consequence, **corrected** — ⚠ inferred (Decision 3) | `src/queue.js` `lastStep` record → `test/queue.test.js` |
| AC-37 | ID§Modules | `src/console.js` export surface → `test/console.test.js` |
| AC-38 | US-40, ID§HTTP surface | `src/console.js` route wrapper → `test/console.test.js` |
| US-31, US-32, US-33, US-34, US-35, US-36, US-39 | US-31..36, US-39 | `src/console.js` inline poll script + `StatusBanner`/`ConfirmPanel` markup. **Not covered by an automated AC** — the client script is the one deliberately untested surface (TD accepted risk); the server half (`/fragment` responding, `POLL_MS`/`STALE_MS` constants present in the emitted document, confirm page carrying no poll loop) *is* asserted, in AC-5 / AC-22 / AC-33 |
| US-51 | US-51 | `test/console.test.js` existing — every console AC above is driven over real HTTP |
| US-52 | US-52 | `src/console.js` module doc comment — reviewed at spec-review, no runtime assertion possible |

## Risks & Watch-outs

* **`src/queue.js` is a shared file** — the queue module is the repo's only source file and the only
  thing the existing tests cover. All three changes must be additive; `verified:baseline` gives the
  pre-change green (2 pass) to diff against.
* **Spread-order regression.** `{ attempts: 0, ...message }` is load-bearing: adding `enqueuedAt` as
  `{ ...message, enqueuedAt: now() }` would silently overwrite a caller-supplied value and break both
  AC-35 and every clock-pinned test that depends on it (`verified:probe-a` A1). Default first, spread
  second.
* **Test-runner hang.** An unclosed server keeps the process alive — `verified:probe-d` D4 (handle
  count 2 → 0 only after `close()`). Every test that starts one must close it, and port `0` always.
* **Handler-registry leakage** across test files (module-global `Map`, never reset) — distinct type
  names per new test, no reset export (TD§hazards).
* **The client poll script is untested by construction.** Mitigation is structural: all rendering is
  server-side, so the script stays at poll / swap / track last success / toggle stale. If a change
  makes it big enough to want a DOM test, that is the signal to move logic to the server, not to add
  a test framework (TD accepted risk).
* **Async-rejecting handler kills the process** under Node 22 defaults (`verified:probe-e`, exit 1),
  taking the console with it. Out of scope to fix (OOS), but it means "console unreachable" has a
  second, more likely cause than "worker blocked" — the STALE state must not claim which.
* **Race between confirm page and `POST`** is specified, not defensive: the confirm page may promise
  a move the `POST` answers as already-completed (US-26).

## Out of Scope

* Authentication, authorisation, multi-user access — loopback, one operator; a decision for this
  version, not an oversight (OOS).
* Any mutation other than requeue: no payload edits, no deletes, no pause/resume, no handler
  registration from the UI, no clearing `done` (OOS).
* Persistence of anything across process restarts — console state, history, metrics (OOS).
* Charts, time-series, trend lines, alerting, paging integration (OOS).
* A worker loop — the repo has none and this feature adds none (OOS).
* Search and pagination — list and type filters are the only navigation (OOS).
* Fixing the pre-existing queue behaviours the console now exposes: handler-less messages circulating
  at attempts 0, async rejections landing in `done`, non-unique ids (OOS, FN). The console makes them
  visible; changing them is separate work.
* Browser-level / end-to-end tests — unreachable without a third-party dependency (OOS, TD).
* Remote access, TLS, reverse proxy, any non-loopback binding (OOS).

## Flags

* `needs_ba`: **false** — the ticket settles every domain rule (requeue semantics, three outcomes, id
  resolution, enqueue-time immutability, filter whitelist, error retention) and both stakeholder roles
  across 52 stories; nothing is vague on *what*. The residual gaps are numeric thresholds, not rules —
  bounced upstream in OI-5/OI-6 rather than authored here.
* `needs_ui`: **true** — an entire new set of screens: console page, polled fragment, detail, confirm,
  404/500. Fired; step-3 work done above (component audit against the real tree, token baseline, all
  four screen states per view with the impossible ones named and explained, design ACs AC-29..AC-33).
* `needs_sa`: **true** — competing approaches with lasting consequences (state access, freshness
  transport) plus explicit NFRs (10k responsiveness, zero added `step()` cost, same-moment
  consistency, loopback-only). Fired; step-3 work done above (three decisions, each with 3 approaches,
  trade-offs, and a recorded choice — Decision 3 decided on execution evidence).
* `needs_devops`: **false** — no env var, no migration, no feature flag, no infra. `package.json`
  unchanged; port is a function argument defaulting to an ephemeral one; no deploy artefact.

## Exit Criteria

**Stop condition:** every AC-1..AC-38 passes at its named seam with `npm test` green and every Runtime
Invariant's check present in the code — **or** two consecutive attempt rounds pass without the
relevant progress number below moving, at which point stop and summon the human rather than attempt a
third.

* progress: number of failing assertions reported by `npm test` (must reach 0, from a baseline of 2
  passing / 0 failing before any change).
* progress: number of ACs in the AC Coverage Map with no passing test at their named seam (must reach
  0 of 38).
* progress: number of the four rendering views (`/`, `/fragment`, `/message`, `/requeue`) whose body
  still contains the raw sequence `<script` under the hostile-message sweep (must reach 0 of 4).
* progress: number of (view, state) cells in the Screen States table with no implementation or no
  explicit impossible-by-design justification (must reach 0 of 20).
* progress: number of Runtime Invariants rows whose detection check is absent from the code (must
  reach 0 of 5).
* progress: number of servers started by the test file that are not closed (must reach 0) —
  observable as the runner failing to exit.
* Single-shot pass/fail, no progress number: the loopback-binding check (AC-26); the requeue
  conservation assert (AC-17); the 10k smoke ceiling (AC-28); the export-surface check (AC-37).

## Mode Prediction

* **kestra-build mode: `full`.** Reason: two seams, one new module plus additive edits to the repo's
  only shared source file, 38 ACs including a security-shaped escaping sweep and a queue-conservation
  invariant — the write-tests / freeze-tests split is load-bearing here, because the hostile-sweep and
  requeue-conservation tests are exactly the ones a `fixing` stage would be tempted to soften. `lite`
  would collapse that split and remove the only cheap window to repair a defective test before the
  hash freeze.

## Open Items

Non-empty — flagged plainly at handoff. Items OI-1..OI-3 are the ticket's **own** recorded
unconfirmed assumptions, carried forward unresolved; OI-4 and OI-5 are new bounces raised by this
pass. None blocks starting the build; OI-4 changes one queue field if reversed, OI-2 would rewrite
most of this spec.

* **OI-1 — bounce upstream (seam altitude).** The ticket assumes "highest seam possible" means the
  HTTP boundary, not the browser, because every route to a browser seam is a third-party dependency.
  If a dev-only test dependency were acceptable, the browser becomes the better seam and the whole
  Testing Decisions section should be revisited. Needs the person who owns the no-dependency rule.
* **OI-2 — bounce upstream (process topology).** The ticket assumes the console may live in the
  worker's process. Decisions 1 *and* 2 both rest on it. If the console must survive the worker dying,
  Decision 1 flips to a snapshot file, requeue needs a command channel, US-28 becomes unsatisfiable as
  written, and most of this spec changes. Needs a product/ops decision, not an engineering one.
* **OI-3 — bounce upstream (queue-seam reuse).** The ticket assumes asserting the three queue changes
  at the existing queue seam is preferable to routing them through HTTP for a seam count of one.
  Needs confirmation from whoever owns the one-seam ideal (FN§seam count).
* **OI-4 — bounce upstream (ticket correction, evidence attached).** The ticket's ID§Chosen-1
  "Accepted consequence" paragraph says the retained in-flight mark lets "the first successful poll
  after the handler returns name the message that was eating the worker", while ID§Modules says the
  mark is *cleared* when the message leaves the handler. Both cannot hold: `probe-b` shows zero
  requests served during a 705 ms synchronous handler and all three polls reading `null` afterwards.
  This spec adopts the minimal honest fix (Decision 3: a **retained last-step record**), but the
  vetted ticket text still needs correcting upstream so the two documents do not disagree.
* **OI-5 — bounce upstream (operator SLO, defaults chosen so build is not blocked).** `POLL_MS` and
  `STALE_MS` are the numbers that decide how fast "lost contact" becomes visible — the feature's
  stated reason to exist (PS, US-32) — and the ticket fixes neither, saying only "a fixed poll
  interval, and a stale threshold of a small multiple of it". Defaults taken here: 3 s / 10 s
  (⚠ inferred). Needs the on-call owner to confirm 10 s is the right trust horizon at 3am.
* **OI-6 — chosen, non-blocking.** `ROW_CAP = 200` and `PAYLOAD_MAX = 4000` are ⚠ inferred; the ticket
  says only "a fixed number of rows" and "a fixed length". Both are single named constants, cheap to
  change; the 200-row figure is grounded in the measured 8 KB vs 431 KB payload difference at 10k
  (`verified:probe-c` C5).
* **OI-7 — chosen, non-blocking.** The ticket names no filename for the new module. Taken:
  `src/console.js` with `test/console.test.js` mirroring it per CLAUDE.md (⚠ inferred).
  `src/operator-console.js` was the alternative; the shorter name was preferred only for the mirrored
  test filename, and either satisfies the convention.
