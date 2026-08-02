# Folding a sliced ticket set — the long-run fold

Load this when the invocation names a **sliced ticket set** alongside the spec (the long-run path:
one `0-spec.md`, N tickets, one `workflow.yaml`), when a ticket body changed and something has to
decide re-fold vs. escalate, or when a `body_sha256` / `ac_hash` / `Verified-against` value needs
recomputing. A **monolithic** fold — run folder with `0-spec.md` and no ticket set — needs none of
this: `SKILL.md`'s own Process is complete for it, and nothing here fires.

`SKILL.md`'s "Folding a sliced ticket set" section is the procedure and the order; this file is the
exact commands, regexes, hashes and refusal texts it points at. The field grammars the fold writes
into `workflow.yaml` live in [`workflow-schema.md`](workflow-schema.md) (`spec_anchor`, `tickets`,
embedded ticket blocks, `exit_criteria.progress`) — stated there once, not restated here.

---

## 1. The input contract — the set is named, never searched

Three invocation forms, decided mechanically before anything else, the same posture as
`kestra-spec`'s in-chain/standalone split:

| Form | What the invocation names | Behavior |
|---|---|---|
| **A — sliced fold** | a run folder with `0-spec.md` **plus** the slice set — either (a) GitHub refs (`#N` / full URLs) with the repo, or (b) a directory of local-file tickets (`.scratch/<feature-slug>/issues/<NN>-<slug>.md`) | this file's whole procedure |
| **B — monolithic fold** | a run folder with `0-spec.md` only | unchanged from before the fold existed: no `tickets:` block, and `spec_anchor` written only if the spec carries a `> Spec-ticket:` preamble marker |
| **C — chain-marked spec, no set named** | a run folder whose `0-spec.md` carries `> Spec-ticket: <url>` but the invocation names no slices | ask **once**: "this spec is chain-marked `<url>` — name the sliced ticket set, or fold monolithically?" |

**Never search the tracker for tickets nobody named.** This is verbatim the rule `kestra-spec`'s
Input section already holds, and for the same reason: a set that was guessed at rather than named is
how scope no human vetted enters a frozen workflow. No named set *is* the monolithic signal.

### Materialization — byte provenance starts here

Every slice is copied into `<run>/tickets/<id>.md` and committed with the workflow, using the
chain's *one* declared normalization and nothing more:

```bash
RUN=<run-folder>; mkdir -p "$RUN"/tickets
gh issue view <N> --repo <R> --json body --jq .body | tr -d '\r' > "$RUN"/tickets/issue-<N>.md
tr -d '\r' < <dir>/<NN>-<slug>.md               > "$RUN"/tickets/<NN>-<slug>.md
```

`tr -d '\r'` only — identical to `kestra-spec` step 0b, so "verbatim" means the same thing at both
ends of the chain. **This is the only point in the whole run where the tracker is read**: everything
downstream reads `tickets/*.md`, so `kestra-run` never needs network, auth, or `gh` at all.

`id` is the tracker's own identifier, normalized: GitHub ⇒ `issue-<N>`; local file ⇒ the basename
without extension (`04-cancel-endpoint` — the numbers are the slicing tool's dependency order, and
are not renumbered here). Never derive `id` from the title: a retitled ticket must not orphan its
file on the next fold. `tickets/<id>.md`, the `tickets:` entry's `id:`, and the brief delimiter's id
are the same string, always.

### What a slice carries

`## What to build` · `## Acceptance criteria` (checkbox list) · `## Blocked by` · optional
`## Parent`. **`## Blocked by` is the only input to `depends_on` ordering** — filename order is not,
because a slicing tool numbering files in dependency order is a convention, while `Blocked by` is a
statement. `to-tickets` is the suggested tool for producing these, *if installed*; nothing here
requires it, and the fold never edits a ticket to make it conform.

`gh` is needed only for form A(a). Form A(b) and form B work offline.

---

