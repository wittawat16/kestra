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
`workflow.yaml`. One agent, one pass, one file — spec-sharpening (PM), business-rule clarification
(BA), design notes, solution-architecture decisions, and a verified codebase survey, so nothing gets
lost at a handoff between separately-invoked skills and `kestra-build`'s stage agents never have to
fill a gap by guessing. Retired: `meta-pm`, `meta-ba`, `meta-sa`, `meta-architect` — this file covers
their jobs. Still separate: [`meta-designer`](../../meta/meta-designer/SKILL.md), which produces an
actual openable artifact (HTML mockup/wireframe) that this skill's Design Notes feed into, not
compete with.

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
This matters most where `needs_ba: true` — it forces every branch ("what if it already shipped?")
into its own visible line instead of hiding inside prose. Don't force it onto pure data-shape/perf
ACs — no benefit there.

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
* **`needs_devops`** → no checklist needed now (that's `deploy-readiness`'s job later) — just make
  sure Edge Cases/Functional Requirements actually name the env vars/migrations/flags involved.

Flag `false` → do nothing for it.

### 4. Survey the real codebase and verify every file path (architect pass)

* Read the real code in every directory/file this feature touches before deciding anything.
* **Verify every file in "Files to Touch" exists** (`ls`/`find`/read) before writing it down. New
  files follow the nearest existing convention — name which file you patterned it after.
* A chosen `needs_sa` approach is a hard constraint here — a conflict is a contradiction to resolve
  (back to step 3), not something to route around silently.
* Every AC maps to at least one concrete implementation step — incomplete mapping means the AC or
  the survey is incomplete; fix before moving on.
* **For every AC that names a runnable check, actually run it now** — don't take the spec's own
  wording as given.
* **Read the code behind each Runtime Invariant's on-violation behaviour, even when it's not a file
  you're changing.** This survey is otherwise scoped to what the feature touches, and "what happens
  when this fails" is almost never in that set (a plugin loader, a supervisor, a deploy policy) — an
  invariant whose on-violation claim you never checked outside your own diff sends both the
  implementer and the reviewer looking for a behavior that cannot happen. This is what step 6
  grades; do the work here, not there.
* List new dependencies and name risks (shared files, race conditions, fragile migrations)
  explicitly.

### 5. Name what the world won't guarantee, and what must hold at runtime

Acceptance criteria cover cases someone thought of. This step covers the ones nobody did — absent
here, they're absent from every test derived from here, so implementation passes and still misses
them. Four things, each cheap now, expensive later:

**a. Runtime invariants.** Not an AC in a different hat — enforced *forever*, against inputs nobody
predicted. Test: if this condition went false and the system carried on, would anyone find out
before the damage was done? If no, it's an invariant: name the condition, how it's detected at
runtime, and what happens on violation (halt/refuse/alert). "Logged, then continues" is not an
invariant — it's a comment wearing one's clothes.

**b. What each external dependency actually does — and doesn't guarantee.** Enforced ordering/
preconditions, real returned types/shapes, and — the column people skip — what completeness/
consistency it does *not* promise. This is the standard the project's test doubles get judged
against later.

**c. Pairs of paths that must agree.** Replay vs. live, cached vs. computed, sync vs. async — name
the pair, what "equivalent" means, what may legitimately differ. Nobody else will ever declare this
pair for a parity check to test against.

**d. Non-deterministic inputs: pinned or floating.** Clock, randomness, timezone/locale, network,
filesystem, env — for each one this feature reads, say which, and why.

Grounding: [`../kestra-build/references/test-quality-taxonomy-research.md`](../kestra-build/references/test-quality-taxonomy-research.md)
— a starting point, not a complete list; add whatever this codebase's own history says belongs.

### 6. Self-check against the list `spec-review` will grade this by

Keep this list in sync with `kestra-build`'s spec-review brief — change one, change both.

1. **Each Runtime Invariant vs. the Edge Cases/ACs describing the same condition** — no
   contradictions (e.g. an invariant that halts where an edge case says "no-op").
2. **No invariant's on-violation action is "log and continue."**
3. **Each AC is testable without a follow-up question** — exact inputs named, not "the right subset."
4. **Each "does not guarantee" column is filled.**
5. **Every claim checked in items 1–4 was verified by actually running the command or reading the
   real code in step 4 — not just read internally for self-consistency.** A spec can pass 1–4 by
   being internally consistent and still be wrong about what the world actually does; that gap is
   exactly what real `spec-review` catches and this item is what closes it. Don't broaden this into
   running the full test suite — that's the verify stage's job, at a later point, on frozen tests
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

