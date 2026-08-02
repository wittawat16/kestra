---
name: kestra-exam
description: >
  Derive a requirement-level, black-box exam from a feature's `0-spec.md` — one `exam.py` that
  drives only the spec's declared seam, one check per acceptance criterion, one `manifest.md`
  carrying the AC→check map, each check's class (must-flip / must-hold / unexaminable), its
  provenance, its recorded red proof and failure signature, the anchor triple, and the verdict
  contract as its final section. The exam lives in the user-level exams directory, keyed by the
  repo's `origin` URL, git-committed there, and recorded by exactly one pointer — a tracker ticket
  edited in place, or a local pointer file. Use this skill when the user asks to build the exam for
  a feature, "derive an exam from 0-spec.md", "prove these ACs actually fail before we implement
  them", "regenerate the exam after the spec changed", "is this exam stale?", "run the
  pre-delivery exam gate", "which ACs are unproven", or asks "does the delivered work actually
  match what was asked" — and right after `kestra-spec` raises `0-spec.md` on a full-mode feature,
  before `kestra-build` derives stages. A spec change re-proves only the checks whose ACs moved; a
  moved anchor produces a refusal, never a verdict.
---

# kestra-exam — the spec-derived exam

**Role:** Turn `0-spec.md`'s requirement surface into executable evidence — an exam that is *red
before the work and green after it*, with the red recorded at the moment it was red. The exam is
derived from the requirement text only, and driven only through the seam the spec declared, so it
cannot accidentally test the implementation's shape instead of the requirement.

**What this buys, stated exactly:** it **turns trust in the AI into trust in evidence.** A verdict
names a requirement text (by hash), a moment (by commit), and a recorded red-to-green transition per
acceptance criterion. That is a different claim from "the AI got it right", and it is checkable by
someone who does not trust the agent that produced it.

**What this does not claim.** Two boundaries, both load-bearing:

* **Spec-derived coverage only.** The exam covers what `0-spec.md`'s requirement surface says. It
  does **not** cover runtime invariants or the guards that enforce them — those are enforced by the
  workflow machinery, and [`../kestra-build/references/design-principles.md`](../kestra-build/references/design-principles.md)
  is their single owner. An AC the declared seam cannot induce becomes an `unexaminable` row with a
  reason, never a silent omission.
* **Not a hallucination fix.** Nothing here makes a model more correct. It makes a wrong result
  *visible before delivery*, and it makes a right result *provable after*. Pitching it as a
  correctness guarantee is the one framing that would make people stop reading the red proofs.

---

## When this runs, and when it does not

**Opt-in, decided by a fact the spec already carries** — `## Mode Prediction`'s single
`kestra-build mode:` line:

| Recorded mode | Exam |
|---|---|
| `full` | build the exam — this skill runs |
| `lite` | **no exam, deliberately.** A lite feature's whole point is that the ceremony costs more than it buys |

Read the fact; do not re-derive the mode. If `## Mode Prediction` is absent or carries more than one
such line, stop and say so — that is a spec defect, and inventing the mode here would put an exam on
a feature nobody sized for one.

**A standalone (unmarked) spec is a first-class input.** No `> Spec-ticket:` preamble line just means
the raise commit reads `spec(<id>): write 0-spec.md from a hand-written idea` instead of the chain
subject; `exam_anchor.py` already tries both, in that order (see §Staleness refusal). The pointer
transport is independent of chaining: a standalone spec on a `github.com` origin still gets a GitHub
pointer ticket.

`kestra-spec`, `kestra-build` and `to-spec` are **suggestions** throughout this file — a machine
without them simply does not run the exam leg, and no generated `workflow.yaml` breaks.

---

## The read rule

**Read exactly the requirement surface**, whose section list is owned by one place and never
restated: `requirement_surface.SURFACE_SECTIONS` (import it or run
`python3 -c 'import requirement_surface as r; print(r.SURFACE_SECTIONS)'`). Add the declared seam
from `## External Interface`, and stop.

**Never read**, even when it is right there: `## Files to Touch`, `## Codebase Survey`,
`## Solution Architecture`, and the Coverage Map's `Covered by (files/steps)` column.