## 2. Source labels on sliced ACs — presence, resolved from the map, one owner

A slice's AC lines carry no `Source` labels (the slicing tool emits none, and is not edited to add
them). Enforcement is therefore kestra-side, and it resolves each sliced AC against the spec's own
`## AC Coverage Map` rather than grading a second vocabulary:

1. **Normalize** each ticket AC line exactly as `requirement_surface._units` does — strip the list
   marker (`_BULLET`), strip the checkbox (`_CHECKBOX`), collapse whitespace (`_ws`) — then
   additionally strip a trailing explicit label with the narrow regex
   `\s*\(Source:\s*[^()]*\)\s*$`. Nothing wider: a wider strip eats legitimate parentheses out of a
   requirement.
2. **Look up** the normalized text among `extract_surface(spec).ac_rows` ids — the `AC` cell,
   normalized by the same code, in the same module. One normalizer, one boundary.
3. **Match ⇒ the AC's Source *is* the map row's `Source` cell.** An empty cell stops the fold:
   ```
   FAIL: sliced AC "<text>" resolves to an AC Coverage Map row with an empty Source cell — a green
   column that lies (validate_spec.py flags the same fact on the spec side).
   ```
4. **Ticket line carries its own `(Source: X)` and the matched row says `Y`** ⇒ stop, printing both.
   The map is the single owner of the mapping; a ticket may echo it, never contradict it.
5. **No match** ⇒ the AC-row mismatch refusal in §3 F2.

Resolving rather than re-grading is what keeps the Source column a single fact. A second labelling
vocabulary on the ticket side would be a copy that can drift, and the drift would be invisible: both
copies would look populated.

---

## 3. Fold-start verification — F0…F5

A fixed, numbered sequence at the top of every fold, first fold and re-fold alike. Run it in order;
each step's output is what the next one is allowed to assume.

### F0 — resolve the raise commit

Use [`../../kestra-spec/references/chain-provenance.md`](../../kestra-spec/references/chain-provenance.md)
§2's exactly-one predicate: current branch only, both `--grep` anchors, `--all-match`. 0 or >1
matches ⇒ that file's hard-fail messages verbatim. Never pick the newest, never anchor to a
hand-picked SHA — an anchor whose commit was chosen by a tie-break proves nothing about what was
raised.

### F1 — surface freshness: recompute vs. recompute, never hash-vs-hash across versions

```bash
python3 "$RUN"/requirement_surface.py "$RUN"/0-spec.md --hash                    # working tree
git show <raise>:<spec-path> > /tmp/kestra-fold-raise-spec.md
python3 "$RUN"/requirement_surface.py /tmp/kestra-fold-raise-spec.md --hash      # as raised
```

* **Equal** ⇒ proceed.
* **Different** ⇒ **stop**. Print both hashes and the extract diff, then name the two honest paths:
  re-raise (`kestra-spec`), or — if the human judges the slice boundaries still intact — re-anchor to
  the current raise. **"Slice boundaries intact vs. redrawn" is never automated:** the hash says the
  surface moved, the extract diff says which rows, the human says whether the slicing survives.
  Boundaries redrawn ⇒ re-slice (a printed prompt naming `to-tickets` as the suggested tool if
  installed — not code this skill runs).
* **On a re-fold**, compare the recorded `spec_anchor.extractor_version` to the run copy's
  `EXTRACTOR_VERSION` *first*. Different ⇒ the two hashes are **not comparable** ⇒ recompute and
  re-anchor; never diff hashes across extractor versions, since a bump changes what the hash means
  and a difference would carry no information about the spec.

Recomputing both sides with the *same* script is the point. Comparing a stored hash against a fresh
one only tests the spec when the extractor is identical, and that is exactly the assumption a
recorded number cannot make.

### F2 — per-ticket normalized AC rows

For each `tickets/<id>.md`, normalize its `## Acceptance criteria` lines (§2 steps 1–4) and match
them against `extract_surface(spec).ac_rows` ids.

