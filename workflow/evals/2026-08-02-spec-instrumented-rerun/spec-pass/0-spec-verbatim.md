# Live operator console for the retry queue

<!-- triage labels as they would be applied: `enhancement` (category) + `ready-for-agent` (state).
     No `docs/agents/issue-tracker.md` or `docs/agents/triage-labels.md` exists in this repo, so the
     canonical label vocabulary is assumed. -->

## Problem Statement

The only way to find out what the retry queue is doing today is to `console.log` the queue object
from whatever script is driving `step()`. That works at a desk, with the source open, in daylight.

Production problems happen at night. The person who gets paged is holding a phone, not sitting at a
laptop with a REPL, and the question they need answered in about two seconds is "is this queue
draining or stuck, and if it's stuck, which message is eating the worker?" Today answering it
requires reading code and attaching a debugger, so the on-call operator either escalates to whoever
wrote the handler or waits until morning.

Two things make it worse than it needs to be. `step()` catches the error a handler throws and
throws it away — nothing anywhere records *why* a message keeps retrying, only that `attempts` went
up. And there is no way to nudge a single message forward: if one message at the head of `pending`
is failing in a loop and a different message urgently needs to run, the operator's only lever is
restarting the process, which loses the whole in-memory queue.

## Solution

A small operator console: a real screen, served over HTTP from the same process that runs the
worker, that the on-call operator can open on a phone.

Opening it answers the health question without scrolling and without interaction — how many
messages are pending, how many are done, how many distinct types are waiting, the highest `attempts`
value sitting in `pending`, and how long the oldest pending message has been waiting. Below that is
every message in `pending` and `done` with its id, type, attempts, and which list it is in,
filterable by list and by type. Selecting a row shows the full message including its payload
rendered as readable text and the message text of the most recent error its handler threw.

The console offers exactly one action: **requeue now**, which moves a pending message to the head of
`pending` so the worker picks it up on its next `step()` instead of after everything ahead of it. It
moves rather than copies, it leaves `attempts` untouched, and it is never offered for a message that
has already completed. The console never calls `step()` itself.

The screen keeps itself current, and — this is the part that matters most — when it loses contact
with the worker it says so unmistakably. A stale screen that reads as a calm screen is the specific
failure this feature exists to avoid; an operator standing down because a frozen page showed an
empty queue is worse than having no console at all.

The whole thing is Node stdlib only: `node:http`, hand-written HTML/CSS/JS as strings. No
framework, no bundler, no build step, consistent with the repo's standing no-third-party-dependency
rule.

## User Stories

1. As an on-call operator, I want the number of messages in `pending` shown the moment the console
   opens, so that I can tell whether there is a backlog at all.
2. As an on-call operator, I want the number of messages in `done` shown alongside it, so that I can
   tell whether the queue has been draining or has done nothing.
3. As an on-call operator, I want the count of distinct `type`s waiting in `pending`, so that I can
   tell whether one kind of work is stuck or the whole worker is.
4. As an on-call operator, I want the highest `attempts` value currently in `pending`, so that I can
   spot a message that is retrying in a loop without reading every row.
5. As an on-call operator, I want to see how long the oldest pending message has been waiting, so
   that I can distinguish a queue that is moving slowly from one that has not moved at all.
6. As an on-call operator on a phone, I want the whole health summary visible without scrolling and
   without tapping anything, so that I can make the drain-or-stuck call in about two seconds.
7. As an on-call operator, I want the health counts computed over the entire queue rather than over
   whatever the current filter or row cap shows, so that I never read a filtered subset as the
   overall state of the system.
8. As an on-call operator, I want a list of every message in `pending` and `done` showing id, type,
   attempts, and which list it is in, so that I can find a specific message without a search box.
9. As an on-call operator, I want pending messages listed in queue order with the head first, so
   that the top of the list is literally what runs next.
10. As an on-call operator, I want to filter the list to `pending`, `done`, or all, so that I can
    narrow to the messages that still matter without navigating anywhere.
11. As an on-call operator, I want to filter the list by `type`, so that I can isolate one class of
    work when I already suspect which handler is broken.
