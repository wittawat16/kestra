# The gate procedure — sweeps, exemptions, pointer discipline

Read this when running the pre-delivery gate, when a leak sweep reports a hit, when a pointer body
looks edited, or when deciding which tracker a check is allowed to touch.

**Building the gate runner is not part of kestra-exam.** This file is the procedure a runner must
follow; kestra-exam produces the artifacts it reads and stops there. Writing the runner inside this
skill would produce a phantom nobody wired up.

**Single owner of the framing:** design ticket `arkaphat/arkaphat-builder#27` (c) owns the leak-sweep
recipe, its exit semantics, and — importantly — the statement that **all of this is detection, never
prevention**. That framing and its residual list are cited here **by reference and not paraphrased**,
because a paraphrase of an honest-limits list is how the limits get softened.

---

## 1. Which tracker hosts what

Three trackers exist in this reality and conflating them is what makes a sweep unpassable.

| Tracker | Hosts | Swept? |
|---|---|---|
| **Design tracker** — `arkaphat/arkaphat-builder` | the effort's design and wave tickets | **never** — out of the sweep baseline *by definition*, not by exemption |
| **Chain tracker** — the tracker of the repo whose `origin` keys the exam dir | that feature's vetted spec ticket, its sliced tickets, its exam pointer | **yes**, feature-scoped, with one issue exempted by number |
| **Upstream** — the repo this skill was forked from | nothing in this chain | never written to, never swept |

**Why the boundary is drawn here rather than exempting things:** the design tracker permanently
contains structural mentions of the exams directory — that is what design tickets are for. A sweep
with several permanent hits cannot be rescued by a one-number exemption; it becomes a check that
structurally cannot pass, and a check that cannot pass gets softened or ignored. Bounding the sweep to
the chain tracker removes every one of those hits without weakening anything, because the design
tracker holds no exam and no feature.

The transport rule that follows from this is mechanical and lives in `exam_paths.transport()`:

```bash
host=<the origin key's first segment>
if [ "$host" = "github.com" ]; then
  gh auth status >/dev/null 2>&1 || HARD STOP        # never a silent downgrade
  gh repo view <owner>/<repo> --json hasIssuesEnabled --jq .hasIssuesEnabled
fi
# issues disabled, or host is not github.com -> local-file transport
```

---

## 2. The four sweeps

**The token is `kestra/exams`** — the invariant substring of both `~/.kestra/exams/…` and
`$HOME/.kestra/exams/…`. It contains a slash, so this skill's own name never self-hits:
`printf 'kestra-exam skill' | grep -c 'kestra/exams'` prints `0`. Mentions of the skill in READMEs, in
`install.sh` and in commit messages are therefore structurally safe.

**Exit semantics, unchanged from `arkaphat/arkaphat-builder#27` (c): exit 1 is the only clean
outcome.** `0` means a hit, i.e. a leak. `≥2` means the check itself failed (e.g. `128` outside a repo)
— a gate failure, never "clean".

```sh
# S1 — worktree. TWO commands, both must be clean (see §3 — `--untracked`
# implies --exclude-standard and skips tracked-but-excluded paths):
git grep -q --untracked 'kestra/exams' -- . ':(exclude).claude/skills/kestra-exam/*' ':(exclude)workflow/kestra-exam/*' ; [ $? -eq 1 ]
git grep -q             'kestra/exams' -- . ':(exclude).claude/skills/kestra-exam/*' ':(exclude)workflow/kestra-exam/*' ; [ $? -eq 1 ]

# S2 — commit messages (git grep cannot see them). NO exemption, by decision.
test -z "$(git log --all --grep='kestra/exams' --oneline)"

# S3 — history blobs, guarded. MUST run under `sh -c`.
sh -c 'revs=$(git rev-list --all)
       [ -n "$revs" ] || { echo "FAIL: no commits — the blob sweep did not run"; exit 9; }
       git grep -q "kestra/exams" $revs -- . ":(exclude).claude/skills/kestra-exam/*" ":(exclude)workflow/kestra-exam/*"; [ $? -eq 1 ]'

# S4 — chain tracker only, pointer issue exempted by number
gh issue list --repo <chain-repo> --state all --limit 200 --search 'kestra/exams' \
  --json number --jq "[.[]|select(.number != <pointer-number>)]|length"   # must be 0
gh search issues --repo <chain-repo> 'kestra/exams' --json number \
  --jq "[.[]|select(.number != <pointer-number>)]|length"                # comments, as far as search reaches
```

