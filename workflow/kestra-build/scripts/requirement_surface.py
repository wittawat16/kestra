#!/usr/bin/env python3
"""The canonical requirement-surface extractor — one boundary, one hash, one place.

Files: this module is `requirement_surface.py`; its deterministic fixture tests
are `test_requirement_surface.py`, beside it in the skill's scripts/ directory
(tests stay in the skill, they are not emitted per run — see Packaging).

No third-party dependencies. Hand-parses the Markdown subset a 0-spec.md
actually uses (ATX headings, `-`/`*`/`+` bullets, pipe tables, ``` / ~~~ code
fences) exactly like validate_spec.py and validate_workflow.py do — a fresh
`python3` must be enough.

WHY THIS FILE EXISTS
    Four mechanisms have to agree, byte for byte, on "what the requirements
    are": kestra-exam's derivation, the workflow.yaml anchor triple, the
    per-ticket ac_hash, and kestra-run's pre-spawn surface check. A second
    implementation of the boundary anywhere is the failure this module exists
    to prevent. Everything reads SURFACE_SECTIONS / extract_surface() from
    here; nothing re-states the boundary in prose or in code.

THE BOUNDARY (design ticket #24's five sections; standing default, unvetoed)
    IN surface:
      1. "## Functional Requirements"
      2. "## Edge Cases & Error States"
      3. "## Runtime Invariants"
      4. "## AC Coverage Map"  — restricted to its `AC` and `Source` columns
      5. "## External Interface"
    OUT of surface, deliberately: "## Acceptance Criteria" (the Given-When-Then
    rows the Coverage Map paraphrases), "## Business Rules", and every other
    section (Overview, Problem Statement, Reality Constraints, Codebase Survey,
    Files to Touch, Dependencies, Design Notes, Solution Architecture, Risks,
    Out of Scope, Flags, Open Items). The Coverage Map's "Covered by
    (files/steps)" column is OUT — it records where a build put the coverage,
    not what the requirement is, so re-planning coverage must not read as a
    moved requirement.
    Consequence, stated so nobody re-derives it: an AC edited in the GWT
    "## Acceptance Criteria" section but not in the Coverage Map hashes FRESH.
    That is the vetter's standing default, not an oversight.

BOTH SPEC SHAPES
    Today's template (workflow/runs/order-cancellation-refund/0-spec.md) has
    emoji-decorated headings, no "## External Interface", and a two-column
    Coverage Map with no `Source`. The grown Wave-2 shape
    (workflow/evals/2026-08-02-spec-instrumented-rerun/spec-pass/0-spec.md) has
    plain headings, External Interface, and a `Source` column. Both extract;
    absent sections and an absent `Source` column are simply absent from the
    surface, never an error here (presence is validate_spec.py's job, and only
    under the chain marker).

PACKAGING / BOOTSTRAP — decided against the copy-per-run precedent
    Same as validate_spec.py: kestra-build emits a byte copy of this file into
    the run folder next to workflow.yaml/state.json and commits it. Callers
    import it from the run folder (it is import-safe: no side effects at
    import), never from ~/.claude/skills/.
    Why, given "shared byte-identically" sounds like an argument for one
    installed copy: the checks that read this run for months (pre-spawn surface
    check, a re-fold, an exam gate) must not change their answer because the
    skill was reinstalled or updated in between. A live import from the install
    makes drift SILENT — the same spec text starts hashing differently and the
    run reads it as "the human edited the spec". The committed copy freezes the
    semantics for the life of the run, and EXTRACTOR_VERSION in the anchor
    triple makes any cross-run difference visible instead. Byte-identity is
    thus guaranteed within a run by the commit, and across runs by the version
    field. Single file, stdlib only, no imports from sibling scripts, precisely
    so the copy is self-sufficient. A sibling in the same run folder (e.g.
    validate_workflow.py checking the anchor) imports it as
    `from requirement_surface import extract_surface, EXTRACTOR_VERSION` —
    same directory, no path setup.

EXTRACTOR_VERSION — bump semantics
    Bump on any change that can make an UNCHANGED 0-spec.md produce a different
    surface_hash: the section list, the column restriction, normalization,
    fence handling, heading matching, or the serialized form fed to sha256.
    That includes bug fixes — a fix that corrects the hash is exactly the case
    the version field exists to explain. Do NOT bump for docstring, CLI, error
    text, or test-only changes. A recorded anchor whose version differs from
    this constant is not comparable: recompute or re-raise, never diff the
    hashes.

ASSUMPTIONS (surfaced rather than silently chosen)
    * Heading match is exact after stripping leading decoration (emoji) and a
      trailing italic parenthetical: "## 🥑 Functional Requirements" and
      "## External Interface  *(new)*" match; "## Non-Functional Requirements"
      deliberately does NOT (a substring match would silently absorb a foreign
      section into the surface — invisible). A boundary section whose heading is
      renamed therefore drops out of the surface; that is loud, not silent —
      this script's CLI prints WARN per absent section, and validate_spec.py
      FAILs on it under the chain marker.
    * Normalization drops the list marker entirely, so `-`/`*`/`+`, an indented
      sub-bullet, and a bare paragraph line with the same text are equal. That
      is the "whitespace/list-prefix variations never read as ACs moved"
      requirement taken at its word.
    * Wrapped continuation lines are joined into their bullet, so re-flowing a
      paragraph does not move the hash.
    * Sections are serialized in the fixed boundary order above, under their
      canonical heading text — reordering sections in the file, or changing a
      heading's emoji, is not a requirement change.
    * Per-AC rows come from the Coverage Map only: it is the one in-surface
      place where an AC carries identity (`AC-1`) and a `Source`. In today's
      shape the `AC` cell is free text, so the id is that text — an AC whose
      text is rewritten reads as a new row, which is the honest answer. Columns
      are located by header name and serialized in AC_COLUMNS order, so the id
      is the `AC` cell whatever order the table is written in, and reordering
      the Coverage Map's columns is not a requirement change.

Usage:
    python3 requirement_surface.py <path-to-0-spec.md>          # hash + surface
    python3 requirement_surface.py <path-to-0-spec.md> --hash   # hash only

Exits 1 and prints FAIL only on an unreadable spec or an unclosed code fence —
the false-fresh failure mode, where a runaway fence would swallow the rest of
the file and hand back a silently truncated surface that still hashes cleanly.
"""
import hashlib
import re
import sys
from collections import namedtuple
from pathlib import Path