```markdown
# ☕ [<feature-id>] Spec — <feature title>

> **Status:** 🟢 READY_FOR_BUILD | **Created:** YYYY-MM-DD
> **Next:** 🏗️ kestra-build

---

## ☕ Overview
[1–2 sentences: what this delivers and why.]

## 🪵 Problem Statement
* [context / current behaviour]
* 🎯 **Goal:** [the measurable outcome]

## 🥑 Functional Requirements
* [ ] [requirement — specific enough to implement]
* [ ] [behavioral requirement — Given-When-Then where it clarifies a scenario, else plain prose]

## 🌤️ Edge Cases & Error States
* **[edge case]:** [how it's handled]
* **[failure mode]:** [expected behaviour]

## 🛡️ Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| [condition] | [the actual check, and where it sits in the flow] | [halt / refuse / alert — who finds out] |

## 📜 Business Rules  *(only if needs_ba: true)*
* **BR-1:** [rule + example + counter-example, Given-When-Then]
* 👥 **Stakeholder variations:** [role/locale/state → behaviour difference]

## 🎨 Design Notes  *(only if needs_ui: true)*
### Component Audit
| Component | Reuse? | Token ref | Notes |
|-----------|--------|-----------|-------|
| `[Name]` | ✅ reuse `@path/to/Component` | `token.name` | [usage] |
| `[Name]` | 🆕 new | `token.name` | [why existing ones didn't fit] |
### Token Mapping
* [usage]: `token.name` (or ⚠️ no design system — hardcoded baseline noted)
### Screen States
| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|
| [Name] | [desc] | [desc] | [desc] | [desc] |

## 🔭 Solution Architecture  *(only if needs_sa: true)*
**Chosen approach:** [A] — [one-sentence rationale]
| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| [A] | ... | ... | ✅ chosen |
| [B] | ... | ... | ❌ rejected — [why] |
* **Integration contracts:** [service A → service B: what's exposed/consumed]
* **Data model impact:** [new tables/columns/migrations — or "none"]
* **NFR targets:** [latency / throughput / fault-tolerance / compliance]

## 🔎 Codebase Survey
* **Explored:** [dirs/files actually read]
* **Integrate with:** [existing modules/patterns/conventions to follow]

## 🌐 Reality Constraints
*(what the world outside this feature actually does — verified by running/reading, not assumed.
Omit a subsection only when genuinely not applicable, and say so.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| `[name]` | [e.g. X must be released before Y — or "none known"] | [real types as observed/documented] | [completeness / ordering / uniqueness / timeliness it won't promise] |

### Paths that must agree
* `[path A]` ↔ `[path B]` — **equivalent means:** [what must match] · **may differ:** [what's
  allowed to diverge, and why] — *(or "none — single path")*

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| [clock / randomness / timezone / locale / network / filesystem / env] | 📌 pinned \| 🌊 floating | [reason] |

## 🗂️ Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| src/... | edit | ✅ exists | ... |
| src/... | new | ✅ follows pattern at src/... | ... |

## 🔗 Dependencies
* [new packages / schema changes / migrations — or "none"]

## 🎯 Acceptance Criteria
* [ ] [testable, measurable — includes design ACs; Given-When-Then for behavioral ACs]

## 🎯 AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| [ac text] | [file(s) / step] |

## ⚠️ Risks & Watch-outs
* [shared files, race conditions, migrations needing care — or "none"]

## 🚫 Out of Scope
* [explicitly excluded — point to future work if relevant]

## 🔀 Flags
* `needs_ba`: [true|false] — [reason]
* `needs_ui`: [true|false] — [reason]
* `needs_sa`: [true|false] — [reason]
* `needs_devops`: [true|false] — [reason]

## ❓ Open Items
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

## Mindset

- **Detective, not tourist** — verify paths and *run/read* real code before naming behavior; never
  invent, and never trust the spec's own prose as proof of what the world does
- **Flags are facts, not opinions** — don't re-litigate a derived flag's value
- **ACs cover what you thought of; invariants cover what you didn't**
- **One file, no dangling handoffs**
- **Honest gaps over confident guesses**

## Handoff

→ `kestra-build`, which reads this `0-spec.md` directly and can skip straight to deriving stages.