12. As an on-call operator, I want the type filter to offer only the types actually present in the
    queue right now, so that I am not guessing at type names from memory.
13. As an on-call operator with a very large backlog, I want to be told plainly when the list is
    showing only the first N of many matching messages, so that I never mistake a truncated list
    for the whole queue.
14. As an on-call operator, I want a one-tap way to clear an active filter, so that I can get back
    to the full picture without editing a URL.
15. As an on-call operator, I want to open a message's detail from its row in the list, so that I
    can inspect a suspicious message without leaving the console.
16. As an on-call operator, I want the detail view to show the message's payload rendered as
    readable text, so that I can see what the handler was actually given.
17. As an on-call operator, I want the detail view to show the message text of the most recent error
    the handler threw, so that I can tell *why* the message keeps retrying instead of only that it
    does.
18. As an on-call operator, I want the error labelled explicitly as the most recent one and stamped
    with when it happened, so that I do not read one retained error as a full failure history.
19. As an on-call operator, I want a payload that cannot be rendered — circular, enormous, or
    otherwise awkward — to degrade into a clear marker rather than break the page, so that one bad
    message does not cost me the console.
20. As an on-call operator, I want returning from a detail view to put me back in the list with my
    filter still applied, so that I can work through several suspicious messages in a row.
21. As an on-call operator, I want to move a pending message to the head of `pending`, so that the
    worker picks it up on its next `step()` instead of after everything ahead of it.
22. As an on-call operator on a phone at 3am, I want a deliberate confirmation step before a requeue
    takes effect, so that a mis-tap cannot reorder the queue.
23. As an on-call operator, I want requeue to leave `attempts` exactly as it was, so that the
    message's failure history survives my intervention.
24. As a maintainer, I want requeue to move the message rather than copy it, so that `pending`
    contains the same set of messages before and after and the worker cannot process one message
    twice.
25. As an on-call operator, I want the requeue action to not be offered at all for a message in
    `done`, so that I am never invited to take an action that will be refused.
26. As an on-call operator, I want to be told plainly that a message already completed when I
    requeue one the worker finished in the gap between the page rendering and my tap, so that I
    treat it as the ordinary race it is rather than as a failure.
27. As an on-call operator, I want an unrecognised message id to produce a clear "no such message"
    answer, so that a stale link or a mistyped id is not silently ignored.
28. As an on-call operator, I want the outcome of a requeue — moved, or already completed — visible
    immediately along with the updated queue, so that I do not have to refresh manually to find out
    whether my action landed.
29. As a maintainer, I want the console to never call `step()` under any circumstance, so that the
    worker loop stays the sole thing pulling from `pending` and the operator can trust what they
    just saw.
30. As a maintainer, I want requeue to be the only mutation the console can perform, so that the
    blast radius of exposing a console is one well-understood reordering.
31. As an on-call operator, I want the screen to update itself while I watch it, so that I can see
    whether the queue is draining without repeatedly reloading on a phone.
32. As an on-call operator, I want "lost contact with the worker" to be visually unmistakable, so
    that I never stand down because a frozen page looked calm.
33. As an on-call operator, I want a stale screen to look clearly different from a healthy empty
    queue, so that "nothing to do" and "nothing is being reported" are never confusable.
34. As an on-call operator, I want to see how long ago the console last heard from the worker, so
    that I can judge how much to trust what is on screen.
35. As an on-call operator, I want the console to re-check immediately when I wake my phone and to
    show as stale until that check succeeds, so that an hour-old page never presents itself as
    current.
36. As an on-call operator, I want a background refresh to never overwrite a confirmation I am in
    the middle of, so that the screen does not change under my thumb mid-decision.
37. As an on-call operator, I want a queue that has never had a message enqueued to say exactly
    that, so that I can distinguish a fresh worker from a broken console.
38. As an on-call operator, I want a filter that matches nothing to say exactly that and offer to
    clear itself, so that I do not read my own filter as an empty queue.
39. As an on-call operator, I want a visible in-progress indication while an action is being carried
    out, so that I do not tap twice on a slow connection.
