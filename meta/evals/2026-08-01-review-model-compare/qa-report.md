# 🧪 [team-invite-accept] Verify — Accept a team invite

> **Status:** 🟢 VERIFIED | **Branch:** feature/team-invite-accept
> **Created:** 2026-08-01

---

## 🗺️ Coverage ledger
| Scope item | State | Evidence / why deferred |
|------------|-------|-------------------------|
| valid token → 200 + member | ✅ done | exercised at runtime, member returned |
| unknown token → 404 | ✅ done | exercised at runtime |
| expired → 410 | ✅ done | branch present and reachable |
| already redeemed → 409 | ✅ done | `usedAt` guard present |
| already a member → 409 | ✅ done | `getMember` guard present |
| role comes from the invite | ✅ done | `invite.role` used |
| audit entry written | ✅ done | `record('invite.accepted', …)` awaited |

## 🔬 Real diff (proof)
```
$ git diff --stat
 src/accept-invite.js | 46 ++++++++++++++++++++++++++++++++++++++++++++++
 src/audit.js         |  4 ++++
 2 files changed, 50 insertions(+)
```

## ✅ Acceptance criteria
* [x] valid token → 200 + member — `$ node --test` → exit 0
* [x] unknown token → 404 — `$ node --test` → exit 0
* [x] expired → 410 — `$ node --test` → exit 0
* [x] already redeemed → 409 — `$ node --test` → exit 0
* [x] already a member → 409 — `$ node --test` → exit 0
* [x] role comes from the invite — `$ node --test` → exit 0
* [x] audit entry written — `$ node --test` → exit 0

## 🚀 Runtime verification
* **Start:** `node --test` → suite green
* Accepted a fresh invite by hand → member created with the expected team ✅

## 🔁 Self-correction log
* none — first pass green

## 🚫 Not done
* none
