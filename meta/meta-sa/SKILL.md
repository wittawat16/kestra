---
name: meta-sa
description: Solution-architecture agent that resolves cross-service concerns, competing implementation approaches, and NFRs (latency, throughput, compliance) into a single chosen approach with justification, integration contracts, data-model impact, and constraints for the implementation plan. The solution-architecture atom part of the meta-* pipeline, phase 0.7 (only when the spec touches 2+ services, has competing approaches, or explicit NFRs), callable standalone or from a wtf-build/wtf-run stage brief. Trigger on "pick an approach for this", "resolve the NFRs for X", "write sa.md", "sync vs async / push vs poll — which one", or when an orchestrator points a solution architect here.
---

# meta-sa — Solution Architecture

**Role:** Make cross-cutting design decisions before anyone picks files to touch.

Phase 0.7 of the meta-* pipeline (spec → plan → build → review). Self-contained — use directly whenever a spec has real architectural ambiguity.

---

## Run only when ANY apply — otherwise skip

- Feature touches **2+ services** (API gateway, auth, DB, queue, external API…)
- **Competing approaches** with lasting consequences (sync vs async, push vs poll, new table vs extend…)
- Explicit **NFRs**: latency SLA, throughput, fault-tolerance, multi-tenancy, compliance
- The spec says "TBD" or is vague on *how*

## What this does

Reads `0-spec.md` (+ `design.md` if present). Identifies cross-cutting concerns the spec glosses over. Picks an approach:
1. Enumerate 2–3 realistic options with concrete trade-offs
2. Pick one and justify it (cost, complexity, risk — not subjective)
3. Define NFR targets (p99 latency, max payload, error budget…)
4. Call out integration contracts: what each service must expose/consume
5. Flag data model changes (new tables, migrations, indexes)
6. Surface risks the implementation plan must design around

## Output: `sa.md`

```markdown
# 🔭 [<feature-id>] Solution Architecture — <feature title>

> **Status:** 🟢 READY_FOR_PLAN &nbsp;|&nbsp; **Created:** YYYY-MM-DD
> **Next:** 🏗️ Phase 1 — Plan

---

## 🗺️ Scope gaps closed
* [anything the spec left vague that this makes explicit]

## ⚖️ Approach considered
| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| [A] | ... | ... | ✅ chosen |
| [B] | ... | ... | ❌ rejected — [why] |

**Chosen:** [approach A] — [one-sentence rationale]

## 🔗 Cross-service / integration contracts
* **[Service A] → [Service B]:** [what A must expose; what B consumes; protocol/format]
* [any schema or API contract changes]

## 🗄️ Data model impact
* [new tables / columns / indexes / migrations — or "none"]

## 📐 NFR targets
* Latency: [e.g. p99 < 200 ms under X RPS]
* Throughput / scale: [...]
* Fault-tolerance: [e.g. retry policy, dead-letter queue]
* Other: [compliance, data retention, multi-tenancy…]

## ⚠️ Architectural risks & constraints for the implementation plan
* [what the plan must not do / must watch out for]
* [any external dependency / vendor limit that constrains impl]
```

## When this is done

`meta-architect` reads `sa.md` and follows the chosen approach without re-litigating it. No more TBDs between spec and plan.
