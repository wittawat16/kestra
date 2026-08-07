#!/usr/bin/env python3
"""Exam — @@EXAM@@. Six checks, one per AC of the Coverage Map, plus C-0.

Authored by hand from `0-spec.md`'s requirement surface only: Functional
Requirements, Edge Cases & Error States, Runtime Invariants, the Coverage Map's
`AC`/`Source` columns, and `## External Interface`. `## Files to Touch`,
`## Codebase Survey`, `## Solution Architecture` and the Coverage Map's
`Covered by` column were not read, and no file under `src/` was opened.

This file is a template in the eval's `fixtures/`: `build-exam.py` substitutes
`EXAM`, the `ANCHOR` triple, the default repo root, and each check's
`provenance=` from the spec's own `Source` cell — so no anchor value and no
provenance is ever typed by hand. Every check body below is hand-written.

Header + EXAM + ANCHOR + SEAM + checks, and nothing else: every runner mechanic
lives in `exam_harness.py`.
"""
from exam_harness import (Cli, check, expect, expect_contains, expect_true,
                          repo_root, run_main)

EXAM = "@@EXAM@@"

ANCHOR = {
    "raise_commit": "@@RAISE@@",
    "surface_hash": "@@SURFACE@@",
    "extractor_version": "@@VER@@",
}

REPO = repo_root(default="@@REPO@@")

# `## External Interface` declares exactly one seam: `python3 src/tally.py`,
# run from the repository root, with sample inputs at `data/*.csv`.
SEAM = Cli(argv_prefix=["python3", "src/tally.py"], cwd=REPO)


@check(id="C-0", ac="—", cls="must-hold", provenance="—")
def c0(seam):
    """harness smoke — the declared seam answers"""
    r = seam.call([])
    expect(r.exit_code, 1, "exit", "tally (no args)")
    expect_contains(r.stderr, "usage: tally.py", "usage line", "tally (no args)")


@check(id="C-1", ac="AC-1", cls="must-flip", provenance="@@PROV:AC-1@@")
def c1(seam):
    """--refund subtracts refund rows from the total"""
    r = seam.call(["--refund", "data/mixed.csv"])
    expect(r.exit_code, 0, "exit", "tally --refund")
    expect_contains(r.stdout, "total: 90", "total line", "tally --refund")


@check(id="C-2", ac="AC-2", cls="must-flip", provenance="@@PROV:AC-2@@")
def c2(seam):
    """a non-integer amount is refused with exit 2, naming the file line"""
    r = seam.call(["data/bad.csv"])
    expect(r.exit_code, 2, "exit", "tally bad.csv")
    expect_contains(r.stderr, "line 3", "line number", "tally bad.csv")


@check(id="C-3", ac="AC-3", cls="must-hold", provenance="@@PROV:AC-3@@")
def c3(seam):
    """without --refund every row still adds — pre-existing behavior preserved"""
    r = seam.call(["data/mixed.csv"])
    expect(r.exit_code, 0, "exit", "tally (no flag)")
    expect_contains(r.stdout, "total: 150", "total line", "tally (no flag)")


@check(id="C-4", ac="AC-4", cls="must-flip", provenance="@@PROV:AC-4@@")
def c4(seam):
    """an undefined option is refused with the usage line and exit 1"""
    r = seam.call(["--bogus", "data/mixed.csv"])
    expect(r.exit_code, 1, "exit", "tally --bogus")
    expect_contains(r.stderr, "usage: tally.py", "usage line", "tally --bogus")


@check(id="C-5", ac="AC-5", cls="must-hold", provenance="@@PROV:AC-5@@")
def c5(seam):
    """a refusal leaves stdout empty"""
    r = seam.call(["data/bad.csv"])
    expect(r.stdout, "", "stdout", "tally bad.csv")
    expect_true(r.exit_code != 0, "nonzero exit", "tally bad.csv")


@check(id="C-6", ac="AC-6", cls="unexaminable", provenance="@@PROV:AC-6@@",
       unexaminable="a single-pass / resident-memory invariant is not observable "
                    "at the declared seam: the CLI exposes only stdout, stderr "
                    "and an exit code, none of which can induce or witness "
                    "memory growth")
def c6(seam):
    """single streaming pass; memory does not grow with row count"""


if __name__ == "__main__":
    run_main(SEAM)