**S3 must be wrapped in `sh -c`, and this is not stylistic.** The guarded form relies on unquoted
`$revs` word-splitting, which **zsh does not do**: run directly in a zsh session the command returns
`128` with `fatal: unable to resolve revision` and all revisions concatenated into one argument.
Fail-closed saves the gate from reporting a false clean, but the check never actually runs. `sh -c`
makes it shell-dialect-independent. The empirical claim behind S3 reproduces (a leak committed at stage
N and removed at N+2 gives `S1=1`, `S2` empty, `S3=0`); the *recipe* does not, under zsh.

---

## 3. The exemption boundary — exactly two classes

**(a) Repo sweeps (S1, S3) exempt exactly the skill's own definition site, by path.** Two paths,
fixed:

* `.claude/skills/kestra-exam/*` — `install.sh --project` legitimately copies `SKILL.md` into a target
  worktree, and `SKILL.md` documents the path.
* `workflow/kestra-exam/*` — this skill's own source repo is itself a candidate host for a feature run.

**Nothing else.** Not docs, not READMEs, not the run folder, not a stage brief, not `state.json`.
Withholding the literal path from this prose would buy nothing (the path is public, and an agent that
cannot see it cannot check it); the *exemption*, not coyness, is what makes the sweeps passable.

**(b) S4 exempts exactly one issue, by number** — the single-match pointer ticket, resolved first (§4)
and then excluded. **A label-based exemption is a hole**: labels are appliable by whoever can open an
issue, so an attacker exempts their own leak by labelling it.

**S2 takes no exemption at all, by decision.** No commit message may ever contain the token, including
the commit that lands this skill. It is trivially satisfiable — write "the user-level exams directory"
— and it keeps the one sweep whose scope cannot be path-limited hole-free.

**Residuals** — carried unchanged from `arkaphat/arkaphat-builder#27` (c), which is their single owner,
and restated here only so nobody rediscovers them as findings: an alias or `~`-expansion variant evades
all four sweeps; a leak pasted into a tracker ticket or comment after build time is reached only as far
as the tracker's own search reaches. And the framing above all of them: **detection, never prevention.**

**One residual is sharper than #27 (c) states it — corrected here rather than paraphrased, because it
was measured** (eval `workflow/evals/2026-08-02-wave3-kestra-exam`, finding F1). The residual as written
says `--untracked` skips *gitignored* files. Measured, it skips more than that: `--untracked` implies
`--exclude-standard`, and that walk skips every excluded path **including paths that are tracked**. So a
token committed inside a directory covered by `.gitignore` or `.git/info/exclude` makes **S1 report a
false clean over a committed leak**, while S3 — which walks history blobs, not the worktree — hits.
`git check-ignore` *without* `--no-index` does not reveal the condition either: it assumes tracked ⇒ not
ignored. **S1 is therefore two commands, not one, and both must be clean:**

```sh
git grep -q --untracked 'kestra/exams' -- . ':(exclude).claude/skills/kestra-exam/*' ':(exclude)workflow/kestra-exam/*' ; [ $? -eq 1 ]
git grep -q             'kestra/exams' -- . ':(exclude).claude/skills/kestra-exam/*' ':(exclude)workflow/kestra-exam/*' ; [ $? -eq 1 ]
```

`--untracked --no-exclude-standard` reaches the same files, but drags `node_modules` and every other
ignored tree in with them; the tracked-only second pass costs nothing and has no such noise.