* **Unmatched ticket AC ⇒ the fold refuses**, and no `workflow.yaml` is handed over:
  ```
  FAIL: ticket issue-47 AC 2 "<normalized text>" matches no row in the spec's AC Coverage Map —
  the slice set and the raised spec disagree. Either the spec moved after slicing (re-run to-tickets
  over the current spec — a suggestion, if installed), or the AC was edited on the tracker.
  kestra-build does not reconcile this; it stops.
  ```
* **Map row covered by no ticket ⇒ WARN**, listed by id, and it must appear in the audit line shown
  to the user. Not a stop: whether an uncovered row belongs to a later slice is exactly the human
  judgment F1 already refuses to automate.
* **Map row claimed by two tickets ⇒ WARN**: legitimate under an expand–contract batch set, still
  worth naming.

### F3 — `ac_hash`, defined once, in the extractor's own terms

```python
rows = [row for ac_id, row in surface.ac_rows if ac_id in this_ticket_ids]  # spec's Coverage Map order
ac_hash = hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()
```

Serialized in the **spec's Coverage Map order**, not the ticket's own bullet order, and over the
extractor's already-normalized `"<AC cell> | <Source cell>"` row form. Two consequences worth
stating because they are what make the hash useful: reordering ACs inside a ticket is presentation
and moves nothing, and the union of a partitioning slice set's row sets reproduces the map exactly.
No second normalization is invented anywhere — one boundary, one hash, one place.

### F4 — refresh: always runs, always shown, even on a clean fold