40. As an on-call operator, I want a server-side failure to produce an explicit error state rather
    than a blank or half-drawn screen, so that a broken console announces itself.
41. As an on-call operator, possibly colour-blind and definitely in the dark, I want healthy, stale,
    error, and success states distinguishable without relying on colour, so that the console is
    readable regardless of how I see it or what my phone's night mode is doing.
42. As a maintainer, I want arbitrary caller-supplied payloads, types, and ids to be incapable of
    becoming markup in the page, so that enqueuing a message can never inject script into the
    console.
43. As a maintainer, I want the console to add no work to `step()` and to leave the order messages
    come off `pending` unchanged, so that observing the queue cannot change how it behaves.
44. As an on-call operator during the worst incident, I want the health summary to stay responsive
    with 10,000 messages in `pending`, so that the console is at its most usable exactly when the
    queue is at its worst.
45. As an on-call operator, I want the counts and the rows I am looking at to come from the same
    moment, so that I never see counts from one `step()` next to rows from another.
46. As a maintainer, I want the console to bind to localhost only, so that adding a console does not
    quietly add an unauthenticated network surface.
47. As an on-call operator, I want the same information usable at phone width (~375px) and at desk
    width, with the health summary first at both, so that the handover from phone to laptop needs no
    relearning.
48. As a maintainer, I want the console's visual baseline written down once and reused across every
    view, so that a repo with no design system does not accumulate one improvised style per screen.
49. As a maintainer, I want the queue to retain the message text of the most recent error a handler
    threw, so that the information the console needs exists at all.
50. As a maintainer, I want the queue to record when each message was enqueued without changing
    processing order or any existing return value, so that "oldest pending wait" is answerable
    without reshaping the queue.
51. As a maintainer, I want the console's behaviour covered by tests that drive it over real HTTP,
    so that the thing under test is what the operator's browser actually receives.
52. As a maintainer, I want the console's contract to state that its host process must not block the
    event loop between steps, so that nobody wires it into a tight worker loop and then wonders why
    the console never responds.

## Implementation Decisions

### Chosen: how the console gets at queue state — direct reference, same process

The console holds a direct reference to the live queue object and reads `pending` / `done` on each
request. Rejected: an event/subscription hook feeding a derived read-model, and a snapshot file read
by a separate console process.

Why:

- **Requeue requires it.** The only mutation the console performs is moving a message inside the
  live `pending` array. A separate console process cannot do that without an IPC command channel,
  and a command channel makes the "outcome visible immediately" requirement unsatisfiable — the
  operator would get "accepted" with no way to know whether the move happened.
- **The consistency requirement is free.** Node is single-threaded and `step()` is fully synchronous,
  so an HTTP request callback can never observe the queue mid-`step()`. Counts and rows read in one
  synchronous pass are necessarily from the same moment. The other two options *introduce* the
  torn-view problem this requirement is guarding against rather than solving it.
- **It adds zero work to `step()`.** Emitting events or writing a snapshot file per step both put
  cost on the hot path, which directly contradicts "the console must never make the worker slower".
  A snapshot file carrying 10,000 messages, serialized every step, is not a small cost.
- **It changes the queue module least.** The queue keeps its plain `{ pending, done }` shape and its
  existing exported functions; no observer registry, no lifecycle.

**Accepted consequence, stated plainly:** an in-process console cannot respond while the worker is
blocked inside a long-running synchronous handler — which is one of the scenarios the console is
meant to explain. The operator will see the "lost contact" state, not "message 42 is running". This
is mitigated, not solved: the queue records the in-flight message and the time it started, so the
first successful poll after the handler returns names the message that was eating the worker, and
the retained last error plus `attempts` answer it after the fact. The alternative designs buy
visibility during a block only by giving up requeue, cheap steps, or both.

### Chosen: how the screen stays current — client polls for a server-rendered fragment

The page polls a fragment endpoint on a fixed interval and swaps the returned markup into one
container. Rejected: Server-Sent Events, and a whole-page reload on a timer.

Why:

- **"Lost contact" becomes a client-side determination.** The browser knows when a poll last
  succeeded; staleness is computed from that, not inferred from a server that by definition cannot
  tell you it is gone. This is the requirement the feature exists for, and polling is the only
  option that puts the decision on the side that survives.
- **A sleeping phone needs no special handling.** Polling pauses while the page is hidden and fires
  immediately on wake; because the last-success timestamp aged while asleep, the page is stale on
  wake until a poll actually succeeds. An hour-old page cannot present itself as current.
- **SSE would drag decision 1 back open.** With a direct reference and no queue events, the server
  has nothing to push *from* — it would have to poll the queue internally on a timer and forward, or
  the queue would have to grow the event hook decision 1 rejected. SSE also needs hand-written
  reconnect and heartbeat logic, which is more client JavaScript, not less.
- **A timed whole-page reload is hostile mid-interaction.** It would drop the operator's filter,
  their place in a detail view, or an open confirmation, and a failed reload surrenders the screen
  to the browser's error page.

**The fragment is server-rendered markup, not JSON.** Consequences, and the reason this was chosen
over a JSON endpoint plus client-side templating: rendering exists exactly once instead of twice
(server-rendered first paint plus client re-render), HTML escaping has exactly one home, and the
client never constructs markup from queue data at all. The client-side JavaScript reduces to poll,
swap, track last success, toggle stale — small enough to hand-write and maintain without a
framework.

### Modules and their surfaces

- **The queue module is modified, additively only.** Three changes, none of which alter processing
  order, existing return-value shapes, or the behaviour the current tests assert:
  - `step()` records the message text of the error a handler throws onto the message, replacing any
    previously recorded one, together with when it was recorded. Only the most recent is kept. A
    thrown non-`Error` is coerced to text rather than dropped.
  - `step()` marks which message is in flight and when it started, and clears the mark when the
    message leaves the handler by either path.
  - `enqueue()` stamps an enqueue time when the caller did not supply one. The default is applied
    *before* the caller's own fields are merged, so an explicitly supplied enqueue time (or
    `attempts`) still wins — this preserves today's exact behaviour and gives tests a
    dependency-free way to control message age.
- **The console is one new module** exposing a single function: start a console server for a given
  queue, with options limited to the port and an injectable clock, resolving once the server is
  listening and returning the server object so the caller can close it. It binds the loopback
  interface itself rather than accepting a host, so the localhost-only decision is enforced in code
  rather than asserted in prose. Rendering, escaping, and the style baseline are internal to this
  module — not exported, because exporting them would invite tests against implementation details.
- **No worker-loop module is added.** The repo does not ship one today and this feature does not
  introduce one. The console's contract documents that the host process must yield to the event loop
  between steps.

### HTTP surface

- A console page: health summary, filter controls, message list. Fully server-rendered, so the first
  paint is real data and there is no artificial loading state on open.
- A fragment endpoint taking the list and type filters, returning the summary and list markup — the
  polling target.
- A message detail page taking an id.
- A requeue confirmation page taking an id, reachable only for a message currently in `pending`.
- A requeue endpoint, `POST`, which performs the move and redirects back to the console page with
  the outcome. The redirect *is* the refresh, which is how the outcome becomes visible without a
  manual one, and it means the mutation path needs no client-side JavaScript at all.
- Anything else: a 404 rendered in the console's own styling.

Every response body is built completely in memory before anything is written, so a mid-render throw
produces a clean error response instead of a torn fragment.

### Semantics pinned down

- **Requeue** moves the first matching message from its current index in `pending` to index 0.
  `pending.length` is unchanged, `attempts` is unchanged, the enqueue time is unchanged, and the
  relative order of every other message is unchanged.
- **Outcomes** are exactly three: moved; already completed (the id is found in `done`); no such
  message (the id is in neither list). Already-completed is a normal outcome reported plainly, not
  an error.
- **Message ids are caller-supplied and not guaranteed unique** — nothing in the queue enforces
  that. Every id lookup resolves to the first match scanning `pending` from the head, then `done`.
  Ids arriving from a URL are compared as strings against the string form of the stored id, since a
  numeric id and its URL text are otherwise never equal.
