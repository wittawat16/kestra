---
name: kestra-spec
description: >
  Produce a single, build-ready 0-spec.md for kestra-build from a sharpened idea —
  normally the output of /grilling. Combines spec-sharpening (testable acceptance
  criteria, explicit error states, needs_ba/needs_ui/needs_sa/needs_devops flags),
  inline business-rule clarification, inline UI/design notes, inline solution-
  architecture decisions, runtime invariants and external-dependency reality
  constraints, a codebase survey with verified file paths, and an execution-verified
  self-check — all in one pass. Outputs two files: 0-spec.md, and an
  acceptance-tests.csv table a non-engineer can execute and sign off before any test
  code exists. Use this whenever the user wants a
  spec that kestra-build can consume without an agent having to guess or interpret
  gaps: "write the spec for kestra-build", "turn this idea into 0-spec.md", "make a
  spec kestra-build can use directly", "sharpen this into a build-ready spec", or
  right after a /grilling session when the next step is producing the spec artifact.
  If no grilling/interview has happened yet and the input is still a rough idea, this
  skill runs its own short clarifying pass first — don't skip straight to writing.
---

# kestra-spec — One-Pass, Build-Ready Spec for kestra-build

**Role:** Turn a sharpened idea into the `0-spec.md` that `kestra-build` reads to derive a
`workflow.yaml` — one pass, covering PM (spec-sharpening), BA (business rules), design
notes, and SA (architecture decisions) inline plus a verified codebase survey, so no `kestra-build`
stage agent has to guess. Plus a second file, `acceptance-tests.csv`: the same acceptance criteria
rendered as steps a person with no access to the code can execute and sign off. Separate:
[`meta-designer`](../../meta/meta-designer/SKILL.md), which
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

## Process — one continuous pass, one sitting, two output files

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

**Give every AC and every edge case a stable id** — `AC-1`, `AC-2`…, `EC-1`, `EC-2`… (business
rules already get `BR-n` in step 3; design states get `DS-n` under `needs_ui`). Step 7's table and
`kestra-build`'s `generate-tests` both reference these ids, and "the third bullet under Acceptance
Criteria" is not a reference that survives one edit to the list. Ids are append-only: a deleted AC
leaves its number retired rather than renumbering the ones after it.

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

### 7. Render the acceptance criteria as a table a non-engineer can execute

Same content, different reader. `0-spec.md` is written for the stage agents; this table is written
for whoever has to *approve* what will be tested — a QA lead, a product owner, a client — before
any test code exists and while a change is still cheap.

Why here and not later: `kestra-build` can generate a `design-tests` stage that stops mid-run for
the same approval, but that adds a human stop to a pipeline whose default is zero, and it sits
downstream of a freeze where a rejected row costs a `reworking` bounce. Doing it here folds the
approval into the moment a human already reads the spec, and leaves the generated workflow fully
automatic.

* **One row per scenario, every row carrying the id it came from** — `AC-n`, `BR-n`, `EC-n`,
  `DS-n`. Every id enumerated in the spec appears in at least one row; a row whose id resolves to
  nothing is scope you invented, not a bonus test.
* **Split an AC that hides more than one outcome.** "Refunded, inventory released, all in one
  atomic operation" needs the happy-path row *and* a row that fails when the operation is only
  half-applied — one row per AC would let a half-working implementation pass, which is the exact
  false positive the table exists to catch.
* **The Expected Result bar:** could a person with no access to the code disagree with the tester
  about whether it passed? If yes, rewrite it. "Moves smoothly" fails; "within 500ms", "403
  Forbidden shown", "row disappears from the list" pass. This is step 6 item 3 applied to a reader
  who can't fall back on reading the implementation — an AC that survives here is testable in a
  stronger sense than one that only survives the spec's own review.
* **Test Data holds literal values**, never "valid input".
* **A row nobody intends to automate is marked `Manual` with a reason** — an unmarked row and a
  deliberately-manual one are indistinguishable otherwise.
* **Runtime Invariants get a row only where the violation is observable from outside.** One
  detected by an internal assertion has no black-box row; say so rather than inventing one.

An id you cannot write a row for is a finding, not a rounding error: either the AC isn't testable
(fix it in step 1) or it's genuinely internal (say which, in **Open Items**).

**Run the two-direction check before you call the table done — don't eyeball it.** Step 6 item 5's
standard applies here too, and this is the one claim in the whole skill you can settle with a
command:

```bash
python3 - <<'PY'
import re, csv
from pathlib import Path
d = Path("<run-folder>")
ids = set(re.findall(r"\b(?:AC|BR|EC|DS)-\d+\b", (d / "0-spec.md").read_text()))
refs = set()
for row in csv.DictReader((d / "acceptance-tests.csv").open(newline="")):
    refs |= set(re.findall(r"\b(?:AC|BR|EC|DS)-\d+\b", row["Source Ref"] or ""))
print("uncovered:", sorted(ids - refs), "| unresolved:", sorted(refs - ids))
PY
```