**Recorded disposition for this skill's own host repo, as of 2026-08-02:** two tracked diagram exports,
`idea/flow-final.excalidraw` and `idea/flow-final.svg`, carry the token, sit outside both exempt paths,
and are covered by an `idea/` line in that repo's `.git/info/exclude` — so the tracked-only pass above
hits and S3 hits, today. **That is an accepted and recorded fail, not a third exemption.** The two files
must be re-exported with the path elided (the diagram says the same thing with
`<exams-root>/<key>/<slug>/`) before the first gate run on this repo; until they are, a gate run here
reports the hit rather than treating it as known noise. Growing §3(a) to cover a diagram path would move
the boundary from *the skill's own definition site* to *wherever a leak happens to live*, which is the
softening §1 exists to refuse.

---

## 4. Pointer discipline

One pointer record per exam, edited in place. **`>1` match is never resolved by recency.**

### GitHub transport

One issue, label `kestra-exam`, title **exactly** `kestra-exam: <feature-slug>`. Discovery is
read-only. Paginate the repository's authoritative issue collection, then apply exact title equality
and the required-label check locally. Do not pre-filter by label: that could hide an unlabeled
duplicate.

```bash
POINTER_PAGES=$(gh api --paginate --slurp \
  'repos/<chain-repo>/issues?state=all&per_page=100') || \
  { echo 'FAIL: pointer-ticket search did not run' >&2; exit 1; }
printf '%s\n' "$POINTER_PAGES" | jq '[.[][]
    | select(.pull_request == null)
    | select(.title=="kestra-exam: <slug>")
    | {number,title,url:.html_url,labels:[.labels[].name]}]'
```

Apply the `0`/`1`/`>1` rule to the resulting array; the one-match case additionally requires `labels`
to contain `kestra-exam`, or the pointer is malformed and must be labelled by hand before continuing.

* **`0` at creation** → create it.
* **`0` at a gate or regeneration** → hard fail: *"no pointer ticket titled 'kestra-exam: `<slug>`' on
  `<chain-repo>` — the exam has no durable record; re-run kestra-exam creation, do not trust an
  unrecorded exam dir."*
* **`>1`** → hard fail, exact text:

```
FAIL: <n> tracker tickets titled 'kestra-exam: <slug>' (#<a>, #<b>) — ambiguous by
construction. A regeneration edits the existing pointer in place; a second ticket is
forgery or confusion, and picking the newer one crowns the forgery. Close or retitle
the wrong one by hand, then re-run. Never auto-select, never take the newest.
```

Same posture as the raise-commit convention's ">1 is never resolved by taking the newer" (see
[`../../kestra-spec/references/chain-provenance.md`](../../kestra-spec/references/chain-provenance.md)
§2).

### The body — a fixed parseable block, the whole body, nothing else

```
<!-- kestra-exam-pointer v1 -->
exam_dir: /Users/<user>/.kestra/exams/<origin-key>/<slug>/
exam_commit: <40hex>
exam_script_sha256: <64hex>
manifest_sha256: <64hex>
raise_commit: <40hex>
surface_hash: <64hex>
extractor_version: 1
recorded_at: <ISO-8601 Z>
generation: <n>
```

Per-line recognizer `^(\w+):\s*(\S+)$`; the first line must be the exact `v1` marker, or the pointer is
**malformed ⇒ hard fail** — never "assume defaults". `exam_anchor.py` enforces both.

### Regeneration edits in place

`gh issue edit <N> --body-file -` on the **same** issue, `generation` incremented, **plus one appended
comment per regeneration**:

```
regenerated C-3,C-7 (AC-4 changed, AC-9 added); deleted C-11 (AC-6 removed);
surface 9a1c… → 4de7…; raise 1f2a… → 8b90…; generation 1 → 2
```

The comment is not a log line for humans. It is the artifact the **GraphQL `userContentEdits` check**
described in `arkaphat/arkaphat-builder#27` (c) needs in order to tell a *legitimate* body edit from
tampering: a body edit with no matching comment is a gate failure. Because exactly one record exists and
every movement of it is accounted for, "latest wins" is a non-question rather than a tie-break rule.