**Why, since these would obviously help:** those sections describe the *implementation's planned
shape*. A check written after reading them tests that plan rather than the requirement, so it goes
green on a faithful implementation of a wrong plan and red on a better implementation of the right
one. The exam's only value is being an *independent* derivation; reading the plan spends that value
to save a few minutes. This is also why the exam never reads source files under `src/` before
writing a check.

The one thing you do read outside the surface is the spec preamble's `> Spec-ticket:` line — to know
whether the raise commit is the chain subject or the standalone one.

---

## Process

Seven steps. Each ends in a command whose exit code is the completion criterion.

### 1. Resolve the paths and take the hard stops

```bash
S=<skill>/scripts        # this skill's scripts/ directory
RUN=<repo>/workflows/runs/<feature-id>
python3 $S/exam_paths.py <repo-root> "$RUN"; echo "paths exit=$?"
```

`exit=0` prints `origin_key`, `feature_slug`, `exam_dir`, `pointer_file`, `transport`. `exit=1` is a
hard stop with its own text — no origin, an unkeyable URL, an unconventional run-folder name, or an
exam repo that has grown a remote. **Nothing is created on a hard stop**; verify with
`test ! -d <exam-dir>`.

Then, before writing anything:

```bash
mkdir -p <exam-dir> && cp $S/exam_harness.py $S/exam_anchor.py <exam-dir>/
cp <extractor-dir>/requirement_surface.py <exam-dir>/     # first hit of the four candidates
python3 <exam-dir>/exam_anchor.py "$RUN" <exam-dir> --creatable; echo "creatable exit=$?"
git init -q <exam-dir>
```

Three files are copied in **byte-identically**, not imported from the install: a gate reading this
exam in six months must not get a different answer because a skill was reinstalled since. `git init`
goes at the **feature** directory, not the origin-key directory — one feature is one independent
history, so a regeneration is one small commit and an audit reads one log. Never add a remote.

`--creatable` exit 1 means an exam already exists here anchored to a *different* surface: go to
§Regeneration. Creation never overwrites another exam's evidence.

### 2. Derive one check per AC, from the surface only

For every row of the Coverage Map, decide and write down:

* **The check's assertion** — in the requirement's own terms (inputs → observable result at the
  seam), never in the implementation's terms.
* **Its class, provisionally.** `must-flip` = new or changed behavior (for a bug-fix AC, the red
  *is* the repro). `must-hold` = the AC asserts *preservation* of behavior that exists today. The
  provisional class is settled by measurement in step 5, not by intent.
* **`unexaminable`, when the declared seam genuinely cannot induce the condition** — one sentence
  saying why. Every AC owns at least one row; a missing AC is a manifest FAIL, so "the exam skipped
  the awkward AC" cannot hide.
* **Provenance** — copy the Coverage Map's `Source` cell. A check derived from an `⚠ inferred` line
  is marked, because the requirement behind it originated in a spec pass rather than upstream.

Completion criterion: the count of Coverage-Map rows equals the count of ACs you have check rows for.

### 3. Write `exam.py` and `manifest.md`

`exam.py` is **header + `EXAM` + `ANCHOR` + `SEAM` + checks**, nothing else — every runner mechanic
lives in `exam_harness.py`, so two exams are comparable. `SEAM` is exactly one of `Cli`, `Http`,
`Module`; read `## External Interface` and encode it by hand. **Do not write a parser for that
section** — a fragile parser sitting at the one place where a false-fail is permanent is worse than
a human reading four lines.

`assert` is banned in `exam.py`: `python3 -O` strips it, so every check would be born green. Use
`expect` / `expect_true` / `expect_contains`. The harness refuses to run under `-O` as the backstop.

Read [`references/exam-script-contract.md`](references/exam-script-contract.md) before writing the
first check — it carries the `@check` signature, the three seam constructions, the reached/behavioral
discriminator, the exit-code ladder and the `--json` schema.

Read [`references/manifest-schema.md`](references/manifest-schema.md) while writing `manifest.md` —
seven sections in fixed order, the closed Red-proof vocabulary, and the verdict-contract text to copy
verbatim.

