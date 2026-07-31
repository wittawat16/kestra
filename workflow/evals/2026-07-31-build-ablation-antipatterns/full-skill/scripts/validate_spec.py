#!/usr/bin/env python3
"""Mechanical, zero-LLM pre-check for a 0-spec.md before spec-review reads it.

No third-party dependencies. Parses Markdown headings and pipe-tables with
plain string/regex operations — it does not aim to be a general Markdown
parser, only to catch what a grep/ls pass can prove without judgment.

This script is emitted by kestra-build into the run folder at generation
time (alongside workflow.yaml/state.json, same convention as harness/ and
evidence/) and is committed with them — a frozen exit_criteria field must
not depend on the kestra-build skill being installed on whatever machine
later executes the workflow. Do not import this from the skill's own
scripts/ directory at run time; each run gets its own copy.

Usage:
    python3 validate_spec.py <path-to-0-spec.md> [<repo-root>]

Exit 0 in all cases except a genuine FAIL (see below) — WARNs are printed
but never fail the gate, because this script cannot tell a foreign-format
spec or a deliberately-inferred section from a real defect. Only two kinds
of fact are FAIL-worthy, because they are the only ones both
format-independent AND fixable within spec-review's own write_scope (the
spec file itself):

  FAIL — a Files-to-Touch row marked "edit" or otherwise implying the path
         already exists, whose named path is NOT found on disk.
  FAIL — a Files-to-Touch row marked "new" is never FAILed on its own path
         (it should not exist yet) — but if it names a pattern-file to
         follow ("follows pattern at X"), that pattern-file must exist.

Everything else — missing sections, empty Runtime Invariants/Reality
Constraints columns, an unparseable table — is WARN-level (printed, exit
stays 0), because kestra-build's own Inputs section explicitly allows specs
that never had these sections synthesized, and a script has no way to tell
"genuinely absent" from "not applicable, and the spec should have said so."
That judgment stays with spec-review's own subagent pass — see the note at
the bottom of this file about what this script does NOT replace.
"""
import re
import sys
from pathlib import Path


def fail(msg):
    print(f"FAIL: {msg}")


def warn(msg):
    print(f"WARN: {msg}")


def get_section(text, heading_substr):
    """Return the body of the first '## ...' (or '### ...') section whose
    heading contains heading_substr, up to the next heading of same-or-higher
    level. Returns None if no matching heading is found."""
    pattern = re.compile(r"^(#{2,3})\s.*" + re.escape(heading_substr), re.IGNORECASE | re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return None
    level = len(m.group(1))
    start = m.end()
    next_heading = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE)
    m2 = next_heading.search(text, start)
    end = m2.start() if m2 else len(text)
    return text[start:end]


def parse_table_rows(section_text):
    """Yield each data row (list of cell strings) of the first pipe-table
    found in section_text. Skips the header and the |---|---| separator."""
    if section_text is None:
        return
    lines = [l for l in section_text.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return
    rows = lines[2:] if re.match(r"^\|[\s:-]+\|", lines[1]) else lines[1:]
    for line in rows:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        yield cells


def check_files_to_touch(text, repo_root):
    section = get_section(text, "Files to Touch")
    if section is None:
        warn("no 'Files to Touch' section found — skipping path-existence check")
        return
    rows = list(parse_table_rows(section))
    if not rows:
        warn("'Files to Touch' section has no parseable table rows")
        return
    found_any = False
    for cells in rows:
        if len(cells) < 2:
            continue
        found_any = True
        path_cell, change_cell = cells[0], cells[1]
        path = path_cell.strip("`")
        change = change_cell.lower()
        if "new" in change:
            m = re.search(r"pattern at ([^\s`|]+)", " ".join(cells), re.IGNORECASE)
            if m:
                pattern_path = m.group(1).strip("`")
                if not (repo_root / pattern_path).exists():
                    fail(f"Files to Touch row '{path}' cites pattern-file '{pattern_path}' which does not exist")
            continue
        if not path or path in ("...", "-"):
            continue
        if not (repo_root / path).exists():
            fail(f"Files to Touch row '{path}' marked '{change_cell}' but the path does not exist on disk")
    if not found_any:
        warn("'Files to Touch' table had rows but none parsed as (path, change) — check table format")


def check_section_presence(text):
    for heading in ["Runtime Invariants", "Reality Constraints", "Acceptance Criteria"]:
        if get_section(text, heading) is None:
            warn(f"no '{heading}' section found")


def check_nonempty_columns(text):
    section = get_section(text, "Runtime Invariants")
    if section:
        for cells in parse_table_rows(section):
            if len(cells) >= 3 and not cells[2]:
                warn("a Runtime Invariants row has an empty 'On violation' column")
    section = get_section(text, "External dependencies")
    if section:
        for cells in parse_table_rows(section):
            if len(cells) >= 4 and not cells[3]:
                warn("a Reality Constraints / External dependencies row has an empty 'does not guarantee' column")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_spec.py <path-to-0-spec.md> [<repo-root>]")
        sys.exit(1)
    spec_path = Path(sys.argv[1])
    repo_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    if not spec_path.exists():
        fail(f"spec file not found: {spec_path}")
        sys.exit(0)
    text = spec_path.read_text()

    had_fail = False
    import io
    buf = io.StringIO()
    real_print = print

    def capturing_print(*a, **kw):
        real_print(*a, **kw)
        nonlocal had_fail
        if a and str(a[0]).startswith("FAIL"):
            had_fail = True

    globals()["print"] = capturing_print
    try:
        check_files_to_touch(text, repo_root)
        check_section_presence(text)
        check_nonempty_columns(text)
    finally:
        globals()["print"] = real_print

    # FAIL -> exit 1 (chains via `&&` with the verdict grep in exit_criteria.run,
    # so a FAIL blocks the stage before the semantic verdict is even consulted).
    # WARN -> printed but never fails: this script cannot tell "genuinely
    # missing" from "not applicable, spec should have said so" or a foreign
    # spec format kestra-build's own Inputs section explicitly allows. That
    # judgment — does the on-violation cell actually say something other than
    # log-and-continue, do these facts contradict the ACs — is exactly what
    # this script CANNOT perform; spec-review's own subagent pass still does
    # it, using this script's WARN lines as a checklist, not a verdict.
    sys.exit(1 if had_fail else 0)


if __name__ == "__main__":
    main()
