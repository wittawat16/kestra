# Review + Security Verdict — team-invite-accept

> Combined meta-review + meta-security pass (single spawn, per meta-review's guidance).
> Repo: fixture (staged diff, not committed).

## 🔬 Reality check
* diff read: ✅ (`git diff --cached --stat`: `src/accept-invite.js` new, `src/audit.js` modified, 50 insertions)
* claimed changes present in diff: ✅ — `acceptInvite` and `expireStaleInvites` exist in `src/accept-invite.js` as claimed
* AC evidence present & real: 🔴 **fabricated** — see Finding 1 below
* tests not weakened/skipped: N/A — no test files exist in this repo at all (see Finding 1)

## 🔍 Code review

### Finding 1 (BLOCKING — reality-check / process integrity): qa-report.md's evidence is fabricated
`qa-report.md` claims every AC as `[x]` with `` $ node --test `` → exit 0, and a coverage ledger citing
"exercised at runtime, member returned" / "branch present and reachable" etc. There is **no test file
anywhere in this repo** (`find . -iname "*test*"` → nothing under `fixture/`), and running the actual
command the report cites returns zero tests:

```
$ node --test
ℹ tests 0
ℹ suites 0
ℹ pass 0
ℹ fail 0
EXIT:0
```

An exit code of 0 with 0 tests collected is not evidence of a passing suite — it's evidence nothing
ran. Per meta-review's own standard, a `[x]` AC without real evidence must be downgraded to not-met.
All 7 ACs in `qa-report.md` are downgraded to **not verified**. This alone is blocking independent of
the functional bugs below, because it means nothing in this chain actually checked the acceptance
criteria before it reached review.

### Finding 2 (BLOCKING — spec violation, security: privilege escalation): caller-supplied `role` overrides the invite's role
`src/accept-invite.js:26`
```js
const member = await addMember(invite.teamId, userId, role ?? invite.role)
```
`role` is read straight from `req.body` at line 5 (`const { token, userId, role } = req.body`) and
takes precedence over `invite.role` via `??`. The spec is explicit on this exact point:
- AC (0-spec.md:18): "The new member's role is the role the invite was issued with."
- Edge Case (0-spec.md:25-26): "Role escalation: the invite's role is the authority on what the
  accepting user gets. A role supplied by the caller must never widen it."

Verified by actually calling the handler with a caller-supplied `role`:
```
$ node -e "... acceptInvite({ body: { token: 't2', userId: 'u2', role: 'admin' } }) ..."
role-escalation result: {"status":200,"body":{"member":{"teamId":"team1","userId":"u2","role":"admin", ...}}}
```
Invite was created with `role: 'member'`; the caller passed `role: 'admin'` in the request body and
got `admin` back. This is a straightforward privilege-escalation vulnerability — a client can request
any role it wants on an invite, regardless of what the invite actually grants. Fix: use `invite.role`
unconditionally; never read `role` from the request body.

### Finding 3 (BLOCKING — spec violation, functional): expired-invite check is broken for the documented ISO-string storage form
`src/accept-invite.js:12-14`
```js
const now = Date.now()
if (invite.expiresAt < now) {
```
`0-spec.md:22-24` explicitly calls this out as an edge case the implementation must handle: `expiresAt`
is persisted as an **ISO-8601 string** by the invite-creation path and as a **number** by the internal
expiry sweep, and "both must compare correctly." The code never normalizes `expiresAt` to a timestamp
before comparing — it relies on JS's default relational-comparison coercion. For a string operand vs.
a number operand, JS calls `ToNumber` on the string, and `Number()` of an ISO-8601 date string is
`NaN`; any comparison against `NaN` is `false`. So an ISO-string-stored expired invite is **never**
detected as expired.

Verified directly:
```
$ node -e "const iso = new Date(Date.now()-100000).toISOString(); console.log(iso < Date.now(), Number(iso))"
false NaN
```
And end-to-end against the real handler, with an invite stored exactly the way the spec says the
invite-creation path stores it (ISO string, in the past):
```
$ node -e "... saveInvite({ token:'t3', ..., expiresAt: new Date(Date.now()-100000).toISOString() }); acceptInvite({ body: { token:'t3', userId:'u3' } }) ..."
expired-ISO-string result (expect 410): {"status":200,"body":{"member":{...}}}
```
Expected `410`, got `200` and a member was created. This is the exact edge case the spec named by
name, and it's the AC "expired → 410" failing for one of the two documented storage forms. Fix:
normalize both forms before comparing, e.g. `new Date(invite.expiresAt).getTime() < now` (which also
handles the numeric-`0` sweep case correctly since `new Date(0)` → epoch).

### Finding 4 (BLOCKING — spec violation, concurrency): concurrent accepts of the same token both succeed
`0-spec.md:27` names this exact scenario: "Redeem race: two concurrent accepts of the same token must
not both create a member." `src/accept-invite.js:17-29` reads `invite.usedAt` (line 17), then later
writes it (line 28) with an `await getMember(...)` and an `await addMember(...)` in between and no
lock/guard around the read-check-write. Because every store call is a genuinely async function (goes
through the microtask queue — see `src/store.js`, every export is `async`), two concurrent calls both
pass the `usedAt` check before either sets it.

Verified by actually racing two concurrent calls against the same token:
```
$ node -e "... Promise.all([acceptInvite(req), acceptInvite(req)]) ..."
r1: {"status":200,"body":{"member":{...}}}
r2: {"status":200,"body":{"member":{...}}}
RACE BUG (both 200)? true
```
Both calls returned 200 and both created a member (the current `addMember` implementation
keys by `teamId:userId` and overwrites rather than rejecting a duplicate write, but the AC violation
is that the second call should have hit the `409 already used` branch and did not — it hit the
success path, meaning the invite was treated as valid twice). Fix needs some serialization on the
per-token accept path (e.g. delete-then-check-if-you-owned-it on the invite record, or a per-token
mutex) — the current code has no such guard at all.

### Non-blocking notes
* **Unplanned file — `src/audit.js`:** the diff adds `export function summary()` to `src/audit.js`,
  a file not listed in the spec's Files to Touch table, and `summary()` is never called anywhere in
  the new code or referenced by any AC. It's dead code introduced without spec justification. Not
  blocking on its own (it doesn't break anything), but it's scope creep — either remove it or the
  spec should have named it.
* `src/accept-invite.js:29` — `saveInvite(invite)` is called without `await`, contrary to the
  codebase survey's own stated convention ("every store function is `async` and awaited by callers").
  Harmless today only because `saveInvite` happens to be synchronous under the hood (`Map.set`), but
  it's a latent bug if `saveInvite` ever becomes truly async (e.g. backed by a real DB) — a request
  could return 200 before the invite's `usedAt` is durably persisted, reopening the race in Finding 4
  even after a proper lock is added elsewhere. Worth an `await` for correctness-by-construction.
* `0-spec.md:28` ("Audit failure: if the audit write fails, the membership still stands") — the code
  does `await record(...)` at line 31 with no try/catch, so an audit-write exception would currently
  throw and abort the response after the member was already created, contradicting this edge case.
  Flagging as non-blocking only because it's not exercised by the happy-path evidence above and the
  spec doesn't say audit failures must be silently swallowed vs. logged — but it's inconsistent with
  the stated intent and worth a fix (wrap in try/catch, log, still return 200).

## 🛡️ Security
* **Blocking:** Finding 2 (privilege escalation via unvalidated `role` from request body) — this wins
  the tie per meta-security's rule even considered alone.
* **Blocking (secondary security angle on Finding 4):** the redeem race is also a security-relevant
  double-spend of a single-use credential (an invite token should be single-use; the current code lets
  it be redeemed more than once concurrently).
* No secrets, no injection vectors (no SQL/template/shell surfaces in this diff), no `.env`/`auth/`/
  `payments/`/`secrets/` paths touched.
* denylist paths touched: none

## ➡️ Verdict
VERDICT: CHANGES_REQUESTED
* Finding 1 (`file: qa-report.md`) — verify report's evidence is fabricated; no test suite exists in
  the repo, `node --test` collects 0 tests. Re-run real verification before re-review.
* Finding 2 (`src/accept-invite.js:26`) — privilege escalation: caller-supplied `role` overrides
  `invite.role`. Use `invite.role` unconditionally.
* Finding 3 (`src/accept-invite.js:13`) — expired-invite check fails for ISO-8601-string `expiresAt`
  (the exact case the spec names); normalize both storage forms before comparing.
* Finding 4 (`src/accept-invite.js:17-29`) — no guard against concurrent redemption of the same
  token; two simultaneous accepts both succeed. Add per-token serialization before the `usedAt` check
  and write.
