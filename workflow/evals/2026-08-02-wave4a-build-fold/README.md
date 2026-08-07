# Eval — Wave 4a, the `kestra-build` sliced-ticket fold: anchor triple, embedded briefs, `progress:`

Ticket [#37](https://github.com/arkaphat/arkaphat-builder/issues/37) (Wave 4a of the prep-chain
implementation, parent [#31](https://github.com/arkaphat/arkaphat-builder/issues/31)).

Like wave 2, **this eval runs no LLM passes.** #37's deliverable is machinery — a materialization
pipeline, an anchor triple, a byte-provenance delimiter, an `ac_hash`, a copy rule — and machinery is
falsifiable by command. The fold itself was *enacted by hand from the skill text* (`SKILL.md`'s
"Folding a sliced ticket set" + `references/ticket-fold.md` F0–F5), and every command that
enactment ran is in `logs/01-fold-enactment.log`. Everything asserted below is a line of a log in
`logs/`, quoted literally. Where a claim cannot be settled by a command it is in §7 as *not
established*, not softened.

| Subject | Path | State |
|---|---|---|
| the fold procedure | `workflow/kestra-build/SKILL.md` | 923 lines (modified on this branch) |
| its reference | `workflow/kestra-build/references/ticket-fold.md` | 281 lines, new |
| the field grammars | `workflow/kestra-build/references/workflow-schema.md` | +203 lines |
| the shipped validator | `workflow/kestra-build/scripts/validate_workflow.py` | 968 lines — §A1–A5, §A4 ported from `logs/fold_check.py` |
| the extractor | `workflow/kestra-build/scripts/requirement_surface.py` | unchanged, `EXTRACTOR_VERSION = 1` |
| its anchor tests | `workflow/kestra-build/scripts/test_validate_workflow_anchor.py` | 625 lines, new, 42 tests (20 of them §A4) |
| the fixture spec | `fixtures/spec/0-spec.md` | chain-marked, 5 Coverage-Map rows, 2 `progress:` bullets |
| the fixture slice set | `fixtures/ticket-set/0{1,2,3}-*.md` | 3 local-file slices that partition those 5 rows |
| the folded artifact | `runs/wave4a-fixture/` | `workflow.yaml` + `state.json` + `tickets/` + the 3 F5-emitted scripts |

Environment: macOS 25.5.0, `python3` stdlib only (`python3 -m py_compile` clean), `git 2.50.1`,
branch `arkaphat/prep-chain-impl`, `gh` never invoked (form A(b) — local-file tracker — is offline by
design). Anchor commit used throughout: `cc834eb914911fd1f4d92d7f5914271821e8a455`.

---

## 0. The honesty that shapes this eval: what is shipped vs. what this eval implements

When this eval was first written, `validate_workflow.py` implemented the design's **§A1–A3**
(anchor presence/shape/comparability + a real surface recompute) and **§A5**
(`exit_criteria.progress` empty ⇒ FAIL) only — **§A4** (the embedded ticket blocks, the `tickets:`
map, the `ac_hash` recompute) existed as prose. So the eval shipped `logs/fold_check.py` (402 lines,
stdlib only): that missing half, implemented **inside the eval directory**, with the FAIL texts
copied verbatim out of `ticket-fold.md`, so that no claim here was quoting an intention.

**§A4 has since been ported into `validate_workflow.py`** (same checks, same texts, +286 lines), and
the driver now runs the **shipped** validator over the same mutated sets as `fold_check.py` — legs 3,
4 and 9 show both, and the two agree message for message. What remains eval-only, by design, is
listed in §7: F0/F1's git-side recompute, the mid-run re-fold guard (kestra-build's own refusal, not
a property of a finished artifact), and the `progress:` owner-resolution ladder.

`fold_check.py` still imports `requirement_surface` and `validate_workflow.parse_yaml` **from the run
folder** (the F5-frozen copies), never from the skill — one normalizer, one parser, the run's own
vintage. It is eval scaffolding: not installed, not in `install.sh`, not imported by anything, and
kept because a port is worth diffing against the reference it came from.

## 1. What ran

`bash logs/run-legs.sh` — one driver, 12 legs, one log file each, no interactive step, no network,
no `git` write. Counts below are `grep -c` over the logs it wrote (`logs/00-summary.txt`):

```
log                                 FAIL  WARN   exit=0  exit!=0
01-fold-enactment.log                  0     7       16        0
02-parsed-brief-loss.log               0     0        1        0
03-ac-mismatch-refusal.log            10     8        2        3
04-hand-edit-routes.log               14    26        0        8
05-refold.log                          3     9        4        2
06-midrun-refold-refusal.log           1     3        2        1
07-anchor-matrix.log                  11    38        3       10
08-progress-copy.log                   3     3        4        3
09-nonvacuity.log                      8     2       12        4
10-worked-example.log                  0     6        2        1
11-unit-suites.log                     0     0        4        0
12-measured-numbers.log                0     3        3        0
```

## 2. AC 1 — the fixture set folds to one valid `workflow.yaml`, anchor triple present

`logs/01-fold-enactment.log`. Form **A(b)**: a run folder with `0-spec.md` plus a directory of
local-file slices. Materialization used the documented pipeline and nothing else —
`tr -d '\r' < fixtures/ticket-set/<NN>-<slug>.md > runs/wave4a-fixture/tickets/<NN>-<slug>.md` — and
F5 copied the three scripts in, verified byte-identical:

```
$ cmp runs/wave4a-fixture/requirement_surface.py …/scripts/requirement_surface.py && cmp …
emitted copies byte-identical to the skill
```

F1–F3, computed (`logs/fold_check.py values`, the values the fold then recorded):

```
F1  extractor_version: 1
F1  surface_hash(0-spec.md): 2f2e17eda1f05b60b310aca3ab72cd3565772dd56207f6007248f38dd871d42f
F2  ac_rows in the map: 5
F2  01-csv-writer: 2 AC(s) matched, sources=['US-1', 'ID§csv-quoting']
F2  02-export-endpoint: 2 AC(s) matched, sources=['US-1', 'US-2']
F2  03-streaming: 1 AC(s) matched, sources=['NFR-1']
```

All five map rows are covered exactly once (no uncovered/doubly-covered WARN), which is the
partition the fixture set was built to be. `01-csv-writer`'s first AC carries an explicit
`(Source: US-1)`; it is stripped by `\s*\(Source:\s*[^()]*\)\s*$` and **agrees** with the map row, so
no contradiction stop — the resolve-don't-regrade rule exercised on its happy path.

Step 7's dry-run, in the form `ticket-fold.md` F5 mandates (the run folder's own copy, the run folder
as target), and `fold_check.py`'s F1 recompute-vs-recompute:

