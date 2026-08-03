---
name: kestra-catalog
description: >
  This skill should be used when the user asks "what test cases do we have", "build a test case
  catalog/dashboard", "รวม test case ไว้ที่เดียว", "I can't tell what's tested across all these
  runs", "index the acceptance criteria", "refresh the testcases dashboard", or otherwise wants
  the acceptance criteria scattered across many `workflows/runs/<feature-id>/0-spec.md` files
  gathered into one searchable place. Scans every run's spec, extracts its ACs, groups them by
  business area via a hand-edited `areas.yml`, and generates a single self-contained
  `workflows/docs/testcases/index.html` with search and filters. Read-only over the pipeline —
  never edits a spec, a workflow.yaml, or a state.json, and never runs a stage. This is NOT:
  writing new test cases (that's kestra-spec or meta-test-writer), running tests, or recording
  per-test pass/fail results — status shown is per run, read from state.json.
---

# kestra-catalog — Central Test Case Catalog

**Role:** Answer the question a folder of `workflows/runs/<feature-id>/` can't — *what test cases
does this system have?* Reads every run's `0-spec.md`, pulls out its acceptance criteria, groups
them by **business area** rather than by ticket, and writes one searchable `index.html` a human
opens.

Read-only over the pipeline: it never edits a `0-spec.md`, never touches `workflow.yaml` or
`state.json`, and never runs a stage. `kestra-spec`/`kestra-build`/`kestra-run` are unchanged by
this skill's existence.

**Suggested model, if spawning this as a subagent with a model to choose:** unset. The mechanical
half is a script, and the judgment half is one small classification pass — neither is
model-sensitive enough to be worth an override. Ask before spawning either way.

---

## Why a catalog at all, and why it's derived

A repo that has run this pipeline for a while has one folder per ticket — 36 of them in the case
this skill was built against — each holding a `0-spec.md` whose acceptance criteria are the only
human-readable statement of what the system is supposed to do. That is a real archive and a
useless index: nobody can answer "what do we test about order submission?" without opening 36
files, and `AC-1` means a different thing in every one of them.

The catalog is **derived, not authored**. Specs stay the source of truth; `index.html` is a
regenerated view over them. That direction matters and is easy to get backwards:

* A run's `0-spec.md` is committed with the run and frozen by it. Editing one months later to fix
  a catalog entry rewrites history the pipeline already stood behind.
* Derived means the 40-odd runs that already exist are worth something on day one, with no
  migration. An authored catalog starts empty and only fills as new features land.
* Derived also means **anything typed into `index.html` is lost on the next build**. Say so in the
  page itself (the generator does), because a file that looks editable and isn't will eventually
  eat someone's afternoon.

The one thing that genuinely cannot be derived is the **business area** — see below.

---

## Layout it installs into the target repo

```
workflows/
  runs/<feature-id>/0-spec.md    <- read-only input
  docs/testcases/
    areas.yml                    <- taxonomy, hand-edited, committed
    build_index.py               <- copied from this skill, committed
    index.html                   <- generated, committed
```

`workflows/docs/` sits next to `workflows/runs/` on purpose: everything the pipeline produces
stays under `workflows/`, so a repo's own top-level `docs/` (ADRs, experiments, operations) keeps
its own meaning. It also makes the layout identical in every repo that uses kestra, rather than
depending on where that repo happens to keep documentation.

`build_index.py` is **copied into the target repo**, not run from this skill's directory — same
reasoning as `kestra-build` emitting `validate_spec.py` into a run folder. Anyone who clones the
repo, and any CI runner, can regenerate the catalog without having this skill installed. The cost
is that a fix to the script here has to be re-copied; the skill does that on its next run, and
should say so plainly rather than silently overwriting a file the user may have edited.

---

## The two halves — keep them separate

**Mechanical half — `scripts/build_index.py`.** Zero third-party dependencies, no LLM, same input
always gives the same output. It scans runs, extracts ACs, prefixes every id with its run id,
reads `state.json` for status, and renders the page. Everything it reports is a fact read off a
file. Run it and paste the real output; do not describe what it "would" produce.

**Judgment half — this skill.** Exactly one thing: deciding which business area a run belongs to,
for runs `areas.yml` doesn't cover yet. That is a product decision, so it gets proposed to the
user and confirmed, never written silently. Everything else is the script's job — resist the pull
to hand-write catalog content the generator already produces.

---

## Process

1. **Locate the repo's runs directory.** Normally `workflows/runs/`. If there isn't one, stop and
   say so — this skill has nothing to catalog and should not invent a place for test cases to live.

2. **Install or refresh the script.** Copy `scripts/build_index.py` to
   `workflows/docs/testcases/build_index.py`. If a copy is already there and differs, say what
   changed before overwriting; the user may have edited it.

3. **Run it once to see what's there.**
   ```
   python3 workflows/docs/testcases/build_index.py
   ```
   It prints one `WARN` per run not assigned to an area, and never fails on that — an unmapped run
   lands in an `unassigned` group. Those warnings are the work list for the next step.

4. **Propose areas for the unassigned runs.** Read enough of each unassigned run's `0-spec.md` to
   tell what part of the product it belongs to, then propose additions to `areas.yml` and **wait
   for the user to confirm** before writing. Two rules that matter more than they look:

   * **Group by what the product does, not by what the ticket was about.** Runs arrive named after
     tickets (`isu-107-nl2-submit-exit-idempotency-claim-fix`), and several unrelated fixes often
     ship in one run because they happened in the same sprint. Six months later people ask "what
     do we test about order submission?", never "what was in isu-107?". Cutting the taxonomy along
     ticket lines rebuilds the exact problem this catalog exists to solve.
   * **Prefer globs over listing every run.** `isu-1??-nl2-submit-*` keeps future runs assigned
     automatically; an exhaustive list guarantees the catalog drifts the moment nobody remembers
     to update it.

   Never invent an area to make a leftover run fit. Leaving it `unassigned` is honest and visible;
   a wrong area is neither.

5. **Regenerate and report.** Run the script again, paste its real output line, and say how many
   ACs, runs, and areas the catalog now holds — plus how many runs are still unassigned. A catalog
   that quietly hides its own gaps is worse than none.

6. **Tell the user how to open it.** `open workflows/docs/testcases/index.html` (or the platform
   equivalent). It's a single self-contained file — no server, no build step, no network. It opens
   on the coverage dashboard; clicking a run deep-links into that run's ACs at
   `index.html#run/<run-id>`.

---

## `areas.yml`

Hand-edited. This is the one file in the system a human owns outright.

```yaml
areas:
  nl2-order-flow:
    title: NL2 — Order submission & exit
    runs:
      - isu-107-*
      - isu-106-*
      - isu-095-097-*
  nl2-ranking:
    title: NL2 — Ranking & signal
    runs: [isu-091-*, isu-093-*, isu-094-*]
  reporting:
    title: Reporting
    runs:
      - report-generator
```

Area ids are kebab-case and stable; `title` is what humans read and can be reworded freely. A run
matches the **first** area whose patterns match it, so order matters when globs overlap — put the
specific area above the general one.

Keeping the taxonomy in one file rather than as a field inside each spec is deliberate: renaming
an area, or splitting one in two, is a single edit here instead of an edit to every frozen spec it
touches.

---

## Status — what the badges do and don't claim

Status is read from each run's `state.json` and is **per run, never per AC**:

| Badge | Means |
|---|---|
| `done` | every stage in `state.json` is `passed` |
| `in-progress` | stages exist, not all passed |
| `blocked` | some stage is `blocked` |
| `legacy` | no `state.json` — a run from before the stage machine |
| `unknown` | `state.json` present but unreadable |

The page says "มาจาก run ที่ผ่าน pipeline ครบ", not "this AC passed", and that distinction is
load-bearing. The pipeline verifies ACs through frozen tests, not by anyone ticking a box — across
the 36 specs this skill was built against, **570 `* [ ]` checkboxes and not one ever ticked**. A
catalog that read those checkboxes literally would report 0% passing on finished work, and would
be believed exactly once. Don't add a per-AC status field on the theory that someone will start
filling it in; the archive already answered that.

---

## Stopping rule

Done once:

- `build_index.py` is in the target repo and runs clean
- Every run either belongs to a user-confirmed area, or is reported as still unassigned
- `index.html` regenerated, with the script's real output pasted
- The user has been told where the file is and that editing it by hand is pointless

## What this skill does not do

- Does not edit `0-spec.md`, `workflow.yaml`, or `state.json` — ever
- Does not add per-AC pass/fail, and does not invent a place for testers to record results
- Does not catalog hand-written manual test cases; its only input is `workflows/runs/*/0-spec.md`
- Does not run as part of `kestra-run` — it's invoked when someone wants the catalog refreshed.
  Wiring it into the `done` stage later is one line, and deliberately not done yet.