Completion criterion:

```bash
python3 <exam-dir>/exam.py --list;       echo "list exit=$?"        # expect 0
python3 <exam-dir>/exam.py --audit-seam; echo "audit exit=$?"       # expect 0
```

`--audit-seam` proves the seam the exam drives appears **verbatim** in the External Interface block
quoted in `manifest.md`. That is why the quote is load-bearing rather than decoration.

### 4. Red-proof in a disposable clone at the raise commit

```bash
TMP=$(mktemp -d); CLONE="$TMP/red-proof"
git clone -q --no-hardlinks <repo-root> "$CLONE"
git -C "$CLONE" checkout -q <raise_commit>
python3 <exam-dir>/exam.py --repo "$CLONE" --json > <exam-dir>/red-proof.json
python3 <exam-dir>/exam.py --repo "$CLONE"        > <exam-dir>/red-proof.log 2>&1
echo "red-proof exit=$?"; rm -rf "$TMP"
```

A disposable clone at the **raise commit** — the moment before any implementation, and the same SHA
the anchor names — so nothing lands in the working repo and the classification is measured against
the tree the requirement was written about.

**C-0 red at red-proof time voids the entire red-proof.** No other check's red counts as proof: a
harness that cannot reach the seam reds everything indiscriminately, so a red proof taken through a
broken harness is exactly the laundering this skill exists to prevent. On a red C-0 the run exits 2,
every other check reports `blocked`, and every `must-flip` row is `unproven`. Fix the harness and
re-run; do not record the run.

Completion criterion: `red-proof.json` exists and `jq -r .smoke.result` (or a `python3 -c` read) is
`pass`.

### 5. Classify from the measurement, then flag `unproven`

Set each row's class from what step 4 measured, not from what step 2 intended: a check is
`must-hold` iff it was measured **green** on the pre-implementation tree *and* its AC asserts
preservation. A declared class the measurement contradicts is a manifest defect — fix the row.

`unproven` has exactly three producers, and no fourth:

| Producer | Red-proof cell |
|---|---|
| **born green** — a `must-flip` that passed at red-proof | `**born-green — `unproven`**` |
| **infrastructure red** — the seam was never reached, so the red proves nothing | `**red <ISO> infrastructure — `unproven`**` |
| **void red-proof** — C-0 was red | ``void — C-0 red at red-proof (harness) — `unproven``` |

**Never auto-demote a born-green `must-flip` to `must-hold`.** Demotion would turn missing evidence
into a legitimate-looking regression guard — the laundering the class split exists to make visible.
It keeps its class and carries the flag.

`unproven > 0` makes the verdict's evidence clause **mandatory**:
`PASS (evidence: degraded — <U> unproven of <F> must-flip)`. A `PASS` with `U > 0` and no clause is a
malformed verdict, i.e. a gate failure — that is what makes "never silently counted as passing"
mechanically checkable instead of aspirational. Every `unproven` row also carries a one-line reason
in `red-proof.log`, so a reviewer sees *why* the evidence is degraded, not merely that it is.

Completion criterion: `summary.unproven` in `red-proof.json` equals the count of `unproven`-flagged
rows in `manifest.md`.

### 6. Open or edit the one pointer

The pointer is the exam's durable record: one issue titled **exactly** `kestra-exam: <feature-slug>`
with the label `kestra-exam`, or one `<slug>.pointer` file beside the exam dir. The transport comes
from `exam_paths.py`, never from judgment.

Discovery is read-only and its predicate is exact title equality — `--search` is only the fetch,
because a tracker tokenizes titles:

```bash
gh issue list --repo <chain-repo> --label kestra-exam --state all --limit 100 \
  --json number,title,url \
  --jq '[.[]|select(.title=="kestra-exam: <slug>")]'
```

`0` matches at creation → create it. `0` at a gate or regeneration → hard fail. **`>1` → hard fail,
never resolved by taking the newer one** (§Hard stops carries the text). A regeneration **edits the
existing pointer in place** and appends one comment; it never opens a second.

