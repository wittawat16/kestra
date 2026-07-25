---
name: kestra-spec
description: >
  Produce a single, build-ready 0-spec.md for kestra-build from a sharpened idea —
  normally the output of /grilling. Combines spec-sharpening (testable acceptance
  criteria, explicit error states, needs_ba/needs_ui/needs_sa/needs_devops flags),
  inline business-rule clarification, inline UI/design notes, inline solution-
  architecture decisions, and a codebase survey with verified file paths — all in
  one pass, one output file. Use this whenever the user wants a spec that
  kestra-build can consume without an agent having to guess or interpret gaps:
  "write the spec for kestra-build", "turn this idea into 0-spec.md", "make a spec
  kestra-build can use directly", "sharpen this into a build-ready spec", or right
  after a /grilling session when the next step is producing the spec artifact. If
  no grilling/interview has happened yet and the input is still a rough idea, this
  skill runs its own short clarifying pass first — don't skip straight to writing.
---

# kestra-spec — One-Pass, Build-Ready Spec for kestra-build

**Role:** Turn a sharpened idea into the single `0-spec.md` that `kestra-build` reads to derive a
`workflow.yaml`. Where the meta-* pipeline splits this across five skills and five files
(`meta-pm` → `0-spec.md`, `meta-ba` → `ba.md`, `meta-designer` → `design.md`, `meta-sa` → `sa.md`,
`meta-architect` → `1-plan.md`), this skill does the same underlying work — spec sharpening,
business-rule clarification, design notes, solution-architecture decisions, and a verified
codebase survey — in **one pass, one file**, so nobody has to remember to chain five skills by
hand and `kestra-build`'s stage agents don't have to fill gaps by guessing.

This is a **separate, new skill** — it does not replace or modify `meta-pm`, `meta-architect`,
`meta-ba`, `meta-designer`, or `meta-sa`, which remain available standalone for anyone who wants
just one piece of this (e.g. only a business-analysis pass). Read those five files before using
this skill if you haven't already — this skill borrows their templates, mindsets, and anti-pattern
lists directly rather than reinventing them.

---

## Why one pass, one file (read before writing anything)

The problem this skill exists to fix: running `meta-pm` then `meta-architect` (and sometimes
`meta-ba`/`meta-designer`/`meta-sa`) separately produces a spec that still isn't detailed enough —
`kestra-build`'s stage agents end up interpreting gaps themselves, and the loop keeps bouncing
back to "fix the spec" after implementation has already started. Two things cause that gap:

1. **`0-spec.md` alone never touches real code.** `meta-pm` reads only the rough spec and
   `CLAUDE.md` — it has no mechanism to know if a referenced file exists, what the surrounding
   pattern looks like, or whether an assumption in the spec even holds against the real codebase.
   That's `meta-architect`'s job, but it runs as a separate stage later, often *after* code review
   has already started asking "wait, which file was this supposed to touch?"
2. **Splitting the work across five skills means five separate invocations to remember**, and each
   boundary is a place state gets lost — `meta-ba`'s resolved business rules have to make it into
   `meta-designer`'s and `meta-architect`'s hands accurately, `meta-sa`'s chosen approach has to
   reach `meta-architect` before it plans files, and so on. When a human has to manually chain
   these, gaps slip through at the handoffs, not because any one skill did its job badly.

Doing it as one continuous pass with one agent removes both failure modes: the same agent that
just resolved a business rule is the one deciding which files that rule touches, and nothing has to
survive a handoff to a differently-scoped invocation.

---

## Input

Expect a **sharpened understanding**, not a rough one-liner — normally the output of a `/grilling`
session (or an equivalent back-and-forth) where ambiguity has already been interviewed out. Read
whatever the grilling session settled on directly; don't re-litigate decisions it already made.

**If you're invoked directly, with no grilling/interview behind you, and the ask is still a rough
idea** ("add CSV export", "let users reset their password"): run a short clarifying pass first —
a handful of pointed questions about scope, error states, and any obvious ambiguity — before
writing anything. Don't silently invent acceptance criteria for gaps you could have just asked
about. This is the one place this skill behaves like `meta-pm`'s own interview loop; skip it
entirely when the input already arrived pre-sharpened.

---

## Process — one continuous pass

Work through these steps in order, in a single sitting, for a single output file. Don't stop to
call another skill for steps 3–4 — do the same *kind* of work those skills do, inline, using their
templates below as your guide for structure and rigor.

