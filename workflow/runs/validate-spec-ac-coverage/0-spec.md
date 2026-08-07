# [validate-spec-ac-coverage] Spec — validate_spec.py checks the acceptance-tests.csv contract

> Status: READY_FOR_BUILD | Created: 2026-08-04 | Next: kestra-build

---

## Overview
Extend `validate_spec.py` to mechanically check the id↔row contract between `0-spec.md` and the
`acceptance-tests.csv` that `kestra-spec` now emits, so a coverage gap is caught before spec-review
spends a turn on it.

## Problem Statement
* `kestra-spec` now emits two files; nothing mechanically checks they agree.
* Its stopping rule requires every AC/BR/EC/DS id to appear in ≥1 CSV row and every `Source Ref` to
  resolve — both currently self-attested by the same pass that wrote them.
* Goal: `validate_spec.py` reports both directions, FAILing only where the report is both certain
  and fixable in scope; every other outcome WARNs, exit 0.

## Functional Requirements
* [ ] New check runs after the existing three, from the same `main()`, same capturing-print
  mechanism — no change to existing check behaviour or output.
* [ ] CSV located as `acceptance-tests.csv` in the spec file's own directory. Not found → one WARN,
  check skipped.
* [ ] Spec ids harvested by regex `\b(?:AC|BR|EC|DS)-\d+\b` over the whole spec text.
* [ ] CSV parsed with stdlib `csv.DictReader` — never `str.split(",")`.
* [ ] Forward direction: spec id with no row → report.
* [ ] Reverse direction: `Source Ref` value naming no spec id → report.
* [ ] Optional third arg overrides the CSV path; absent → sibling-of-spec default.
* [ ] Script stays dependency-free and runnable under a plain `python3`.

## Edge Cases & Error States
* **EC-1 — CSV absent:** WARN `no acceptance-tests.csv found beside the spec — skipping coverage
  check`, exit unchanged. Foreign specs and pre-convention specs must keep passing.
* **EC-2 — Spec has no ids at all:** WARN, skip both directions. Verified real, not hypothetical:
  the repo's only existing spec has three `BR-<n>` ids and zero `AC-`/`EC-` ids.
* **EC-3 — CSV present but empty or header-only:** WARN `acceptance-tests.csv has no data rows`,
  skip. Distinguished from EC-1 so "file forgotten" and "file started but unfilled" don't collapse.
* **EC-4 — CSV missing the `Source Ref` column:** WARN naming the columns actually seen, skip the
  reverse direction. Never FAIL — a foreign table may use another header.
* **EC-5 — Malformed CSV (`csv.Error`, unbalanced quotes):** WARN with the exception text, skip.
  Never crash — a traceback from a pre-check reads as a broken gate, not a spec defect.
* **EC-6 — Duplicate `Test Case ID`:** WARN. Not FAIL: harmless to the coverage question itself,
  but it silently breaks the grep-by-TC-id coverage gate `generate-tests` installs downstream.
* **EC-7 — A `Source Ref` cell holding several ids** (`AC-1, AC-2`): every id in the cell counts as
  covered. Splitting is by the same id regex, not by comma — a cell is free-text, not a list.
* **EC-8 — Id referenced only in prose, never defined** (e.g. `AC-9` inside a Risks paragraph, with
  no `AC-9` bullet): indistinguishable from a definition by regex alone. Counts as defined; a
  reverse-direction FAIL therefore cannot fire on it. Stated so the limit is known, not discovered.

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|---|---|---|
| A FAIL is only ever emitted for a fact fixable inside spec-review's own `write_scope` | Review-time, not runtime: only the two conditions in AC-3/AC-4 call `fail()`; every other branch calls `warn()` | Refuse — a FAIL outside that scope makes the gate unfixable and the run escalates to `reworking` with no legal fix |
| The script never raises out of `main()` | Every new parse path wrapped; `csv.Error`/`OSError`/`UnicodeDecodeError` → WARN | Refuse to crash — WARN and exit 0; an unhandled traceback is a broken gate, not a spec verdict |
| Exit code stays 0 whenever only WARNs were emitted | Existing `had_fail` capture in `main()`, unchanged | Halt: any regression here fails every foreign-format spec, blocking runs the docstring promises to allow |

