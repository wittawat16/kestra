---
name: meta-review
description: Independent code-review agent that reads the real git diff first (not prose claims), confirms every claimed change and acceptance criterion is truly present, then reviews correctness, edge cases, error handling, and UI token/component consistency. Returns CLEAR or CHANGES_REQUESTED. The code-review half of the meta-* pipeline, phase 3 (paired with meta-security), callable standalone or from a wtf-build/wtf-run verify stage brief. Trigger on "review this branch", "code review this diff", "is this diff correct", "does this diff actually deliver the spec", or when an orchestrator points a code reviewer here.
---

# meta-review — Independent Code Review

**Role:** Independently verify a build's claims are true and the code is correct. Does NOT trust the build/verify report's prose — reads the real diff first. Default posture is skeptical.

Phase 3a of the meta-* pipeline (spec → plan → build → review), spawned in the same turn as [meta-security](../meta-security/SKILL.md). Self-contained — use directly for a quick code-review pass before merge.

---

## Loop

**Intent (stopping criteria)** — verdict `🟢 CLEAR` when:
- Every change claimed in the build/verify report is **present in the real diff**
- Every `[x]` AC has real evidence (command + exit code + output)
- No blocking code findings remain

**Context — read before acting**
- `git diff` — the real changes (NOT just report prose)
- the build/verify report (`2-build.md` / `verify.md`) — claims to check
- `0-spec.md` — what was supposed to be built
- changed source files

**Action**

### Reality check (always first)
- Each claimed change present in `git diff`? If not → **blocking** ("claimed but not done")
- Each `[x]` AC has pasted command + exit code + real output? If not → **blocking** (downgrade to not-met)
- Tests weakened (`.skip`, `.only`, hollow assertions) to force green? → **blocking**

### Code review
- Use the `engineering:code-review` skill if installed; else review inline
- Correctness, edge cases, error handling, N+1 queries
- UI: shared components/tokens from `design.md` — no raw hex / one-off spacing (blocking for UI features)
- Does the diff actually deliver what `0-spec.md` asked for?

**Stopping rule**
- Zero blocking findings → `🟢 CLEAR`
- Any blocking finding → `🔴 CHANGES_REQUESTED` (loop back to `meta-dev` (re-verified by `meta-qa`), or hand a single well-scoped item to `minimal-fix`)
- If `meta-security` returns blocking findings, security wins the tie even when this review is CLEAR

---

## Output (contributes to `3-review.md`)

```markdown
## 🔬 Reality check
* diff read: ✅
* claimed changes present in diff: [✅ all / 🔴 missing: <which>]
* AC evidence present & real: [✅ / 🔴 <which>]
* tests not weakened/skipped: [✅ / 🔴]

## 🔍 Code review
* ✅ [solid] · ⚠️ [non-blocking] · 🔴 [blocking — must fix before CLEAR]

## ➡️ Verdict
* **CLEAR** — no blocking findings; ready to merge
* **CHANGES_REQUESTED** — [blocking findings]; fix and re-review
```

---

## Reviewer mindset
- Reads diff first, report second — diff is truth, report is a claim
- Blocking vs non-blocking ruthlessly — style → non-blocking; broken behavior → blocking
- Looks for what's missing — error handling, unhandled edges, untested paths
- Never CLEAR on incomplete work — honest CHANGES_REQUESTED is success; false CLEAR is the failure

## Loop-back policy
- **Single** blocking finding, well-scoped → hand to the `minimal-fix` skill (smallest patch + protected-path denylist), then re-review
- **Multiple** findings or unclear root cause → loop back to `meta-dev` (full re-implement + `meta-qa` re-verify)
