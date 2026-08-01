# [team-invite-accept] Spec — Accept a team invite

> Status: READY | Created: 2026-08-01 | Next: meta-orc

## Overview
Let an invited user redeem an invite token and become a member of the team it was issued for.

## Acceptance Criteria
* [ ] Given a valid, unexpired, unused invite token, when the user accepts it, then they are added
  as a member of that team and the response is 200 with the created member.
* [ ] Given an invite token that does not exist, when the user accepts it, then the response is 404.
* [ ] Given an invite whose expiry has passed, when the user accepts it, then the response is 410
  and no member is created.
* [ ] Given an invite that has already been redeemed, when the user accepts it again, then the
  response is 409 and no second member is created.
* [ ] Given a user who is already a member of the team, when they accept another invite to it,
  then the response is 409 and no duplicate member is created.
* [ ] The new member's role is the role the invite was issued with.
* [ ] A successful acceptance is written to the audit log as `invite.accepted`.

## Edge Cases & Error States
* **Expired invite:** the expiry comparison must hold for whatever type `expiresAt` is stored as —
  invites are persisted with `expiresAt` as an ISO-8601 string by the invite-creation path, and as
  a number by the internal expiry sweep. Both must compare correctly.
* **Role escalation:** the invite's role is the authority on what the accepting user gets. A role
  supplied by the caller must never widen it.
* **Redeem race:** two concurrent accepts of the same token must not both create a member.
* **Audit failure:** if the audit write fails, the membership still stands — the audit log is not
  a transactional participant.

## Codebase Survey
* Explored: `src/store.js` (invite + member persistence), `src/audit.js` (append-only event log)
* Follow these patterns: every store function is `async` and awaited by callers; handlers return
  `{ status, body }` rather than writing to a response object.

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `src/accept-invite.js` | new | follows the handler shape used across `src/` | the acceptance handler |

## AC Coverage Map
| AC | Covered by |
|----|------------|
| valid token → 200 + member | `src/accept-invite.js` |
| unknown token → 404 | `src/accept-invite.js` |
| expired → 410 | `src/accept-invite.js` |
| already redeemed → 409 | `src/accept-invite.js` |
| already a member → 409 | `src/accept-invite.js` |
| role comes from the invite | `src/accept-invite.js` |
| audit entry written | `src/accept-invite.js` |

## Dependencies
* none

## Flags
* `needs_ui`: false — server-side handler only, no page/route/interactive element
* `needs_devops`: false — no env var, migration, feature flag, or infra change
* `tests_first`: false — not requested by the caller

## Escalation Check
* None of the three escalation triggers apply — single component, no external dependency to fake,
  no silent-failure path (every branch returns a status the caller sees).

## Out of Scope
* Sending the invite email
* Rate limiting the accept endpoint

## Open Items
* none
