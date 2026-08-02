# Rough idea (post-grilling) — a live operator console for the retry queue

Settled in discussion, ready for a spec:

## Why

Right now the only way to find out what the queue is doing is to `console.log` the queue object from
whatever script is driving `step()`. When something goes wrong in production it goes wrong at night,
and the person who gets paged is holding a phone, not sitting at a laptop with a REPL. We want a
small operator console — a real screen they can open — that answers "is the queue healthy, and if
not, which message is eating the worker" without anyone having to read code or attach a debugger.

Hard constraint from the repo: **no third-party dependencies**. Node stdlib only (`node:http`,
`node:fs`, hand-written HTML/CSS/JS as strings). No React, no Express, no template engine, no
bundler, no build step. If a decision needs a library, it's the wrong decision.

## What the operator needs to see and do

- **Health at a glance.** Opening the console shows, without scrolling and without interaction: how
  many messages are in `pending`, how many in `done`, how many distinct `type`s are waiting, the
  highest `attempts` value currently sitting in `pending`, and how long the oldest pending message
  has been waiting. The one question this view must answer in about two seconds, from a phone, is
  "is this queue draining or stuck?"
- **A message list.** Every message in `pending` and `done`, showing id, type, attempts, and which
  list it's in. Filterable by list (`pending` / `done` / all) and by `type`. The filter is the only
  navigation — no search box, no pagination controls.
- **A message detail view.** Selecting a row shows the full message: id, type, attempts, the payload
  rendered as readable text, and the message text of the most recent error thrown by its handler
  (today `step()` throws the error away — the queue will need to start keeping the last one).
- **One action: requeue now.** For a message in `pending`, the operator can move it to the *head* of
  `pending` so the worker picks it up on the next `step()` instead of after everything ahead of it.
  That is the only mutation the console is allowed to perform.

Exact semantics for requeue, so nobody has to guess:

- It moves the message; it does not copy it. `pending.length` is unchanged.
- `attempts` is left exactly as it was. Attempts is a history record of what happened, not a retry
  budget being refunded, and an operator nudging the queue must not erase that history.
- Messages in `done` cannot be requeued. The console must not offer the action for them at all —
  not offer-then-refuse.
- If the message is no longer in `pending` when the request arrives (the worker completed it in the
  gap between the page rendering and the operator tapping), the requeue does nothing to the queue and
  the operator is told plainly that it already completed. This is expected, not an error.
- The console never calls `step()` itself, ever. The worker loop owns advancing the queue; a console
  that can advance it too means two things pulling from `pending` and an operator who can't trust
  what they just saw.

## Screen-level expectations

- Usable at phone width (~375px) and at desk width. Same information, and the health summary stays
  the thing you see first at both sizes.
- The repo has no design system, no tokens, no component library and no CSS at all today — the
  console has to establish its own minimal visual baseline and that baseline should be written down
  once and reused, not re-invented per view.
- Every view needs a real answer for all four of empty / loading / success / error, including the
  awkward ones: a queue that has never had a message enqueued, a filter that matches nothing, the
  first paint before any data has arrived, and the console having lost contact with the worker.
- "Lost contact with the worker" must be visually unmistakable and must not look like "the queue is
  empty and healthy". A stale screen that reads as a calm screen is the specific failure we're
  trying to avoid — an operator deciding everything is fine off a frozen page is worse than no
  console at all.
- Requeue is a destructive-ish action taken by a tired human on a small screen. It needs a
  deliberate confirmation step, and the outcome (moved / already completed) has to be visible
  afterwards without a manual refresh.
- Error and success states must be distinguishable without relying on colour alone.
- Payloads are arbitrary caller-supplied values — strings, `null`, objects. They get rendered into
  the page, and whatever renders them must not let a payload become markup.

## Architecture, deliberately not settled

Two things we argued about and did not resolve. Pick one of each, write down why, and treat the
choice as binding:

1. **How the console gets at queue state.** Either it holds a direct reference to the live queue
   object in the same process and reads `pending` / `done` on each request; or the queue module grows
   an event/subscription hook and the console maintains its own derived read-model; or the worker
   periodically writes a snapshot file and a separate console process reads it. These differ on
   whether the console survives the worker dying, whether the console can show a torn half-updated
   view mid-`step()`, and how much the queue module itself has to change.
2. **How the screen stays current.** Either the browser polls a JSON endpoint on an interval; or the
   server pushes over Server-Sent Events; or the page just full-reloads on a timer. These differ on
   how fast "lost contact with the worker" becomes visible, on how much client-side JavaScript we
   are signing up to hand-write and maintain without a framework, and on what happens with a phone
   whose screen has been asleep for an hour.

Non-functional targets we care about: the console must never make the worker slower or change the
order in which messages come off `pending`; the health summary must stay responsive with 10,000
messages in `pending`; and a snapshot the operator is looking at must be internally consistent —
counts and rows from the same moment, never counts from one `step()` and rows from another.

## Out of scope

- Authentication and multi-user access. The console binds to localhost only, one operator at a time,
  and that is a deliberate decision for this version rather than an oversight.
- Any action other than requeue — no editing payloads, no deleting messages, no pausing the worker,
  no registering handlers from the UI.
- Persisting console state, history, or metrics across process restarts. When the worker restarts,
  the console starts from an empty picture, same as the queue does.
- Charts, time-series, or trend lines. Current state only.
