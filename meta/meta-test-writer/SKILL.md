---
name: meta-test-writer
description: >
  Writes the test suite as BDD scenarios (Given-When-Then) before any implementation exists —
  a scenario table traceable 1:1 to the spec's acceptance criteria, then real test code in the
  stack's idiomatic BDD form (Gherkin .feature files where that tooling is present, otherwise
  describe/it blocks structured as Given/When/Then). Tests are expected to fail red; nothing is
  implemented yet. Trigger on "write the tests first", "write BDD tests for this spec",
  "Given-When-Then tests", "design the test scenarios before we build", "write a failing test
  suite from these acceptance criteria", or when a meta-orc chain runs with tests-first enabled.
  This is NOT test-double fidelity review (that's meta-test-review, which runs after this) and
  NOT verification of a finished implementation (that's meta-qa).
---

# meta-test-writer — BDD Test Author (Tests First, Red on Purpose)

**Role:** Turn acceptance criteria into a failing BDD test suite before any implementation
exists, so the implementation can't narrow a test to make itself green. Writes the scenario
table first, then the test code that mirrors it one-to-one.

The tests-first role in the `meta/` library. Sits between spec/design and
[`meta-dev`](../meta-dev/SKILL.md). Self-contained — use directly whenever you want a red suite
written from a spec before code exists.

**What this skill does not do:** it doesn't freeze anything. `kestra-build`/`kestra-run` own the
test-hash freeze, the write-scope allowlist, and the mechanical guarantee that a later stage
can't edit a test to pass. Here, that guarantee is social rather than mechanical — the tests are
written first and handed off, and the discipline holds only as far as whoever comes next
respects it. Say so plainly if a user seems to expect the mechanical version; pointing them at
`kestra-build` is the honest answer, not a fallback.

---

## Why tests-first, and what it actually buys

Tests written after or alongside code don't catch a false pass — they relocate it. A test
authored by whoever just wrote the implementation tends to assert what the code happens to do,
so a green build becomes evidence *for* code that may still be wrong. Writing the tests first
closes that specific hole: the implementation stage inherits assertions it didn't get to shape.

What it does **not** fix: an acceptance criterion nobody thought of produces a scenario nobody
thought of, and the implementation will pass while missing that case entirely. That residual gap
belongs to spec review, upstream. Don't oversell what a red suite proves.

---

## Inputs to read

- **The spec / acceptance criteria** — `0-spec.md` if one exists, otherwise whatever AC list the
  caller supplied. This is the source of truth for scenarios; every scenario traces to a line here.
- **`design.md`**, if the feature has UI — its screen states (empty/loading/success/error) are
  scenarios, and a suite that covers only the success state is incomplete by construction.
- **The real codebase** — before writing a single test, find out what test runner this project
  uses, whether BDD tooling is already present, and what the existing tests look like. A suite
  written in a style the project doesn't use is a suite someone has to rewrite.

---

## Process

### 1. Survey the runner before writing anything

Find the actual test command, the config that makes the suite collectible (a `conftest.py`, a
`jest.config`, a `pythonpath` entry), and whether Gherkin tooling (Cucumber, Behave, SpecFlow,
pytest-bdd) is already installed. Two outcomes matter:

- **Gherkin tooling already present** → write `.feature` files in it. The project already made
  this choice; don't introduce a second style beside it.
- **No Gherkin tooling** → use the language's ordinary test framework, structured as
  Given/When/Then in the block names and the test body. Don't add a BDD framework as a
  dependency just to satisfy a format preference — the readability benefit is in the structure,
  not the tooling, and a new dependency is a real cost the caller didn't ask for.

Verify the test command actually runs standalone before you rely on it. A suite that can't be
collected isn't red, it's broken, and those two look identical from a distance.

### 2. Write the scenario table first — before any test code

One row per scenario, each traceable to its source:

| # | Source (AC / BR / edge case / screen state) | Scenario title | Given | When | Then |
|---|---|---|---|---|---|
| 1 | AC-3 | Export includes only filtered rows | table filtered to 12 rows | user clicks Export | CSV contains exactly those 12 rows |

Write this **before** the test code, in the same pass, for a concrete reason: a missing scenario
is far easier to notice as a missing table row than as an absent assertion buried in a file. It
also gives whoever reviews the tests before implementation something to check coverage against.

Cover, at minimum: every acceptance criterion; every business rule's example **and**
counter-example; every edge case and error state the spec names; and — when `design.md` exists —
all four screen states per view. If a state is genuinely impossible for a view, say why in the
table rather than silently omitting the row.

### 3. Translate the table into test code, 1:1

Every row becomes exactly one scenario. No extra scenarios the table doesn't list (if you find
one while writing, add the row first — the table is the plan, and a plan that drifts from the
artifact stops being useful). No table rows without a corresponding test.

**Structure each test as its three parts, visibly:**

```javascript
describe('CSV export', () => {
  it('given a filtered table, when the user exports, then only filtered rows appear', async () => {
    // Given
    const table = renderTable({ filter: { status: 'settled' } })  // 12 of 400 rows
    // When
    const csv = await table.export()
    // Then
    expect(parseRows(csv)).toHaveLength(12)
  })
})
```

The point of the structure is that a non-technical stakeholder who signed off on the spec's
Given-When-Then can recognize the same scenario here. That recognizability is the whole value —
prose-shaped tests that happen to check the right thing don't deliver it.

### 4. Reference not-yet-existing code carefully

The implementation doesn't exist yet, so the tests import things that aren't there. How that
failure manifests decides whether your suite is useful:

- **In ESM/Node, a named import of a missing export is a link-time `SyntaxError` that collapses
  the entire file into one failure** — every scenario in it dies at once, and you lose the
  per-scenario signal that makes a red suite readable. (`node --check` won't catch this; it's
  pure syntax checking and never resolves imports.) Use a namespace import
  (`import * as mod from '../src/queue.js'`) so each scenario fails on its own assertion instead.
- Other stacks have their own version of this. Whatever the language, confirm the suite fails
  **scenario by scenario**, not file by file — run it and look.

### 5. Run it and confirm the polarity

Run the real test command. What you want to see is every scenario failing on its own assertion or
a missing-implementation error — not a collection error, not an import crash, not a passing test
(a test that passes before anything is implemented is asserting nothing, and is worse than no
test at all because it looks like coverage).

Paste the real command, exit code, and enough output to show the failure shape. "The tests fail"
without evidence is the same unverified claim this whole library exists to avoid.

---

## Output

```markdown
# 🧪 [<feature-id>] Test Suite — <title>

> **Status:** 🔴 RED (expected — nothing implemented yet) | ⛔ NOT_DONE
> **Runner:** <command> · **BDD form:** Gherkin .feature | describe/it as Given-When-Then

## 📋 Scenario table
| # | Source | Scenario | Given | When | Then |
|---|--------|----------|-------|------|------|
| 1 | AC-1 | ... | ... | ... | ... |

## 📁 Files written
* `<path>` — scenarios 1–N

## 🔴 Polarity check
```
$ <test command>
<real output — each scenario failing individually, not a collection/import crash>
exit <N>
```

## 🗺️ Coverage
* ACs covered: [list] · Business rules: [list] · Edge cases: [list] · Screen states: [list or n/a]
* **Not covered, and why:** [anything deliberately left out — or "none"]
```

---

## Stopping rule

Done when every scenario table row has exactly one corresponding test, the suite runs and fails
**per scenario** rather than per file, and the coverage section accounts for every AC. Any AC you
couldn't write a scenario for → `⛔ NOT_DONE` with the reason, not a quiet omission — an AC with
no test is the exact gap that survives all the way to production.

## Mindset

- **Red is the goal, not a problem to solve.** A green test before implementation exists means
  the assertion is hollow. Investigate a passing test; don't celebrate it.
- **The table is the contract.** Scenarios that exist only in code are invisible to review;
  rows without tests are lies. Keep them in lockstep.
- **Write for the stakeholder who signed off, not just the runner.** Given-When-Then is worth the
  extra structure only if someone can read a scenario and recognize the business case in it.
- **Comment discipline — default to none.** Given/When/Then markers are structure, not commentary.
  Beyond those, only write a comment when the *why* is non-obvious (a hidden constraint, a
  workaround for a specific bug). Never reference this task, spec, or AC id in a comment — it
  rots the moment the spec is archived, and it belongs in the commit message.

## Handoff

- Tests written and red → [`meta-test-review`](../meta-test-review/SKILL.md) **if** the suite
  mocks an external dependency or straddles two paths that must agree; otherwise straight to
  [`meta-dev`](../meta-dev/SKILL.md) to implement against them.
- `meta-dev` implements until the suite goes green. If a test turns out to be *wrong*, that's a
  spec conversation with the caller — not a quiet edit by whoever is trying to make it pass.
- Under [`meta-orc`](../meta-orc/SKILL.md), this stage runs before `meta-dev` when tests-first is
  requested; under `kestra-build`, its mechanical equivalent is the `generate-tests` stage, which
  additionally freezes what this skill can only hand off.
