---
name: kestra-spec
description: >
  Produce a single, build-ready 0-spec.md for kestra-build from a sharpened idea —
  normally the output of /grilling. Combines spec-sharpening (testable acceptance
  criteria, explicit error states, needs_ba/needs_ui/needs_sa/needs_devops flags),
  inline business-rule clarification, inline UI/design notes, inline solution-
  architecture decisions, runtime invariants and external-dependency reality
  constraints, a codebase survey with verified file paths, and an execution-verified
  self-check — all in one pass, one output file. Use this whenever the user wants a
  spec that kestra-build can consume without an agent having to guess or interpret
  gaps: "write the spec for kestra-build", "turn this idea into 0-spec.md", "make a
  spec kestra-build can use directly", "sharpen this into a build-ready spec", or
  right after a /grilling session when the next step is producing the spec artifact.
  If no grilling/interview has happened yet and the input is still a rough idea, this
  skill runs its own short clarifying pass first — don't skip straight to writing.
---

# kestra-spec — One-Pass, Build-Ready Spec for kestra-build

**Role:** Turn a sharpened idea into the single `0-spec.md` that `kestra-build` reads to derive a
`workflow.yaml` — one pass, one file, covering PM (spec-sharpening), BA (business rules), design
notes, and SA (architecture decisions) inline plus a verified codebase survey, so no `kestra-build`
stage agent has to guess. Separate: [`meta-designer`](../../meta/meta-designer/SKILL.md), which
produces an actual openable artifact (HTML mockup/wireframe) that this skill's Design Notes feed
into, not compete with.

**Suggested model, if spawning this as a subagent with a model to choose:** Opus 5. Measured
same-effort against Sonnet 5 on this same skill: Opus caught a real spec defect (an execution-
verified edge case, e.g. a spread-order default-overwrite bug) that Sonnet's read-and-reason pass
missed entirely, for ~14% more tokens. This is a suggestion to offer the user, not a default to pick
silently — ask before spawning. Doesn't apply when running inline in an already-active session; a
skill can't switch that session's model on its own.

---

## Input