```
$ python3 runs/wave4a-fixture/validate_workflow.py runs/wave4a-fixture
PASS — 7 stages, structurally sound.
exit=0

F1  working tree 2f2e17eda1f05b60b310aca3ab72cd3565772dd56207f6007248f38dd871d42f
F1  as raised    2f2e17eda1f05b60b310aca3ab72cd3565772dd56207f6007248f38dd871d42f   [equal — proceed]
FOLD OK — 3 slices, 3 embedded blocks, anchor triple present, 3 warning(s).
exit=0
```

The artifact carries `spec_anchor` (3 fields), `tickets:` (3 entries × 6 fields), 3 matched
`ticket:begin`/`ticket:end` pairs on the three `implement-*` stages (one ticket per stage), and two
`exit_criteria.progress` values byte-equal to the spec's two bullets. No `spec_anchor` WARN appears
in the shipped validator's output — the anchored path is silent when the recompute agrees.

The seven WARNs in this leg are one `validate_spec.py` Files-to-Touch WARN plus the parser-trap
WARN once per sliced brief, emitted twice over — once by `fold_check.py`, once by the shipped
validator that now owns the same check. See §6.

## 3. AC 2 — the refusal on an AC-row mismatch, and the refresh table

`logs/03-ac-mismatch-refusal.log`. One word of one sliced AC changed (`completed` → `finished`):

```
FAIL: ticket 02-export-endpoint AC 1 "AC-1 a finished export returns 200 with a text/csv body" matches no row in the spec's AC Coverage Map — the slice set and the raised spec disagree. Either the spec moved after slicing (re-run to-tickets over the current spec — a suggestion, if installed), or the AC was edited on the tracker. kestra-build does not reconcile this; it stops.
FAIL: tickets['02-export-endpoint'].body_sha256 9463b2cb24b7 ≠ sha256(tickets/02-export-endpoint.md) a28b1eb0d568 — re-fold
FAIL: tickets['02-export-endpoint'].ac_hash 7b2cbf9f76ee ≠ recomputed 3fa4ea9dd6a4 — re-fold
FAIL: ticket '02-export-endpoint' body changed since the fold (file a28b1eb0d568 ≠ brief 9463b2cb24b7) — re-fold, never hand-edit the brief
FAIL: stage 'implement-export-endpoint' embedded ticket block does not match tickets/02-export-endpoint.md — the brief was hand-edited; re-fold

5 problem(s) found — the fold refuses.
exit=1
```