Both lists empty, or every remaining entry explained in **Open Items** — nothing else counts as
done. Measured on this skill's own first real run: the check found six ids whose rows existed but
whose `Source Ref` named only the AC and not the edge case it also covered — invisible to reading,
obvious to the command. Use `csv.DictReader`, never `cut -d,` or `split(",")`: a quoted cell
containing a comma silently truncates under both, and a coverage gate that always passes is worse
than no gate.

**Never write a concrete id number in prose that isn't a real reference — use the placeholder form
`AC-<n>` instead.** A sentence describing a *fixture* ("a spec with ids AC-1, AC-2, BR-1") is
indistinguishable from a definition to the check above: the same run reported a business-rule id
that existed nowhere but inside one AC's own example text, on a spec with `needs_ba: false`.
**Backticks do not help** — the regex sees inside code spans, so quoting a phantom id leaves it just
as visible; only changing the digits to `<n>` removes it. Confirmed by re-running the check after
wrapping one in backticks: still reported. The cost of the convention is nothing; the cost of
skipping it is a phantom id that gets either a fabricated test row or an Open Item explaining a
non-problem.

### 8. Write both files

`0-spec.md` — every section step 3 produced content for folded in under its own heading below, no
separate `ba.md`/`design.md`/`sa.md`/`1-plan.md`. Plus `acceptance-tests.csv` from step 7.

---

## Output: `0-spec.md` + `acceptance-tests.csv`

Default: `<repo>/workflows/runs/<feature-id>/` (next to `kestra-build`'s output). Ask if the
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
* **EC-1 — [edge case]:** [how it's handled]
* **EC-2 — [failure mode]:** [expected behaviour]

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
* [ ] **AC-1:** [testable, measurable — includes design ACs; Given-When-Then for behavioral ACs]

## AC Coverage Map
| AC | Covered by (files/steps) | Test rows |
|----|--------------------------|-----------|
| AC-1 | [file(s) / step] | TC-001, TC-002 |

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

### `acceptance-tests.csv`

Header, exactly — column order is load-bearing, `kestra-build`'s `generate-tests` reads it
positionally:

```
Test Case ID,Source Ref,Module/Feature,Test Case Title,Preconditions,Test Steps,Test Data,Expected Result,Priority,Test Type,Automation
```

| Column | Rule |
|---|---|
| Test Case ID | `TC-NNN`, append-only — never renumber an existing row |
| Source Ref | a real id from the spec: `AC-3`, `BR-1`, `EC-2`, `DS-1` |
| Test Case Title | what is being proven, action-shaped — not "test the cancel button" |
| Preconditions | exact state to set up, with concrete records/ids |
| Test Steps | numbered, executable by someone who has never seen the feature |
| Test Data | literal values |
| Expected Result | observable and decidable without reading the code |
| Priority | High (core) / Medium (supporting) / Low |
| Test Type | Functional / Security / Performance / Usability |
| Automation | `Auto`, or `Manual — [reason]` |

Execution results never come back into this file — it's the approved contract. They belong in a
separate `acceptance-results.csv` (`Test Case ID,Actual Result,Status,Tester Name,Execution
Date,Comments`), written at run time, joined on Test Case ID.

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
- Every AC, BR, edge case, and design state carries an id, and every id appears in at least one
  row of `acceptance-tests.csv` — or is named in **Open Items** as observable-from-inside-only
- Every `Source Ref` in the table resolves to an id that exists in `0-spec.md`
- **Step 7's two-direction check was actually run**, output pasted — not asserted from reading
- No silent gaps — unresolved → **Open Items**

Non-empty **Open Items** → say so plainly at handoff.

## Handoff

→ **A human, first.** `acceptance-tests.csv` is the artifact they sign off — this is the approval
point that keeps the generated workflow free of a mid-run `human_approval` stop. Say plainly that
approving it freezes what will be tested, and that a change after `kestra-build` runs costs a
`reworking` bounce rather than an edit.

→ Then `kestra-build`, which reads `0-spec.md` directly and can skip straight to deriving stages.
Its `generate-tests` brief translates each approved row 1:1 into test code with the Test Case ID
embedded in the test name, so coverage stays checkable by grep — and it generates **no**
`design-tests` stage, since the approval already happened here.

**If the spec changes after approval** — `spec-review` rewording an AC, a new edge case — the table
is stale the moment an id it references changes meaning. Regenerate the affected rows and get them
re-approved rather than letting the two drift; the ids are what make the drift detectable at all.
