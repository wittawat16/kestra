# 0-spec — `tally --refund`

*(Fixture spec for the Wave-3 `kestra-exam` eval. Grown Wave-2 shape: plain headings, an
`## External Interface` section, and an `## AC Coverage Map` with a `Source` column. **Standalone
deliberately** — no `> Spec-ticket:` preamble line — so the eval exercises `exam_anchor.py`'s
standalone raise-subject fallback.)*

> Delimiter precondition: every requirement-surface section below uses `### ` for subsections, so no
> bare `## ` truncates the surface.

## Overview

`src/tally.py` sums the `amount` column of a CSV and prints one line. Refunds are stored in the same
file with `type=refund` and are currently added like every other row, so a month with refunds reads
high. This feature adds an opt-in `--refund` flag that subtracts refund rows, and makes a malformed
amount a refusal instead of a traceback.

## Problem Statement

Two failures, both silent today. A refund inflates the tally rather than reducing it, and a
non-integer amount aborts with a Python traceback whose exit code is indistinguishable from a usage
error — so a caller cannot tell "you passed the wrong flag" from "row 3 of your data is broken".

## Mode Prediction

kestra-build mode: `full` — three interacting behaviors (a flag, an arithmetic change, a refusal
path) with an exit-code contract; the ceremony costs less than one wrong tally.

## Functional Requirements

- FR-1 `tally.py <csv>` prints exactly one line, `total: <sum>`, on stdout and exits 0.
- FR-2 `tally.py --refund <csv>` subtracts the `amount` of every row whose `type` cell is `refund`,
  and adds every other row.
- FR-3 A row whose `amount` cell is not an integer is refused: exit code 2, with a diagnostic on
  stderr naming the file line number of the offending row.
- FR-4 An option the CLI does not define is refused with the usage line on stderr and exit code 1.
- FR-5 The tally goes to stdout; every diagnostic goes to stderr. The two streams are never mixed.

## Edge Cases & Error States

- A CSV with a header and no data rows tallies `total: 0` and exits 0.
- `--refund` against a CSV with no `type` column behaves as if no row were a refund.
- A refund row is subtracted exactly once even when `--refund` is passed twice.
- An amount with surrounding whitespace is accepted; an empty amount cell is a malformed amount.

## Runtime Invariants

- The input file is opened read-only; the process never writes to it.
- A refusal leaves stdout empty — no partial `total:` line is printed before an error.
- The tally is computed in a single streaming pass; resident memory does not grow with row count.

## External Interface

The only seam this feature exposes is the command line:

```
python3 src/tally.py [--refund] <csv-path>
  stdout : exactly one line, `total: <integer>`, on success
  stderr : diagnostics only
  exit   : 0 success · 1 usage error (missing/unknown option, wrong argument count)
           2 malformed input data
  cwd    : the repository root; sample inputs live at `data/*.csv`
```

Sample inputs committed with the CLI, and part of the seam a test may drive:
`data/mixed.csv` (3 rows: sale 100, refund 30, sale 20) and `data/bad.csv` (a non-integer amount on
file line 3).

## Acceptance Criteria

- **AC-1** — *Given* `data/mixed.csv`, *when* `tally.py --refund data/mixed.csv` runs, *then* stdout
  carries `total: 90` and the exit code is 0.
- **AC-2** — *Given* `data/bad.csv`, *when* `tally.py data/bad.csv` runs, *then* the exit code is 2
  and stderr names file line 3.
- **AC-3** — *Given* `data/mixed.csv`, *when* `tally.py data/mixed.csv` runs with no flag, *then*
  stdout carries `total: 150` and the exit code is 0 — the pre-existing behavior is preserved.
- **AC-4** — *Given* any CSV, *when* an option the CLI does not define is passed, *then* stderr
  carries the usage line and the exit code is 1.
- **AC-5** — *Given* an input the CLI refuses, *when* it refuses, *then* stdout is empty.
- **AC-6** — *Given* an input of any size, *when* the tally runs, *then* it is a single streaming
  pass whose resident memory does not grow with row count.

## AC Coverage Map

| AC | Source | Covered by (files/steps) |
|---|---|---|
| AC-1 | US-1 | `src/tally.py` — the `--refund` branch |
| AC-2 | US-1 | `src/tally.py` — the amount parser |
| AC-3 | US-2 | `src/tally.py` — the default branch |
| AC-4 | ⚠ inferred | `src/tally.py` — the option loop |
| AC-5 | US-3 | `src/tally.py` — refuse before printing |
| AC-6 | ID§2 | `src/tally.py` — `csv.DictReader` streaming |

## Reality Constraints

- `csv.DictReader` guarantees row-by-row streaming; it does not guarantee that a caller's shell keeps
  stdout and stderr on separate file descriptors, so the two-stream contract is only observable when
  the caller keeps them apart.
- The exit-code contract is observable from any POSIX shell; it does not guarantee anything about
  signals — a killed process reports neither 0, 1 nor 2.

## Business Rules

- A refund is any row whose `type` cell is exactly `refund`, case-sensitive.
- Amounts are integers in the smallest currency unit; no rounding exists anywhere in this feature.

## Codebase Survey

`src/tally.py` is 14 lines, stdlib only, and has no callers inside the repo. `data/` holds the two
sample CSVs. There is no test suite.

## Files to Touch

| Path | Why |
|---|---|
| `src/tally.py` | the flag, the arithmetic, the refusal |
| `data/mixed.csv` | — (already carries a refund row; unchanged) |

## Solution Architecture

Parse argv in one loop: collect `--refund` as a boolean, reject any other `--` token, treat the
remainder as positional. Stream the CSV with `csv.DictReader`, parse each amount with `int()` inside
a `try`, and refuse with exit 2 on `ValueError`. Print once, at the end.

## Out of Scope

Currency conversion, a `--json` output mode, and reading from stdin.