Write `body_sha256`, `ac_hash`, `verified_against` (= F0's resolved raise SHA) and `verified_at`
(ISO-8601 UTC, `YYYY-MM-DDTHH:MM:SSZ`) for every slice, then print the table:

```
ticket        body_sha256  ac_hash               verified_against  status
issue-47      9f2c1a…      7ab13f…               4f1c0b9e…         unchanged
issue-48      3d0e7b…      c1f902… (was 88ab41…) 4f1c0b9e…         refreshed: 1 AC row changed
issue-49      55c2de…      a7739e…               4f1c0b9e…         new
```

`unchanged` rows are printed, not suppressed. A refresh nobody can see is indistinguishable from a
refresh that did not run, and the whole value of a last-checked marker is that someone can tell the
difference.

### F5 — emit the run's frozen tooling

Byte-identical copies, committed with the workflow:

```bash
cp <skill-scripts-dir>/requirement_surface.py <skill-scripts-dir>/validate_spec.py \
   <skill-scripts-dir>/validate_workflow.py "$RUN"/
```

`kestra-spec` already emits the first two at raise time; kestra-build overwrites them — idempotent,
and a genuine skill-version difference then surfaces as a git diff instead of hiding. **The third
one is not optional:** `validate_workflow.py` imports `requirement_surface` as a *same-directory
sibling with no path setup*, so run from the skill directory it would bind the **skill's** extractor
and quietly defeat the per-run freeze. Emitting it means the checker, the extractor and the artifact
it grades are all the same vintage. `SKILL.md` step 7's dry-run therefore runs
`python3 <run-folder>/validate_workflow.py <run-folder>`.

---

## 4. Re-fold — the only path a ticket change takes

**Any ticket-body change ⇒ re-fold.** There is no hand-edit path, and that is enforced rather than
requested.

### Why no hand-edit path exists

A brief is a *derived* artifact. Only a re-fold re-runs the three things that make the file safe:
the freeze / `write_scope` non-overlap validation (`SKILL.md` step 7), the anchor recompute (F1), and
the per-ticket `ac_hash` refresh (F3–F4). Hand-patching a brief keeps the words current while
leaving the freeze un-revalidated and the anchor stale — the same reasoning
`workflow-schema.md`'s `mode:` field already states about itself ("changing the value by hand does
nothing; regenerate from the spec"), applied to a field that actually gates execution. Say this in
the brief's own footer as well as here, so the instruction travels with the artifact into every
spawn.

### Change detection — two recorded hashes, one truth on disk

Truth is `tickets/<id>.md`, committed with the workflow. It is recorded twice: in `tickets:` as
`body_sha256`, and inline in the brief's `ticket:begin` delimiter. Detection fires at three points:

| Point | What it compares | On difference |
|---|---|---|
| Fold start | re-materialize each slice with §1's pipeline vs. the recorded `body_sha256` | the ticket moved upstream ⇒ re-fold, which is what is already running (the fold is idempotent when nothing moved) |
| `validate_workflow.py`, every run | `sha256(tickets/<id>.md)` vs. the delimiter hex vs. `tickets[].body_sha256`, plus a whitespace-normalized text compare of the raw embedded block against the file | FAIL, naming which of the three disagrees |
| `kestra-run` pre-spawn | the same fields, before pasting a brief into a spawn | its own concern; the fold's obligation is only that the fields exist and are exact |

Two recorded copies plus one file is what closes all four hand-edit routes, which is why the
apparent redundancy is load-bearing:

1. edit the brief only ⇒ embedded block ≠ file;
2. edit the file only ⇒ `sha256(file)` ≠ the delimiter hex;
3. edit both consistently ⇒ both ≠ `tickets[].body_sha256`;
4. edit all three ⇒ `ac_hash` / `verified_against` no longer match the recomputed surface.

### Invocation

A re-fold is a plain re-run of kestra-build over the same run folder — no flag, no CLI. It
overwrites `workflow.yaml`, `tickets/*.md`, the emitted scripts, and `state.json`.

### The one hard guard — a re-fold mid-run is a `reworking`-class event

`state.json` holds live run state, so overwriting it after stages have passed destroys the resume
checkpoints and orphans the commits that were the rollback points. So kestra-build **refuses** to
re-fold when any stage in the existing `state.json` is not `pending`:

```
FAIL: refusing to re-fold — stages [implement-cancel, verify-cancel] are past 'pending'. A ticket
changed mid-run; the honest paths are (a) let kestra-run escalate to reworking (the design's one
guaranteed human stop, which resets counters and unlocks the freeze), or (b) git reset --hard to the
pre-run commit and re-fold from there (destructive — confirm first). kestra-build does not
reconcile a live run with a moved ticket.
```

Deliberately the same posture as `fixing → reworking`: escalate upward, never patch sideways.

---

## 5. The tracker-side carrier — printed, never posted

kestra-build produces artifacts and stops. It already refuses to commit, so mutating an external
tracker is strictly outside its contract, and its sibling `kestra-spec` is declared read-only on the
tracker for the same reason. So the tracker-side anchor is a **paste-ready line in the fold's closing
report**, one per slice:

```
Verified-against: 4f1c0b9e… · ac_hash: 7ab13f… · extractor: v1 · fold: 2026-08-02T09:14:03Z
```

First-line-matchable, same family as `VETTED-FOR-KESTRA:`; latest comment wins; the ticket body is
never edited. Named residual, not hidden: a human who never pastes it leaves that ticket anchorless
on the tracker side — detectable only at the next fold, which re-prints the line.

---

## 6. Where the refusal actually bites

* **On a re-fold** the prior artifacts exist, so F0–F4 run before anything is overwritten — a
  genuine pre-write refusal.
* **On a first fold** there is no `workflow.yaml` yet, so the mechanical half of F1–F3 lands at
  `SKILL.md` step 7's dry-run: after the artifacts are written, but **before** they are shown,
  committed, or handed off. Step 7's standing rule ("don't show a workflow this check already knows
  is broken") carries it.

Accepted cost, stated rather than hidden: a first fold over a mismatched set can waste one derivation
pass. Rejected alternative: a new script or a CLI flag whose only job is moving the check earlier —
new machinery, permanently, against one wasted pass on a set that was already wrong.
