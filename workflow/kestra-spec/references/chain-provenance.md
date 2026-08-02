# Chain provenance — finding the raise, reading the marker, tracking without GitHub

Load this when something needs to resolve *which commit is the raise* (a re-raise after a bounce or
a re-vet, an anchor being recorded, a downstream skill asking for provenance), when a `Spec-ticket:`
line looks malformed, or when the ticket lives in a local file instead of on GitHub. Everything a
normal pass needs is already in `SKILL.md`.

---

## 1. The chain marker

One line, in the **preamble** (the text above the first `## ` heading), written by the raise and
nowhere else:

```
> Spec-ticket: https://github.com/<owner>/<repo>/issues/<N>
```

Recognizer: `^>\s*Spec-ticket:\s*(\S+)\s*$`, searched in the preamble only. A spec is **in-chain**
iff there is exactly one match whose value matches `https?://\S+`; otherwise standalone.

Why the URL and not, say, the recorded mode-prediction fact: the fact is an obligation *every*
Wave-2 spec carries, so as a marker it self-references — a chain spec that forgot the fact would
read as standalone (its own check could never FAIL), and a diligent hand-written spec that carried
it would get hard-gated for no reason. The URL exists exactly when the spec was materialized from a
vetted ticket, and it is the same string commit 1's message carries.

**The marker is out of the requirement surface**, verified empirically: injecting the line into a
grown-shape spec leaves `surface_hash` byte-identical, because `requirement_surface.py` only
collects lines *after* a matched `## ` heading. That is why the marker may live in the spec at all —
adding provenance must not read as a moved requirement.

Degenerate cases, following `validate_workflow.py`'s partial-anchor precedent:

| What the file has | Verdict |
|---|---|
| no `Spec-ticket:` line in the preamble | standalone — the five template checks WARN |
| one line, value is a URL | in-chain — the five template checks FAIL on a defect |
| one line, value missing or a `<placeholder>` | **FAIL** — a partial marker is never treated as absent |
| two or more lines | **FAIL** — ambiguous by construction |
| a `Spec-ticket:` line below the first `## ` | **FAIL** — it could land inside a requirement-surface section and move `surface_hash` |

A hand-written spec stays unmarked by construction: standalone mode is forbidden from writing the
line, and the template marks it chain-only.

---

## 2. Finding the raise commit

The convention is **exactly one match**, mirroring `enforcement.md`'s rollback grep and tightened so
there is nothing to pick between. Current branch only — `--all` finds sibling-branch raises and
produces a spurious `>1`:

```bash
git log -E --all-match \
  --grep='^spec\(<feature-id>\): raise vetted ticket into 0-spec\.md$' \
  --grep='^Spec-ticket: <ticket-url>$' \
  --format='%H' > /tmp/raise-matches
test "$(wc -l < /tmp/raise-matches)" -eq 1
```

`git log -E --grep='^…'` anchors per message line, so the subject pattern and the trailer pattern
each match their own line, and `--all-match` requires both.

* **0 matches** → hard fail: *"no raise commit for `<feature-id>` @ `<url>` on this branch — the spec
  was never materialized by kestra-spec here (or history was rewritten). Re-run kestra-spec on the
  vetted ticket; do not anchor to a hand-picked SHA."*
* **>1 match** → hard fail: *"`<n>` raise commits match `<feature-id>` @ `<url>` (`<sha…>`) —
  ambiguous by construction. A re-raise replaces its predecessor (`git reset --hard <raise>^^`, then
  re-run), never stacks. Resolve by naming the intended SHA explicitly; never pick the newest."*

**Never take the newer one** — the same posture the pointer-ticket convention uses. A re-raise after
a bounce or a re-vet therefore resets to before commit 1 (destructive: confirm with the user, same
as any hard reset) so exactly-one holds by construction rather than by tie-breaking.

The predicate targets **commit 2** — the commit whose `0-spec.md` a `surface_hash` is computed over —
so an anchor SHA and the extractor's input are the same object.

Commit 1 is then always `<raise>^`, because nothing is committed between the two. That is what lets
the verbatim check name its source without a second search:

```bash
git show "$(git rev-parse <raise-sha>^)":<spec-path> | diff -u - /tmp/kestra-spec-ticket-body.md
```

Offline fallback when the tracker is unreachable: commit 1's message carries
`Ticket-body-sha256: <hex>`, so `git show <c1>:<spec-path> | sha256sum` proves the verbatim content
without the network.

---

## 3. Tracker that is a local file

Same two facts, same order, no `gh`:

* **Ticket** — `<NN>-<slug>.md` (the ticket body *is* the file).
* **Vet** — a sibling `<NN>-<slug>.vet` whose first line is the same marker over the ticket file's
  hash: `VETTED-FOR-KESTRA: $(sha256sum <NN>-<slug>.md | cut -d' ' -f1)`. Newest file wins if more
  than one exists; the hash must equal the live file's hash.
* **No `> Spec-ticket:` preamble line.** The marker's value must be a URL, and a present-but-not-a-URL
  value is a malformed marker (FAIL), not an absent one — so a file-tracked spec carries no marker,
  `validate_spec.py` reads it as standalone, and the five template checks WARN. The vet still gates
  the pass, and the commit trailers still record the provenance: put the repo-relative ticket path
  in `Spec-ticket:` in **both commit messages**, which is what the discovery predicate in §2 matches
  on. Say plainly at handoff that the marker is absent because the tracker is a file.
* **Materialization** — `tr -d '\r' < <NN>-<slug>.md > "$RUN"/0-spec.md`, so the one declared
  normalization stays identical to the GitHub path.

kestra-spec stays read-only here too: it never writes the `.vet` file, and never edits the ticket.
