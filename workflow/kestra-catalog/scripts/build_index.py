#!/usr/bin/env python3
"""Build a central, searchable HTML catalog of every acceptance criterion in a
repo's kestra runs.

No third-party dependencies (PyYAML is frequently unavailable in a plain
python3 install) — parses the constrained YAML subset areas.yml actually uses
and the Markdown shapes 0-spec.md actually emits. It does not aim to be a
general YAML or Markdown parser.

This script is copied by the kestra-catalog skill into the target repo at
workflows/docs/testcases/ and committed with areas.yml and index.html, so
regenerating the catalog never requires the skill to be installed on whatever
machine (or CI runner) does it.

Usage:
    python3 build_index.py [--runs DIR] [--areas FILE] [--out FILE] [--check]

Defaults are resolved relative to this script's own location, matching the
layout the skill installs:

    workflows/runs/                  <- --runs
    workflows/docs/testcases/
        areas.yml                    <- --areas
        build_index.py               (this file)
        index.html                   <- --out

Exits 0 on success, printing a WARN line per run that areas.yml does not
assign to an area (those land in an "unassigned" group rather than failing —
an unmapped run is a taxonomy gap for a human to close, not a broken build).
With --check, writes nothing and exits 1 if index.html is missing or stale,
for use as a CI guard.
"""

import argparse
import fnmatch
import html
import json
import os
import re
import sys
import unicodedata

# --------------------------------------------------------------------------
# areas.yml
# --------------------------------------------------------------------------

# Deliberately not a YAML parser. areas.yml is hand-edited by humans and its
# shape is fixed by the skill's own template, so a line-oriented reader that
# fails loudly on anything unexpected beats a dependency.
#
#   areas:
#     <area-id>:
#       title: <human label>
#       runs:
#         - <run-id or glob>
#         - ...
#
# `runs: [a, b]` on one line is accepted too, since that is what a human
# writing a one-entry area tends to reach for.


class AreaSpec:
    def __init__(self, area_id, title):
        self.id = area_id
        self.title = title or area_id
        self.patterns = []


def parse_areas(path):
    if not os.path.exists(path):
        return [], ["areas.yml not found at %s — every run will be unassigned" % path]

    areas = []
    warnings = []
    current = None
    in_runs = False
    seen_root = False

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue

            indent = len(line) - len(line.lstrip(" "))
            body = line.strip()

            if indent == 0:
                if body == "areas:":
                    seen_root = True
                    current, in_runs = None, False
                else:
                    warnings.append("%s:%d ignored unknown top-level key %r" % (path, lineno, body))
                continue

            if not seen_root:
                warnings.append("%s:%d content before 'areas:' — ignored" % (path, lineno))
                continue

            if indent == 2 and body.endswith(":"):
                current = AreaSpec(body[:-1].strip(), None)
                areas.append(current)
                in_runs = False
                continue

            if current is None:
                warnings.append("%s:%d content outside any area — ignored" % (path, lineno))
                continue

            if indent == 4 and body.startswith("title:"):
                current.title = body[len("title:"):].strip().strip("\"'") or current.id
                in_runs = False
                continue

            if indent == 4 and body.startswith("runs:"):
                rest = body[len("runs:"):].strip()
                if rest.startswith("[") and rest.endswith("]"):
                    for item in rest[1:-1].split(","):
                        item = item.strip().strip("\"'")
                        if item:
                            current.patterns.append(item)
                    in_runs = False
                else:
                    in_runs = True
                continue

            if in_runs and body.startswith("- "):
                current.patterns.append(body[2:].strip().strip("\"'"))
                continue

            warnings.append("%s:%d unrecognized line %r — ignored" % (path, lineno, body))

    return areas, warnings


# --------------------------------------------------------------------------
# 0-spec.md
# --------------------------------------------------------------------------