plus `WARN: AC Coverage Map row "AC-1 a completed export…" is covered by no ticket in this set` —
the uncovered-row WARN firing for real. And the refusal wrote nothing:
`shasum -a 256 workflow.yaml` is `0e51cc1f78ab…` both before and after.

The same log then runs the **shipped** `validate_workflow.py` over the identical folder and prints the
same five FAILs (differing only in the closing line, `5 problem(s) found — fix before treating this
workflow as frozen.`, exit 1) — the port and the reference agree message for message.

The clean fold's F4 refresh table and the printed-never-posted carrier
(`logs/01-fold-enactment.log`; `unchanged` rows are printed, not suppressed):

```
ticket              body_sha256   ac_hash                verified_against  status
01-csv-writer       c9a89fea09ac…  3ce0ab14e046…          cc834eb91491…      unchanged
02-export-endpoint  9463b2cb24b7…  7b2cbf9f76ee…          cc834eb91491…      unchanged
03-streaming        5c348c00f7ab…  d19586d35515…          cc834eb91491…      unchanged

Verified-against: cc834eb91491… · ac_hash: 3ce0ab14e046… · extractor: v1 · fold: 2026-08-02T14:55:47Z
Verified-against: cc834eb91491… · ac_hash: 7b2cbf9f76ee… · extractor: v1 · fold: 2026-08-02T14:55:47Z
Verified-against: cc834eb91491… · ac_hash: d19586d35515… · extractor: v1 · fold: 2026-08-02T14:55:47Z
```

The `values` run over the same set prints the same three hashes with status `new` (nothing recorded
yet) — that is what a genuine first fold shows, and the two runs together prove the status column
is computed rather than decorative.

## 4. AC 3 — a ticket edit forces a re-fold, and no hand-edit path exists

**Re-fold** (`logs/05-refold.log`). A prose word added to `03-streaming.md`'s `## What to build`
upstream; fold start re-materializes with §1's pipeline and refuses:

```
FAIL: tickets['03-streaming'].body_sha256 5c348c00f7ab ≠ sha256(tickets/03-streaming.md) 942ddcdd761c — re-fold
… 3 problem(s) found — the fold refuses.   exit=1
```

Then the re-fold (overwrite `tickets/`, recompute, rewrite *both* recorded copies + `verified_at`):

```
$ python3 logs/fold_check.py check /tmp/wave4a/refold        → FOLD OK …  exit=0
$ python3 /tmp/wave4a/refold/validate_workflow.py …/refold   → PASS — 7 stages…  exit=0
$ diff -rq /tmp/wave4a/refold-before /tmp/wave4a/refold
Files …/tickets/03-streaming.md and …/tickets/03-streaming.md differ
Files …/workflow.yaml and …/workflow.yaml differ
exit=1
```

Exactly two files moved. `ac_hash` did **not** move — the edit was prose, not an AC row, which is the
`ac_hash`-over-Coverage-Map-rows decision paying off rather than being asserted. (`state.json` did
not move either: the stage set is unchanged. `diff -rq` stands in for `git diff --stat` because the
run folder is untracked until the orchestrator commits it.)

**The four hand-edit routes** (`logs/04-hand-edit-routes.log`) — all exit 1 **through both
implementations** (`fold_check.py` and the shipped `validate_workflow.py` are run back-to-back on each
route), each naming a different disagreement, which is the actual claim:

| Route | What was edited | Exit | The distinguishing FAIL |
|---|---|---|---|
| (a) | the brief block only | 1 | `stage 'implement-csv-writer' embedded ticket block does not match tickets/01-csv-writer.md — the brief was hand-edited; re-fold` (1 FAIL, the sha still agrees with the untouched file) |
| (b) | `tickets/01-csv-writer.md` only | 1 | `ticket '01-csv-writer' body changed since the fold (file fbbf5ba53318 ≠ brief c9a89fea09ac)` + the map's `body_sha256` (3 FAILs) |
| (c) | file + block + delimiter hex, map left stale | 1 | `tickets['01-csv-writer'].body_sha256 c9a89fea09ac ≠ sha256(tickets/01-csv-writer.md) fbbf5ba53318 — re-fold` (1 FAIL — the second recorded copy is what caught it) |
| (d) | all three consistently, on an AC line | 1 | the AC-row refusal + `tickets['03-streaming'].ac_hash d19586d35515 ≠ recomputed 01ba4719c80b` |

