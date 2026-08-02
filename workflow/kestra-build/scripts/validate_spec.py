#!/usr/bin/env python3
"""Mechanical, zero-LLM pre-check for a 0-spec.md before spec-review reads it.

No third-party dependencies. Parses Markdown headings and pipe-tables with
plain string/regex operations — it does not aim to be a general Markdown
parser, only to catch what a grep/ls pass can prove without judgment.

This script is emitted into the run folder and committed with it — by
kestra-spec at raise time (with requirement_surface.py beside it, so the
spec is checked before the exam is derived from it) and again by
kestra-build at generation time (alongside workflow.yaml/state.json, same
convention as harness/ and evidence/). A frozen exit_criteria field must
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

THE CHAIN MARKER — the one exception to "presence is always WARN"
Five template obligations (a Source column in the AC Coverage Map, a
"## External Interface" section, a recorded mode-prediction fact, an
"## Exit Criteria" section with its stop head and progress fragments, and
the delimiter precondition) are checked CONDITIONALLY: FAIL when the spec
carries the chain marker, WARN when it does not. The marker is a single
preamble line, written by kestra-spec's raise commit and nowhere else:

    > Spec-ticket: https://github.com/<owner>/<repo>/issues/<N>

"Preamble" means above the first '## ' line — the marker therefore sits
outside the requirement surface and marking a spec never moves its
surface_hash. A marker line present but without a URL, more than one, or
one below the first '## ' is a FAIL in itself (partial marker, same rule as
validate_workflow.py's partial anchor triple). The search is fence-aware on
both sides, by the same fence rules the extractor applies: a 'Spec-ticket:'
line inside a code fence is an example — never a marker, never a misplacement —
so a spec documenting the marker's own syntax neither claims the chain nor
false-FAILs for showing it below a heading.

The conditional exists because a marked spec is one this repo's own skill
produced from a vetted ticket, so its template is a contract and a missing
section is a defect. An unmarked spec is hand-written, standalone, or
foreign — the same missing section proves nothing, and this script must
keep passing it exactly as promised above. Only these five checks read the
marker; every pre-existing check behaves identically in both modes.

The delimiter check needs requirement_surface.py beside this file. If it is
missing, the check reports through the same conditional rather than being
skipped outright: WARN when unmarked, FAIL when marked. Not-run is not
passed, and the thing it fails to catch — a truncated requirement surface
hashed as fresh — is invisible everywhere downstream.
"""
import re
import sys
from pathlib import Path

# The chain marker (see the docstring). Strict form: exactly one value.
CHAIN_MARKER = re.compile(r"^>\s*Spec-ticket:\s*(\S+)\s*$", re.MULTILINE)
# Loose form: catches a marker line whose value is missing entirely, which is
# a partial marker (FAIL), not a standalone spec.
SPEC_TICKET_LINE = re.compile(r"^>\s*Spec-ticket:.*$", re.MULTILINE)
TICKET_URL = re.compile(r"^https?://\S+$")
FIRST_H2 = re.compile(r"^ {0,3}## ", re.MULTILINE)
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*$")
MODE = re.compile(r"^\s*[-*]?\s*\**\s*kestra-build mode:?\**\s*[`*]*\s*(full|lite)\b",
                  re.IGNORECASE | re.MULTILINE)
PROSE_PRECONDITION = re.compile(r"^>\s*Delimiter precondition:", re.MULTILINE)

# The canonical H2 names the kestra-spec template emits. NOT the requirement
# surface (that stays single-owner in requirement_surface.py) — this is the
# set of headings a '## ' line is allowed to be, so a bare '## ' inside a
# section body is detectable. Must stay a superset of SURFACE_SECTIONS.
TEMPLATE_SECTIONS = (
    "Overview",
    "External Interface",
    "Problem Statement",
    "Functional Requirements",
    "Edge Cases & Error States",
    "Runtime Invariants",
    "Business Rules",
    "Design Notes",
    "Solution Architecture",
    "Codebase Survey",
    "Reality Constraints",
    "Files to Touch",
    "Dependencies",
    "Acceptance Criteria",
    "AC Coverage Map",
    "Risks & Watch-outs",
    "Out of Scope",
    "Flags",
    "Exit Criteria",
    "Mode Prediction",
    "Open Items",
)

try:
    # One owner of the heading and fence rules — see requirement_surface.py.
    # It is emitted into the run folder beside this file, so this resolves as
    # a same-directory sibling, never from ~/.claude/skills/.
    from requirement_surface import canonical_heading, extract_surface, SurfaceError, _scan
except ImportError:  # copied without its sibling — degrade loudly, never silently
    canonical_heading = None


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


def table_header(section_text):
    """Cells of the first pipe-table header line in section_text, or None."""
    if section_text is None:
        return None
    for line in section_text.splitlines():
        if line.strip().startswith("|"):
            return [c.strip() for c in line.strip().strip("|").split("|")]
    return None


def scanned(text):
    """[(line, in_fence)] for every line, or None when the file cannot be
    scanned honestly (no extractor beside us, or an unclosed fence — which
    check_delimiter_precondition reports on its own)."""
    if canonical_heading is None:
        return None
    try:
        return list(_scan(text))
    except SurfaceError:
        return None