Completion criterion: exactly one pointer exists, its first line is
`<!-- kestra-exam-pointer v1 -->`, and its `exam_script_sha256` equals
`sha256sum <exam-dir>/exam.py`.

### 7. Commit inside the exam dir

```
exam(<slug>): create from surface <hash12> @ raise <sha12>
exam(<slug>): regenerate C-3,C-7 for surface <hash12> @ raise <sha12>
exam(<slug>): re-anchor to surface <hash12> @ raise <sha12>
```

Identity is inherited from global git config. A `git commit` that fails for a missing identity is a
loud stop — this skill does not configure a user's git identity behind their back.

Completion criterion: `git -C <exam-dir> log --oneline | wc -l` increased by exactly 1, and
`git -C <exam-dir> remote` prints nothing.

---

## Regeneration

A spec change re-proves **only the checks whose ACs moved**. The AC→check map is not a second
artifact — it is the `AC` column of `manifest.md`'s `## Checks` table; the `## Delta map`
fingerprints are what turn "the surface moved" into "*these* ACs moved".

```bash
python3 <skill>/scripts/exam_delta.py "$RUN" <exam-dir>; echo "delta exit=$?"
```

The plan's first line is the scope: `delta` (regenerate the named checks) · `full` (the declared seam
moved, so nothing is delta-able) · `re-anchor` (prose the ACs paraphrase moved; regenerate nothing,
rewrite the anchor) · `current` (nothing moved).

Two rules that hold in every scope: a check carries over **only** on an identical
`(check id, normalized AC row)`, and a regenerated `must-flip` needs a **fresh** red proof in a new
disposable clone at the **new** raise commit. The pointer is edited in place, `generation`
incremented, one comment appended.

Read [`references/regeneration.md`](references/regeneration.md) when a spec changed after the exam was
created, or when `exam_delta.py` prints `scope: full`.

---

## Staleness refusal

The anchor triple is `raise_commit` (40-hex) · `surface_hash` (64-hex) · `extractor_version` (int),
recorded in three places that must agree: `manifest.md` §Anchor (authoritative), the pointer body
(durable off-repo mirror), and `exam.py`'s `ANCHOR` (so a bare script run self-reports). Disagreement
among the three is itself a refusal — otherwise a tamper that edits one copy reads as fresh.

```bash
python3 <exam-dir>/exam_anchor.py "$RUN" <exam-dir>    # 0 fresh · 2 REFUSED · 3 unreadable
```

Freshness is recomputed from the **working tree**, never `HEAD`: an uncommitted human edit to
`0-spec.md` is exactly what this check exists to catch, and it is what every spawned subagent reads.

```
REFUSED: exam is stale — no verdict emitted.
  cause:             <the named fail-closed arm>
  surface_hash:      recorded 9a1c4e77b210 != current 4de7f0c9a883
  raise_commit:      recorded 1f2a9c04 == current 1f2a9c04
  extractor_version: recorded 1 == current 1
A verdict here would certify the delivered work against a superseded requirement.
Regenerate the affected checks (kestra-exam regeneration is delta-scoped by the
AC->check map), then re-run the gate. Do not edit the anchor to match.
```

All three fields print every time, equal ones included: a refusal that showed only the mismatching
field would hide which of the three moved on the next run.

**Every fail-closed arm is a refusal, never a skip** — partial anchor · raise commit unreachable or
not exactly-one · extractor version differs (*hashes are not comparable across extractor versions —
re-derive, never diff*) · anchor copies disagree · extractor missing. A comparison that cannot run
counts as a mismatch.

