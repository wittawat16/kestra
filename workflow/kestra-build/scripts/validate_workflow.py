#!/usr/bin/env python3
"""Mechanical, zero-LLM dry-run check for a workflow.yaml + state.json pair.

No third-party dependencies (PyYAML is frequently unavailable in a plain
python3 install) — parses the constrained YAML subset kestra-build actually
emits: block mappings, block/inline sequences, quoted/bare scalars, and
folded (">") or literal ("|") block scalars for `brief`. It does not aim to
be a general YAML parser.

Usage:
    python3 validate_workflow.py <dir-containing-workflow.yaml-and-state.json>

Exits 0 and prints "PASS" if the stage graph is structurally sound. Exits 1
and prints every problem found otherwise. This never asks an LLM's opinion —
every check here is a graph/set operation, on purpose: it's the same
"mechanical, not judged" standard kestra-run's own enforcement holds itself to,
just applied before the first stage ever runs instead of after.

THE SPEC ANCHOR — absent is a WARN, partial is a FAIL
A chained workflow.yaml carries a top-level `spec_anchor` mapping
(raise_commit / surface_hash / extractor_version) recording which commit of
which spec it was folded from. Absent, this workflow is standalone and still
valid; present, every field is graded and the surface is recomputed for real.
That recompute needs requirement_surface.py **beside this file** — kestra-build
emits a byte copy of it into the run folder and commits it, so run this script
from the run folder (`python3 <run>/validate_workflow.py <run>`) whenever the
workflow is anchored. Running the skill's own copy in place stays a valid
convenience for unanchored workflows; if it then reports a version mismatch,
that is a true signal, not a bug.

THE SLICED FOLD — the tickets[] map and the embedded ticket blocks
A sliced fold also carries a top-level `tickets:` sequence and one embedded
ticket block per owning stage brief. Both are *derived* from
`<run>/tickets/<id>.md`, so this script recomputes them the way the fold did:
sha256 of each ticket file against the block delimiter's hex and against
`tickets[].body_sha256`, a whitespace-normalized text compare of the raw
embedded block against the file, `verified_against` against
`spec_anchor.raise_commit`, and each `ac_hash` against the spec's AC Coverage
Map recomputed now. That is what makes "the fold refuses" an exit code rather
than an instruction. A monolithic fold carries none of these and nothing in that
group fires. Every embedded-block check reads the RAW workflow.yaml text, never
the parsed brief: the parser's pre-pass strips ` #…` comments and `---` lines
from block-scalar bodies too, so the parsed brief is a lossy view of a ticket
body (WARNed below, never "fixed" by escaping — that would break the byte
identity the sha256 protects).
"""
import sys
import re
import json
import fnmatch
import hashlib
from pathlib import Path

try:
    # One owner of the requirement-surface boundary. kestra-build emits a byte
    # copy of requirement_surface.py into the run folder beside this script, so
    # this resolves as a same-directory sibling — never from ~/.claude/skills/,
    # and never through search-path surgery or a dynamic import (a test asserts
    # this file contains no such thing). That is the point: the
    # hashes this script compares must keep their meaning for the life of the
    # run, which they only do if the extractor is the copy committed with it.
    # _ws / _BULLET / _CHECKBOX come along for the ticket-AC normalization: the
    # sliced ACs must be normalized by *the same code* that built the AC Coverage
    # Map rows they are matched against (ticket-fold.md §2 step 1 names these three
    # by name). A second copy of those transforms here would be a second
    # vocabulary that can drift while both sides still look populated.
    from requirement_surface import (EXTRACTOR_VERSION, extract_surface, SurfaceError,
                                     _ws, _BULLET, _CHECKBOX)
except ImportError:  # copied without its sibling — degrade loudly, never silently
    EXTRACTOR_VERSION = None


# ---------------------------------------------------------------------------
# Minimal YAML-subset parser
# ---------------------------------------------------------------------------

def _strip_comment(line):
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            if i == 0 or line[i - 1] in (" ", "\t"):
                return line[:i]
    return line


def _parse_scalar(s):
    s = s.strip()
    if s == "" or s == "~" or s == "null":
        return None
    if s == "[]":
        return []
    if s == "true":
        return True
    if s == "false":
        return False
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = [_parse_scalar(x) for x in _split_flow(inner)]
        return items
    return s