def template_section(text, name):
    """Body of the '## <name>' section, matched the way the surface matches
    headings — canonically and fence-aware. get_section's substring match
    would accept '## External Interfaces', which the extractor drops."""
    lines = scanned(text)
    if lines is None:
        return get_section(text, name)
    want = canonical_heading(name)
    body, found = [], False
    for line, in_fence in lines:
        m = None if in_fence else HEADING.match(line)
        if m and len(m.group(1)) <= 2:
            if found:
                break
            found = canonical_heading(m.group(2)) == want
        elif found:
            body.append(line)
    return "\n".join(body) if found else None


def preamble(text):
    """Everything above the first '## ' line — the one region provably outside
    the requirement surface, and so the only place a marker may live."""
    m = FIRST_H2.search(text)
    return text[:m.start()] if m else text


def report(chained, msg):
    """The whole conditional: chain marker present ⇒ FAIL, absent ⇒ WARN."""
    (fail if chained else warn)(msg)


def marker_lines(text):
    """(above, below) — the 'Spec-ticket:' lines above and below the first
    '## ' heading, ignoring every fenced line on both sides.

    One rule, applied to both sides: a 'Spec-ticket:' line inside a code fence
    is an example, never a marker and never a misplacement. Documentation that
    shows the marker's own syntax must not be read as claiming it.

    Returns None when the file cannot be scanned honestly (no sibling
    extractor, or an unclosed fence — which check_delimiter_precondition
    reports on its own); the caller then falls back to the fence-blind regex,
    alongside the 'heading matching is approximate' WARN main() already prints."""
    lines = scanned(text)
    if lines is None:
        return None
    above, below, in_body = [], [], False
    for line, in_fence in lines:
        if in_fence:
            continue
        if not in_body and FIRST_H2.match(line):
            in_body = True
            continue
        (below if in_body else above).append(line)
    return ([l for l in above if SPEC_TICKET_LINE.match(l)],
            [l for l in below if SPEC_TICKET_LINE.match(l)])


def resolve_chain_marker(text):
    """True if this spec claims chain provenance (see the docstring).

    A malformed, duplicated or misplaced marker line FAILs here and still
    counts as chained — a spec reaching for the chain is held to it."""
    found = marker_lines(text)
    if found is None:
        head = preamble(text)
        lines = SPEC_TICKET_LINE.findall(head)
        below = SPEC_TICKET_LINE.findall(text[len(head):])
    else:
        lines, below = found
    if below:
        fail("'Spec-ticket:' line outside the preamble — it must sit above the first "
             "'## ' or it can land inside a requirement-surface section and move surface_hash.")
        return True
    if not lines:
        return False
    if len(lines) > 1:
        fail(f"{len(lines)} 'Spec-ticket:' marker lines in the preamble — exactly one is allowed")
        return True
    m = CHAIN_MARKER.match(lines[0])
    value = m.group(1) if m else ""
    if not TICKET_URL.match(value):
        fail(f"chain marker 'Spec-ticket:' present but malformed ('{value}') — a partial marker "
             "is a FAIL (same rule as validate_workflow.py's partial anchor triple); give the "
             "full ticket URL or remove the line.")
    return True


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
    for idx, cells in enumerate(rows, 1):
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
        # A cell naming no path at all — prose, or wholly wrapped in *(...)* — is
        # not a path claim, so the path-existence check has nothing to check. Say
        # so rather than FAILing it (outside this check's documented intent) or
        # skipping it silently (which would make *(TBD)* a dodge).
        #
        # The discriminator is SHAPE, not extension: prose contains whitespace, a
        # path claim is a single whitespace-free token. An earlier "no '/' and no
        # '.'" test read `Makefile`, `Dockerfile`, `LICENSE` and `Justfile` as
        # prose and dropped them to WARN — real path claims escaping the one check
        # that can prove them wrong.
        bare = path_cell.strip().strip("`").strip("*").strip()
        if (re.fullmatch(r"\*\(.*\)\*", path_cell.strip())
                or re.search(r"\s", bare)
                or bare.lower() in {"", "...", "-", "—", "n/a", "na", "tbd", "none"}):
            warn(f"Files to Touch row {idx} names no file path ('{path_cell}') — "
                 "the path-existence check cannot run on it")
            continue
        if not (repo_root / bare).exists():
            fail(f"Files to Touch row '{bare}' marked '{change_cell}' but the path does not exist on disk")
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


def check_source_column(text, chained):
    """Every AC cites its intent-layer origin, or the column lies."""
    section = template_section(text, "AC Coverage Map")
    if section is None:
        report(chained, "no 'AC Coverage Map' section found — the Source column check cannot run")
        return
    header = table_header(section) or []
    at = None
    for i, cell in enumerate(header):
        if cell.strip("`* ").lower() == "source":
            at = i
            break
    if at is None:
        report(chained, "no 'Source' column in the AC Coverage Map header — every AC must "
                        "cite its intent-layer origin (US-n / ID§x / ⚠ inferred)")
        return
    empty = sum(1 for cells in parse_table_rows(section)
                if at >= len(cells) or not cells[at])
    if empty:
        report(chained, f"{empty} AC Coverage Map row(s) have an empty 'Source' cell — "
                        "a green column that lies")


