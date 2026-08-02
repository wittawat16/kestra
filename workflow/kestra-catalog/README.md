# kestra-catalog

A folder of `workflows/runs/<feature-id>/` is a good archive and a useless index. Every run's
`0-spec.md` holds the acceptance criteria for one ticket, so after thirty-odd runs nobody can
answer *"what do we test about order submission?"* without opening thirty-odd files — and `AC-1`
means something different in each of them.

This skill reads all of them, pulls the acceptance criteria out, groups them by **business area**
instead of by ticket, and writes one searchable HTML page.

## What you get

```
workflows/docs/testcases/
  areas.yml          # taxonomy — you own this file
  build_index.py     # copied here, so CI and a fresh clone can regenerate without the skill
  index.html         # generated, self-contained, open it with a double-click
```

```
$ python3 workflows/docs/testcases/build_index.py
WARN: run 'isu-104-nl2-equity-read-failure' is not assigned to an area in areas.yml
wrote index.html — 305 AC across 36 run in 4 area (1 unassigned)
```

The page groups **area → run → AC**, with the full AC text (not just a link), a client-side search
box, filters by area and run status, per-area counts, and a link from each run back to its
`0-spec.md`.

## The one decision that isn't automatic

Business area. It genuinely isn't in the data — run folders are named after tickets, and deriving
areas from each spec's *Files to Touch* was tried and doesn't work: in a service-shaped repo
nearly every run resolves to the same path prefix, and older specs have no such section at all.

So `areas.yml` is hand-edited, and the skill's only judgment call is proposing where a new run
belongs, for you to confirm:

```yaml
areas:
  nl2-order-flow:
    title: NL2 — Order submission & exit
    runs:
      - isu-107-*
      - isu-106-*
  reporting:
    title: Reporting
    runs: [report-generator]
```

Prefer globs to exhaustive lists — future runs stay assigned without anyone remembering to come
back. A run that matches nothing lands in an `unassigned` group and prints a warning; that's the
honest outcome, and better than inventing an area to make it fit.

Keeping the taxonomy in one file rather than as a field in each spec is deliberate: renaming an
area is one edit here instead of an edit to every frozen spec it touches.

## What the status badges claim

Status comes from each run's `state.json` and is **per run, never per AC** — `done`,
`in-progress`, `blocked`, `legacy` (a run from before the stage machine), `unknown`.

The badge says *this AC comes from a run that completed the pipeline*, not *this AC passed*. Those
aren't the same claim, and only the first one is backed by a file. Across the 36 specs this was
built against there were 570 `* [ ]` checkboxes and not one had ever been ticked — a catalog that
read them literally would have reported 0% passing on finished work.

## Derived, not authored

`index.html` is a view. Specs stay the source of truth, so anything typed into the generated page
is gone on the next build (the page says so itself). To change an AC, change its `0-spec.md` and
regenerate.

The upside is that every run you already have counts from day one, with no migration and no change
to `kestra-spec`, `kestra-build`, or `kestra-run`.

## Usage

Ask for it in whatever words fit — "รวม test case ไว้ที่เดียว", "build the test case catalog",
"refresh the testcases dashboard". Or run the script directly once it's installed:

```bash
python3 workflows/docs/testcases/build_index.py
```

`--check` writes nothing and exits non-zero if `index.html` is missing or stale, for use as a CI
guard.

Full detail — process, `areas.yml` rules, what the skill deliberately doesn't do — is in
[`SKILL.md`](SKILL.md).