# Specs written before the no-emoji rule prefix their headings with a decorative
# emoji, and both "Acceptance Criteria" and the abbreviated "AC" are in the wild.
# Match on the text left after stripping symbol characters so every generation
# of the template resolves to the same section.
_AC_HEADING = re.compile(r"^\s*(acceptance criteria|ac)\s*$", re.IGNORECASE)
_AC_ID = re.compile(r"^\s*(AC-\d+[a-z]?)\s*[:.\)]?\s*", re.IGNORECASE)
_BULLET = re.compile(r"^\s*[-*+]\s+(?:\[( |x|X)\]\s*)?(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _heading_text(raw):
    """Strip decorative symbols and trailing parentheticals from a heading."""
    text = raw.strip()
    text = re.sub(r"\s*\*\(.*?\)\*\s*$", "", text)  # "## Foo *(needs_sa: true)*"
    kept = [c for c in text if not unicodedata.category(c).startswith("S")]
    return "".join(kept).strip()


def extract_acs(spec_path):
    """Return (list of AC dicts, warning or None)."""
    try:
        with open(spec_path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        return [], "cannot read %s: %s" % (spec_path, exc)

    start = None
    depth = 0
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and _AC_HEADING.match(_heading_text(m.group(2))):
            start, depth = i + 1, len(m.group(1))
            break

    if start is None:
        return [], "no Acceptance Criteria heading in %s" % spec_path

    # Collect raw bullets, folding indented continuation lines into the bullet
    # they belong to — the template wraps long Given-When-Then ACs across lines.
    bullets = []
    for line in lines[start:]:
        m = _HEADING.match(line)
        if m and len(m.group(1)) <= depth:
            break
        b = _BULLET.match(line)
        if b:
            bullets.append([b.group(2).strip()])
        elif bullets and line.strip():
            bullets[-1].append(line.strip())

    acs = []
    for n, parts in enumerate(bullets, 1):
        text = " ".join(p for p in parts if p).strip()
        if not text:
            continue
        m = _AC_ID.match(text)
        if m:
            local_id, text = m.group(1).upper(), text[m.end():].strip()
        else:
            local_id = "AC-%d" % n
        if text:
            acs.append({"local_id": local_id, "text": text})

    if not acs:
        return [], "Acceptance Criteria section is empty in %s" % spec_path
    return acs, None


def run_status(run_dir):
    """Status of a run, read off state.json — never inferred from the spec."""
    path = os.path.join(run_dir, "state.json")
    if not os.path.exists(path):
        return "legacy"
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return "unknown"

    stages = state.get("stages")
    statuses = []
    if isinstance(stages, dict):
        statuses = [v.get("status") for v in stages.values() if isinstance(v, dict)]
    elif isinstance(stages, list):
        statuses = [v.get("status") for v in stages if isinstance(v, dict)]

    if not statuses:
        return "unknown"
    if all(s == "passed" for s in statuses):
        return "done"
    if any(s == "blocked" for s in statuses):
        return "blocked"
    return "in-progress"


STATUS_LABEL = {
    "done": "ผ่าน pipeline ครบ",
    "in-progress": "กำลังทำ",
    "blocked": "ค้าง",
    "legacy": "legacy (ไม่มี state.json)",
    "unknown": "อ่าน state.json ไม่ได้",
}


def collect_runs(runs_dir):
    runs, warnings = [], []
    if not os.path.isdir(runs_dir):
        return runs, ["runs directory not found: %s" % runs_dir]

    for name in sorted(os.listdir(runs_dir)):
        run_dir = os.path.join(runs_dir, name)
        spec = os.path.join(run_dir, "0-spec.md")
        if not os.path.isdir(run_dir) or not os.path.exists(spec):
            continue
        acs, warn = extract_acs(spec)
        if warn:
            warnings.append(warn)
        if not acs:
            continue
        for ac in acs:
            ac["id"] = "%s/%s" % (name, ac["local_id"])
        runs.append({
            "id": name,
            "spec": spec,
            "status": run_status(run_dir),
            "acs": acs,
        })
    return runs, warnings


def assign_areas(runs, areas):
    """Map each run to the first area whose patterns match it."""
    grouped = [{"id": a.id, "title": a.title, "runs": []} for a in areas]
    by_id = {g["id"]: g for g in grouped}
    unassigned = []

    for run in runs:
        for area in areas:
            if any(fnmatch.fnmatch(run["id"], p) for p in area.patterns):
                by_id[area.id]["runs"].append(run)
                break
        else:
            unassigned.append(run)

    grouped = [g for g in grouped if g["runs"]]
    if unassigned:
        grouped.append({
            "id": "unassigned",
            "title": "ยังไม่ได้จัดกลุ่ม — เติมใน areas.yml",
            "runs": unassigned,
        })
    return grouped, unassigned


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def inline_md(text):
    """Escape, then restore the two inline marks the AC template actually uses."""
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


# A Given-When-Then AC written as one paragraph is the single hardest thing to
# read in the catalog, and specs write the keywords three different ways: bold
# (`**When**`), bare after a comma, or bare at the very start. Match all three,
# but only treat a hit as a clause boundary — never mid-sentence prose.
# Lowercase "and"/"but" after a comma is ordinary prose, so only the three real
# scenario keywords are recognized in lowercase; And/But need a capital or bold.
_GWT = re.compile(
    r"(?:\*\*(?P<bold>Given|When|Then|And|But)\*\*"
    r"|(?:^|(?<=[,;]\s))(?P<bare>Given|When|Then|And|But)\b"
    r"|(?<=[,;]\s)(?P<low>given|when|then)\b)\s*,?\s+"
)


def split_gwt(text):
    """Split a Given-When-Then AC into (keyword, clause) pairs, or None.

    Returns None unless the text really is a scenario — a stray "And" in an
    ordinary sentence must not turn that sentence into a fake clause list.
    """
    matches = list(_GWT.finditer(text))
    if not matches:
        return None

    words = [(m.group("bold") or m.group("bare") or m.group("low")).capitalize() for m in matches]
    if "Then" not in words or not ({"Given", "When"} & set(words)):
        return None
    if matches[0].start() != 0:
        return None  # prose that merely mentions the keywords partway through

    clauses = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip().rstrip(",")
        if body:
            clauses.append((words[i], body))
    return clauses or None


CSS = """
:root { color-scheme: light dark; --bg:#fff; --fg:#1a1a1a; --muted:#6b7280;
  --line:#e5e7eb; --card:#f9fafb; --accent:#2563eb; }
@media (prefers-color-scheme: dark) { :root { --bg:#111317; --fg:#e6e6e6;
  --muted:#9ca3af; --line:#2a2f37; --card:#181b20; --accent:#60a5fa; } }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
  "Noto Sans Thai","Helvetica Neue",sans-serif; }
.wrap { max-width: 1000px; margin: 0 auto; }
h1 { font-size:22px; margin:0 0 4px; }
.sub { color:var(--muted); font-size:13px; margin-bottom:20px; }
.controls { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px;
  position:sticky; top:0; background:var(--bg); padding:10px 0; z-index:2;
  border-bottom:1px solid var(--line); }
input,select { font:inherit; padding:7px 10px; border:1px solid var(--line);
  border-radius:6px; background:var(--card); color:var(--fg); }
input { flex:1; min-width:220px; }
.area { margin-bottom:28px; }
.area > h2 { font-size:17px; margin:0 0 2px; }
.area-meta { color:var(--muted); font-size:12px; margin-bottom:10px; }
.run { border:1px solid var(--line); border-radius:8px; margin-bottom:10px;
  overflow:hidden; }
.run > summary { cursor:pointer; padding:10px 12px; background:var(--card);
  display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.run-id { font-weight:600; font-size:14px; }
.badge { font-size:11px; padding:2px 7px; border-radius:99px;
  border:1px solid var(--line); color:var(--muted); white-space:nowrap; }
.badge.done { border-color:#16a34a; color:#16a34a; }
.badge.in-progress { border-color:#d97706; color:#d97706; }
.badge.blocked { border-color:#dc2626; color:#dc2626; }
.spec-link { margin-left:auto; font-size:12px; color:var(--accent); }
ul.acs { list-style:none; margin:0; padding:4px 12px 12px; }
ul.acs li { padding:8px 0; border-top:1px solid var(--line); }
.ac-id { display:block; font-size:11px; color:var(--muted); margin-bottom:4px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.clause { display:flex; gap:8px; align-items:baseline; padding:1px 0; }
.clause.plain { display:block; }
.kw { flex:0 0 3.4em; font-weight:600; font-size:12px; text-transform:uppercase;
  letter-spacing:.04em; color:var(--muted); }
.txt { flex:1; min-width:0; }
code { background:var(--card); padding:1px 4px; border-radius:4px;
  font-size:13px; border:1px solid var(--line); }
.empty { color:var(--muted); padding:20px 0; display:none; }
[hidden] { display:none !important; }
"""

JS = """
(function () {
  var q = document.getElementById('q'),
      areaSel = document.getElementById('area'),
      statusSel = document.getElementById('status'),
      count = document.getElementById('count'),
      empty = document.getElementById('empty'),
      areas = [].slice.call(document.querySelectorAll('.area'));

  function apply() {
    var term = q.value.trim().toLowerCase(),
        wantArea = areaSel.value, wantStatus = statusSel.value, shown = 0;

    areas.forEach(function (area) {
      var areaOk = !wantArea || area.dataset.area === wantArea, anyRun = false;

      [].slice.call(area.querySelectorAll('.run')).forEach(function (run) {
        var statusOk = !wantStatus || run.dataset.status === wantStatus,
            anyAc = false;

        [].slice.call(run.querySelectorAll('li')).forEach(function (li) {
          var hit = !term || li.dataset.search.indexOf(term) !== -1;
          li.hidden = !hit;
          if (hit) { anyAc = true; shown++; }
        });

        var show = areaOk && statusOk && anyAc;
        run.hidden = !show;
        if (show) { anyRun = true; if (term) run.open = true; }
      });

      area.hidden = !anyRun;
    });

    count.textContent = shown;
    empty.style.display = shown ? 'none' : 'block';
  }

  [q, areaSel, statusSel].forEach(function (el) {
    el.addEventListener('input', apply);
    el.addEventListener('change', apply);
  });
})();
"""


def render(grouped, runs_dir, out_path):
    total_acs = sum(len(r["acs"]) for g in grouped for r in g["runs"])
    total_runs = sum(len(g["runs"]) for g in grouped)
    rel_root = os.path.relpath(runs_dir, os.path.dirname(os.path.abspath(out_path)))

    parts = [
        "<!doctype html>",
        '<html lang="th"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>Test Case Catalog</title>",
        "<style>%s</style></head><body><div class='wrap'>" % CSS,
        "<h1>Test Case Catalog</h1>",
        '<p class="sub">acceptance criteria ทั้งหมดที่ดึงจาก <code>%s</code> — '
        "ไฟล์นี้ generate จาก build_index.py ห้ามแก้ด้วยมือ "
        "แก้ที่ <code>0-spec.md</code> ต้นทางแล้ว generate ใหม่</p>" % html.escape(rel_root),
        '<div class="controls">',
        '<input id="q" type="search" placeholder="ค้นหา AC, run, ข้อความ…">',
        '<select id="area"><option value="">ทุก area</option>',
    ]
    for g in grouped:
        parts.append('<option value="%s">%s</option>' % (html.escape(g["id"]), html.escape(g["title"])))
    parts.append("</select>")

    parts.append('<select id="status"><option value="">ทุกสถานะ</option>')
    for key in ("done", "in-progress", "blocked", "legacy", "unknown"):
        parts.append('<option value="%s">%s</option>' % (key, html.escape(STATUS_LABEL[key])))
    parts.append("</select></div>")

    parts.append(
        '<p class="sub"><strong id="count">%d</strong> AC · %d run · %d area</p>'
        % (total_acs, total_runs, len(grouped))
    )

    for g in grouped:
        n_acs = sum(len(r["acs"]) for r in g["runs"])
        parts.append('<section class="area" data-area="%s">' % html.escape(g["id"]))
        parts.append("<h2>%s</h2>" % html.escape(g["title"]))
        parts.append('<p class="area-meta">%d run · %d AC</p>' % (len(g["runs"]), n_acs))

        for run in g["runs"]:
            status = run["status"]
            spec_rel = os.path.relpath(run["spec"], os.path.dirname(os.path.abspath(out_path)))
            parts.append('<details class="run" data-status="%s">' % html.escape(status))
            parts.append(
                '<summary><span class="run-id">%s</span>'
                '<span class="badge %s">%s</span>'
                '<span class="badge">%d AC</span>'
                '<a class="spec-link" href="%s">0-spec.md</a></summary>'
                % (
                    html.escape(run["id"]),
                    html.escape(status),
                    html.escape(STATUS_LABEL[status]),
                    len(run["acs"]),
                    html.escape(spec_rel),
                )
            )
            parts.append('<ul class="acs">')
            for ac in run["acs"]:
                search = html.escape((ac["id"] + " " + ac["text"]).lower(), quote=True)
                clauses = split_gwt(ac["text"])
                if clauses:
                    body = "".join(
                        '<div class="clause"><span class="kw">%s</span><span class="txt">%s</span></div>'
                        % (html.escape(kw), inline_md(rest))
                        for kw, rest in clauses
                    )
                else:
                    body = '<div class="clause plain">%s</div>' % inline_md(ac["text"])
                parts.append(
                    '<li data-search="%s"><span class="ac-id">%s</span>%s</li>'
                    % (search, html.escape(ac["id"]), body)
                )
            parts.append("</ul></details>")
        parts.append("</section>")

    parts.append('<p class="empty" id="empty">ไม่พบ AC ที่ตรงกับเงื่อนไข</p>')
    parts.append("<script>%s</script></div></body></html>" % JS)
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------

def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", default=os.path.join(here, "..", "..", "runs"))
    ap.add_argument("--areas", default=os.path.join(here, "areas.yml"))
    ap.add_argument("--out", default=os.path.join(here, "index.html"))
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit 1 if --out is missing or stale")
    args = ap.parse_args(argv)

    runs_dir = os.path.normpath(args.runs)
    areas, area_warnings = parse_areas(os.path.normpath(args.areas))
    runs, run_warnings = collect_runs(runs_dir)
    grouped, unassigned = assign_areas(runs, areas)

    for w in area_warnings + run_warnings:
        print("WARN: %s" % w)
    for run in unassigned:
        print("WARN: run %r is not assigned to an area in areas.yml" % run["id"])

    document = render(grouped, runs_dir, args.out)

    if args.check:
        if not os.path.exists(args.out):
            print("FAIL: %s does not exist" % args.out)
            return 1
        with open(args.out, encoding="utf-8") as fh:
            if fh.read() != document:
                print("FAIL: %s is stale — re-run build_index.py" % args.out)
                return 1
        print("OK: %s is up to date" % args.out)
        return 0

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(document)

    total = sum(len(r["acs"]) for g in grouped for r in g["runs"])
    print("wrote %s — %d AC across %d run in %d area (%d unassigned)"
          % (args.out, total, len(runs), len(grouped), len(unassigned)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