**What does not move the anchor:** everything outside `requirement_surface.SURFACE_SECTIONS` — that
module owns the boundary and this skill adds no second one. Prose edits, typo fixes, the whole
provision layer, and (by the vetter's standing default) the Given-When-Then `## Acceptance Criteria`
and `## Business Rules` sections are non-events.

---

## The gate procedure

**Building the gate runner is not part of this skill.** kestra-exam produces the artifacts a gate
reads — `exam.py`, `manifest.md`, `red-proof.json`, the anchor, the pointer — and stops there.
Implementing a phantom gate here would produce a runner nobody wired up.

The procedure a gate must follow — the four leak sweeps and their exemption boundary, the
hash-vs-pointer comparison, the single-match pointer resolution, and the GraphQL `userContentEdits`
body-edit check — lives in [`references/gate-procedure.md`](references/gate-procedure.md). Read it when
running the pre-delivery gate, when a sweep reports a hit, or when a pointer body looks edited.

---

## Hard stops

Closed list. Each stops the pass, creates nothing further, and says which one fired.

| Stop | Text lives in |
|---|---|
| no `origin` remote on the repo | `exam_paths.NO_ORIGIN`, quoted below |
| the origin URL yields fewer than two path segments | the same text, with `— the origin URL yields fewer than two path segments (<url>)` appended |
| the run-folder basename is not a usable feature slug | `exam_paths.feature_slug` |
| the exam repo has a remote | `exam_paths.assert_no_remote` |
| origin is `github.com` but `gh` is missing or unauthenticated | `exam_paths.NO_AUTH` — never a silent downgrade; `--local-pointer` makes the same choice honest |
| `>1` pointer titled `kestra-exam: <slug>` | `references/gate-procedure.md` §Pointer discipline |
| `0` pointers at a gate or regeneration | same |
| stale / partial anchor, or the three copies disagree | §Staleness refusal |
| `requirement_surface.py` resolves at none of four paths | `exam_anchor.load_extractor` |
| an exam already exists here anchored to a different surface | `exam_anchor.assert_creatable` |
| an unlisted seam kind | `exam_harness` — name it and extend the harness deliberately |
| `__debug__` is False (`python3 -O`) | `exam_harness` |

The no-origin stop, verbatim (exit 1, nothing created — `test ! -d <exam-dir>` must hold):

```
FAIL: no `origin` remote on <repo-root> — kestra-exam refuses to create an exam.
The exam directory is keyed by the origin URL so two clones or forks sharing a
directory basename cannot cross-wire onto one exam dir. There is no fallback
naming: add an origin remote (`git remote add origin <url>`), or run without an
exam — the exam is opt-in on kestra-build's full mode.
```

**Why the missing extractor is a hard stop here when `kestra-spec` only WARNs about it:** kestra-spec
can still write a spec without its validator, and it must not hard-depend on kestra-build being
installed. kestra-exam cannot write an *anchored* artifact without the extractor, and an unanchored
exam is precisely what makes a verdict meaningless. The exam is opt-in — a machine without
kestra-build simply does not run the exam leg — so this is a missing input, not a cross-skill
dependency.

---

## Stopping rule

Done once:

- `exam_paths.py` printed `exit=0` and the exam dir sits at `<exams-root>/<origin-key>/<slug>/`
- `exam_harness.py`, `exam_anchor.py` and `requirement_surface.py` are byte copies in the exam dir
- Every Coverage-Map AC owns at least one check row; every `unexaminable` row carries a reason
- `exam.py --list` and `exam.py --audit-seam` both exit 0
- `red-proof.json` and `red-proof.log` exist, and `smoke.result` is `pass`
- Every `must-flip` row's Red-proof cell is one of the five closed values, and every `unproven` row
  has a one-line reason in `red-proof.log`
- `summary.unproven` equals the count of `unproven` rows in the manifest
- `manifest.md` carries all seven sections in order, `## Verdict contract` last
- The anchor triple is byte-identical in `manifest.md`, the pointer body and `exam.py`, and
  `exam_anchor.py` exits 0
- Exactly one pointer exists, carries the `v1` marker, and its `exam_script_sha256` matches
  `sha256sum exam.py`
- One commit landed in the exam dir, and `git -C <exam-dir> remote` prints nothing

Any `unproven > 0` → say so plainly at handoff, with the count and the producer per row. A red C-0 at
red-proof time ⇒ no handoff at all: fix the harness and re-run step 4.

## Handoff

→ `kestra-build`, which derives stages from the same `0-spec.md`. The exam is not one of its stages
and does not gate it; it gates **delivery**, and the gate runner reads the artifacts this skill left
behind. Say the exam dir path, the pointer's identity, the check counts, and the `unproven` count out
loud at handoff — an exam nobody knows about certifies nothing.