def check_external_interface(text, chained):
    """The seam kestra-exam is allowed to drive, named by the spec."""
    section = template_section(text, "External Interface")
    if section is None:
        report(chained, "no '## External Interface' section — kestra-exam must run at the seam "
                        "this section declares; without it the exam guesses (permanent "
                        "false-fail risk)")
        return
    body = [l for l in section.splitlines()
            if l.strip() and not HEADING.match(l)]
    if not body:
        report(chained, "'## External Interface' is empty — name the seam tests may drive, "
                        "the seams deliberately absent, and what is not an interface")


def check_mode_prediction(text, chained):
    """The recorded kestra-build mode fact — one line, with its reason."""
    section = template_section(text, "Mode Prediction")
    matches = list(MODE.finditer(section)) if section else []
    if not matches:
        report(chained, "no recorded mode-prediction fact — '## Mode Prediction' must carry a "
                        "line 'kestra-build mode: `full`|`lite`' with the reason")
        return
    if len(matches) > 1:
        report(chained, f"{len(matches)} mode-prediction lines — exactly one is allowed")
        return
    tail = section[matches[0].end():].split("\n", 1)[0]
    if not tail.strip("`*—- \t"):  # grading the prose is not this script's job
        warn("the mode-prediction line records no reason for the mode")


def check_exit_criteria(text, chained):
    """The stop head and per-loop progress fragments kestra-build copies onto
    owning stages — a dropped section leaves clause 2 of the stop condition
    unable to ever fire, silently, two skills downstream."""
    section = template_section(text, "Exit Criteria")
    if section is None:
        report(chained, "no '## Exit Criteria' section — kestra-build copies its 'progress:' "
                        "fragments onto the owning stages; without them clause 2 of the "
                        "stop condition can never fire")
        return
    if not re.search(r"\*\*Stop condition:\*\*", section):
        report(chained, "'## Exit Criteria' has no '**Stop condition:**' head line")
    if not (re.search(r"^\s*[-*]\s*progress:", section, re.MULTILINE)
            or re.search(r"single-shot", section, re.IGNORECASE)):
        report(chained, "'## Exit Criteria' carries no 'progress:' fragment and no "
                        "closing single-shot bullet — every check is one or the other")
    # Whether a fragment names a number rather than a state is prose judgment —
    # not this script's job, same rule as the mode-prediction reason.


def check_delimiter_precondition(text, chained):
    """The two facts the extractor actually enforces: fences close, and every
    '## ' outside a fence is a template section heading (a bare one inside a
    section body truncates the requirement surface)."""
    if canonical_heading is None:
        # Not-run is not the same as passed. Standalone: WARN, like every other
        # unprovable fact here. Chained: FAIL — the surface of a marked spec is
        # what a later hash is taken over, so skipping the only check that can
        # catch a truncated one would ship a false-fresh hash downstream, where
        # nothing else can see it.
        report(chained, "delimiter-precondition check cannot run — requirement_surface.py is "
                        "not beside this script, so a silently truncated requirement surface "
                        "would pass as fresh. Copy requirement_surface.py next to "
                        "validate_spec.py (kestra-spec emits both together) and re-run")
        return
    try:
        extract_surface(text)
    except SurfaceError:
        report(chained, "unclosed code fence — the requirement surface would be silently "
                        "truncated (false-fresh hash)")
        return
    known = {canonical_heading(name) for name in TEMPLATE_SECTIONS}
    for line, in_fence in _scan(text):
        m = None if in_fence else HEADING.match(line)
        if m and len(m.group(1)) == 2 and canonical_heading(m.group(2)) not in known:
            report(chained, f"'## {m.group(2)}' is not a template section heading — a bare "
                            "'## ' inside a requirement-surface section body truncates the "
                            "surface; use '### ' for a subsection, or fence a literal")
    if not PROSE_PRECONDITION.search(preamble(text)):
        warn("no 'Delimiter precondition:' line in the preamble — prose only, but the "
             "template asks for it")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_spec.py <path-to-0-spec.md> [<repo-root>]")
        sys.exit(1)
    spec_path = Path(sys.argv[1])
    repo_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    if not spec_path.exists():
        fail(f"spec file not found: {spec_path}")
        sys.exit(1)  # a FAIL always exits 1 — see the note at the bottom
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
        chained = resolve_chain_marker(text)
        check_files_to_touch(text, repo_root)
        check_section_presence(text)
        check_nonempty_columns(text)
        if canonical_heading is None:
            warn("requirement_surface.py not found beside this script — "
                 "heading matching is approximate")
        check_source_column(text, chained)
        check_external_interface(text, chained)
        check_mode_prediction(text, chained)
        check_exit_criteria(text, chained)
        check_delimiter_precondition(text, chained)
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