## Codebase Survey
* Explored: `workflow/kestra-build/scripts/validate_spec.py` (all 176 lines),
  `workflow/kestra-build/scripts/validate_workflow.py`, `workflow/kestra-build/SKILL.md` (Inputs,
  spec-review, generate-tests bullets), `workflow/kestra-spec/SKILL.md` (steps 7–8, output section),
  `workflow/runs/order-cancellation-refund/{0-spec.md,workflow.yaml}`.
* Integrate with: `fail()`/`warn()` helpers; `get_section()`/`parse_table_rows()` for Markdown;
  one `check_*(text, ...)` function per concern, called from `main()` inside the existing
  capturing-print block. No new module.

## Reality Constraints

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|---|---|---|---|
| `csv` (stdlib) | `DictReader` needs a header row; file opened `newline=""` per stdlib docs | `dict[str, str \| None]` per row; missing trailing cells → `None`, extra cells → `restkey` list | That every row has every key; that values are stripped; that a ragged row raises rather than silently yielding `None` |
| `re` (stdlib) | none | `findall` → `list[str]`, empty list when no match | Nothing about whether a matched id was *defined* vs merely mentioned (EC-8) |
| `pathlib.Path` | none | `.parent` of a bare filename is `.`, not the cwd string | That `spec_path.parent / "acceptance-tests.csv"` is inside the repo root — the two args are independent |
| Existing `validate_spec.py` behaviour | new checks run after the current three | Prints `FAIL:`/`WARN:` lines; exit 1 iff any FAIL | That callers parse anything but the exit code — `exit_criteria.run` chains it with `&&` |

### Paths that must agree
* `validate_spec.py`'s CSV-coverage verdict ↔ `kestra-spec`'s step-7/stopping-rule self-check —
  equivalent means: same two directions over the same id set · may differ: the script counts a
  prose-only mention as a definition (EC-8) and cannot judge whether a row's Expected Result is
  decidable, which stays `kestra-spec`'s and spec-review's judgment.
* Confirmed non-agreement, deliberate: `generate-tests`'s downstream `cut -d,`-based TC-id gate
  parses the same CSV **more weakly**. Executed: on `"TC-001, note",AC-1,x`, `cut -d, -f1` yields
  `"TC-001` while `csv.reader` yields `TC-001, note`. This script must not adopt `cut`'s behaviour
  to match it; EC-6's duplicate WARN is the compensating signal.

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|---|---|---|
| Filesystem | pinned — `tmp_path` fixtures, never the real repo | The repo's own specs change; a test reading them would break on unrelated edits |
| Clock / randomness / locale / network | not read | Pure text processing, no I/O beyond reading the two files |
| Text encoding | pinned — UTF-8 fixtures, one explicit invalid-byte case | `read_text()` default is platform-dependent; a decode error must WARN, not crash (EC-5) |

## Files to Touch
| File | Change | Verified? | Why |
|---|---|---|---|
| `workflow/kestra-build/scripts/validate_spec.py` | edit | exists | The new checks and their `main()` wiring |
| `workflow/kestra-build/SKILL.md` | edit | exists | spec-review's `write_scope` must cover the CSV (see Risks) |
| `workflow/kestra-build/scripts/test_validate_spec.py` | new | follows pattern at `workflow/kestra-build/scripts/validate_workflow.py` (stdlib-only, no pytest dependency assumed) | No test file exists for either script today |

## Dependencies
* none — stdlib only, no new packages, no migrations.

## Acceptance Criteria
* [ ] **AC-1:** **Given** a spec declaring three ids of mixed kinds (two `AC-<n>`, one `BR-<n>`)
  and a CSV whose rows reference all three **When** the script runs **Then** no `FAIL:` or `WARN:`
  line mentions coverage, and exit is 0.
* [ ] **AC-2:** **Given** a spec directory with no `acceptance-tests.csv` **When** the script runs
  **Then** exactly one WARN naming the missing file is printed and exit is 0.
* [ ] **AC-3:** **Given** spec ids `AC-1, AC-2` and a CSV referencing only `AC-1` **When** the
  script runs **Then** a `FAIL:` line names `AC-2` specifically and exit is 1.
* [ ] **AC-4:** **Given** a CSV row whose `Source Ref` is `AC-7`, absent from the spec **When** the
  script runs **Then** a `FAIL:` line names `AC-7` and its `Test Case ID`, and exit is 1.
