# Eval — Wave 3, `kestra-exam`: a real exam, red at the raise commit and green after the work

Ticket [#36](https://github.com/arkaphat/arkaphat-builder/issues/36) (Wave 3 of the prep-chain
implementation, parent [#31](https://github.com/arkaphat/arkaphat-builder/issues/31)), design record
D1–D11.

**A checklist cannot pass this eval.** Every claim below is the output of a command that ran, and the
central claim — *the exam is red before the work and green after it* — is one `exam.py` executed
three times against three real tree states of a real git repo, with the exit codes recorded. The
same exam file, unmodified, produces exit `1` at the raise commit, exit `0` at the implemented
commit, and exit `1` again at a commit where exactly one AC is violated. That third run is the one a
red→green demo cannot fake: it shows the exam discriminates *which* AC broke.

Subjects, all on branch `arkaphat/prep-chain-impl`:

| Subject | Path | Lines |
|---|---|---|
| the skill | `workflow/kestra-exam/SKILL.md` | 403 |
| its references | `references/exam-script-contract.md` · `gate-procedure.md` · `manifest-schema.md` · `regeneration.md` | 208 · 317 · 180 · 148 |
| its scripts | `scripts/exam_harness.py` · `exam_paths.py` · `exam_anchor.py` · `exam_delta.py` | 644 · 211 · 382 · 220 |
| its tests | `scripts/test_exam_harness.py` | 392 |
| the produced exam | `exam/exam.py` · `exam/manifest.md` | 94 · 103 |

Environment: macOS 25.5.0 (Darwin), `python3` stdlib only, `git 2.50.1 (Apple Git-155)`, `zsh` and
`sh` both exercised deliberately, `gh` read-only by rule (`gh auth status` in
[`logs/sweeps.log`](logs/sweeps.log)). No third-party Python anywhere.

---

## 0. What was actually run, and where it landed

```
sh workflow/evals/2026-08-02-wave3-kestra-exam/fixtures/run-legs.sh
```

One command, fifteen numbered legs (0–14, with 4b/5b/5c as sub-legs). It rebuilds the fixture from
scratch, drives kestra-exam's own Process against it, and writes every log in [`logs/`](logs/). The
slowest single step is the 30-test harness suite at 2.0 s; everything else is measured in §4 and none
of it exceeds 0.31 s. Re-running is safe and idempotent: the
fixture repo is deleted and rebuilt, so SHAs and timestamps change while every recorded outcome
(exit codes, counts, causes) does not.

**One-command re-runnability was a claim before it was true.** The round-1 review re-ran this eval with
a fresh `KX_ROOT` that did not pre-exist and it aborted at `. "$ROOT/shas.env"`: `mkdir -p "$ROOT"` sat
*after* leg 0, which already redirected `run()`'s capture file into `$ROOT/.out`, so the fixture was
never built. Fixed 2026-08-02 — the root is created in the prologue, and leg 0 parks its capture file
under `logs/` because `make-fixture.sh` opens with `rm -rf "$ROOT"` (which is what put the perennial
`cat: …/.out: No such file` line into `logs/fixture.log`). Verified by running the prologue and leg 0
with a root that did not exist: exit 0, `shas.env` sourced, no `cat:` line, and `fixture.log` now
carries `make-fixture.sh`'s own output instead of losing it. The committed `logs/fixture.log` predates
that fix — see §5 *Dispositions*.

**Two substitutions, both deliberate and both visible in the logs:**

1. **The exams root is redirected to `/tmp`.** Every invocation runs under
   `KESTRA_EXAMS_ROOT=$KX_ROOT/exams` (default `/tmp/kx36/exams`), and `exam_paths.py` echoes
   `exams_root_overridden: yes` on every single run, so a redirected root can never be mistaken for
   the user-level one. The real user-level exams directory is never created, read or written.
2. **The fixture origin is a host-shaped placeholder**, `https://git.example.test/kx-fixture/tally.git`,
   never contacted (no fetch, no push, `transport: local`). The ticket suggested a `file://` or bare
   local origin; **measured, neither can be keyed at all** — both produce the `< 2 path segments`
   hard stop, because `urllib.parse.urlsplit("file:///…").hostname` is empty
   ([`logs/no-origin.log`](logs/no-origin.log) 10c/10d, and
   [`fixtures/keying.py`](fixtures/keying.py) pins all four stop forms). That is finding **F7**.

**The eval never writes the sweep token.** Sweep S2 forbids the token in any commit message and
S1/S3 forbid it outside the skill's own two exempt paths, so this eval constructs it at run time
(`TOK=$(printf 'kestra%sexams' '/')`) and every sweep runs with `grep -q`, so no hit text can land in
a log either. Verified: `grep -rn "$TOK" <eval-dir> | wc -l` → **0**
([`logs/sweeps.log`](logs/sweeps.log) 12i). An eval that spelled the token would break the sweeps it
tests — including the orchestrator's own commit message for this directory.

### The fixture

[`fixtures/make-fixture.sh`](fixtures/make-fixture.sh) builds a scratch repo with a 14-line stdlib
CLI (`src/tally.py`, sums a CSV `amount` column) and four commits plus one on a branch:

| Commit | Subject | Tree state |
|---|---|---|
| c0 | `add the tally CLI and its sample data` | feature absent |
| **RAISE** | `spec(tally-refund): write 0-spec.md from a hand-written idea` | the spec, feature still absent |
| **IMPL** | `implement --refund and the malformed-amount refusal` | the feature |
| **BROKEN** (branch `broken`) | `fixture: regress the refund test so exactly one AC is violated` | one AC violated (`"refund"` → `"refunded"`) |

The spec, [`fixtures/0-spec.md`](fixtures/0-spec.md) (127 lines), is a grown Wave-2 shape:
`## External Interface` declaring the CLI seam, a Coverage Map with a `Source` column, six ACs — one
`⚠ inferred`, one asserting preservation of existing behavior, one that the declared seam cannot
examine. It is **standalone on purpose** (no `> Spec-ticket:` line), which is what exercises
`exam_anchor.discover_raise`'s standalone-subject fallback. Through kestra-build's own validator it
is silent: `validate_spec.py <spec> <repo>` → **0 FAILs, 0 WARNs, exit 0**
([`logs/modes.log`](logs/modes.log) 5c).

### How the exam was produced

[`fixtures/build-exam.py`](fixtures/build-exam.py) (499 lines) walks SKILL.md §Process steps 1–7 and
§Regeneration. The split matters for reading this eval honestly:

* **Every judgment is hand-written** in [`fixtures/exam-template.py`](fixtures/exam-template.py) —
  which check, which assertion at the seam, which class, the unexaminable reason. Those are the parts
  a real kestra-exam pass asks an agent for.
* **Every derived value is computed**, never typed: the anchor triple (`discover_raise` +
  `extract_surface`), both `sha256`s, the section and per-AC fingerprints, each check's `provenance`
  (read out of the Coverage Map's own `Source` cell), every Red-proof cell (read out of
  `red-proof.json`), and the coverage arithmetic. A hand-typed hash in an eval proves nothing.
* **Two guards run inside the builder**, so a defective manifest cannot be produced quietly: an AC
  with no check row is a hard stop, and a `must-hold` measured red at red-proof time is a hard stop
  (the class-vs-measurement contradiction manifest-schema.md §Manifest FAILs names).

---

## 1. Red at the raise commit, green at the implemented commit, and one behavioral fail in between

The same `exam/exam.py`, three tree states, three `python3` runs
([`logs/red-proof.log`](logs/red-proof.log) · [`logs/green.log`](logs/green.log) ·
[`logs/broken.log`](logs/broken.log)):

| Run | Tree | pass | fail | blocked | unexaminable | unproven | **exit** |
|---|---|---|---|---|---|---|---|
| red proof | clone at RAISE | 4 | **2** | 0 | 1 | 1 | **1** |
| green | clone at IMPL | 6 | 0 | 0 | 1 | 3 | **0** |
| broken | clone at BROKEN | 5 | **1** | 0 | 1 | 2 | **1** |

Per check, literal (`logs/red-proof.log`):

```
C-0    —        must-hold     pass          -                 0.03s
C-1    AC-1     must-flip     FAIL          behavioral        0.04s  CheckFailure: exit 1 != 0 @ tally --refund
C-2    AC-2     must-flip     FAIL          behavioral        0.05s  CheckFailure: exit 1 != 2 @ tally bad.csv
C-3    AC-3     must-hold     pass          -                 0.03s
C-4    AC-4     must-flip     pass          -                 0.03s
C-5    AC-5     must-hold     pass          -                 0.05s
C-6    AC-6     unexaminable  UNEXAMINABLE  -                 0.00s  a single-pass / resident-memory invariant is not observable at the declared seam: …
pass 4 · fail 2 · blocked 0 · unexaminable 1 · unproven 1 · exit 1
```

and the one row that moves at BROKEN (`logs/broken.log`):

```
C-1    AC-1     must-flip     FAIL          behavioral        0.03s  CheckFailure: total line missing 'total: 90' @ tally --refund
```

Three things this table settles that a checklist could not:

* **The reds are `behavioral`, not `infrastructure`** — the seam answered and the answer was wrong.
  The discriminator is `seam.reached`, set by the harness, not by an author's opinion.
* **`must-hold` is not decoration.** C-3 and C-5 are green at RAISE *and* at IMPL *and* at BROKEN;
  had either been red at RAISE, the builder would have refused the manifest.
* **Non-vacuity.** Red→green alone is satisfiable by an exam that only checks "the CLI runs". The
  BROKEN run localises the break to C-1 while the other five stay green.

The failure signature `CheckFailure: exit 1 != 0 @ tally --refund` is byte-for-byte the example the
design record (D2) invented before any of this existed — the `expect(…, where=…)` shape reproduces
it exactly.

### C-0 red voids the whole proof (legs 4 and 4b)

Delete the seam entry point from the clone and re-run
([`logs/smoke-red.log`](logs/smoke-red.log)):

```
C-0    —        must-hold     FAIL          behavioral        0.03s  CheckFailure: exit 2 != 1 @ tally (no args)
C-1 … C-5                     BLOCKED
C-6    AC-6     unexaminable  UNEXAMINABLE
pass 0 · fail 1 · blocked 5 · unexaminable 1 · unproven 3 · exit 2
```

Every `must-flip` becomes `unproven` and the run exits **2**, not 1 — "the harness is broken" and
"the feature fails" are different answers and the ladder keeps them apart. Note the measured detail
(finding **F8**): C-0's red kind here is `behavioral`, because deleting the script still spawns
`python3`, which exits 2, so a `Result` exists. The void rule keys on C-0's *result*, never on its
red kind, so the proof is void either way — but D11's label "infra-red" for this leg was imprecise.
Leg 4b reaches the infrastructure arm honestly, with an unspawnable seam
([`logs/infra-red.log`](logs/infra-red.log)):

```
C-0    —        must-hold     FAIL          infrastructure    0.01s  SeamUnavailable: cannot spawn python3-does-not-exist src/tally.py: [Errno 2] …
pass 0 · fail 1 · blocked 5 · unexaminable 1 · unproven 3 · exit 2
```

The `unexaminable` row is **not** blocked in either leg: it never touched the seam, so `blocked`
would be noise. That is the implementer's decision 4, measured.

### Modes and the exit ladder (leg 5, [`logs/modes.log`](logs/modes.log))

| Command | exit |
|---|---|
| `exam.py --list` (touches no seam) | 0 |
| `exam.py --audit-seam` | 0 |
| `exam.py --only C-2 --repo <clone> --json` (**C-0 ran too**) | 0 |
| `exam.py --only C-99` | 3 |
| `exam.py --bogus-flag` | 3 |
| `python3 -O exam.py` | 3 |
| `--audit-seam` against a manifest whose quoted seam was edited to `src/other.py` | 1 |

`--only C-2` returning a two-row `checks` array (`C-0`, `C-2`) is the mechanical form of "a delta red
proof with no smoke is void by the same rule as a full one".

---

## 2. The manifest, the anchor, and staleness

[`exam/manifest.md`](exam/manifest.md) carries all seven sections in the fixed order with
`## Verdict contract` last. Its §Anchor, as the eval left it (generation 2):

| Field | Value |
|---|---|
| raise_commit | `f59837b1323b009647d266ed99ee35f49b2bb10d` (discovered, never hand-picked) |
| surface_hash | `7f2b7f2fa398…` (`7e47c7ab7978…` at generation 1) |
| extractor_version | 1 |
| exam_script_sha256 | `a403e490b02f…` |
| generation | 2 |

`exam_anchor.py` compares three copies — manifest, pointer body, `exam.py`'s `ANCHOR` — and the
pointer's two hashes match the artifacts on disk (`shasum -a 256` in
[`logs/pointer-duplicate.log`](logs/pointer-duplicate.log)).

**Nine staleness arms, one command each** ([`logs/stale-anchor.log`](logs/stale-anchor.log)):

| Leg | Mutation | Cause line printed | exit |
|---|---|---|---|
| 7a | none | `FRESH: surface 7e47c7ab7978 @ raise … — manifest, pointer and exam.py agree.` | 0 |
| 7b | one Coverage-Map `Source` cell (in surface) | `surface or raise moved since the exam was written` | **2** |
| 7c | a Files-to-Touch cell **and** an Out-of-Scope line (out of surface) | `FRESH …` | **0** |
| 7d | pointer `surface_hash` tampered | `anchor copies disagree — manifest vs pointer on surface_hash; pointer says …` | 2 |
| 7e | pointer `v1` marker removed | `pointer body is malformed — its first line must be exactly …` | 2 |
| 7f | manifest `raise_commit` truncated to 8 hex | `partial anchor — malformed or absent: raise_commit` | 2 |
| 7g | `exam.py`'s own `ANCHOR` edited | `anchor copies disagree — manifest vs exam.py on raise_commit; exam.py says …` | 2 |
| 7h | extractor removed, `HOME` redirected so all four candidates miss | `extractor missing — no requirement_surface.py at any of: <four paths>` | 2 |
| 7i | everything restored | `FRESH …` | 0 |

Legs 7b and 7c are the two halves of story 21 in one file: **an AC row moves the anchor; the whole
provision layer does not.** Both were measured on the same spec, one edit apart. Every refusal printed
all three fields with `==` on the ones that had not moved, exactly as designed — a refusal that showed
only the mismatching field would hide which of the three moved next time.

### The born-green `must-flip` and the verdict (leg 6, [`logs/verdict.log`](logs/verdict.log))

C-4 (AC-4, `⚠ inferred`) is a `must-flip` whose AC was *already satisfied* at the raise commit: at
RAISE, `tally.py --bogus data/mixed.csv` already exits 1 with a usage line. Measured `pass` at
red-proof time, so:

* manifest row: `` | AC-4 | C-4 | must-flip | ⚠ inferred | **born-green — `unproven`** | — | — | ``
* **the class is not demoted** to `must-hold` — that would launder missing evidence into a
  legitimate-looking regression guard
* `## Coverage`: `ACs in surface: 6 · executably covered: 5 · unexaminable: 1 · must-flip: 3
  (unproven: 1) · must-hold: 3`, and `red-proof.json`'s `summary.unproven` is `1` — the builder
  hard-stops if those two disagree
* [`logs/red-proof.log`](logs/red-proof.log) carries the one-line reason, so a reviewer sees *why* the
  evidence is degraded

The verdict a gate runner would emit, computed from the artifacts (not typed):

```
verdict:   PASS
evidence:  degraded — 1 unproven of 3 must-flip
coverage:  5/6 ACs executably covered; unexaminable: AC-6
run:       2026-08-02T15:22:40Z · exam.py sha256 202404e5e49f · exit 0
```

A `PASS` that dropped the `evidence:` clause with `U > 0` would be a malformed verdict — which is what
makes "never silently counted as passing" checkable instead of aspirational. The full appended file is
[`logs/manifest-with-verdict.md`](logs/manifest-with-verdict.md), and producing it surfaced two design
defects: findings **F4** and **F5** below.

---

## 3. Delta regeneration and pointer discipline

All four scopes, one command each, same spec, one edit apart
([`logs/delta-regen.log`](logs/delta-regen.log)):

| Leg | Edit | `scope:` | `regenerate:` | `carry:` |
|---|---|---|---|---|
| 8a | none | `current` | `-` | C-0 … C-6, and `generation: unchanged` |
| 8b | one Edge-Cases bullet reworded | `re-anchor` | `-` | C-0 … C-6, plus the "verify the Coverage Map still paraphrases them" note |
| 8c | one `## External Interface` line | `full` | **C-0 C-1 C-2 C-3 C-4 C-5 C-6** | `-` |
| 8d | AC-1's `Source` cell | `delta` | **C-1** | C-0 C-2 C-3 C-4 C-5 C-6 |

Then the regeneration itself (8f–8h), with the 8d edit in place:

* fresh red proof for **C-1 only**, in a new disposable clone at the new raise commit, `--only C-1`
  (and C-0 ran regardless): `red-proof (gen2) json exit=1`
* `exam.py`'s `ANCHOR` and C-1's `provenance="US-1, US-4"` rewritten — the provenance came from the
  spec's own `Source` cell, so re-authoring is derived, not invented
* the exam dir's git log is **2 commits**, and the second is a bounded diff — `git diff --stat
  HEAD~1 HEAD` touches four files (`exam.py`, `manifest.md`, `red-proof.json`, `red-proof.log`) for
  **34 insertions and 17 deletions**; the full diff of `manifest.md` and `exam.py` is in the log
* **carried rows keep their original red-proof timestamp** and the regenerated row gets a new one, in
  the same table — visible in the diff: C-1 moves to `15:22:42`, C-2 stays at `15:22:36`. The
  timestamp itself shows which evidence predates this generation.
* `git -C <exam-dir> remote` prints nothing, at both generations
* afterwards: `exam_anchor.py` → `FRESH … generation 2`, `exam_delta.py` → `scope: current`, and the
  exam still runs green at IMPL (exit 0)

**The pointer was edited in place** ([`logs/pointer-duplicate.log`](logs/pointer-duplicate.log)):
one `tally-refund.pointer` file, `generation: 2` in the body, both hashes matching `shasum -a 256`,
and exactly one appended line in `tally-refund.pointer.log`:

```
2026-08-02T15:22:43Z regenerated C-1 (AC-1 changed); surface 7e47c7ab… → 7f2b7f2f…; raise f59837b1… → f59837b1…; generation 1 → 2
```

**`>1` is a hard fail, never resolved by recency.** With a second record planted, the check reports
`matches=2` and the designed text is emitted with paths in place of issue numbers; `ls -t | head -1`
is shown only to name what recency *would* have picked, and it is refused. Removing the plant returns
`matches=1`. This is the local-file transport end to end — a first-class decided path (D4), not a
stand-in.

### The hard stops (leg 10, [`logs/no-origin.log`](logs/no-origin.log))

| Leg | Situation | exit |
|---|---|---|
| 10a | the fixture origin | 0 (`transport: local`) |
| 10b | `git remote remove origin` | 1, verbatim `NO_ORIGIN` text, and `test ! -d <exams-root>` → **0: nothing was created** |
| 10c | `file:///tmp/…/origin.git` | 1, + `— the origin URL yields fewer than two path segments (…)` |
| 10d | a bare local path | 1, same |
| 10e | run folder `Tally_Refund` | 1, `not a usable feature slug (needs ^[a-z0-9][a-z0-9-]{0,63}$)` |
| 10f | a remote added to the exam repo | 1, `an exam is local evidence and is never pushed` |
| 10g | [`fixtures/keying.py`](fixtures/keying.py): 9 URL forms + 4 unkeyable forms | 0 — every expectation held |

10g reproduces D3's five published examples byte-for-byte and re-measures the collision that motivated
full-path joining: `gitlab.example.co.th/team/sub/kestra` and `…/other/sub/kestra` both key to
`gitlab.example.co.th__sub__kestra` under a last-two-segments rule, and to distinct keys under the
shipped one.

---

## 4. The sweeps, the harness tests, the installer, and the cost

**The skill's own tests**: `python3 test_exam_harness.py` → `Ran 30 tests in 2.0s … OK`
([`logs/harness-tests.log`](logs/harness-tests.log)). `py_compile` on all five skill scripts plus this
eval's three Python files plus the generated `exam.py` → **8 files, exit 0** (the `.pyc` output is
redirected to `/tmp`, and the whole run sets `PYTHONDONTWRITEBYTECODE=1`, so nothing in the repo grew a
`__pycache__`).

