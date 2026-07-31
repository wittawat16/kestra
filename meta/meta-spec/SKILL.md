---
name: meta-spec
description: >
  Writes a lean, build-ready spec for the meta/ role library — testable acceptance criteria,
  the needs_ui / needs_devops / tests_first flags, edge cases, a verified codebase survey, and
  explicit out-of-scope — in one short pass, one file. Deliberately lighter than kestra-spec:
  no runtime-invariant table, no reality-constraints matrix, no execution-verified self-check.
  Trigger on "write a spec for this", "turn this idea into acceptance criteria", "spec this out
  before we build", "what are the ACs for this feature", or as meta-orc's first stage. If the
  work carries silent-failure risk, multi-service contracts, or test doubles whose fidelity
  matters, escalate to kestra-spec instead — this skill says so itself rather than pretending
  the lighter pass covers it.
---

# meta-spec — Lean Spec for the meta/ Chain

**Role:** Get from a rough ask to acceptance criteria someone can actually build and test
against, fast — without the ceremony `kestra-spec` needs to feed a mechanically-enforced stage
machine. One pass, one file.

The spec role in the `meta/` library. Feeds [`meta-designer`](../meta-designer/SKILL.md),
[`meta-test-writer`](../meta-test-writer/SKILL.md), and [`meta-dev`](../meta-dev/SKILL.md),
and is [`meta-orc`](../meta-orc/SKILL.md)'s first stage when no spec exists yet.

---

## When this is the wrong tool — check first, it takes one read

`meta-spec` is lighter because it assumes a human reviews the result downstream and the blast
radius of a miss is small. Escalate to [`kestra-spec`](../../workflow/kestra-spec/SKILL.md) when
any of these hold, and say which one:

* **Silent failure is possible** — a condition could go false and the system carry on, with
  nobody finding out until damage is done. That's what `kestra-spec`'s Runtime Invariants table
  exists for, and there's no lightweight substitute.
* **Test doubles whose fidelity matters** — a faked external dependency where "what it does *not*
  guarantee" is the interesting question. `kestra-spec`'s Reality Constraints feeds
  `meta-test-review`; without it, that review has no standard to judge against.
* **2+ services, or a decision with lasting architectural consequence** — approach comparison and
  integration contracts belong in a spec that has room for them.

None of those → this skill is the right size. Deciding by reflex that "more spec is safer" costs
a longer pass on every small feature, which is the exact overhead `meta/` exists to avoid.

---

## Process — one sitting

### 1. Sharpen into testable acceptance criteria

Each AC must be checkable without a follow-up question. "Users can filter" is not an AC;
"filtering by status returns only matching rows, and an empty result renders the empty state" is.
Add the error states and edge cases the ask didn't mention — that omission is the normal case,
not a sign the requester was careless.

**Use Given-When-Then for any AC that describes behavior under a condition.** It forces each
branch onto its own visible line instead of hiding inside prose, and if `tests_first` is on,
`meta-test-writer` maps those scenarios 1:1 into test code — so the shape you write here is the
shape the suite takes. Plain bullets are fine for data-shape and performance ACs.

Anything genuinely unresolved goes to **Open Items** rather than getting a confident guess.
Anything deliberately excluded goes to **Out of Scope** — an unstated exclusion reads as an
oversight to whoever builds this.

### 2. Set the flags — mechanically, no re-litigating

| Flag | True when | Consequence in `meta-orc` |
|---|---|---|
| `needs_ui` | any new/changed page, route, modal, form, or interactive element — a single added button qualifies | `meta-designer` runs first |
| `needs_devops` | new/changed env vars, migrations, feature flags, or infra | `meta-devops` runs at the end |
| `tests_first` | **the caller asked** for tests-first / BDD / TDD | `meta-test-writer` runs before `meta-dev` |

Note what does *not* set `tests_first`: your own ACs coming out as Given-When-Then. Step 1 tells
you to write them that way whenever a condition is involved, so treating that as a signal would
make the flag true on nearly every spec — a default dressed up as a derivation. GWT here is house
style; the flag tracks whether the caller wants to pay for an extra stage, which only they can
say. (Elsewhere the reasoning differs: when ACs arrive already in GWT form from *another* author,
that genuinely is intent, because that author chose the form freely.)

If you think the work would benefit from tests-first, say so as a recommendation alongside the
flag rather than setting it — the difference between "I recommend this" and "this is required" is
information the caller needs to keep.

These are read off the feature, not judged for proportionality. "It's only one button, a design
stage is overkill" is exactly the reasoning the mechanical rule exists to prevent — the
downstream skill decides how much effort the stage deserves; this one only reports what's true.

For `needs_ui`, name the four screen states per view (empty / loading / success / error) as ACs.
If one is genuinely impossible for a view, say why — don't drop it silently.

### 3. Survey the codebase and verify every path

Read the real code in each area this touches before naming files. **Every path in Files to Touch
gets verified to exist** (`ls`/read it) — a spec that sends the implementer to a file that isn't
there costs more than it saved. New files name the existing file they're patterned after.

Every AC must map to at least one file or step. An AC with no landing place is either
underspecified or out of scope, and finding out which is cheaper now than during implementation.

### 4. Self-check before handing off

- Every AC testable without a follow-up question
- Every Files-to-Touch path verified, or marked as new with a named pattern to follow
- Every AC maps to at least one file/step
- Flags set, with a reason each
- Escalation check from the top of this file done, with its answer stated
- Unresolved → **Open Items**, not a guess

---

## Output: `0-spec.md`

Default location `<repo>/workflows/runs/<feature-id>/0-spec.md`, or wherever the repo already
keeps specs — ask if there's an existing convention.

```markdown
# [<feature-id>] Spec — <feature title>

> Status: READY | Created: YYYY-MM-DD | Next: meta-orc (or meta-designer / meta-test-writer)

## Overview
[one line: what this delivers and why]

## Acceptance Criteria
* [ ] [testable — Given-When-Then for behavioral ACs, plain bullet for data/perf ACs]

## Edge Cases & Error States
* **[edge case]:** [how it's handled]

## Screen States  *(only if needs_ui)*
| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|

## Codebase Survey
* Explored: [dirs/files actually read]
* Follow these patterns: [existing modules/conventions to match]

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|

## AC Coverage Map
| AC | Covered by |
|----|------------|

## Dependencies
* [new packages / migrations — or "none"]

## Flags
* `needs_ui`: [true|false] — [reason]
* `needs_devops`: [true|false] — [reason]
* `tests_first`: [true|false] — [reason]

## Escalation Check
* [none of kestra-spec's triggers apply — or: escalate because <which one>]

## Out of Scope
* [explicitly excluded]

## Open Items
* [unresolved — or "none"]
```

---

## Mindset

- **Lean is the point, not a compromise.** Every section here earns its place by being something
  a downstream stage actually reads. Adding a section "for completeness" makes this
  `kestra-spec` with extra steps.
- **Verified beats plausible.** A file path you didn't check is a guess wearing a spec's
  authority. Checking costs seconds.
- **Honest about its own ceiling.** The escalation check is not a formality — a spec that quietly
  under-covers silent-failure risk is worse than no spec, because it looks like due diligence
  was done.
- **Open Items are a feature.** An honest unknown survives review; a confident wrong answer
  becomes a test, then an implementation, then a bug.

## Handoff

→ [`meta-orc`](../meta-orc/SKILL.md), which reads the flags and resolves the stage list, or
directly to `meta-designer` / `meta-test-writer` / `meta-dev` when driving stages by hand.
Non-empty **Open Items** → say so plainly at handoff rather than letting it be discovered later.
