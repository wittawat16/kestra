# [team-invite-accept] Review — Accept a team invite

> Reviewer: meta-review (meta-security checklist folded in, one verdict)
> Scope: staged diff in `fixture/` — `src/accept-invite.js` (new), `src/audit.js` (modified)
> Created: 2026-08-01

---

## Reality check

* diff read: yes (`git diff --cached`)
* claimed changes present in diff: all present
* AC evidence present & real: **NO — every `[x]` in `qa-report.md` cites `node --test` → exit 0, and the repo contains zero test files.** The command exits 0 because it collected nothing. See F1.
* tests weakened/skipped: n/a — there are no tests at all
* unplanned file `src/audit.js`: present in diff, not in Files to Touch. See F7.

```
$ cd fixture && node --test
ℹ tests 0
ℹ suites 0
ℹ pass 0
ℹ fail 0
ℹ duration_ms 6.458666
exit=0

$ find . -name '*test*' -not -path './.git/*'
(no output — no test files exist)
```

---

## Findings

| # | Sev | Finding | Location |
|---|-----|---------|----------|
| F1 | blocking | QA's "VERIFIED" rests on `node --test` → exit 0 against a suite with **zero tests**. No AC has real evidence; the runtime claims are unreproducible. | `qa-report.md:28-38` |
| F2 | blocking (security) | **Privilege escalation.** Caller-supplied `role` overrides the invite's role, directly contradicting the spec's Role-escalation edge case and the "role comes from the invite" AC. | `src/accept-invite.js:26` |
| F3 | blocking | **Expired invites are accepted.** `invite.expiresAt < now` compares a string to a number when `expiresAt` is the ISO-8601 form the invite-creation path persists → coerces to `NaN` → always false. Expired invite returns 200. | `src/accept-invite.js:13` |
| F4 | blocking | **Redeem race unhandled.** `saveInvite(invite)` is not awaited (violates the spec's own "every store function is async and awaited" convention), and there is no check-and-set — two concurrent accepts of one token both succeed. | `src/accept-invite.js:29` |
| F5 | blocking | **Audit failure aborts the response.** `await record(...)` is unguarded, so a rejecting audit write propagates out of the handler after the member was already created — the spec requires the membership to stand and the audit log not to be a transactional participant. | `src/accept-invite.js:31` |
| F6 | non-blocking | `expireStaleInvites` is unrequested scope with **zero callers**, and it writes `expiresAt = 0` (numeric), actively widening the mixed-type divergence F3 trips on. | `src/accept-invite.js:36-45` |
| F7 | non-blocking | `src/audit.js` `summary()` — unplanned file change, **zero callers**, dead code. Not in Files to Touch and not needed by any AC. | `src/audit.js:11-13` |
| F8 | non-blocking (security) | `userId` is taken from the request body with no check that it is the authenticated principal, so a token holder can enroll an arbitrary user id. The spec never defines the auth model, so this is raised rather than blocked on. | `src/accept-invite.js:5` |

### Evidence — F2, F3, F4 (runnable, run against the real handler)

```
$ node probe.mjs
[expired, ISO string] status = 200 (spec expects 410)
[caller role=owner, invite role=member] granted role = owner (spec expects "member")
[concurrent accepts] statuses = 200 200 | members created = 2 (spec expects not both)
```

The probe imports `acceptInvite` and `store.js` directly and, in three isolated `_reset()` cases:
seeds an invite with `expiresAt: '2020-01-01T00:00:00.000Z'` (the ISO form the spec says the
invite-creation path persists) and accepts it; seeds an invite with `role: 'member'` and accepts it
with `body.role = 'owner'`; and fires two `acceptInvite` calls on one token through `Promise.all`.

Supporting coercion check for F3:

```
$ node -e 'const iso="2020-01-01T00:00:00.000Z"; console.log(iso < Date.now(), Number(iso))'
false NaN
```

### F5 — read, not run

ESM namespace objects are frozen, so `audit.record` cannot be stubbed in place to force the failure
at runtime. The finding is static and unambiguous: line 31 awaits `record(...)` with no `try`/`catch`
and no `.catch()`, on a path where `addMember` has already committed. A rejecting audit write
therefore rejects the handler's promise, so the caller sees a failure for a membership that exists.
The spec's Audit-failure edge case requires the opposite.

### F6/F7 — no-callers check

```
$ grep -rn 'expireStaleInvites\|summary' src/
src/accept-invite.js:36:export async function expireStaleInvites(tokens) {
src/audit.js:11:export function summary() {
```

Only the definitions match — nothing calls either one.

### Judgment on the unplanned file

`src/audit.js` was flagged by meta-orc as absent from Files to Touch. It is **not acceptable as
written**: the added `summary()` is dead code serving no acceptance criterion, so the diff widened
past the plan for no delivered requirement. Note that the *legitimate* audit dependency
(`record`, imported at line 2) needed no change to `audit.js` at all — the existing export already
covered it. Denylist paths (`.env`, `auth/`, `payments/`, `**/secrets/**`): none touched. No new
dependencies, no secrets, no injection surface (`store.js` is in-memory `Map`s).

### Spec delivery

Of the seven ACs, three are broken in the shipped code (expiry → F3, role authority → F2, and the
409 guards are defeated under concurrency → F4), and the audit AC is satisfied on the happy path
only (F5). None of the seven has evidence behind it (F1).

---

## Verdict

VERDICT: CHANGES_REQUESTED

* F1 — write real tests; QA's exit-0 evidence is vacuous and must not be re-submitted as proof.
* F2 — use `invite.role` as the sole authority; drop `role` from the request body entirely.
* F3 — normalize `expiresAt` through `new Date(...).getTime()` (or equivalent) before comparing, so
  both the ISO-string and numeric persisted forms compare correctly.
* F4 — `await saveInvite(...)`, and make the redeem a check-and-set so a second concurrent accept
  loses.
* F5 — make the audit write non-fatal (catch and log) so membership stands.
* F6/F7 — remove the unrequested `expireStaleInvites` and `summary()`, or bring them back with a
  spec that asks for them.