Route (c) is the one that justifies the apparent redundancy of two recorded hashes: with only the
delimiter, (c) is green. Route (d) collapses into leg 3's refusal — the three hashes *can* be made to
agree, but they then describe an AC the Coverage Map does not contain. The only all-three edit that
survives is one that touches no AC, and that is a re-fold (it must also refresh `verified_at`), not a
hand edit. **Four routes, four different messages, zero greens.**

**The mid-run guard** (`logs/06-midrun-refold-refusal.log`) — `freeze-tests: passed`,
`implement-csv-writer: running` in `state.json`, then a re-fold:

```
FAIL: refusing to re-fold — stages [freeze-tests, implement-csv-writer] are past 'pending'. A ticket
changed mid-run; the honest paths are (a) let kestra-run escalate to reworking …
exit=1
```

and the same run folder validated *without* `--refold` exits 0 — the guard is scoped to a re-fold,
not to reading a live run.

## 5. The rest of the matrix

**Anchor WARN/FAIL, shipped script, 12 variants** (`logs/07-anchor-matrix.log`, each run with
`cwd=/` to prove the sibling import needs no path setup):

| Variant | Result |
|---|---|
| absent anchor | `WARN: no spec_anchor …` + `PASS` · exit 0 |
| complete valid | `PASS` · 0 WARN · exit 0 |
| each of `raise_commit` / `surface_hash` / `extractor_version` missing | `FAIL: spec_anchor is partial — '<key>' is missing…` · exit 1 (×3) |
| `raise_commit: cc834eb9149` (abbreviated) | `FAIL: … not a full 40-hex commit SHA … abbreviated SHAs are not comparable` |
| `surface_hash: 2f2e17ed` | `FAIL: … not a 64-hex sha256` |
| `extractor_version: v1` | `FAIL: … not a positive integer` |
| `extractor_version: 2` | `FAIL: … 2 ≠ … EXTRACTOR_VERSION 1 — the hashes are not comparable; re-fold` |
| spec moved (one FR bullet added) | `FAIL: spec_anchor.surface_hash 2f2e17eda1f0 ≠ … recomputed now 0ded4ecbe766 …` |
| `requirement_surface.py` deleted, anchored | `FAIL: spec_anchor present but requirement_surface.py is not beside this script …` |
| `requirement_surface.py` deleted, unanchored | `FAIL: this workflow carries a sliced ticket set but requirement_surface.py is not beside this script …` · exit 1 — the fixture is a *sliced* fold, so an unverifiable `ac_hash` FAILs even with no anchor to check |

10 of the 12 variants exit 1 (11 FAIL lines); only `absent-anchor` and `complete-valid` exit 0 —
absent is a WARN, partial is a FAIL, and not-run is not passed. Every variant also carries the 3
parser-trap WARNs the fixture's sliced briefs always produce (§6), and an abbreviated
`raise_commit` is reported **once**: the per-ticket `verified_against` cross-check stands down when
the anchor's own shape has already FAILed, so one defect is not counted four times.

**`progress:` copy and owner resolution** (`logs/08-progress-copy.log`):

```
progress → 'implement-csv-writer' by unique containment: byte-equal to the spec bullet
progress → 'integrate-and-verify' by exact match: byte-equal to the spec bullet
```

Rule order matters and is exercised: `python3 -m pytest tests/csv_export` is *contained* in five
stages' commands, so only rule 1 (exact match) resolves it to `integrate-and-verify`, and the
`test_writer.py` bullet resolves by rule 2 alone. Byte-equality is asserted by string comparison, not
eyeballed — a one-word rewording (`must reach 0` → `must hit 0`) exits 1 and prints both strings. A
third bullet naming `npm run export:bench` prints `ASK: … resolves to 0 candidate stage(s) [] — name
the owner.` followed by the documented stop. And the shipped validator's §A5 line:

```
$ python3 /tmp/wave4a/progress-empty/validate_workflow.py /tmp/wave4a/progress-empty
FAIL: stage 'integrate-and-verify' exit_criteria.progress is empty — omit the field or give it the spec's own progress fragment
exit=1
```

**Non-vacuity** (`logs/09-nonvacuity.log`). Five mutants under `/tmp`, no source file touched; each
must make one *named* leg above stop failing, and each does. Mutants 4 and 5 repeat mutants 1 and 2
against the **shipped** validator, which is what makes the port itself non-vacuous rather than
inherited from the reference:

| Mutant | Named leg | Mutant result |
|---|---|---|
| `fold_check`'s block-vs-file text compare → `if False:` | leg 4 route (a) | `FOLD OK …` exit 0 — so route (a) is caught by that compare and nothing else |
| `fold_check`'s `verified_against` cross-check → `if False:` | a map refreshed against `000…0` (3 FAILs unmutated) | `FOLD OK …` exit 0 |
| `validate_workflow`'s absent-anchor `warnings.append` → `problems.append` | leg 10's worked example | `FAIL: no spec_anchor …` exit 1 |
| **shipped** `validate_workflow`'s block-vs-file compare → `if False:` | leg 4 route (a), shipped half (1 FAIL unmutated) | `PASS — 7 stages …` exit 0 |
| **shipped** `validate_workflow`'s `verified_against` cross-check → `if False:` | the `000…0` map, shipped half (3 FAILs unmutated) | `PASS — 7 stages …` exit 0 |

**Story 24, the worked example, unmoved** (`logs/10-worked-example.log`): `validate_spec.py` over
`workflow/runs/order-cancellation-refund/0-spec.md` ⇒ **0 FAIL / 5 WARN / exit 0**;
`validate_workflow.py` over the folder ⇒ `WARN: no spec_anchor …` + `PASS — 11 stages, structurally
sound.` / exit 0; `grep -c 'spec_anchor\|ticket:begin' workflow.yaml` ⇒ `0`. The monolithic,
unanchored, ticket-free path is still fully valid, and its only new output is one WARN.

**The repo's own checks** (`logs/11-unit-suites.log`): `py_compile` clean on all five scripts;
`test_requirement_surface.py` → `Ran 12 tests … OK`; `test_validate_workflow_anchor.py` →
`Ran 42 tests … OK` (20 new §A4 cases: the four hand-edit routes, the five graded map fields,
map↔file↔brief in every direction, the partial delimiter, two blocks in one stage, the parser-trap
WARN, and the missing-extractor FAIL); `fold_check.py` compiles. The fixture spec through `validate_spec.py`:
**0 FAIL / 1 WARN** (the `*(none — illustrative fixture spec…)*` Files-to-Touch row, which is D9's
intended WARN and confirms wave 2's shape-not-extension discriminator still lets prose through).

## 6. Measured numbers

`logs/12-measured-numbers.log`, and the two findings a reader should carry away.

```
0-spec.md                        4214 bytes
workflow.yaml (folded)           7856 bytes
  block 01-csv-writer             581 bytes  (ticket file 386 + 195 of delimiters/indent)
  block 02-export-endpoint        647 bytes  (ticket file 430 + 217 of delimiters/indent)
  block 03-streaming              395 bytes  (ticket file 214 + 181 of delimiters/indent)
  embedded blocks, total         1623 bytes  = 21% of workflow.yaml

per-spawn context rent for one implement stage's brief:
  implement-csv-writer       brief   1087 bytes   vs the full spec   4214 bytes   = 26%
  implement-export-endpoint  brief   1128 bytes   vs the full spec   4214 bytes   = 27%
  implement-streaming        brief    848 bytes   vs the full spec   4214 bytes   = 20%
```

So the embedded block costs ~**190 bytes of delimiter/indentation per slice** (a fixed cost: the
64-hex sha256 twice-named id delimiter pair), and a per-spawn implement brief is **20–27% of the
full spec it replaces** on this fixture. Story 14's context-rent claim is therefore *directionally
confirmed at this size* and no more: on a 4 KB spec the saving is ~3 KB per spawn, and the ratio will
move with spec size — a bigger spec makes the fold look better, a spec barely longer than one slice
makes it look worse. Validator wall time: `real 0.05` for both `validate_workflow.py` and
`fold_check.py` over the run folder.

**Finding 1 — parser trap #1 is wider than the design record says** (`logs/02-parsed-brief-loss.log`,
measured, not reasoned):

```
'## What to build'         in raw file: True   in parsed brief: False
'## Acceptance criteria'   in raw file: True   in parsed brief: False
'#47'                      in raw file: True   in parsed brief: False
'ticket:begin'             in raw file: True   in parsed brief: True
```