EXTRACTOR_VERSION = 1

# The boundary. One data structure, canonical order, read by every other
# mechanism. Do not restate this list anywhere else.
SURFACE_SECTIONS = (
    "Functional Requirements",
    "Edge Cases & Error States",
    "Runtime Invariants",
    "AC Coverage Map",
    "External Interface",
)
AC_COLUMNS = ("AC", "Source")  # the only Coverage Map columns in surface

_BY_NAME = {name.lower(): name for name in SURFACE_SECTIONS}
_AC_COLS_ORDERED = tuple(c.lower() for c in AC_COLUMNS)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*$")
_BULLET = re.compile(r"^([-*+])\s+")
_CHECKBOX = re.compile(r"^\[[ xX]\]\s*")
_SEPARATOR = re.compile(r"^[\s:|-]+$")

Surface = namedtuple("Surface", "sections ac_rows text surface_hash")


class SurfaceError(Exception):
    """The spec cannot be extracted honestly (today: an unclosed code fence)."""


def _ws(s):
    return re.sub(r"\s+", " ", s).strip()


def _scan(text):
    """Yield (line, in_fence) for every line, tracking ``` / ~~~ fences.

    A '##' line inside a fence is content, never a delimiter. An unclosed fence
    raises rather than truncating the surface."""
    fence = None
    for line in text.splitlines():
        m = _FENCE.match(line)
        if fence is None:
            fence = m.group(1) if m else None
            yield line, fence is not None
        else:
            yield line, True
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip().strip(fence[0]):
                fence = None
    if fence is not None:
        raise SurfaceError(
            "unclosed code fence — the surface would be silently truncated"
        )