### Local-file transport (tracker-free repos)

Same shape, no `gh` — following the `.vet`-file precedent in `chain-provenance.md` §3:

* Pointer file `~/.kestra/exams/<origin-key>/<slug>.pointer` — a **sibling of** the feature dir, never
  inside it, so the pointer is not one of the artifacts whose hashes it records.
* Identical body format, identical `v1` marker.
* Multiplicity is the same rule in file form, but the predicate is **narrower than a `pointer*` glob** —
  two counts, both mechanical, run in the pointer's directory `D=~/.kestra/exams/<origin-key>`:

  ```sh
  ls "$D" | grep -cx '<slug>\.pointer'                                    # must be exactly 1
  ls "$D" | grep '^<slug>\.pointer' | grep -vxE '<slug>\.pointer(\.log)?' \
          | wc -l                                                         # must be 0
  ```

  The first count is the record itself: `0` is the *no pointer record* hard fail above, and one exact
  filename cannot exceed 1. The second count is the forgery predicate: every other `<slug>.pointer…`
  name — `.pointer.bak`, `.pointer.2`, `.pointer.new`, `.pointer.orig` — is a match, and
  `<slug>.pointer.log` is the **only** exempt sibling, because the line below mandates it. `>0` ⇒ the
  same hard-fail text with paths in place of issue numbers, and the same never-pick-the-newer. (A slug
  matches `^[a-z0-9][a-z0-9-]{0,63}$`, so it carries no regex metacharacter and needs no quoting.)

  **Surfaced correction to D4, measured 2026-08-02** (eval
  `workflow/evals/2026-08-02-wave3-kestra-exam`, finding F3): D4 wrote this predicate as the bare glob
  `ls ~/.kestra/exams/<origin-key>/<slug>.pointer*`, which counts the mandated `.pointer.log` sibling.
  A *healthy* exam therefore reports `matches=2` from its first regeneration onward and hard-fails as a
  forgery — a check that structurally cannot pass, i.e. exactly what §1 says gets softened or ignored.
  The two counts above replace that glob; a runner still using the bare glob is wrong, not strict.
* Edited in place (rewrite the file); the comment equivalent is one appended line per regeneration in
  `<slug>.pointer.log`.

**Named residual, stated rather than papered over:** the local pointer buys durability and
evidence-against-accident, and **nothing** against an actor who has already found the exams directory.
There is no server-side edit history to anchor tamper-evidence against, so the `userContentEdits` check
has no local equivalent. This is the correct trade for a tracker-free repo — it is not an equivalent of
the GitHub transport, and `--local-pointer` on a `github.com` origin chooses the weaker of the two
deliberately.

---

## 5. Hash-vs-pointer comparison at the gate

Run the anchor in isolated/no-bytecode mode and every exam invocation with `-B`. The explicit ignored
path check is load-bearing: ordinary porcelain omits ignored files, but a local ignored Python module
can still shadow a committed helper. Any old generated `__pycache__` must be removed before the exam
commit; a gate never exempts it.

```bash
E=<exam-dir>
test "$(git -C "$E" rev-parse HEAD)" = "<pointer exam_commit>"
test -z "$(git -C "$E" status --porcelain --untracked-files=all | grep -vx ' M manifest.md')"
test -z "$(git -C "$E" ls-files --others --ignored --exclude-standard)"
sha256sum "$E/exam.py"                                     # vs the pointer's exam_script_sha256
awk '{ print } /^--- verdict \(appended by the gate runner/ { exit }' "$E/manifest.md" \
  | sha256sum                                              # vs the pointer's manifest_sha256 (see below)
gh issue view <N> --repo <R> --json body --jq .body > /tmp/pointer.txt   # GitHub transport
python3 -I -B "$E/exam_anchor.py" "$RUN" "$E" --pointer-body /tmp/pointer.txt
```