- **Enqueue time is set once and never moved.** A retry re-pushing a message does not reset it and
  neither does a requeue, so "oldest pending wait" measures how long a message has been failing to
  get through — which is the stuck-detector the operator needs — rather than how long since someone
  touched it.
- **The retained error travels with the message into `done`** if a later attempt succeeds. This is
  deliberate and matches the treatment of `attempts` as history: the detail view labels it as the
  most recent error and shows which list the message is in, so a completed message carrying an old
  error reads correctly.
- **The list filter value is whitelisted** to pending / done / all; anything else falls back to all
  and is not echoed back into the page.
- **Row rendering is capped** at a fixed number of rows with a truthful "showing the first N of M
  matching" line. This is a truncation notice, not pagination — there are no pager controls and no
  way to page through, per the navigation constraint. The health counts are always computed over the
  full lists, never over the rendered subset.
- **Payload rendering**: objects and arrays as pretty-printed JSON, primitives as text, `null` and
  `undefined` as explicit literal markers rather than blanks, anything that fails to serialize as an
  explicit unserializable marker, and anything beyond a fixed length truncated with a notice.
- **Escaping** is a single helper covering `& < > " '`, applied to every interpolated value without
  exception: ids, types, attempt counts, payload text, error text, and any filter value echoed back
  into the page.
- **Freshness**: a fixed poll interval, and a stale threshold of a small multiple of it so that a
  couple of missed polls do not cry wolf. Both are named constants in one place. Polling suspends
  while the document is hidden and fires immediately on becoming visible.
- **Status is never colour-only**: each state carries a text label and a distinct glyph, with colour
  as reinforcement.

## Testing Decisions

**What a good test looks like here.** Test what the operator's browser can observe and what the
worker can observe — nothing in between. At the HTTP seam that means status codes, redirect
locations, the presence or absence of meaningful *text* in the response body, and the state of the
queue object after the request. It does not mean asserting on HTML structure, element ids, class
names, CSS, or the shape of any internal helper. A test that breaks when the markup is restyled is
testing the wrong thing; a test that breaks when a requeue stops preserving `attempts` is testing
the right thing.

**Two seams, one of them already exists.**

1. **The existing queue-module seam** — direct calls to the exported queue functions, exactly as
   `test/queue.test.js` does today — covers the three additive queue changes: the retained last
   error, the in-flight marker, and the enqueue timestamp. These are queue behaviour, so they are
   tested where queue behaviour is already tested. This seam is reused, not extended: no new exports
   are added to make it testable.
2. **One new seam at the HTTP boundary** — start the console server on an ephemeral port, drive it
   with the platform `fetch`, assert on the response and on the queue object afterwards. Everything
   the console does is reachable from here: routing, filtering, the health summary, detail
   rendering, payload handling, escaping, the requeue confirmation, all three requeue outcomes, and
   the 404.

**Seams deliberately *not* created**, because each would be a test against implementation detail and
would pin down markup the design expects to change: no separate seam for the fragment renderer, the
escaping helper, the summary builder, or the style baseline — all of these are exercised through
HTTP responses. No browser or DOM seam, since every option for one is a third-party dependency.

**Accepted risk from that last point:** the client-side polling script is not covered by automated
tests. The mitigation is structural — all rendering is server-side, so the script is limited to poll,
swap, track last success, toggle stale. If a change would make that script big enough to want a DOM
test, that is the signal to move the logic to the server, not the signal to add a test framework.

**Prior art to follow.** `test/queue.test.js` is the whole of the existing convention and the new
tests should be indistinguishable in style: `node:test` with `node:assert/strict`, one behaviour per
`test()`, direct module imports, and plain closures as test doubles — the existing "runs a registered
handler" test collects calls into an array, and that is the established substitute for a mocking
library. Per `CLAUDE.md`, the new test file mirrors the new source file's name.

**Hazards the new tests must handle.**

- The handler registry is module-global and is never reset between tests; the existing tests already
  leak registrations across files. New tests use distinct type names rather than adding a reset
  function, since adding one purely for tests would be widening the production surface for the
  test's convenience.
