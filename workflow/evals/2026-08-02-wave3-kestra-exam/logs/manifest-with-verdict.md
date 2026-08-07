# Exam manifest — tally-refund

## Anchor

| Field | Value |
|---|---|
| raise_commit | f59837b1323b009647d266ed99ee35f49b2bb10d |
| surface_hash | 7e47c7ab797892606d6c70a72bc5fd54f991d2ca3008ef92bef161fab1388718 |
| extractor_version | 1 |
| origin_key | git.example.test__kx-fixture__tally |
| feature_slug | tally-refund |
| spec_path | workflows/runs/tally-refund/0-spec.md |
| exam_script_sha256 | 202404e5e49f74030a6ffa04a26d6ab57b053432dee602153da52469b6a26ae5 |
| generated_at | 2026-08-02T15:22:36Z |
| generation | 1 |

## Read rule

In surface, and the only sections read: the five named by
`requirement_surface.SURFACE_SECTIONS` (that module is the single owner of the
boundary; this manifest never restates the list). Run
`python3 -c 'import requirement_surface as r; print(r.SURFACE_SECTIONS)'` beside this
file to read it back.

Never read, and not read while writing this exam: `## Files to Touch`,
`## Codebase Survey`, `## Solution Architecture`, and the Coverage Map's
`Covered by (files/steps)` column. No file under `src/` was opened.

The `## External Interface` lines the `SEAM` encodes, verbatim from
`workflows/runs/tally-refund/0-spec.md` — `exam.py --audit-seam` requires `seam.target()` to appear
in this block:

~~~
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
~~~

## Checks

| AC | Check | Class | Provenance | Red-proof | Failure signature | Unexaminable |
|----|-------|-------|------------|-----------|-------------------|--------------|
| — | C-0 | must-hold | — | n/a — must-hold | — | — |
| AC-1 | C-1 | must-flip | US-1 | red 2026-08-02T15:22:36Z behavioral | `CheckFailure: exit 1 != 0 @ tally --refund` | — |
| AC-2 | C-2 | must-flip | US-1 | red 2026-08-02T15:22:36Z behavioral | `CheckFailure: exit 1 != 2 @ tally bad.csv` | — |
| AC-3 | C-3 | must-hold | US-2 | n/a — must-hold | — | — |
| AC-4 | C-4 | must-flip | ⚠ inferred | **born-green — `unproven`** | — | — |
| AC-5 | C-5 | must-hold | US-3 | n/a — must-hold | — | — |
| AC-6 | C-6 | unexaminable | ID§2 | — | — | a single-pass / resident-memory invariant is not observable at the declared seam: the CLI exposes only stdout, stderr and an exit code, none of which can induce or witness memory growth |

## Delta map

### Section fingerprints

| Section | sha256-12 |
|---|---|
| Functional Requirements | 468d9b4429be |
| Edge Cases & Error States | 96af6d52699e |
| Runtime Invariants | caaf14b4dad4 |
| AC Coverage Map | ba1c46dcd579 |
| External Interface | a89548934a5b |

### AC fingerprints

| AC | sha256-12 |
|---|---|
| AC-1 | 34958c6fea62 |
| AC-2 | faf6c8170346 |
| AC-3 | 0c22c6dc34e8 |
| AC-4 | 1804bb8ab08d |
| AC-5 | aa3f9dc85921 |
| AC-6 | 0f1a55745eb4 |

## Coverage

ACs in surface: 6 · executably covered: 5 · unexaminable: 1 · must-flip: 3 (unproven: 1) · must-hold: 3

## Verdict contract

A verdict is emitted only when the anchor triple recomputes equal (see §Anchor);
otherwise REFUSED — stale anchor, and no verdict line is written at all.
PASS iff C-0 passed AND every must-flip and must-hold check passed AND no check
reported an infrastructure red.  FAIL if any check failed behaviorally.
BLOCKED if the run exited 2 (harness).  Unexaminable rows never pass or fail;
they are listed by AC id.  U>0 ⇒ the evidence clause is MANDATORY: a PASS with
U>0 and no clause is a malformed verdict, i.e. a gate failure.

--- verdict (appended by the gate runner; unfilled above this line) ---
verdict:   PASS | FAIL | BLOCKED | REFUSED
evidence:  full | degraded — <U> unproven of <F> must-flip
coverage:  <M>/<N> ACs executably covered; unexaminable: <AC ids>
run:       <ISO-8601 Z> · exam.py sha256 <12> · exit <code>
--- verdict (appended by the gate runner; unfilled above this line) ---
verdict:   PASS
evidence:  degraded — 1 unproven of 3 must-flip
coverage:  5/6 ACs executably covered; unexaminable: AC-6
run:       2026-08-02T15:22:40Z · exam.py sha256 202404e5e49f · exit 0
