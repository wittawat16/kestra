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


STATUS_SHORT = {
    "done": "ผ่านครบ",
    "in-progress": "กำลังทำ",
    "blocked": "ค้าง",
    "legacy": "legacy",
    "unknown": "อ่านไม่ได้",
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
:root { color-scheme: light dark; --bg:#fff; --fg:#16181d; --muted:#6b7280;
  --line:#e5e7eb; --card:#f9fafb; --soft:#f3f4f6; --accent:#2563eb;
  --ok:#16a34a; --warn:#d97706; --bad:#dc2626; }
@media (prefers-color-scheme: dark) { :root { --bg:#0f1115; --fg:#e6e6e6;
  --muted:#9ca3af; --line:#272c34; --card:#161a20; --soft:#1b2027;
  --accent:#60a5fa; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
  "Noto Sans Thai","Helvetica Neue",sans-serif; }
code { background:var(--soft); border:1px solid var(--line); border-radius:4px;
  padding:0 4px; font-size:12.5px; }
a { color:var(--accent); }
[hidden] { display:none !important; }

.badge { font-size:11px; padding:1px 7px; border-radius:99px;
  border:1px solid var(--line); color:var(--muted); white-space:nowrap; }
.badge.done { border-color:var(--ok); color:var(--ok); }
.badge.in-progress { border-color:var(--warn); color:var(--warn); }
.badge.blocked { border-color:var(--bad); color:var(--bad); }
.dot { width:8px; height:8px; border-radius:99px; flex:0 0 auto;
  background:var(--muted); }
.dot.done { background:var(--ok); }
.dot.in-progress { background:var(--warn); }
.dot.blocked { background:var(--bad); }
.kw { display:inline-block; min-width:3.4em; font-size:10.5px; font-weight:700;
  letter-spacing:.05em; text-transform:uppercase; color:var(--muted); }
.acid { font:11px ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--muted); }

/* dashboard */
.dash { padding:22px 24px 40px; max-width:1080px; margin:0 auto; }
.dash h1 { font-size:21px; margin:0 0 3px; }
.dash .sub { color:var(--muted); font-size:12.5px; margin:0 0 20px; }
.dash h2 { font-size:14px; margin:26px 0 9px; display:flex; gap:8px;
  align-items:center; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px; }
.tile { border:1px solid var(--line); border-radius:10px; padding:13px 15px;
  background:var(--card); }
.tile .n { font-size:26px; font-weight:700; line-height:1.1;
  font-variant-numeric:tabular-nums; }
.tile .l { font-size:12px; color:var(--muted); margin-top:2px; }
.tile .bar { height:5px; border-radius:99px; background:var(--soft);
  margin-top:9px; overflow:hidden; display:flex; }
.tile .bar i { display:block; height:100%; }
.matrix { width:100%; border-collapse:collapse; font-size:13px; }
.matrix th, .matrix td { border:1px solid var(--line); padding:8px 10px;
  text-align:left; }
.matrix th { background:var(--card); font-size:11px; text-transform:uppercase;
  letter-spacing:.05em; color:var(--muted); font-weight:600; }
.matrix td.num { text-align:center; width:74px; font-variant-numeric:tabular-nums; }
.matrix tbody tr:hover { background:var(--soft); }
.heat { display:inline-block; min-width:30px; padding:2px 8px; border-radius:5px;
  font-weight:600; font-size:12px; }
.heat.zero { color:var(--muted); opacity:.45; font-weight:400; }
.heat.done { background:color-mix(in srgb,var(--ok) 24%,transparent); color:var(--ok); }
.heat.in-progress { background:color-mix(in srgb,var(--warn) 26%,transparent);
  color:var(--warn); }
.heat.blocked { background:color-mix(in srgb,var(--bad) 24%,transparent); color:var(--bad); }
.heat.legacy, .heat.unknown { background:var(--soft); }
.runrow { display:flex; align-items:center; gap:10px; padding:9px 12px;
  border:1px solid var(--line); border-radius:8px; margin-bottom:6px;
  background:var(--card); font-size:13.5px; text-decoration:none;
  color:inherit; }
.runrow:hover { border-color:var(--accent); }
.runrow strong { font-weight:600; }
.runrow .meta { color:var(--muted); font-size:12.5px; }
.runrow .spark { margin-left:auto; display:flex; gap:2px; }
.runrow .spark i { width:11px; height:15px; border-radius:2px;
  background:color-mix(in srgb,var(--accent) 32%,transparent); }
.attn { border-left:3px solid var(--warn);
  background:color-mix(in srgb,var(--warn) 7%,transparent); }

/* explorer */
.exp { display:grid; grid-template-columns:270px minmax(0,1fr);
  min-height:100vh; }
.exp aside { border-right:1px solid var(--line); padding:14px 10px;
  background:var(--card); }
.exp aside .back { display:inline-block; font-size:12.5px; margin:0 0 12px 8px; }
.exp aside input { width:100%; font:inherit; font-size:13px; padding:6px 9px;
  border:1px solid var(--line); border-radius:6px; background:var(--bg);
  color:var(--fg); margin-bottom:12px; }
.tree-area { margin-bottom:10px; }
.tree-area > .h { font-size:11px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--muted); padding:6px 8px 4px; display:flex;
  justify-content:space-between; gap:8px; }
.tree-run { display:flex; align-items:center; gap:7px; padding:5px 8px;
  border-radius:6px; font-size:13px; text-decoration:none; color:inherit; }
.tree-run:hover { background:var(--soft); }
.tree-run.sel { background:var(--accent); color:#fff; }
.tree-run.sel .cnt, .tree-run.sel .dot { color:#fff; opacity:.9; }
.cnt { margin-left:auto; font-size:11px; color:var(--muted);
  font-variant-numeric:tabular-nums; }
.exp main { padding:20px 26px 40px; min-width:0; }
.exp main h2 { margin:0 0 2px; font-size:19px; }
.crumb { font-size:12px; color:var(--muted); margin-bottom:14px;
  display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.toolbar { font-size:12.5px; color:var(--muted); margin:14px 0 8px; }
.case { border:1px solid var(--line); border-radius:8px; margin-bottom:8px;
  overflow:hidden; }
.case > header { display:flex; gap:10px; align-items:center; padding:8px 12px;
  background:var(--card); border-bottom:1px solid var(--line); }
.gwt { padding:9px 12px; display:grid; grid-template-columns:3.8em minmax(0,1fr);
  gap:3px 8px; font-size:13.5px; }
.gwt.plain { display:block; }
.empty { color:var(--muted); padding:16px 0; }
"""

JS = """
(function () {
  var dash = document.getElementById('dashboard'),
      exp = document.getElementById('explorer'),
      q = document.getElementById('q'),
      panels = [].slice.call(document.querySelectorAll('.runpanel')),
      links = [].slice.call(document.querySelectorAll('.tree-run')),
      empty = document.getElementById('tree-empty'),
      current = null;

  function show(runId) {
    current = runId;
    panels.forEach(function (p) { p.hidden = p.dataset.run !== runId; });
    links.forEach(function (a) {
      a.classList.toggle('sel', a.dataset.run === runId);
    });
    filter();
  }

  function filter() {
    var term = q.value.trim().toLowerCase(), anyRun = false;

    links.forEach(function (a) {
      var hit = !term || a.dataset.search.indexOf(term) !== -1;
      a.hidden = !hit;
      if (hit) { anyRun = true; }
    });
    [].slice.call(document.querySelectorAll('.tree-area')).forEach(function (g) {
      g.hidden = ![].slice.call(g.querySelectorAll('.tree-run'))
        .some(function (a) { return !a.hidden; });
    });
    empty.hidden = anyRun;

    panels.forEach(function (p) {
      if (p.hidden) { return; }
      var shown = 0;
      [].slice.call(p.querySelectorAll('.case')).forEach(function (c) {
        var hit = !term || c.dataset.search.indexOf(term) !== -1;
        c.hidden = !hit;
        if (hit) { shown++; }
      });
      p.querySelector('.case-empty').hidden = shown > 0;
    });
  }

  function route() {
    var m = /^#run\\/(.+)$/.exec(location.hash);
    if (m) {
      var id = decodeURIComponent(m[1]);
      if (panels.some(function (p) { return p.dataset.run === id; })) {
        dash.hidden = true; exp.hidden = false;
        show(id);
        return;
      }
    }
    exp.hidden = true; dash.hidden = false;
  }

  q.addEventListener('input', filter);
  window.addEventListener('hashchange', route);
  route();
})();
"""


def _heat(count, status):
    cls = "zero" if not count else status
    return '<span class="heat %s">%d</span>' % (cls, count)


def _summary(grouped):
    """Everything the dashboard counts, derived once from the grouped runs."""
    order = ("done", "in-progress", "blocked", "legacy", "unknown")
    totals = dict.fromkeys(order, 0)
    rows, attention = [], []

    for g in grouped:
        counts = dict.fromkeys(order, 0)
        for run in g["runs"]:
            counts[run["status"]] += 1
            totals[run["status"]] += 1
        rows.append({
            "id": g["id"],
            "title": g["title"],
            "runs": len(g["runs"]),
            "acs": sum(len(r["acs"]) for r in g["runs"]),
            "counts": counts,
        })
        if g["id"] == "unassigned":
            for run in g["runs"]:
                attention.append((run["id"], "ยังไม่ถูก map เข้า area ไหนใน areas.yml"))

    for g in grouped:
        for run in g["runs"]:
            if run["status"] == "blocked":
                attention.append((run["id"],
                                  "stage ค้างอยู่ — %d AC ยังไม่ถูกพิสูจน์" % len(run["acs"])))
    n_legacy = totals["legacy"]
    if n_legacy:
        acs = sum(len(r["acs"]) for g in grouped for r in g["runs"]
                  if r["status"] == "legacy")
        attention.append(("%d run" % n_legacy,
                          "legacy — ไม่มี state.json เลยบอกไม่ได้ว่า %d AC นี้ผ่านหรือยัง" % acs))

    return order, totals, rows, attention


def _render_dashboard(grouped, all_runs, total_acs, gwt_acs):
    order, totals, rows, attention = _summary(grouped)
    total_runs = sum(len(g["runs"]) for g in grouped)
    parts = ['<section class="dash" id="dashboard">']
    parts.append("<h1>Test Case Catalog</h1>")
    parts.append('<p class="sub">acceptance criteria ทุก run · generate จาก '
                 "<code>build_index.py</code> ห้ามแก้ด้วยมือ "
                 "แก้ที่ <code>0-spec.md</code> ต้นทางแล้ว generate ใหม่</p>")

    pct = lambda n: (100.0 * n / total_runs) if total_runs else 0
    parts.append('<div class="tiles">')
    parts.append(
        '<div class="tile"><div class="n">%d</div><div class="l">acceptance criteria</div>'
        '<div class="bar"><i style="width:%.1f%%;background:var(--ok)"></i>'
        '<i style="width:%.1f%%;background:var(--warn)"></i>'
        '<i style="width:%.1f%%;background:var(--bad)"></i></div></div>'
        % (total_acs, pct(totals["done"]), pct(totals["in-progress"]), pct(totals["blocked"]))
    )
    parts.append('<div class="tile"><div class="n">%d</div>'
                 '<div class="l">run · %d area</div></div>' % (total_runs, len(grouped)))
    share = (100 * gwt_acs // total_acs) if total_acs else 0
    parts.append(
        '<div class="tile"><div class="n">%d</div>'
        '<div class="l">เขียนเป็น Given-When-Then %d%%</div>'
        '<div class="bar"><i style="width:%d%%;background:var(--accent)"></i></div></div>'
        % (gwt_acs, share, share)
    )
    for key, label in (("legacy", "run legacy — ไม่มี state.json"),
                       ("blocked", "run ค้าง (blocked)")):
        colour = "var(--warn)" if key == "legacy" else "var(--bad)"
        style = ' style="color:%s"' % colour if totals[key] else ""
        parts.append('<div class="tile"><div class="n"%s>%d</div>'
                     '<div class="l">%s</div></div>' % (style, totals[key], label))
    parts.append("</div>")

    parts.append("<h2>ความครอบคลุมต่อ area</h2>")
    parts.append('<table class="matrix"><thead><tr><th>Area</th><th class="num">run</th>'
                 '<th class="num">AC</th>')
    for key in order:
        parts.append('<th class="num">%s</th>' % html.escape(STATUS_SHORT[key]))
    parts.append("</tr></thead><tbody>")
    for row in rows:
        cls = ' class="attn"' if row["id"] == "unassigned" else ""
        parts.append("<tr%s><td>%s</td><td class=\"num\">%d</td><td class=\"num\">%d</td>"
                     % (cls, html.escape(row["title"]), row["runs"], row["acs"]))
        for key in order:
            parts.append('<td class="num">%s</td>' % _heat(row["counts"][key], key))
        parts.append("</tr>")
    parts.append("</tbody></table>")

    if attention:
        parts.append('<h2>ต้องดูก่อน <span class="badge in-progress">%d เรื่อง</span></h2>'
                     % len(attention))
        for who, why in attention:
            parts.append('<div class="runrow attn"><strong>%s</strong>'
                         '<span class="meta">%s</span></div>'
                         % (html.escape(who), html.escape(why)))

    parts.append("<h2>ทุก run</h2>")
    for run in all_runs:
        parts.append(
            '<a class="runrow" href="#run/%s"><span class="dot %s"></span>'
            '<strong>%s</strong><span class="badge %s">%s</span>'
            '<span class="meta">%d AC · %s</span>'
            '<span class="spark">%s</span></a>'
            % (html.escape(run["id"]), html.escape(run["status"]), html.escape(run["id"]),
               html.escape(run["status"]), html.escape(STATUS_LABEL[run["status"]]),
               len(run["acs"]), html.escape(run["area_title"]),
               "<i></i>" * min(len(run["acs"]), 12))
        )
    parts.append("</section>")
    return parts


def _render_ac(ac):
    clauses = split_gwt(ac["text"])
    search = html.escape((ac["id"] + " " + ac["text"]).lower(), quote=True)
    if clauses:
        body = "".join('<span class="kw">%s</span><span>%s</span>'
                       % (html.escape(kw), inline_md(rest)) for kw, rest in clauses)
        body = '<div class="gwt">%s</div>' % body
    else:
        body = '<div class="gwt plain">%s</div>' % inline_md(ac["text"])
    return ('<article class="case" data-search="%s">'
            '<header><span class="acid">%s</span></header>%s</article>'
            % (search, html.escape(ac["local_id"]), body))


def _render_explorer(grouped, all_runs, out_path):
    parts = ['<section class="exp" id="explorer" hidden><aside>']
    parts.append('<a class="back" href="#">← ภาพรวมทั้งหมด</a>')
    parts.append('<input id="q" type="search" placeholder="ค้นหา run / AC…">')
    for g in grouped:
        parts.append('<div class="tree-area"><div class="h"><span>%s</span><span>%d</span></div>'
                     % (html.escape(g["title"]),
                        sum(len(r["acs"]) for r in g["runs"])))
        for run in g["runs"]:
            search = html.escape(
                (run["id"] + " " + " ".join(a["text"] for a in run["acs"])).lower(), quote=True)
            parts.append(
                '<a class="tree-run" href="#run/%s" data-run="%s" data-search="%s">'
                '<span class="dot %s"></span>%s<span class="cnt">%d</span></a>'
                % (html.escape(run["id"]), html.escape(run["id"]), search,
                   html.escape(run["status"]), html.escape(run["id"]), len(run["acs"]))
            )
        parts.append("</div>")
    parts.append('<p class="empty" id="tree-empty" hidden>ไม่พบ run ที่ตรงกับคำค้น</p>')
    parts.append("</aside><main>")

    for run in all_runs:
        spec_rel = os.path.relpath(run["spec"], os.path.dirname(os.path.abspath(out_path)))
        n_gwt = sum(1 for ac in run["acs"] if split_gwt(ac["text"]))
        parts.append('<div class="runpanel" data-run="%s" hidden>' % html.escape(run["id"]))
        parts.append("<h2>%s</h2>" % html.escape(run["id"]))
        parts.append('<div class="crumb"><span>%s</span><span class="badge %s">%s</span>'
                     '<a href="%s">0-spec.md</a></div>'
                     % (html.escape(run["area_title"]), html.escape(run["status"]),
                        html.escape(STATUS_LABEL[run["status"]]), html.escape(spec_rel)))
        parts.append('<p class="toolbar">%d test case · %d เขียนเป็น Given-When-Then</p>'
                     % (len(run["acs"]), n_gwt))
        for ac in run["acs"]:
            parts.append(_render_ac(ac))
        parts.append('<p class="empty case-empty" hidden>ไม่พบ AC ที่ตรงกับคำค้น</p>')
        parts.append("</div>")

    parts.append("</main></section>")
    return parts


def render(grouped, runs_dir, out_path):
    all_runs = []
    for g in grouped:
        for run in g["runs"]:
            run["area_title"] = g["title"]
            all_runs.append(run)
    total_acs = sum(len(r["acs"]) for r in all_runs)
    gwt_acs = sum(1 for r in all_runs for ac in r["acs"] if split_gwt(ac["text"]))

    parts = [
        "<!doctype html>",
        '<html lang="th"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>Test Case Catalog</title>",
        "<style>%s</style></head><body>" % CSS,
    ]
    parts += _render_dashboard(grouped, all_runs, total_acs, gwt_acs)
    parts += _render_explorer(grouped, all_runs, out_path)
    parts.append("<script>%s</script></body></html>" % JS)
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