* [ ] **AC-5:** **Given** a spec containing no `AC-`/`BR-`/`EC-`/`DS-` id at all, with a CSV present
  **When** the script runs **Then** a WARN says the spec carries no ids, no coverage FAIL is
  emitted, and exit is 0.
* [ ] **AC-6:** **Given** a CSV whose bytes are not valid UTF-8, or whose quoting is unbalanced
  **When** the script runs **Then** a WARN carries the error text, no traceback reaches stderr, and
  exit is 0.
* [ ] **Given** the existing `order-cancellation-refund` spec, unmodified, with no CSV beside it
  **When** the script runs **Then** its output is byte-identical to today's apart from the single
  EC-1 WARN line, and exit is 0. *(AC-7)*
* [ ] **AC-8:** **Given** a CSV with two rows both `TC-004` **When** the script runs **Then** a WARN
  names `TC-004` as duplicated and exit is 0.
* [ ] **AC-9:** **Given** a CSV whose header lacks `Source Ref` **When** the script runs **Then** a
  WARN lists the headers actually found, no reverse-direction FAIL is emitted, and exit is 0.
* [ ] **AC-10:** **Given** a CSV row whose `Source Ref` cell reads `AC-1, AC-2` **When** the script
  runs **Then** both ids count as covered and neither appears in a FAIL.

## AC Coverage Map
| AC | Covered by (files/steps) | Test rows |
|---|---|---|
| AC-1 | `check_ac_coverage()` happy path | TC-001 |
| AC-2, EC-1 | CSV-locate branch | TC-002 |
| AC-3 | forward direction → `fail()` | TC-003 |
| AC-4 | reverse direction → `fail()` | TC-004 |
| AC-5, EC-2 | id-harvest guard | TC-005 |
| AC-6, EC-5 | parse-error guard | TC-006, TC-007 |
| AC-7 | regression over the real spec | TC-008 |
| AC-8, EC-6 | duplicate scan | TC-009 |
| AC-9, EC-4 | header guard | TC-010 |
| AC-10, EC-7 | multi-id cell | TC-011 |
| EC-3 | header-only guard | TC-012 |
| EC-8 | documented limit | TC-013 |

## Risks & Watch-outs
* **spec-review's `write_scope` is the load-bearing risk.** A FAIL is only legitimate if the fix is
  in scope. `SKILL.md:438` says spec-review's `write_scope` covers `source_spec`; the one real
  workflow in the repo (`order-cancellation-refund/workflow.yaml:30`) gives it `write_scope: []` —
  verified, they disagree today. AC-3/AC-4 FAILs are unfixable under either unless the CSV is added
  to that scope, so the `SKILL.md` edit in Files to Touch is part of this feature, not a follow-up.
* Two parsers now read one CSV at different strengths (see Paths that must agree) — a row that
  passes here can still fail the downstream `cut`-based gate.
* Regex id-harvest over the whole document counts prose mentions as definitions (EC-8). Observed on
  this spec's own first draft: AC-1's fixture text named a literal business-rule id on a
  `needs_ba: false` spec, and the check reported it as uncovered. Rewriting it as `BR-<n>` cleared
  it — backticks alone did not, since the regex reads inside code spans —
  which is why the FAIL-worthy direction is the reverse one (a `Source Ref` naming nothing), never
  the forward one.

## Out of Scope
* Judging Expected-Result quality, `Automation` values, or step executability — human/`spec-review`.
* Fixing `generate-tests`'s `cut -d,` gate to use a real CSV parser — a separate change to
  `kestra-build`'s brief, worth doing, not bundled here.
* Any `acceptance-results.csv` handling.

## Flags
* `needs_ba`: false — one mechanical contract, no domain rules or stakeholder variation.
* `needs_ui`: false — CLI script, stdout only, no page/route/interactive element.
* `needs_sa`: false — one file, stdlib only, no service boundary or competing architecture.
* `needs_devops`: false — no env var, migration, flag, or infra.

## Open Items
* **EC-8 is unresolved, deliberately.** Distinguishing a defined id from a mentioned one needs
  section-scoped parsing (harvest definitions only from Acceptance Criteria / Business Rules /
  Edge Cases / Design Notes bodies) — cheap to add, but it changes what a foreign-format spec
  yields, and the FAIL discipline says a format-dependent rule can't drive a FAIL. Left as a
  documented limit; revisit only with a second real spec shape to test against.