Expect a **sharpened understanding** (normally `/grilling`'s output), not a rough one-liner. Read
what it settled on directly — don't re-litigate.

**No grilling behind it and the ask is still rough** ("add CSV export"): run a short clarifying pass
first — scope, error states, obvious ambiguity — before writing anything. Skip this entirely when
the input already arrived pre-sharpened.

---

## Process — one continuous pass, one sitting, one output file

### 1. Sharpen into testable acceptance criteria (PM pass)

Each requirement testable by QA without a follow-up question ("users can filter" ❌ → "filter
returns results in <200ms on 10k rows" ✅). Add missing error states/edge cases. Cut non-essential
scope into **Out of Scope**. Mark genuine unknowns `⚠️ OPEN`.

**Prefer Given-When-Then for behavior-under-a-condition ACs**, not pure thresholds:
```
Given a paid order
When the customer cancels it
Then the payment is refunded in full
And the order status becomes "cancelled"
```
Matters most where `needs_ba: true` — forces every branch into its own visible line instead of
hiding inside prose. Skip it for pure data-shape/perf ACs.

### 2. Set the flags — mechanically

* `needs_ba` — complex domain/business rules, multi-stakeholder requirements, spec vague on *what*.
* `needs_ui` — **any** new/changed page, route, modal, form, interactive element, or visible
  state — a single added button qualifies.
* `needs_sa` — 2+ services, competing approaches with lasting consequences, or explicit NFRs.
* `needs_devops` — new/changed env vars, migrations, feature flags, infra.

Once derived, each flag's value is a fact for step 3 to act on, not a judgment call to reopen.

### 3. Do the flagged work inline — real content, not a stub

* **`needs_ba`** → BR-1, BR-2… each with example + counter-example (Given-When-Then). Stakeholder/
  role/locale variations. New ACs for anything the rule makes testable. Unresolved → **Open Items**.
* **`needs_ui`** → Read `CLAUDE.md` + the actual token/component source before naming anything.
  Component audit (reuse w/ real import path, or new + why), real token names, breakpoints if
  multi-device, all 4 screen states (empty/loading/success/error) per view — say why if one's
  impossible, don't skip silently. Add design ACs (component + token + state + viewport).
* **`needs_sa`** → 2–3 approaches, concrete trade-offs, chosen one justified (cost/complexity/risk),
  NFR targets, integration contracts, data-model impact.
* **`needs_devops`** → just make sure Edge Cases/Functional Requirements name the env
  vars/migrations/flags involved — the deploy checklist itself is `deploy-readiness`'s job later.

Flag `false` → do nothing for it.

### 4. Survey the real codebase and verify every file path (architect pass)

* Read the real code in every directory/file this feature touches before deciding anything.
* **Verify every file in "Files to Touch" exists** (`ls`/`find`/read) before writing it down. New
  files follow the nearest existing convention — name which file you patterned it after.
* A chosen `needs_sa` approach is a hard constraint here — a conflict goes back to step 3, not
  routed around silently.
* Every AC maps to at least one concrete implementation step — incomplete mapping means fix it now.
* **For every AC that names a runnable check, actually run it now** — don't take the spec's own
  wording as given.
* **Read the code behind each Runtime Invariant's on-violation behaviour**, even outside this
  feature's own files (a plugin loader, a supervisor, a deploy policy) — an unchecked on-violation
  claim sends the implementer and reviewer looking for a behavior that cannot happen. Step 6 grades
  this; do the work here.
* List new dependencies and name risks (shared files, race conditions, fragile migrations)
  explicitly.

### 5. Name what the world won't guarantee, and what must hold at runtime

Acceptance criteria cover cases someone thought of; this step covers the ones nobody did.

* **Runtime invariants.** Enforced *forever*, against inputs nobody predicted. Test: if this
  condition went false and the system carried on, would anyone find out before the damage was
  done? If no, name the condition, how it's detected at runtime, and what happens on violation
  (halt/refuse/alert). "Logged, then continues" is not an invariant — it's a comment wearing one's
  clothes.
* **What each external dependency actually does — and doesn't guarantee.** Enforced ordering/
  preconditions, real returned types/shapes, and — the part people skip — what completeness/
  consistency it does *not* promise. The standard test doubles get judged against later.
* **Pairs of paths that must agree.** Replay vs. live, cached vs. computed, sync vs. async — name
  the pair, what "equivalent" means, what may legitimately differ.
* **Non-deterministic inputs: pinned or floating.** Clock, randomness, timezone/locale, network,
  filesystem, env — for each one this feature reads, say which, and why.

Grounding: [`../kestra-build/references/test-quality-taxonomy-research.md`](../kestra-build/references/test-quality-taxonomy-research.md)
— a starting point, not a complete list; add whatever this codebase's own history says belongs.

### 6. Self-check against the list `spec-review` will grade this by

Keep this list in sync with `kestra-build`'s spec-review brief — change one, change both.

1. Each Runtime Invariant vs. the Edge Cases/ACs describing the same condition — no contradictions
   (e.g. an invariant that halts where an edge case says "no-op").
2. No invariant's on-violation action is "log and continue."
3. Each AC is testable without a follow-up question — exact inputs named, not "the right subset."
4. Each "does not guarantee" column is filled.
5. **Every claim in items 1–4 was verified by actually running the command or reading the real code
   in step 4 — not just cross-checked on paper.** A spec can pass 1–4 by being internally consistent
   and still be wrong about what the world does; this item is what closes that gap. Don't broaden
   this into running the full test suite — that's the verify stage's job, later, on frozen tests
   that don't exist yet.

Fix what this turns up. Anything unresolved → **Open Items** — an honest open item passes
`spec-review`, a contradiction doesn't.

### 7. Write `0-spec.md`

One file. Every section step 3 produced content for gets folded in under its own heading below —
no separate `ba.md`/`design.md`/`sa.md`/`1-plan.md`.

---

## Output: `0-spec.md`

Default: `<repo>/workflows/runs/<feature-id>/0-spec.md` (next to `kestra-build`'s output). Ask if the
repo uses a different convention.

**Written for `kestra-build`'s stage-derivation pass and every generated stage's spawned subagent,
not a human approver** — `kestra-run`'s context pack pastes this file's full text into *every single
spawn* (see `kestra-run`'s `SKILL.md` step 2), so every sentence here is paid for again on every
stage. Bias hard toward density: bullet fragments over full sentences, never restate a heading's own
words in the prose under it. This changes *density*, never *content* — every fact the template asks
for still has to be there in full; cutting a fact to save a sentence just relocates the cost to
whichever stage discovers the gap later, at a worse exchange rate. No emoji in headings — a
decorative prefix is pure overhead for a subagent grepping section names.

```markdown
# [<feature-id>] Spec — <feature title>

> Status: READY_FOR_BUILD | Created: YYYY-MM-DD | Next: kestra-build

---

## Overview
[one line: what this delivers, why.]

## Problem Statement
* [current behaviour]
* Goal: [measurable outcome]

## Functional Requirements
* [ ] [requirement — specific enough to implement]
* [ ] [behavioral requirement — Given-When-Then where it clarifies a scenario, else a bullet fragment]

## Edge Cases & Error States
* **[edge case]:** [how it's handled]
* **[failure mode]:** [expected behaviour]

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| [condition] | [the actual check, and where it sits in the flow] | [halt / refuse / alert — who finds out] |

## Business Rules  *(only if needs_ba: true)*
* **BR-1:** [rule + example + counter-example, Given-When-Then]
* Stakeholder variations: [role/locale/state → behaviour difference]

## Design Notes  *(only if needs_ui: true)*
### Component Audit
| Component | Reuse? | Token ref | Notes |
|-----------|--------|-----------|-------|
| `[Name]` | reuse `@path/to/Component` | `token.name` | [usage] |
| `[Name]` | new | `token.name` | [why existing ones didn't fit] |
### Token Mapping
* [usage]: `token.name` (or "no design system" — hardcoded baseline noted)
### Screen States
| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|
| [Name] | [desc] | [desc] | [desc] | [desc] |

## Solution Architecture  *(only if needs_sa: true)*
Chosen approach: [A] — [one-sentence rationale]
| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| [A] | ... | ... | chosen |
| [B] | ... | ... | rejected — [why] |
* Integration contracts: [service A → service B: what's exposed/consumed]
* Data model impact: [new tables/columns/migrations — or "none"]
* NFR targets: [latency / throughput / fault-tolerance / compliance]

## Codebase Survey
* Explored: [dirs/files actually read]
* Integrate with: [existing modules/patterns/conventions to follow]

## Reality Constraints
*(what the world outside this feature actually does — verified by running/reading, not assumed.
Omit a subsection only when genuinely not applicable, and say so.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| `[name]` | [e.g. X must be released before Y — or "none known"] | [real types as observed/documented] | [completeness / ordering / uniqueness / timeliness it won't promise] |

### Paths that must agree
* `[path A]` ↔ `[path B]` — equivalent means: [what must match] · may differ: [what's allowed to
  diverge, and why] — *(or "none — single path")*

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| [clock / randomness / timezone / locale / network / filesystem / env] | pinned \| floating | [reason] |

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| src/... | edit | exists | ... |
| src/... | new | follows pattern at src/... | ... |

## Dependencies
* [new packages / schema changes / migrations — or "none"]

## Acceptance Criteria
* [ ] [testable, measurable — includes design ACs; Given-When-Then for behavioral ACs]

## AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| [ac text] | [file(s) / step] |

## Risks & Watch-outs
* [shared files, race conditions, migrations needing care — or "none"]

## Out of Scope
* [explicitly excluded — point to future work if relevant]

## Flags
* `needs_ba`: [true|false] — [reason]
* `needs_ui`: [true|false] — [reason]
* `needs_sa`: [true|false] — [reason]
* `needs_devops`: [true|false] — [reason]

## Open Items
* [anything genuinely unresolvable — or "none"]
```

---

## Stopping rule

Done once:
- Every AC is testable without a follow-up question
- Every flagged section (`needs_ba`/`needs_ui`/`needs_sa`) that's `true` has real content
- Every row in **Files to Touch** verified to exist (or placed per a named existing pattern)
- Every AC maps to at least one file/step in the coverage map
- **Runtime Invariants** names the on-violation action for each row, none of them "log and continue"
- **Reality Constraints** filled in or explicitly marked not-applicable with a reason — especially
  "does not guarantee"
- **Step 6 ran, including item 5** — every checkable claim was actually run or read against real
  code, not just cross-checked on paper
- No silent gaps — unresolved → **Open Items**

Non-empty **Open Items** → say so plainly at handoff.

## Handoff

→ `kestra-build`, which reads this `0-spec.md` directly and can skip straight to deriving stages.