def _split_flow(inner):
    parts, depth, cur, in_s, in_d = [], 0, "", False, False
    for ch in inner:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch in "[{" and not in_s and not in_d:
            depth += 1
        elif ch in "]}" and not in_s and not in_d:
            depth -= 1
        if ch == "," and depth == 0 and not in_s and not in_d:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def parse_yaml(text):
    raw_lines = text.split("\n")
    lines = []
    for ln in raw_lines:
        ln = _strip_comment(ln).rstrip()
        if ln.strip() == "" or ln.strip() == "---":
            continue
        lines.append(ln)

    pos = [0]

    def peek_indent():
        return _indent(lines[pos[0]]) if pos[0] < len(lines) else -1

    def skip_block_scalar(base_indent):
        # consumes a folded/literal block scalar body, returns joined text
        collected = []
        while pos[0] < len(lines):
            ln = lines[pos[0]]
            if ln.strip() == "" or _indent(ln) > base_indent:
                collected.append(ln.strip())
                pos[0] += 1
            else:
                break
        return " ".join(collected)

    def parse_block(min_indent):
        if pos[0] >= len(lines):
            return None
        first_indent = peek_indent()
        if first_indent < min_indent:
            return None
        stripped = lines[pos[0]].strip()

        if stripped.startswith("- "):
            return parse_sequence(first_indent)
        return parse_mapping(first_indent)

    def parse_sequence(seq_indent):
        items = []
        while pos[0] < len(lines) and peek_indent() == seq_indent and lines[pos[0]].strip().startswith("- "):
            ln = lines[pos[0]]
            content = ln.strip()[2:]
            if ":" in content and not content.strip().startswith(("[", '"', "'")):
                # inline mapping start, e.g. "- id: foo"
                fake_indent = seq_indent + 2
                lines[pos[0]] = " " * fake_indent + content
                item = parse_mapping(fake_indent)
                items.append(item)
            else:
                pos[0] += 1
                items.append(_parse_scalar(content))
        return items

    key_val_re = re.compile(r"^([A-Za-z0-9_\-\.]+):\s*(.*)$")

    def parse_mapping(map_indent):
        result = {}
        while pos[0] < len(lines) and peek_indent() == map_indent:
            ln = lines[pos[0]]
            stripped = ln.strip()
            if stripped.startswith("- "):
                break
            m = key_val_re.match(stripped)
            if not m:
                pos[0] += 1
                continue
            key, rest = m.group(1), m.group(2)
            pos[0] += 1
            if rest == "" :
                # nested block, or a following block scalar
                if pos[0] < len(lines) and peek_indent() > map_indent:
                    result[key] = parse_block(map_indent + 1)
                else:
                    result[key] = None
            elif rest in (">", "|", ">-", "|-", ">+", "|+"):
                result[key] = skip_block_scalar(map_indent)
            else:
                result[key] = _parse_scalar(rest)
        return result

    return parse_block(0)


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

def fnmatch_overlap(pattern_a, pattern_b):
    """Conservative overlap check for write_scope globs.

    Two globs are treated as overlapping unless their literal (non-wildcard)
    directory prefixes are provably disjoint. This deliberately errs toward
    flagging a possible collision — a false positive here just means a human
    double-checks two write_scopes that were fine; a false negative would let
    a real collision through silently, which is the worse failure mode.

    When one side is a concrete path (no wildcard at all — e.g. a specific
    file an implement stage lists by name), match it against the other side
    with real glob semantics (`fnmatch`) instead of the directory-prefix
    heuristic. This is the common case in practice: an implement stage's
    write_scope is often exact filenames, and a test freeze scope is often a
    suffix glob like `**/*.test.tsx` — those two only really collide if the
    concrete file's name actually matches the glob, not just because it
    lives in the same directory as files that would.
    """
    def has_wildcard(p):
        return "*" in p or "?" in p or "[" in p

    if not has_wildcard(pattern_a) and not has_wildcard(pattern_b):
        return pattern_a == pattern_b
    if not has_wildcard(pattern_a):
        return fnmatch.fnmatch(pattern_a, pattern_b)
    if not has_wildcard(pattern_b):
        return fnmatch.fnmatch(pattern_b, pattern_a)

    def prefix(p):
        parts = []
        for seg in p.split("/"):
            if "*" in seg or "?" in seg:
                break
            parts.append(seg)
        return "/".join(parts)

    pa, pb = prefix(pattern_a), prefix(pattern_b)
    if pa == "" or pb == "":
        return True
    return pa.startswith(pb) or pb.startswith(pa)


# ---------------------------------------------------------------------------
# The spec anchor triple
#
# ABSENT = WARN, PARTIAL = FAIL. That split is the whole design: a workflow
# generated from a standalone or hand-written spec has nothing to anchor to and
# must keep passing, but a workflow that *claims* an anchor is claiming a
# mechanically checkable fact, and half a claim is worse than none — it reads
# green while proving nothing. Same rule validate_spec.py applies to the chain
# marker, deliberately mirrored so the two ends of the chain say one thing.
# ---------------------------------------------------------------------------