Every mismatch is a refusal, and the refusal is loud about which artifact moved:

| Mismatch | Reading |
|---|---|
| `exam_commit` ≠ exam repo `HEAD`, anything except an unstaged `manifest.md` verdict append is dirty, or an ignored untracked path exists | a committed helper/evidence artifact moved or an unpinned file can affect the gate |
| `exam_script_sha256` ≠ `sha256sum exam.py` | the exam was edited after it was recorded — the checks are not the ones that were red-proofed |
| `manifest_sha256` ≠ the manifest's pre-verdict region hash (defined below) | the evidence table was edited after recording |
| anchor triple disagrees across manifest / pointer / `exam.py` | a tamper that edited one copy, or an interrupted regeneration |
| `exam_anchor.py` exits 2 | `REFUSED` — no verdict line is written at all |

`--pointer-body` is required whenever no local `<slug>.pointer` exists: **skipping the pointer
comparison is not a pass.** On the local transport `exam_anchor.py` finds the file itself.

### `manifest_sha256` covers the manifest *above the verdict delimiter*, never the whole file

A gate run appends its verdict block to `manifest.md` (`manifest-schema.md` §7), which changes
`sha256sum manifest.md`. Compared naively against the pointer, the gate's **own** append then reads as
the table row above — *the evidence table was edited after recording* — so the first `PASS` would make
every later gate run refuse. Measured, not predicted: eval
`workflow/evals/2026-08-02-wave3-kestra-exam` finding F4 records the flip `495969728228…` →
`1bf43b3114f3…` across one verdict append.

`manifest_sha256` is therefore defined — for the value written into the pointer at creation and at every
regeneration, and for the value recomputed at every gate — over the manifest **from its first byte
through the first verdict delimiter line, inclusive**:

```bash
grep -c '^--- verdict (appended by the gate runner; unfilled above this line) ---$' \
     "$E/manifest.md"                       # 0 => malformed manifest, hard fail (the template's
                                            #      delimiter line is missing); >=1 is fine
awk '{ print } /^--- verdict \(appended by the gate runner/ { exit }' "$E/manifest.md" \
  | sha256sum                               # manifest_sha256, identical before and after any append
```

Everything the pointer certifies sits above that line — anchor, read rule, check rows, delta map,
coverage, and the verdict *rule* text; only appended verdict blocks sit below it. The region is stable
across gate runs and still sensitive to every edit that could launder evidence, which the whole-file hash
was not: it flipped on an honest append and so had to be either ignored or "fixed" by rewriting the
pointer after every gate. **Re-recording the pointer instead was rejected**: a pointer body edit with no
matching regeneration comment is itself a gate failure (§4), so a gate that rewrote the pointer would be
indistinguishable from tampering.

---

## 6. The gate's own stopping rule

A gate run is complete when: the four sweeps each reported their clean outcome (S1's two passes and S3
exit `1`, S2 empty, S4 length `0`); exactly one pointer resolved by exact title and its `v1` body parsed;
`exam_commit` matched `HEAD`, no unpinned worktree path was dirty, the two hashes and the anchor triple
all matched; `python3 -B exam.py --json` ran against the delivered tree; and the verdict block was
appended to `## Verdict contract` — **with the `evidence: degraded` clause whenever `U > 0`**, since a
`PASS` missing that clause is itself a gate failure.

**Which `U`, spelled out because the two candidates disagree:** `U` and `F` are read from the manifest's
own `## Coverage` line (`must-flip: F (unproven: U)`), whose `U` was filled from `red-proof.json`'s
`summary.unproven` at red-proof time — **never** from the `summary.unproven` of the gate's own
`exam.py --json` run. That per-run count means "must-flip checks that produced no behavioral red *in this
run*", so on a green delivery it equals the must-flip total: a runner reading it would stamp
`degraded — 3 unproven of 3 must-flip` on a perfect delivery (measured 1 vs 3, eval
`workflow/evals/2026-08-02-wave3-kestra-exam` finding F5).