### 1. Sharpen into testable acceptance criteria (meta-pm's job)

For each requirement: is it testable by QA without a follow-up question? ("users can filter" ❌ →
"filter returns results in <200ms on 10k rows" ✅). Add missing error states and edge cases the
rough ask skipped. Cut anything not essential to core value into an explicit **Out of Scope**
section — don't let "nice to have later" quietly become in-scope. Mark anything genuinely
unknowable as `⚠️ OPEN` rather than guessing.

**Prefer Given-When-Then for ACs that describe a business scenario, not just a metric.** A
threshold AC ("filter returns results in <200ms on 10k rows") is already testable as-is — leave it
alone. But an AC that's really describing *behavior under a condition* ("cancelling a paid order
refunds the customer") reads far more precisely, and is far harder to write ambiguously, as a
scenario:

```
Given a paid order
When the customer cancels it
Then the payment is refunded in full
And the order status becomes "cancelled"
```

This matters most exactly where `needs_ba: true` — the whole reason that flag exists is that a
one-line requirement hides business rules a developer would otherwise have to guess. Given-When-Then
forces every "when X happens" and every "and also" branch into its own explicit line, so a missing
case (what if the order already shipped? what if it's a partial refund?) shows up as a *gap in the
scenario list* instead of surfacing three implementation stages later as a bug. It also reads
naturally to a non-technical stakeholder reviewing the spec — they can confirm "yes, that's the
behavior we want" without parsing prose.

Don't force this format everywhere — a pure data-shape or performance AC doesn't gain anything from
Given-When-Then and forcing it just adds noise. Use it where the AC is actually describing behavior
across a condition, especially inside **Business Rules** (BR-N) below, where each rule's example and
counter-example map directly onto a Given-When-Then pair.

### 2. Set the flags — mechanically, not as a vibe check

Set each flag from the criteria `meta-pm` uses:

* `needs_ba` — complex domain/business rules, multi-stakeholder requirements, or a spec that's
  vague on *what* rather than *how*.
* `needs_ui` — **any** new page/route/modal, changes to an existing screen/form/interactive
  element, new or modified error/empty/loading states visible to users, or role-based UI
  variation. A single added button already qualifies — don't downgrade this because the surface
  area feels small.
* `needs_sa` — 2+ services involved, competing approaches with lasting consequences (sync vs
  async, new table vs extend, push vs poll), or explicit NFRs (latency, throughput, compliance).
* `needs_devops` — new/changed env vars, DB migrations, feature flags, or infra changes.

Treat each flag's value as a fact you just derived, not a recommendation to second-guess in the
next step — if `needs_ui` is `true`, step 4 does real design work, full stop, no "it's only one
button so I'll skip it" reasoning.

### 3. Do the flagged work inline — don't skip, don't stub

For every flag that's `true`, do that skill's actual job now, in this same pass, and fold the
result directly into the sections of `0-spec.md` below (not a separate file):

* **`needs_ba: true`** → Enumerate business rules explicitly (BR-1, BR-2…) with an example and a
  counter-example each. Identify stakeholder/role/locale variations. Add any acceptance criteria
  that fall out of a rule the original ask left untestable. Flag anything still needing a human
  decision rather than guessing it — surface it in **Open items**, don't silently resolve it.
* **`needs_ui: true`** → Read `CLAUDE.md` and the actual component library / token source
  (`theme.ts`, `tailwind.config`, CSS vars — whatever this codebase actually uses) before naming
  any component or color. Produce: a component audit (reuse vs. new, with real import paths for
  reused components), real token names (not invented hex values), responsive breakpoints if the
  feature is multi-device, and all four screen states (empty/loading/success/error) per view —
  don't skip one silently; say why if one is genuinely impossible. Add the resulting design ACs
  (component + token + state + viewport, not "looks consistent").
* **`needs_sa: true`** → Enumerate 2–3 realistic approaches with concrete trade-offs, pick one and
  justify the pick (cost/complexity/risk, not a vibe), define NFR targets, spell out any
  cross-service/integration contract, and flag data-model impact (new tables/columns/migrations).
  Note architectural constraints the file survey (step 4) and any future implementation must
  respect.
* **`needs_devops: true`** → this flag is a signal for `kestra-build` to add its own
  `deploy-readiness` stage later (that stage does the actual pre-deploy checklist against the real
  diff, which doesn't exist yet at spec time) — you don't need to produce a checklist now, just
  make sure the spec's **Edge Cases & Error States** and **Functional Requirements** sections
  actually mention the env vars / migrations / flags driving this flag, so that later stage has
  something concrete to check against.

If a flag is `false`, do nothing for it — an unnecessary business-rules section for a
straightforward CRUD change is just noise.

### 4. Survey the real codebase and verify every file path (meta-architect's job)

This is the step that most directly closes the "agent has to interpret" gap, so don't shortcut it.

* Explore the directories/files this feature actually touches or integrates with — read the real
  code before deciding where anything goes.
* For every file you plan to list as a change: **verify it exists** (`ls`, `find`, or a read) before
  writing it down. Never write a path you haven't confirmed. For new files, follow the nearest
  existing convention rather than inventing a new one — say which existing file you patterned it
  after.
* If `needs_sa` was true, the approach chosen in step 3 is a hard constraint here — don't
  re-litigate it, don't silently override it; if the survey reveals it can't work as chosen, that's
  a contradiction to surface and resolve (going back to step 3), not something to quietly route
  around.
* Map every acceptance criterion (from steps 1–3) to at least one concrete implementation step —
  coverage must be complete. If you can't map an AC to a real step, that's a sign the AC or the
  survey is incomplete — fix it before moving on, don't hand incomplete coverage downstream.
* List new dependencies (packages, migrations, infra) and name risks explicitly (shared files,
  race conditions, migrations needing care) — don't bury these in prose elsewhere.

### 5. Write `0-spec.md` — single file, everything included

One file, not five. See the template below. Every section that step 3 produced content for gets
folded in under its own heading in the same document — there is no separate `ba.md`/`design.md`/
`sa.md`/`1-plan.md` to keep in sync.

---

## Output: `0-spec.md`

Default location: `<repo>/workflows/runs/<feature-id>/0-spec.md` (matching `kestra-build`'s default
output convention, so both files sit side by side). Ask if the repo already uses a different
convention.

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
* [ ] [behavioral requirement — expressed as Given-When-Then where it clarifies a scenario, e.g.:
      **Given** [context] **When** [action] **Then** [outcome] — otherwise plain prose is fine]

## 🌤️ Edge Cases & Error States
* **[edge case]:** [how it's handled]
* **[failure mode]:** [expected behaviour]

## 📜 Business Rules  *(only if needs_ba: true)*
* **BR-1:** [rule, stated precisely, with example + counter-example — prefer Given-When-Then for the
  example/counter-example pair, e.g. `Given [state] When [action] Then [expected]` /
  `Given [different state] When [same action] Then [different expected]`]
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

## 🗂️ Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| src/... | edit | ✅ exists | ... |
| src/... | new | ✅ follows pattern at src/... | ... |

## 🔗 Dependencies
* [new packages / schema changes / migrations — or "none"]

## 🎯 Acceptance Criteria
* [ ] [testable, measurable — includes design ACs from step 3 if any; use Given-When-Then for
      behavioral/business-rule ACs, plain testable prose for threshold/data-shape ACs]

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
- Every flagged section (`needs_ba`/`needs_ui`/`needs_sa`) that's `true` has real content, not a stub
- Every row in **Files to touch** has been verified to exist (or is deliberately placed per an
  existing pattern, named explicitly)
- Every AC maps to at least one file/step in the coverage map
- No silent gaps — anything unresolved is in **Open Items**, not left blank

If **Open Items** is non-empty, say so plainly when handing this off — `kestra-build` (or whoever
reads this next) should decide whether to pause on those before generating stages, the same way
`meta-ba`'s "still needs human decision" pauses the old pipeline.

## Mindset

- **Detective, not tourist** — verify paths and read real code before naming them; never invent
- **Flags are facts, not opinions** — once derived in step 2, don't re-litigate their value while
  doing the work they trigger
- **One file, no dangling handoffs** — if you catch yourself wanting to write a second file to hold
  "the rest" of something, that content belongs under a heading in `0-spec.md` instead
- **Honest gaps over confident guesses** — an explicit `⚠️ OPEN` beats a silently invented answer,
  every time

## Handoff

→ `kestra-build`, which reads this `0-spec.md` directly (it already has an `acceptance_criteria`
list and populated flags, so `kestra-build` can skip straight to deriving stages instead of
sharpening a rough spec itself).