`_strip_comment` fires on `" #"`, and **every `to-tickets` section heading is `"  ## …"`, which
contains `" #"`.** So it is not an incidental `#47` that vanishes from the parsed brief — the slice's
own `## What to build` / `## Acceptance criteria` headings do. Two consequences for whoever ports
§A4, both since acted on: (i) the raw `workflow.yaml` text is the *only* truth for an embedded block,
exactly as designed, and the port compares raw text everywhere; (ii) the `" #"` WARN fires on
**every** sliced brief (3 of 3 here), not on the rare one — `workflow-schema.md`'s parser-trap 1 now
words it as a standing property of sliced briefs rather than an incidental `#47`, so the WARN reads
as a note about the parsed view instead of noise about one ticket.

**Finding 2 — the parsed brief also loses every newline.** The block scalar comes back as one joined
line (see the log's `--- the PARSED brief ---` dump). A consumer that reads the parsed value gets the
checkbox list as a single run-on line. Same mitigation, same reason: read the raw file.

## 7. Not established

* **F0 was not exercised.** The fixture spec is not committed (this agent may not commit; the
  orchestrator does), so `chain-provenance.md` §2's exactly-one-match predicate has no raise commit
  to find. `git rev-parse HEAD` stands in as the anchor value. F0's 0-match and >1-match hard fails
  remain untested by command.
* **F1's `git show <raise>:<spec-path>` side is simulated** by a byte copy of the fixture spec. The
  recompute-vs-recompute *comparison* is real (same script, both sides, and the mismatch branch is
  exercised in leg 7's `surface-moved` variant); the git plumbing that fetches the as-raised text is
  not.
* **No LLM fold pass was measured** — the fold was enacted by hand in the session that wrote this
  eval, so there is no isolated token count or wall time for a `kestra-build` fold spawn. Wave 1's
  instrumented-rerun format could not be reproduced without a live pass.
* **The mid-run re-fold guard and the `progress:` owner ladder stay eval-only.** They are
  kestra-build's own fold-time behavior, not properties of a finished artifact, so `fold_check.py`
  is the only thing that exercises them by command; the shipped validator grades what the fold left
  behind (`§A4` + the `progress:` non-empty FAIL) and no more. (The §A4 gap this eval originally
  reported — a hand-edited brief passing `validate_workflow.py` with exit 0 — is closed: legs 3, 4
  and 9 now show the shipped script refusing all four routes.)
* **Form A(a) (GitHub tracker) was not run**: `gh` is read-only for this agent and the eval is
  deliberately offline. Only the `tr -d '\r'` normalization is shared between the two forms, and
  that half is exercised.
* **`progress:` on a non-`fixing` stage (the "will never be compared" WARN)** was not exercised —
  the fixture's two owners both retry.
* **Expand–contract residuals 1 and 2 are only structurally present** (the fixture's
  `integrate-and-verify` owns the unmodified suite command and the suite-level metric, and each batch
  brief carries its own "this gate proves X only" sentence). The freeze-vs-migrate-batch rejection
  paths — post-freeze test paths in a `write_scope`, a second `freeze_after` — are already covered by
  `validate_workflow.py`'s existing checks and were not re-tested here.

## 8. Re-running this

```bash
cd <repo-root>
bash workflow/evals/2026-08-02-wave4a-build-fold/logs/run-legs.sh    # rewrites every log in logs/
```

The driver is idempotent: it re-materializes `runs/wave4a-fixture/` from `fixtures/` with the
documented `tr -d '\r'` pipeline, re-copies the three F5 scripts from
`workflow/kestra-build/scripts/`, does all mutation under `/tmp/wave4a` (wiped at start), and touches
nothing else. It runs no `git` write command and no `gh` command.

Individual pieces, without the driver:

```bash
EV=workflow/evals/2026-08-02-wave4a-build-fold
python3 $EV/runs/wave4a-fixture/validate_workflow.py $EV/runs/wave4a-fixture   # shipped: A1-A5
python3 $EV/logs/fold_check.py values $EV/runs/wave4a-fixture                  # F1-F3 compute
python3 $EV/logs/fold_check.py check  $EV/runs/wave4a-fixture                  # F1-F4 + A4 + progress
python3 $EV/logs/fold_check.py check  $EV/runs/wave4a-fixture --refold         # + the mid-run guard
```

Two things will legitimately change on a re-run and are not regressions: `verified_at` /
`fold:` timestamps in leg 5's re-fold (real clock), and `spec_anchor.raise_commit` if the fixture is
re-anchored to a new branch tip — the recorded value `cc834eb9…` is this eval's `HEAD`, and every
`verified_against` in `runs/wave4a-fixture/workflow.yaml` must equal it or both checkers FAIL (that
cross-check is leg 9's mutants 2 and 5).
