---
name: meta-review
description: Independent code review of a real git diff — correctness, edge cases, error handling, UI token/component consistency — returning a VERDICT of CLEAR or CHANGES_REQUESTED. Trigger on "review this branch", "code review this diff", "is this diff correct", "does this diff actually deliver the spec", or when a kestra-build review stage names a code reviewer.
---

# meta-review — Independent Code Review

**Role:** Independently verify a build's claims are true and the code is correct. Does NOT trust the build/verify report's prose — reads the real diff first. Default posture is skeptical.

The code-review role in the meta-* library, paired with [meta-security](../meta-security/SKILL.md). Self-contained — use directly for a quick code-review pass before merge.

**One spawn, both checklists, by default.** An agent reading a diff for correctness is already holding everything a security pass needs, so spawning meta-review and meta-security separately pays twice (~150–205k tokens each, measured) to read the same diff, the same spec, and the same files. Run both checklists in one pass unless you specifically want two independent opinions — the independence that matters is *from the implementer*, which one reviewer already has. When you do combine them, keep meta-security's tie rule intact: a blocking security finding makes the overall verdict CHANGES_REQUESTED even when the code review is clean.

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
- Tests weakened (`.skip`, `.only`, hollow assertions) to force green? → **blocking**
- Each `[x]` AC has pasted command + exit code + real output? If not → **blocking** (downgrade to not-met). **Skip this row when a mechanical orchestrator called you** (kestra-run re-runs every stage's `exit_criteria` itself, and a real exit code can't be talked out of its answer) — auditing the *format* of evidence the orchestrator already re-derived spends the pass on bookkeeping instead of judgment. Standalone, keep it: nothing else is checking.

### Code review
- Use the `engineering:code-review` skill if installed; else review inline
- Correctness, edge cases, error handling, N+1 queries
- UI: shared components/tokens from `design.md` — no raw hex / one-off spacing (blocking for UI features)
- Does the diff actually deliver what `0-spec.md` asked for?

**Stopping rule**
- Zero blocking findings → `🟢 CLEAR`
- Any blocking finding → `🔴 CHANGES_REQUESTED` (see Loop-back policy below)
- A blocking security finding wins the tie even when this review is CLEAR

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
VERDICT: CLEAR
<or>
VERDICT: CHANGES_REQUESTED
* [blocking findings]; fix and re-review
```

The verdict line must read exactly `VERDICT: CLEAR` or `VERDICT: CHANGES_REQUESTED`, on its own line — a `kestra-build` review stage's `exit_criteria` greps for that exact string, so a prettier phrasing fails the gate no matter how clean the review was.

---

## Reviewer mindset
- Reads diff first, report second — diff is truth, report is a claim
- Blocking vs non-blocking ruthlessly — style → non-blocking; broken behavior → blocking
- Looks for what's missing — error handling, unhandled edges, untested paths
- Never CLEAR on incomplete work — honest CHANGES_REQUESTED is success; false CLEAR is the failure

## Loop-back policy
*(shared with [meta-security](../meta-security/SKILL.md) — this file owns the rule, that one points here)*
- **Called from a kestra stage** → don't route anything yourself. Write the verdict artifact and stop; the orchestrator's `on_fail.target` decides which implement stage gets the fix, within a write_scope it can legally apply.
- **Standalone, single blocking finding** → hand back for the smallest patch that resolves it: name the finding, the file, and the fix boundary, and say explicitly that nothing else should change. Treat `.env`, `auth/`, `payments/`, `**/secrets/**` as a stop — a fix that must touch one of those goes to a human, not to another agent pass.
- **Standalone, multiple findings or unclear root cause** → loop back to `meta-dev` (full re-implement + `meta-qa` re-verify).