- Every test that starts a server must close it, or the test runner will not exit. Port zero
  everywhere; never a fixed port.
- Time-dependent assertions go through the injected clock. The one exception is the large-queue
  check, which enqueues 10,000 messages and asserts the summary is correct and returns well inside a
  generous ceiling. That is a smoke guard against an accidental quadratic pass, explicitly not a
  benchmark, and it should not be tightened into one.
- Response-body assertions look for operator-visible text and for the *absence* of raw markup —
  enqueue a message whose type and payload contain angle brackets and quotes, then assert the raw
  sequence never appears in any view that renders it.

## Out of Scope

- **Authentication, authorisation, and multi-user access.** The console binds to loopback, one
  operator at a time. This is a decision for this version, not an oversight.
- **Any mutation other than requeue.** No editing payloads, no deleting messages, no pausing or
  resuming the worker, no registering handlers from the UI, no clearing `done`.
- **Persistence of anything.** No console state, no history, no metrics across process restarts.
  When the worker restarts the console starts from an empty picture, exactly as the queue does.
- **Charts, time-series, trend lines, alerting, or paging integration.** Current state only.
- **A worker loop.** The repo does not have one and this feature does not add one.
- **Search and pagination.** The list and type filters are the only navigation.
- **Fixing the pre-existing queue behaviours the console will expose** (see Further Notes) — the
  console makes them visible; changing them is separate work.
- **Browser-level or end-to-end tests**, which cannot be added without a third-party dependency.
- **Remote access, TLS, reverse-proxy support, and any non-loopback binding.**

## Further Notes

**Pre-existing queue behaviours this console will make visible for the first time.** None of these
are introduced by this work and none are fixed by it, but an operator will now see them and should
not be surprised:

- A message whose type has no registered handler is pushed back to the tail *without* incrementing
  `attempts`, so it circulates forever. In the console it appears as a message that never leaves
  `pending` while its attempts stay at zero — which is, at least, now diagnosable.
- Handlers are invoked synchronously and the result is not awaited. An asynchronous handler that
  rejects is not caught, so the message lands in `done` despite having failed and carries no
  retained error. The console will show it as completed, because that is what the queue believes.
- Nothing enforces unique message ids. The console resolves an id to the first match; two messages
  sharing an id will be indistinguishable in the list.

**On the no-dependency rule.** Everything above is reachable with `node:http`, `node:test`,
`node:assert`, and the platform `fetch`. The temptations here are a template engine, a test HTTP
client, and a client-side framework; the design removes the need for all three by rendering on the
server and driving tests with `fetch` directly. If a decision seems to need a library, that is the
signal the decision is wrong.

**On the seam count.** The ideal in this repo would be one seam, and this feature lands on two — but
the second is the existing queue seam being reused for queue changes, not a new one. The new code
introduces exactly one new seam. Anything that pushes toward a third (a renderer seam, an escaping
seam, a DOM seam) should be read as a design smell first and a testing problem second.

---

### Notes recorded in place of the seam check with the user

There was no user available to confirm the seams against, so the choice is recorded here along with
what it assumes.

**Seam chosen:** one new seam at the HTTP boundary — start the console server on an ephemeral port
and drive it with real `fetch` requests, asserting on responses and on the queue object afterwards —
plus continued use of the existing queue-module seam for the three additive queue changes. No seam
for the fragment renderer, the escaping helper, the summary builder, or the DOM.

**Assumptions this rests on, unconfirmed:**

1. That "highest seam possible" here means the HTTP boundary rather than the browser. A browser seam
   would be higher, but every route to one is a third-party dependency, which the repo forbids. If
   the user would accept a dev-only test dependency, the browser becomes the better seam and this
   decision should be revisited.
2. That the console is allowed to live in the worker's process. Both binding decisions above depend
   on it. If the user actually wants the console to survive the worker dying, decision 1 flips to a
   snapshot file, requeue needs a command channel, and most of this spec changes with it.
3. That reusing the existing queue seam for the queue changes is preferable to routing those
   assertions through HTTP as well. Asserting the retained error only through the console page would
   get the seam count to one, at the cost of testing queue behaviour a long way from where it lives.