ANCHOR_KEYS = ("raise_commit", "surface_hash", "extractor_version")
_SHA1_HEX = re.compile(r"^[0-9a-f]{40}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_POSITIVE_INT = re.compile(r"^[1-9][0-9]*$")


def _short(value):
    """First 12 hex chars — enough to identify, short enough to read."""
    return str(value)[:12]


def resolve_spec_path(source_spec, target):
    """Locate source_spec on disk: run-folder basename, then the path as given
    (cwd-relative), then run-folder-relative. First hit wins.

    The basename comes first on purpose: the spec committed *into the run
    folder* is the one the anchor was taken over, whatever repo-relative path
    workflow.yaml records."""
    candidates = [target / Path(source_spec).name,
                  Path(source_spec),
                  target / source_spec]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def check_spec_anchor(workflow, target):
    """(problems, warnings) for spec_anchor — presence, shape, comparability,
    and a real recompute of the surface it claims."""
    problems, warnings = [], []

    if "spec_anchor" not in workflow or workflow.get("spec_anchor") is None:
        warnings.append(
            "no spec_anchor — this workflow is not anchored to a raise commit "
            "(standalone/hand-written spec); staleness cannot be checked mechanically"
        )
        return problems, warnings

    anchor = workflow.get("spec_anchor")
    if not isinstance(anchor, dict):
        problems.append(
            "spec_anchor could not be parsed as a mapping — write it as an indented block "
            "(raise_commit:/surface_hash:/extractor_version: on their own lines), not an "
            "inline {...} mapping"
        )
        return problems, warnings

    # The hand parser has no int coercion: _parse_scalar("1") is the string "1".
    # Grade every value as text against its grammar, and only then compare ints.
    values = {}
    for key in ANCHOR_KEYS:
        raw = anchor.get(key)
        values[key] = "" if raw is None else str(raw).strip()
        if not values[key]:
            problems.append(
                f"spec_anchor is partial — '{key}' is missing; a partial anchor is a FAIL "
                f"(an absent anchor is a WARN)"
            )

    if values["raise_commit"] and not _SHA1_HEX.match(values["raise_commit"]):
        problems.append(
            f"spec_anchor.raise_commit is not a full 40-hex commit SHA: "
            f"'{values['raise_commit']}' — abbreviated SHAs are not comparable"
        )
    if values["surface_hash"] and not _SHA256_HEX.match(values["surface_hash"]):
        problems.append(f"spec_anchor.surface_hash is not a 64-hex sha256: "
                        f"'{values['surface_hash']}'")
    if values["extractor_version"] and not _POSITIVE_INT.match(values["extractor_version"]):
        problems.append(f"spec_anchor.extractor_version is not a positive integer: "
                        f"'{values['extractor_version']}'")

    if problems:
        return problems, warnings  # nothing below can mean anything on a broken anchor

    # Not-run is not passed. Without the sibling extractor the recorded
    # surface_hash is unverifiable, and what goes unverified — a spec that moved
    # after the raise — is invisible everywhere downstream.
    if EXTRACTOR_VERSION is None:
        problems.append(
            "spec_anchor present but requirement_surface.py is not beside this script — the "
            "recorded surface_hash cannot be verified (not-run is not passed; kestra-build "
            "emits both files into the run folder)"
        )
        return problems, warnings

    if int(values["extractor_version"]) != EXTRACTOR_VERSION:
        problems.append(
            f"spec_anchor.extractor_version {values['extractor_version']} ≠ this run's "
            f"requirement_surface.py EXTRACTOR_VERSION {EXTRACTOR_VERSION} — the hashes are "
            f"not comparable; re-fold (never diff hashes across versions)"
        )
        return problems, warnings

    source_spec = workflow.get("source_spec")
    if not source_spec:
        problems.append(
            "spec_anchor is present but 'source_spec' is missing — there is no spec to recompute "
            "the surface of, so the anchor can never be checked"
        )
        return problems, warnings

    spec_path = resolve_spec_path(str(source_spec), target)
    if spec_path is None:
        # A property of where this was invoked from, not of the artifact — a FAIL
        # here would make the validator unrunnable from outside the repo root.
        warnings.append(
            f"source_spec '{source_spec}' not found beside workflow.yaml, relative to the "
            f"current directory, or under '{target}' — the spec_anchor.surface_hash could not "
            f"be recomputed (re-run from the directory source_spec is relative to)"
        )
        return problems, warnings

    try:
        recomputed = extract_surface(spec_path.read_text()).surface_hash
    except SurfaceError as e:
        problems.append(
            f"the surface of {spec_path} cannot be extracted honestly ({e}) — a truncated "
            f"surface still hashes cleanly, so this is a false-fresh anchor, not a warning"
        )
        return problems, warnings
    except OSError as e:
        warnings.append(f"source_spec '{spec_path}' could not be read ({e}) — "
                        f"spec_anchor.surface_hash not recomputed")
        return problems, warnings

    if recomputed != values["surface_hash"]:
        problems.append(
            f"spec_anchor.surface_hash {_short(values['surface_hash'])} ≠ the surface of "
            f"{source_spec} recomputed now {_short(recomputed)} — the spec moved since the "
            f"fold; re-fold (kestra-build), do not edit the anchor"
        )

    return problems, warnings


# ---------------------------------------------------------------------------
# The sliced fold — the tickets[] map and the embedded ticket blocks
#
# Same posture as the anchor triple, one level down: absent is silence (a
# monolithic fold has no ticket set and is a legitimate shape), present is a
# mechanically checkable claim, and a partial claim is a FAIL. The three recorded
# copies of one fact — the file on disk, the delimiter hex in the brief, and
# tickets[].body_sha256 — are what close all four hand-edit routes
# (ticket-fold.md §4): edit the brief and the block stops matching the file; edit
# the file and the delimiter hex stops matching; edit both and body_sha256 stops
# matching; edit all three and touch an AC line and ac_hash stops matching the
# surface recomputed here (a four-way-consistent non-AC edit passes here; the
# next fold's F0 re-materialization catches it). The apparent redundancy is the
# enforcement.
# ---------------------------------------------------------------------------

# The five hash/marker fields graded per entry. `ref` is deliberately not one:
# it is provenance for a human, carries no recomputable claim, and grading a URL
# would invent a shape the tracker does not promise (workflow-schema.md says so
# in the field table, once).
TICKET_KEYS = ("id", "body_sha256", "ac_hash", "verified_against", "verified_at")

_BLOCK = re.compile(
    r"<!-- ticket:begin (\S+) sha256:([0-9a-f]{64}) -->(.*?)<!-- ticket:end \1 -->", re.S)
_BEGIN = re.compile(r"<!-- ticket:begin (\S+) sha256:([0-9a-f]{64}) -->")
_STAGE_ID = re.compile(r"^\s*-\s+id:\s*(\S+)\s*$", re.M)
_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# Narrow on purpose: a wider strip eats legitimate parentheses out of a requirement.
_SOURCE_LABEL = re.compile(r"\s*\(Source:\s*[^()]*\)\s*$")


def _sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_ac(line):
    """A ticket AC line, normalized exactly as requirement_surface._units does
    (list marker, checkbox, whitespace), then the trailing explicit Source label
    stripped. Returns (normalized, explicit_source or None)."""
    s = _ws(_CHECKBOX.sub("", _BULLET.sub("", line.strip())))
    m = _SOURCE_LABEL.search(s)
    explicit = None
    if m:
        explicit = m.group(0).strip()[len("(Source:"):].rstrip(")").strip()
        s = _SOURCE_LABEL.sub("", s)
    return s, explicit


def _ticket_ac_lines(text):
    """Non-blank body lines of a ticket's '## Acceptance criteria' section."""
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line[3:].strip().lower() == "acceptance criteria"
            continue
        if on and line.strip():
            out.append(line)
    return out


def _load_surface(workflow, target, problems, warnings):
    """The spec's surface, or None with the reason already recorded. FAIL when the
    extractor or the spec is unusable (an unverifiable ac_hash is the thing this
    check exists to catch); WARN when the spec merely could not be located from
    here, which is a property of the invocation, not of the artifact."""
    if EXTRACTOR_VERSION is None:
        problems.append(
            "this workflow carries a sliced ticket set but requirement_surface.py is not beside "
            "this script — the recorded ac_hash values cannot be recomputed (not-run is not "
            "passed; kestra-build emits both files into the run folder)"
        )
        return None
    source_spec = str(workflow.get("source_spec") or "0-spec.md")
    spec_path = resolve_spec_path(source_spec, target)
    if spec_path is None:
        warnings.append(
            f"source_spec '{source_spec}' not found beside workflow.yaml, relative to the current "
            f"directory, or under '{target}' — the recorded ac_hash values could not be recomputed "
            f"(re-run from the directory source_spec is relative to)"
        )
        return None
    try:
        return extract_surface(spec_path.read_text())
    except SurfaceError as e:
        problems.append(
            f"the surface of {spec_path} cannot be extracted honestly ({e}) — a truncated surface "
            f"still hashes cleanly, so every ac_hash compared against it would be false-fresh"
        )
    except OSError as e:
        warnings.append(f"source_spec '{spec_path}' could not be read ({e}) — the recorded "
                        f"ac_hash values were not recomputed")
    return None


def check_ticket_fold(workflow, raw, target):
    """(problems, warnings) for a sliced fold. Returns ([], []) untouched for a
    monolithic one — no tickets: map, no ticket blocks, no tickets/ directory."""
    problems, warnings = [], []

    entries = workflow.get("tickets")
    recorded = {}
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id"):
                recorded[str(entry["id"]).strip()] = entry
    blocks = list(_BLOCK.finditer(raw))
    ticket_dir = target / "tickets"
    files = sorted(ticket_dir.glob("*.md")) if ticket_dir.is_dir() else []

    if not entries and not files and not _BEGIN.search(raw):
        return problems, warnings

    if entries is not None and not isinstance(entries, list):
        problems.append(
            "tickets: could not be parsed as a sequence of mappings — write it as a block sequence "
            "('- id:' on its own line, the rest indented under it), not an inline [...] list"
        )

    if len(_BEGIN.findall(raw)) != len(blocks):
        problems.append("a ticket:begin delimiter has no matching ticket:end for the same id — a "
                        "partial delimiter, same family as a partial anchor")

    # --- per-ticket recompute: body hash always, ac_hash when the spec is readable
    surface = _load_surface(workflow, target, problems, warnings) if files else None
    rows = dict(surface.ac_rows) if surface else {}
    sources = {ac_id: (row.split(" | ")[1] if " | " in row else "")
               for ac_id, row in (surface.ac_rows if surface else [])}

    derived, claims = {}, {}
    for path in files:
        tid = path.stem
        derived[tid] = {"body_sha256": _sha256_file(path), "ac_hash": None}
        if surface is None:
            continue
        matched = []
        for n, line in enumerate(_ticket_ac_lines(path.read_text()), 1):
            text, explicit = _normalize_ac(line)
            if text not in rows:
                problems.append(
                    f'ticket {tid} AC {n} "{text}" matches no row in the spec\'s AC Coverage Map — '
                    f"the slice set and the raised spec disagree. Either the spec moved after "
                    f"slicing (re-run to-tickets over the current spec — a suggestion, if "
                    f"installed), or the AC was edited on the tracker. kestra-build does not "
                    f"reconcile this; it stops."
                )
                continue
            if not sources[text]:
                problems.append(
                    f'sliced AC "{text}" resolves to an AC Coverage Map row with an empty Source '
                    f"cell — a green column that lies (validate_spec.py flags the same fact on the "
                    f"spec side)."
                )
            elif explicit is not None and explicit != sources[text]:
                problems.append(
                    f'ticket {tid} AC {n} claims (Source: {explicit}) but the AC Coverage Map row '
                    f'says "{sources[text]}" — the map is the single owner; a ticket may echo it, '
                    f"never contradict it."
                )
            matched.append(text)
            claims.setdefault(text, []).append(tid)
        # Serialized in the spec's Coverage Map order, never the ticket's own bullet
        # order — reordering ACs inside a ticket is presentation and must move nothing.
        ordered = [row for ac_id, row in surface.ac_rows if ac_id in set(matched)]
        derived[tid]["ac_hash"] = hashlib.sha256(
            ("\n".join(ordered) + "\n").encode("utf-8")).hexdigest()

    if surface:
        for ac_id, _ in surface.ac_rows:
            owners = claims.get(ac_id, [])
            if not owners:
                warnings.append(f'AC Coverage Map row "{ac_id}" is covered by no ticket in this set')
            elif len(owners) > 1:
                warnings.append(f'AC Coverage Map row "{ac_id}" is claimed by {sorted(owners)}')

    # --- the tickets[] map against the files, in both directions
    anchor = workflow.get("spec_anchor")
    raise_commit = str(anchor.get("raise_commit") or "").strip() if isinstance(anchor, dict) else ""
    if not _SHA1_HEX.match(raise_commit):
        # No anchor, or an anchor whose own shape is already a FAIL: check_spec_anchor
        # owns that verdict, and cross-checking every ticket against a value known to
        # be malformed would report one defect N+1 times.
        raise_commit = ""
    for tid in sorted(derived):
        entry = recorded.get(tid)
        if entry is None:
            problems.append(f"tickets/{tid}.md exists but no tickets[] entry names it — the map "
                            f"and the files are one fact")
            continue
        for key in TICKET_KEYS:
            if not str(entry.get(key) or "").strip():
                problems.append(f"tickets['{tid}'] is partial — '{key}' is missing")
        if str(entry.get("body_sha256") or "").strip() != derived[tid]["body_sha256"]:
            problems.append(f"tickets['{tid}'].body_sha256 {_short(entry.get('body_sha256'))} ≠ "
                            f"sha256(tickets/{tid}.md) {_short(derived[tid]['body_sha256'])} "
                            f"— re-fold")
        if derived[tid]["ac_hash"] is not None \
                and str(entry.get("ac_hash") or "").strip() != derived[tid]["ac_hash"]:
            problems.append(f"tickets['{tid}'].ac_hash {_short(entry.get('ac_hash'))} ≠ recomputed "
                            f"{_short(derived[tid]['ac_hash'])} — re-fold")
        if raise_commit and str(entry.get("verified_against") or "").strip() != raise_commit:
            problems.append(f"tickets['{tid}'].verified_against "
                            f"{_short(entry.get('verified_against'))} ≠ spec_anchor.raise_commit "
                            f"{_short(raise_commit)} — the ticket map was refreshed against a "
                            f"different raise; re-fold")
        if not _ISO_Z.match(str(entry.get("verified_at") or "")):
            problems.append(f"tickets['{tid}'].verified_at is not ISO-8601 UTC "
                            f"(YYYY-MM-DDTHH:MM:SSZ): '{entry.get('verified_at')}'")
    for tid in sorted(recorded):
        if tid not in derived:
            problems.append(f"tickets[] entry '{tid}' has no tickets/{tid}.md")

    # --- the embedded blocks, read from the RAW text (the parsed brief is lossy)
    stage_at = [(m.start(), m.group(1)) for m in _STAGE_ID.finditer(raw)]

    def owning_stage(offset):
        owner = "<before the first stage>"
        for pos, sid in stage_at:
            if pos < offset:
                owner = sid
        return owner

    per_stage = {}
    for m in blocks:
        tid, hex_, body = m.group(1), m.group(2), m.group(3)
        stage = owning_stage(m.start())
        per_stage.setdefault(stage, []).append(tid)
        path = ticket_dir / f"{tid}.md"
        if not path.exists():
            problems.append(f"stage '{stage}' embeds ticket '{tid}' but tickets/{tid}.md does not "
                            f"exist")
            continue
        on_disk = _sha256_file(path)
        if hex_ != on_disk:
            problems.append(f"ticket '{tid}' body changed since the fold (file {_short(on_disk)} ≠ "
                            f"brief {_short(hex_)}) — re-fold, never hand-edit the brief")
        if " ".join(body.split()) != " ".join(path.read_text().split()):
            problems.append(f"stage '{stage}' embedded ticket block does not match "
                            f"tickets/{tid}.md — the brief was hand-edited; re-fold")
        for seq in (" #", "---"):
            if any((seq in ln if seq == " #" else ln.strip() == seq) for ln in body.splitlines()):
                warnings.append(f"stage '{stage}' embedded ticket body contains '{seq}', which "
                                f"this repo's YAML-subset parser strips from the *parsed* brief — "
                                f"consumers must read the brief from the raw file")
        if tid not in recorded:
            problems.append(f"stage '{stage}' embeds ticket '{tid}' which is absent from tickets:")
    for stage, ids in sorted(per_stage.items()):
        if len(ids) > 1:
            problems.append(f"stage '{stage}' embeds {len(ids)} ticket blocks {ids} — a brief with "
                            f"two blocks has no unambiguous owner for on_fail.target routing")
    for tid in sorted(derived):
        if not any(m.group(1) == tid for m in blocks):
            problems.append(f"ticket '{tid}' is embedded in no stage brief")

    return problems, warnings


def validate(workflow, state, target=None, raw=""):
    problems = []
    warnings = []
    target = target or Path(".")

    anchor_problems, anchor_warnings = check_spec_anchor(workflow, target)
    problems.extend(anchor_problems)
    warnings.extend(anchor_warnings)

    # The fold group reads `raw` — the un-parsed workflow.yaml text, which main()
    # always passes. An empty `raw` with a ticket set on disk is still checked:
    # every block-side check then reports the missing block rather than skipping.
    fold_problems, fold_warnings = check_ticket_fold(workflow, raw, target)
    problems.extend(fold_problems)
    warnings.extend(fold_warnings)

    stages = workflow.get("stages") or []
    if not stages:
        return problems + ["workflow.yaml has no stages"], warnings

    ids = [s.get("id") for s in stages]
    seen = set()
    for sid in ids:
        if not sid:
            problems.append("a stage is missing 'id'")
            continue
        if sid in seen:
            problems.append(f"duplicate stage id: {sid}")
        seen.add(sid)

    by_id = {s["id"]: s for s in stages if s.get("id")}

    # depends_on references exist
    for s in stages:
        sid = s.get("id", "<unknown>")
        deps = s.get("depends_on")
        if deps is None:
            problems.append(f"stage '{sid}' missing depends_on (use [] for a start stage)")
            deps = []
        for d in deps:
            if d not in by_id:
                problems.append(f"stage '{sid}' depends_on unknown stage '{d}'")

    # cycle detection
    def has_cycle():
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {sid: WHITE for sid in by_id}

        def visit(sid, chain):
            if color.get(sid) == GRAY:
                return chain + [sid]
            if color.get(sid) == BLACK:
                return None
            color[sid] = GRAY
            for d in (by_id[sid].get("depends_on") or []):
                if d in by_id:
                    result = visit(d, chain + [sid])
                    if result:
                        return result
            color[sid] = BLACK
            return None

        for sid in by_id:
            if color[sid] == WHITE:
                result = visit(sid, [])
                if result:
                    return result
        return None

    cycle = has_cycle()
    if cycle:
        problems.append(f"dependency cycle: {' -> '.join(cycle)}")

    # exactly one freeze_after: true
    frozen = [s["id"] for s in stages if s.get("freeze_after") is True]
    if len(frozen) == 0:
        warnings.append("no stage has freeze_after: true — no test-hash freeze point exists")
    elif len(frozen) > 1:
        problems.append(f"more than one stage has freeze_after: true: {frozen} — only the "
                         f"stage that generates/freezes tests should set this")

    frozen_scopes = []
    if frozen:
        frozen_scopes = by_id[frozen[0]].get("write_scope") or []
        if not frozen_scopes:
            problems.append(
                f"stage '{frozen[0]}' sets freeze_after: true but its write_scope is empty — the "
                f"test-hash is computed from the freeze stage's own write_scope, so this snapshots "
                f"nothing and the freeze invariant silently does not exist. Give the freeze stage "
                f"the test paths it is freezing."
            )

    memo = {}

    def ancestors(sid, visiting=None):
        if visiting is None:
            visiting = set()
        if sid in memo:
            return memo[sid]
        if sid in visiting:
            return set()  # already reported as a cycle above; don't recurse forever
        visiting = visiting | {sid}
        result = set()
        for d in (by_id[sid].get("depends_on") or []):
            if d in by_id:
                result.add(d)
                result |= ancestors(d, visiting)
        memo[sid] = result
        return result

    # write_scope checks
    #
    # The freeze only takes effect when the freeze stage *passes*, so a stage that
    # runs strictly before it may legitimately own test paths — that's how tests get
    # written and revised in the first place. The prohibition applies to everything
    # that could run at or after the freeze point. Ancestors of the freeze stage are
    # therefore exempt; when a cycle was already found, "runs before" isn't
    # well-defined, so fall back to flagging every overlap.
    pre_freeze = ancestors(frozen[0]) if (frozen and not cycle) else set()
    for s in stages:
        sid = s.get("id", "<unknown>")
        ws = s.get("write_scope")
        if ws is None:
            problems.append(f"stage '{sid}' missing write_scope (use [] if it produces no diff)")
            continue
        if frozen and sid != frozen[0] and sid not in pre_freeze:
            for scope in ws:
                for fscope in frozen_scopes:
                    if fnmatch_overlap(scope, fscope):
                        problems.append(
                            f"stage '{sid}' write_scope '{scope}' overlaps the frozen test "
                            f"scope '{fscope}' owned by '{frozen[0]}' — after the freeze, only a "
                            f"reworking pass may touch test paths"
                        )

    # pairwise overlap for stages that are NOT ordered relative to each other.
    # Skipped entirely when a cycle was already found above — ancestor chains
    # aren't well-defined until that's fixed, and the cycle problem alone is
    # enough to block treating this workflow as frozen.
    all_ids = list(by_id.keys()) if not cycle else []
    for i in range(len(all_ids)):
        for j in range(i + 1, len(all_ids)):
            a, b = all_ids[i], all_ids[j]
            if a in ancestors(b) or b in ancestors(a):
                continue  # ordered relative to each other, not a real collision risk
            ws_a = by_id[a].get("write_scope") or []
            ws_b = by_id[b].get("write_scope") or []
            if not ws_a or not ws_b:
                continue
            for sa in ws_a:
                for sb in ws_b:
                    if fnmatch_overlap(sa, sb):
                        warnings.append(
                            f"independent stages '{a}' and '{b}' have overlapping write_scope "
                            f"('{sa}' vs '{sb}') — if kestra-run may run them in parallel, this is "
                            f"a real collision risk, not just a style nit"
                        )

    # exit_criteria / on_fail shape
    valid_actions = {"fixing", "reworking", "blocked"}
    for s in stages:
        sid = s.get("id", "<unknown>")
        ec = s.get("exit_criteria")
        if not ec:
            problems.append(f"stage '{sid}' missing exit_criteria")
        elif not isinstance(ec, dict):
            # e.g. an inline flow mapping `{type: command, ...}`, which this
            # deliberately-minimal parser doesn't read. Report it instead of
            # crashing — a validator that tracebacks on malformed input is
            # useless exactly when it's needed most.
            problems.append(
                f"stage '{sid}' exit_criteria could not be parsed as a mapping — write it as an "
                f"indented block (type:/run: on their own lines), not an inline {{...}} mapping"
            )
        else:
            t = ec.get("type")
            if t not in ("command", "artifact_exists", "human_approval"):
                problems.append(f"stage '{sid}' exit_criteria.type is missing/invalid: {t!r}")
            if t == "command" and not ec.get("run"):
                problems.append(f"stage '{sid}' exit_criteria.type is 'command' but 'run' is empty")
            if t == "artifact_exists" and not ec.get("artifact"):
                problems.append(f"stage '{sid}' exit_criteria.type is 'artifact_exists' but 'artifact' is empty")
            if "progress" in ec and not str(ec.get("progress") or "").strip():
                problems.append(
                    f"stage '{sid}' exit_criteria.progress is empty — omit the field or give it "
                    f"the spec's own progress fragment"
                )

        ec_type = ec.get("type") if isinstance(ec, dict) else None
        of = s.get("on_fail")
        if not of and ec_type != "human_approval":
            problems.append(f"stage '{sid}' missing on_fail")
            continue
        if of and not isinstance(of, dict):
            problems.append(
                f"stage '{sid}' on_fail could not be parsed as a mapping — write it as an "
                f"indented block, not an inline {{...}} mapping"
            )
        elif of:
            action = of.get("action")
            if action not in valid_actions:
                problems.append(f"stage '{sid}' on_fail.action is missing/invalid: {action!r}")
            if action == "fixing":
                if of.get("max_attempts") is None:
                    problems.append(f"stage '{sid}' on_fail.action=fixing missing max_attempts")
                if of.get("escalate_at") is None:
                    problems.append(f"stage '{sid}' on_fail.action=fixing missing escalate_at")
                ws = s.get("write_scope") or []
                target = of.get("target")
                if not ws and not target:
                    problems.append(
                        f"stage '{sid}' has write_scope: [] and on_fail.action=fixing but no "
                        f"'target' — the orchestrator would have nowhere to apply a fix"
                    )
                if target and target not in by_id:
                    problems.append(f"stage '{sid}' on_fail.target references unknown stage '{target}'")
            if action in ("reworking", "blocked") and not of.get("reason"):
                problems.append(f"stage '{sid}' on_fail.action={action} missing 'reason'")

    # human_approval stages skip on_fail by schema convention — nothing further to check there.

    # reachability: every stage should be reachable from a start stage ([] depends_on)
    starts = [s["id"] for s in stages if s.get("depends_on") == []]
    if not starts:
        problems.append("no stage has depends_on: [] — nothing can ever start")
    else:
        reached = set(starts)
        changed = True
        while changed:
            changed = False
            for s in stages:
                sid = s.get("id")
                if sid in reached:
                    continue
                deps = s.get("depends_on") or []
                if deps and all(d in reached for d in deps):
                    reached.add(sid)
                    changed = True
        unreachable = set(by_id) - reached
        if unreachable:
            problems.append(f"stages unreachable from any start stage: {sorted(unreachable)}")

    # state.json alignment
    if state is not None:
        state_stage_ids = set((state.get("stages") or {}).keys())
        workflow_ids = set(by_id.keys())
        if state_stage_ids and state_stage_ids != workflow_ids:
            missing_in_state = workflow_ids - state_stage_ids
            extra_in_state = state_stage_ids - workflow_ids
            if missing_in_state:
                problems.append(f"state.json missing stages present in workflow.yaml: {sorted(missing_in_state)}")
            if extra_in_state:
                problems.append(f"state.json has stages not present in workflow.yaml: {sorted(extra_in_state)}")

        if state.get("test_hash") not in (None, "null"):
            warnings.append("state.json.test_hash is not null at initial state — expected null until the freeze stage passes")

    return problems, warnings


def main():
    if len(sys.argv) != 2:
        print("usage: python3 validate_workflow.py <dir-containing-workflow.yaml-and-state.json>")
        sys.exit(2)

    target = Path(sys.argv[1])
    wf_path = target / "workflow.yaml"
    state_path = target / "state.json"

    if not wf_path.exists():
        print(f"FAIL: {wf_path} not found")
        sys.exit(1)

    raw = wf_path.read_text()
    workflow = parse_yaml(raw)
    state = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except json.JSONDecodeError as e:
            print(f"FAIL: state.json is not valid JSON: {e}")
            sys.exit(1)
    else:
        print(f"WARN: {state_path} not found — skipping state.json alignment checks")

    problems, warnings = validate(workflow, state, target, raw)

    for w in warnings:
        print(f"WARN: {w}")

    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        print(f"\n{len(problems)} problem(s) found — fix before treating this workflow as frozen.")
        sys.exit(1)

    print(f"PASS — {len(workflow.get('stages') or [])} stages, structurally sound.")
    sys.exit(0)


if __name__ == "__main__":
    main()
