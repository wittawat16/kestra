# kestra-spec (minimal / ablated)

Goal: turn the attached sharpened idea into one `0-spec.md` file that `kestra-build` can consume
directly, with no gaps it would have to guess at.

Do the real work yourself, in one pass, before writing the file:
- Sharpen every requirement into an acceptance criterion testable without a follow-up question.
  Use Given-When-Then for behavior-under-a-condition ACs. Mark genuine unknowns as Open Items.
- Decide needs_ba / needs_ui / needs_sa / needs_devops for this feature. For any that are true, do
  that work for real inline (business rules with example + counter-example, design notes, or
  architecture tradeoffs) — not a stub.
- Actually read the target codebase before naming any file or behavior. Verify every file path you
  write down actually exists.
- Name this feature's runtime invariants — conditions that must hold forever, against inputs nobody
  predicted. For each: what's actually checked, where, and what happens on violation. "Logged, then
  continues" does not count as handling it.
- Name what the world doesn't guarantee: what each external dependency actually promises (and
  doesn't), any pair of code paths that must stay consistent with each other, and which
  non-deterministic inputs (clock, randomness, network, filesystem, env) this feature touches and
  whether they're pinned.
- Before writing the final file, check your own invariants against your own edge cases/ACs for
  contradictions, and confirm every claim about what the code/dependencies do came from actually
  reading or running something — not assumption. Fix what you find, or list it under Open Items.

Guardrails: never invent a file path you haven't verified. Never write an AC without its exact
inputs. An honest Open Item beats a confident guess. Write dense — bullet fragments over full
sentences — this file gets pasted whole into every later stage's context, so cut narration, never
cut a fact.

Write the output as `0-spec.md` using exactly this structure:

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

Default output path: `<repo>/workflows/runs/<feature-id>/0-spec.md`, next to where `kestra-build`
would look for it — but for this run, write it to the exact path you're told in the task instead.