def _canonical(heading):
    """Heading text minus emoji/decoration and a trailing *(...)* qualifier."""
    h = heading.split("*(")[0].strip().lower()
    while h and not h[0].isalpha():
        h = h[1:].lstrip()
    return _ws(h)


def _row(stripped):
    """Normalized pipe-table row, or None for the |---|---| separator."""
    if _SEPARATOR.match(stripped):
        return None
    return " | ".join(_ws(c) for c in stripped.strip("|").split("|"))


def _units(lines):
    """Normalize a section body into hashable units.

    Drops the list marker and checkbox state, collapses whitespace, joins
    wrapped continuation lines into their bullet, and keeps fenced content
    line-by-line."""
    units, open_unit = [], False
    for line, in_fence in lines:
        s = line.strip()
        if in_fence:
            units.append(_ws(s))
            open_unit = False
        elif not s:
            open_unit = False
        elif s.startswith("|"):
            row = _row(s)
            if row is not None:
                units.append(row)
            open_unit = False
        elif _HEADING.match(line) or _BULLET.match(s) or not open_unit:
            units.append(_ws(_CHECKBOX.sub("", _BULLET.sub("", s))))
            open_unit = True
        else:
            units[-1] += " " + _ws(s)
    return units


def _ac_rows(lines):
    """(id, normalized row) per Coverage Map data row, AC + Source columns only.

    Columns are located by header name and emitted in AC_COLUMNS order, never in
    document order, so the id is always the `AC` cell and reordering the table's
    columns is presentation, not a requirement change."""
    rows, keep = [], None
    for line, in_fence in lines:
        s = line.strip()
        if in_fence or not s.startswith("|"):
            continue
        cells = [_ws(c) for c in s.strip("|").split("|")]
        if keep is None:  # the first table line is the header
            at = {c.lower(): i for i, c in enumerate(cells)}
            keep = [at[c] for c in _AC_COLS_ORDERED if c in at]
        elif not _SEPARATOR.match(s):
            picked = [cells[i] for i in keep if i < len(cells)]
            if picked:
                rows.append((picked[0], " | ".join(picked)))
    return rows


def extract_surface(text):
    """Extract the requirement surface of a 0-spec.md. Raises SurfaceError."""
    sections, ac_rows = {}, []
    current, buf = None, []
    for line, in_fence in _scan(text):
        m = None if in_fence else _HEADING.match(line)
        if m and len(m.group(1)) <= 2:
            if current:
                sections[current] = buf
            current, buf = _BY_NAME.get(_canonical(m.group(2))), []
        elif current:
            buf.append((line, in_fence))
    if current:
        sections[current] = buf

    for name, lines in sections.items():
        if name == "AC Coverage Map":
            ac_rows = _ac_rows(lines)
            sections[name] = [content for _, content in ac_rows]
        else:
            sections[name] = _units(lines)

    out = []
    for name in SURFACE_SECTIONS:
        if name in sections:
            out.append("## " + name)
            out.extend(sections[name])
    body = "\n".join(out) + "\n"
    return Surface(sections, ac_rows, body,
                   hashlib.sha256(body.encode("utf-8")).hexdigest())


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 requirement_surface.py <path-to-0-spec.md> [--hash]")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"FAIL: spec file not found: {path}")
        sys.exit(1)
    try:
        surface = extract_surface(path.read_text())
    except SurfaceError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    if "--hash" in sys.argv[2:]:
        print(surface.surface_hash)
        sys.exit(0)
    print(f"extractor_version: {EXTRACTOR_VERSION}")
    print(f"surface_hash: {surface.surface_hash}")
    print(f"ac_rows: {len(surface.ac_rows)}")
    for name in SURFACE_SECTIONS:
        if name not in surface.sections:
            print(f"WARN: no '{name}' section found")
    print()
    print(surface.text, end="")


if __name__ == "__main__":
    main()