**The four sweeps** ([`logs/sweeps.log`](logs/sweeps.log)), exit `1` = clean, `0` = a hit, `≥2` = the
check itself failed:

| Sweep | Target | Result |
|---|---|---|
| S1, no exemptions | this repo | **0** — a hit (the skill's own two paths) |
| S1, with the two exemptions | this repo | **1** — clean |
| S2 (commit messages, no exemption) | this repo, `--all` | **0 lines** — clean |
| S3, unwrapped in `zsh` | this repo | **128** — `fatal: unable to resolve revision: …`, the check never ran |
| S3, guarded under `sh -c`, with exemptions | this repo | **0 — a hit** (finding **F1**) |
| S1 / S2 / S3 | scratch repo, leak committed at N and removed at N+1 | **1 / 0 lines / 0** — S1 and S2 clean, **S3 hits** |
| S3 with / without the exemption | scratch repo whose only occurrence is under `workflow/kestra-exam/*` | **1 / 0** |
| self-hit | `printf 'kestra-exam skill' \| grep -c "$TOK"` | **0** (grep exit 1) |
| token in this eval directory | `grep -rn` | **0** |

The leak-committed-then-removed scenario reproduces #27(c)'s empirical claim exactly, and the zsh leg
reproduces the design's own warning about the recipe. S4 is **not applicable to this fixture** — the
origin is `git.example.test`, so `transport()` returns `local` and there is no chain tracker — so the
GitHub read predicates were measured against the real trackers instead, read-only:

```
$ gh issue list --repo arkaphat/kestra --label kestra-exam --state all --limit 100 \
    --json number,title,url --jq '[.[]|select(.title=="kestra-exam: tally-refund")]|length'
the 'arkaphat/kestra' repository has disabled issues            exit=1
$ gh issue list --repo arkaphat/arkaphat-builder --state all --limit 5 --search "$TOK" \
    --json number --jq '[.[]|.number]'
[36,31,27,20,29]                                                exit=0
```

The second line is why D5 bounds the sweep to the chain tracker (five permanent design-tracker hits).
The first is finding **F9**: the real skill repo has issues **disabled**, so `exam_paths.transport()`
returns `local` for `github.com__arkaphat__kestra` today — D5's concrete expectation of a GitHub
pointer ticket there does not hold until issues are enabled.

**The installer** ([`logs/install.log`](logs/install.log)): `bash install.sh --project /tmp/…` exits 0
and installs **16** skills, `kestra-exam` among them (`test -d … → 0`), because `grep -n 'kestra-'
install.sh` shows the `SKILLS` array now carrying `kestra-spec kestra-build kestra-run kestra-exam`.
**This leg moved during the wave and was re-run on 2026-08-02:** at first measurement the entry was
absent (`test -d … → 1`) and this eval recorded the array plus the four README surfaces as the
landing-bar items it did not close; the agent that owns them has since added the entry, so the leg was
re-executed against the current tree rather than left contradicting it. The leg now *measures* the array
instead of asserting a state. (`sh install.sh` dies at line 202 on `< <(find …)`; it is a bash script.
Harness note, not a repo defect.)

**Cost, wall time on this machine** ([`logs/timings.log`](logs/timings.log)):

| Operation | real |
|---|---|
| `exam.py --repo <clone>` — 7 checks, 6 subprocess spawns | **0.304 s** |
| `exam.py --only C-1 --repo <clone>` — subset + C-0 | 0.152 s |
| `git clone --no-hardlinks` + `checkout <raise>` (the red-proof clone) | 0.099 s |
| `exam_anchor.py` (freshness, three-way) | 0.113 s |
| `exam_delta.py` (the regeneration plan) | 0.104 s |
| `test_exam_harness.py` (30 tests) | 2.001 s |
| S1 with exemptions | 0.040 s |
| S3 guarded under `sh -c` | 0.230 s |

Harness-measured, from `red-proof.json`: `duration_s` **0.072**, per check
`C-0 0.034 · C-1 0.037 · C-2 0.046 · C-3 0.032 · C-4 0.035 · C-5 0.046 · C-6 0.0`.

### Counts

| Number | Value |
|---|---|
| ACs in the requirement surface | 6 |
| checks declared | 7 (C-0 + one per AC) |
| executably covered ACs | 5 |
| `unexaminable` | 1 (AC-6, with a reason naming why *the seam* cannot induce it) |
| `must-flip` / `must-hold` | 3 / 3 (C-0 counts as `must-hold`) |
| `⚠ inferred`-derived checks | 1 (C-4) |
| `unproven` at red-proof time | **1** (born-green C-4) |
| `unproven` reported by the green gate run | **3** — see finding F5 |
| exam dir commits | 2 (create, regenerate) |
| generations | 2 |
| eval Python/shell | `build-exam.py` 499 · `run-legs.sh` 612 · `make-fixture.sh` 153 · `exam-template.py` 94 · `keying.py` 78 |
| logs | 17 `.log` files, 1 528 lines, plus `red-proof.json` and `manifest-with-verdict.md` (1 757 lines over 19 files) |

---

## 5. Seven things that did not behave as designed

Reported as found. The eval only measures; none of the skill's files were edited to make a leg pass.

**F1 — S1 can report a false clean over a *tracked* leak, and S3 already hits on this repo.**
The token sits in two tracked files, `idea/flow-final.excalidraw` and `idea/flow-final.svg` (added by
`0028bc7 Assemble flow-final: the locked prep-chain design as one diagram`), which are outside both
exempt paths. Measured, same repo, same pattern:

```
git grep -l "$TOK" -- idea/                            -> 2 files   exit=0 (hit)
git grep -l --untracked "$TOK" -- idea/                -> nothing    exit=1 (a FALSE clean)
git grep -l --untracked --no-exclude-standard "$TOK" -- idea/  -> 2 files  exit=0
git ls-files -v idea/flow-final.svg                    -> H (tracked)
git check-ignore --no-index -v idea/flow-final.svg     -> .git/info/exclude:8:idea/
```

Mechanism, measured end to end: `idea/` is listed in this repo's local `.git/info/exclude`, the two
files are tracked anyway, and `--untracked` implies `--exclude-standard`, whose walk skips excluded
paths **including tracked ones**. `git check-ignore` *without* `--no-index` reports them as not
ignored (it assumes tracked ⇒ not ignored), which is why the condition is invisible by hand. Two
consequences: the residual as written ("`--untracked` skips gitignored files") understates the
failure — S1 also skips tracked files under an exclude rule, so it can report clean over a committed
leak; and **S3 cannot pass on this repo today** until those two diagram exports are re-exported
without the path or the exemption list grows a third entry. A minimal scratch repro does *not*
reproduce it (`--untracked` finds tracked files normally there), so the trigger is specifically
"tracked ∧ excluded".

**F2 — the S3 recipe is shell-dialect-dependent, as its own note says.** Unwrapped in `zsh`: exit
`128`, `fatal: unable to resolve revision: <all SHAs as one argument>`. Under `sh -c`: it runs. The
design record's warning reproduces; recorded here with both outputs so nobody re-derives it.

**F3 — the pointer multiplicity glob matches its own log file.** `ls <slug>.pointer*` returns
`{.pointer, .pointer.log}` after the very first regeneration, i.e. `matches=2` on a *healthy* exam,
which the rule reads as the ">1 is forgery" hard fail. The predicate has to exclude the `.log`
sibling (this eval uses `| grep -v '\.pointer\.log$'`, and both counts are recorded).

**F4 — appending the verdict invalidates the pointer's `manifest_sha256`.** Measured:

```
pointer manifest_sha256 : 495969728228…    sha256 manifest.md now : 495969728228…  (match: True)
                                            sha256 after appending : 1bf43b3114f3…  (match: False)
```

gate-procedure.md §5 reads that mismatch as *"the evidence table was edited after recording"* ⇒
refusal. So the first gate run's own append makes every later gate run refuse, unless the runner
rewrites the pointer after appending — which the procedure does not say it does.

**F5 — "whenever U > 0" does not say *which* U, and the two disagree.** `summary.unproven` is
recomputed per run: `1` in `red-proof.json` (the born-green C-4) but **`3`** on the green gate run,
because every `must-flip` passes there and none produced a behavioral red *in that run*. A gate reading
U from its own JSON would stamp `degraded — 3 unproven of 3 must-flip` on a perfect delivery.
`exam_harness.summarize`'s docstring is the only place that says the manifest's cells come from
`red-proof.json`; gate-procedure.md §6 and manifest-schema.md §7 should name the source explicitly.

**F6 — the AC→check map is a byte match, so a decorated `AC` cell silently under-regenerates.** With
one manifest cell changed from `AC-1` to `AC-1 — refund subtraction` and the same spec edit,
`exam_delta.py` still prints `scope: delta` and `why: AC-1 changed` but `regenerate: -` — nothing
would be re-proved, and nothing says so. The manifest's `AC` cell must be byte-identical to the
Coverage Map's `AC` cell; that constraint is currently implicit.

**F7 — a `file://` or bare-path origin cannot be keyed**, so it is unusable as a fixture (or as a real
origin): both hit the `< 2 path segments` stop because the URL has no host. Correct behavior for the
stated goal, but it removes the obvious offline origin, and nothing in the design record mentions it.

**Two smaller ones.** `exam_delta.py` derives the feature slug from the exam-dir *basename*, so a
copied or renamed exam dir prints `raise … -> UNRESOLV` inside an otherwise-normal plan and still
exits 0 (visible in leg 8e, where the decorated manifest lives in `/tmp/kx36/exam-decorated`). And
the red-proof merge semantics for a delta regeneration are unspecified: this eval merges the fresh
rows into `red-proof.json`, adds a per-row `red_proof_at` so carried rows can keep their original
timestamp, and appends a top-level `generations` list — a decision the design record did not make.

---

## 6. Scope of evidence — what this eval does not establish

- ❌ **No live `kestra-exam` invocation.** No agent was handed the 403-line SKILL.md and asked to
  produce an exam. `build-exam.py` walks the Process *mechanically*; the check bodies were authored by
  hand against the spec's surface. So this eval establishes that the skill's machinery, contracts and
  artifacts work and interlock — not that an agent reading SKILL.md converges on them. That is the
  Wave-5 dogfood.
- ❌ **No gate runner exists**, by design (#24/#31 keep it out of this skill). The verdict in §2 was
  computed by ~40 lines of eval Python following §7 of the manifest, not by a runner. Findings F4 and
  F5 are therefore *predictions about the first runner*, each backed by a hash or a count, not
  observations of one failing.
- ❌ **The GitHub pointer transport was never written to.** `gh` is read-only by rule. What is
  measured: `gh auth status`, the exact-title predicate against `arkaphat/kestra` (issues disabled →
  F9), and the design-tracker sweep returning `[36,31,27,20,29]`. `gh issue create` / `gh issue edit`
  are verified command *shapes* only. The `userContentEdits` tamper check has no local equivalent and
  was not staged.
- ❌ **Only the `Cli` seam kind ran.** `Http` and `Module` are declared, unit-tested inside
  `test_exam_harness.py`, and unexercised by any real exam here. The boot/ready-timeout path of `Http`
  in particular has no end-to-end evidence.
- ❌ **The fixture is small and single-seam** — a 14-line CLI, six ACs, a 94-line `exam.py`. It says
  nothing about a feature with an HTTP seam, fixtures that need a database, or a Coverage Map with
  thirty ACs where the one-check-per-AC rule starts to bite.
- ❌ **The born-green row was authored deliberately.** C-4 demonstrates that the mechanism records and
  flags missing evidence; it does not show that an agent would *notice* an already-satisfied AC and
  still classify it `must-flip` rather than quietly making it `must-hold`.
- ❌ **`unexaminable` is n=1**, and it is the easy case (a memory invariant at a CLI seam). Whether the
  category stays honest — rather than becoming the drawer awkward ACs go into — is a judgment no
  command here can test.
- ⚠️ **The extractor was copied from this repo's `workflow/kestra-build/scripts/`,** because the
  fixture repo is not the skill repo and **none** of the four resolution candidates existed (recorded
  in [`logs/create.log`](logs/create.log), including
  `~/.claude/skills/kestra-build/scripts/requirement_surface.py` → absent on this machine). A real
  feature repo resolves candidate 3 or 4; this eval had to reach outside the list, so the
  copy-per-run *mechanism* is proven while the *resolution order* is only proven in its failing arm
  (leg 7h).
- ⚠️ **The manifest is written twice at creation.** The Red-proof cells cannot exist before the red
  proof runs, so `build-exam.py` writes an §Anchor + §Read-rule stage first (so `--audit-seam` has a
  block to compare against) and the full manifest after. The transient carries a `pending …` cell
  outside the closed five-value vocabulary; it is never committed or hashed, but the design record
  does not describe this ordering at all.

---

## 7. Artifacts

| Path | What it is |
|---|---|
| [`fixtures/0-spec.md`](fixtures/0-spec.md) | the fixture feature's spec — grown shape, standalone, 6 ACs; **0 FAILs / 0 WARNs** through `validate_spec.py` |
| [`fixtures/make-fixture.sh`](fixtures/make-fixture.sh) | builds the scratch repo under `$KX_ROOT` (default `/tmp/kx36`): 4 commits + 1 branch commit, three tree states |
| [`fixtures/exam-template.py`](fixtures/exam-template.py) | the hand-authored exam: header + `EXAM` + `ANCHOR` + `SEAM` + 7 checks, with derived values as placeholders |
| [`fixtures/build-exam.py`](fixtures/build-exam.py) | walks SKILL.md §Process 1–7 (`create`) and §Regeneration (`regenerate`) |
| [`fixtures/keying.py`](fixtures/keying.py) | re-measures `origin_key` on 9 URL forms + 4 unkeyable forms; exit 0 iff every expectation holds |
| [`fixtures/run-legs.sh`](fixtures/run-legs.sh) | **the whole eval, one command**, 15 numbered legs (0–14) → `logs/` |
| [`exam/`](exam/) | byte copies of the produced exam dir at generation 2, plus `manifest-gen1.md` (`git show HEAD~1:manifest.md`) and the exam dir's own `git log` |
| `logs/*.log` | one file per leg; every command line, every literal output, every exit code |

**Do not edit `fixtures/0-spec.md` without re-running `run-legs.sh`.** Every hash, fingerprint and
red-proof cell in `exam/` is derived from it; a hand-edited spec silently invalidates the entire
recorded run — which is, fittingly, the exact failure the staleness refusal exists to catch.
