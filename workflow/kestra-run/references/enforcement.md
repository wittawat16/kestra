# Enforcement — exact commands, not just the idea of them

Every check here must be a real command you actually run, with the real output pasted before you
act on it. This file exists so you don't improvise slightly-wrong versions of these from memory —
the whole design depends on these being precise.

## write_scope check

After a subagent finishes a stage's work, compare what it actually touched against the stage's
`write_scope` globs:

```bash
# Everything changed since the last commit
git diff --name-only HEAD

# Compare each path against the stage's write_scope patterns (bash glob match).
# Example for write_scope: ["src/routes/**", "src/services/csv-export/**"]
while IFS= read -r f; do
  case "$f" in
    src/routes/*|src/services/csv-export/*) ;;   # allowed — one case arm per write_scope glob
    *) echo "VIOLATION: $f outside write_scope" ;;
  esac
done < <(git diff --name-only HEAD)
```

If anything printed as a violation, check whether it's a modified *tracked* file or a brand-new
*untracked* one — `git status --porcelain`'s first column tells you (` M`/`M ` = tracked change,
`??` = untracked). These need different revert commands; using the wrong one silently no-ops:

```bash
# Tracked file that was modified — this reverts cleanly:
git checkout -- <violating-path>

# Untracked (newly created) file — git checkout errors on these ("did not match any file(s)
# known to git", exit 1) and leaves the file in place. Confirmed by direct testing: this is the
# more common violation shape (a stage creating a stray new file outside its scope), so don't
# rely on `git checkout --` alone. Use:
rm -f <violating-path>
```

Then treat this attempt as failed (go to the `fixing` accounting in SKILL.md step 6) — don't
silently keep the out-of-scope change. Always check the exit code of the revert command itself;
a failed revert must not be treated as "handled."

`write_scope: []` (approval gates, verify-only stages) means **zero** tolerance — any diff at all
is a violation.

**Exception: a `fixing` retry with `on_fail.target` set.** A `review`/verify stage with
`write_scope: []` can still declare `on_fail: {action: fixing, target: implement-x}` — the fix
attempt is legitimately allowed to touch `implement-x`'s `write_scope`, not the review stage's own
empty one. When checking a fixing attempt spawned this way, diff against `target`'s `write_scope`
globs instead of the failing stage's own. Everything else about the check is identical — same
tracked-vs-untracked revert distinction, same "treat as failed attempt" outcome on a violation.
Get this wrong (checking against the review stage's own `[]`) and every such fix attempt reads as
a 100% violation regardless of what the subagent actually did.

## Test-hash: computing and checking the freeze

The hashed paths are whatever `write_scope` the `freeze_after: true` stage used — don't invent a
separate list.

**One canonical formula, always — a single `find` over every root, one global sort.** `write_scope`
often lists more than one root (e.g. `["test/**", "package.json", "package-lock.json",
"jest.config.js"]`). Confirmed by direct testing: two different but each-internally-consistent ways
of handling multiple roots exist if you improvise — a single `find <all roots> | sort` over the
whole set, versus running `find` per root and concatenating the results in `write_scope`'s
declaration order without a global re-sort. Both produce a hash that matches itself on
re-verification, but they produce a **different** hash from each other for the identical file set —
so if a human, a different tool, or a resumed run ever recomputes the hash without knowing which of
the two methods the freezing run used, a perfectly-intact test suite reads as MISMATCH. Pick the
single-`find` form below and never the per-root-concatenation form:

```bash
# Build the root list from write_scope: a "dir/**" entry becomes "dir"; a literal filename entry
# is used as-is; entries that don't exist on disk are skipped (e.g. write_scope commonly lists both
# jest.config.js and jest.config.cjs to cover either convention, but only one will actually exist).
ROOTS=()
for p in "test/**" "package.json" "package-lock.json" "jest.config.js" "jest.config.cjs"; do
  p="${p%/\*\*}"
  [ -e "$p" ] && ROOTS+=("$p")
done
find "${ROOTS[@]}" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
```

(the `for` list above is illustrative — substitute the actual frozen stage's `write_scope` entries)

For the common single-root case this collapses to exactly the same one-liner as before:

```bash
find test -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
```

Store the resulting hash string as `state.json`'s `test_hash`.

**Check (before any stage runs, once `test_hash` is non-null):** recompute with the *identical*
`ROOTS`-building logic (same `write_scope` entries, same existence check, same single `find` call),
then compare:

```bash
CURRENT=$(find "${ROOTS[@]}" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')
[ "$CURRENT" = "$STORED_TEST_HASH" ] && echo "OK: hash matches" || echo "MISMATCH: halt"
```

A mismatch is a hard stop (SKILL.md step 1) — report it, don't try to reconcile it yourself. But
first rule out that the mismatch is an artifact of using a different root-combining method than
whichever run froze the hash, not an actual change to the frozen files — re-derive `ROOTS` from the
stage's own `write_scope` in `workflow.yaml` and use the single-`find` form above before concluding
the tests were actually touched.

## Semantic-diff hashing (for `seen_diffs` no-progress detection)

**Scope this to the stage's own `write_scope` paths — never bare `git diff HEAD`.** Confirmed by
direct testing: `fixing` attempts are *not* committed between retries (see Commit-per-stage
below — only a `passed` stage commits), so `state.json` itself sits uncommitted with a changing
`attempt` counter across every retry. A bare `git diff HEAD` includes that `state.json` churn, so
the hash comes out different on every attempt *even when the stage's actual code diff is
byte-for-byte identical* — silently defeating no-progress detection. Scope the diff to the
stage's `write_scope` globs (e.g. `src/**`) so only the stage's own output is hashed:

```bash
# Normalize before hashing so cosmetic re-runs of the same fix don't look "new".
# Replace `src/` with the stage's actual write_scope path(s) — exclude state.json and anything
# outside write_scope.
git diff HEAD -- src/ | grep -E '^[+-]' | grep -v '^[+-][+-][+-]' | sort | sha256sum | awk '{print $1}'
```

Compare this hash against the stage's `seen_diffs` list in `state.json`. Same hash reappearing =
no progress = escalate to `reworking` immediately, even if `attempt < max_attempts`.

## Commit-per-stage

Before the first commit in a repo that doesn't already have one, make sure build/test-runner
artifacts (`__pycache__/`, `*.pyc`, `.pytest_cache/`, `node_modules/`, etc.) are gitignored.
Confirmed by direct testing: a bare `git add -A` after running the exit-criteria test command
happily stages the test runner's own cache files alongside real output — noise that has nothing
to do with the stage's actual work.

Once a stage passes (mechanical checks above both clean):

```bash
git add -A
git commit -m "stage(<feature-id>): <stage-id> passed"
```

`state.json` must be part of that same commit — update it (status, test_hash if this was the
freeze stage, attempt/seen_diffs reset if this followed a `reworking`) and stage it alongside the
code changes before committing, not as a separate commit afterward. One commit per stage, always.

No `git tag` per stage — the commit itself is the rollback point (see Rollback below). Tags
accumulate quickly across a multi-stage run without adding anything a commit SHA doesn't already
give you.

## Rollback

```bash
git log --oneline --grep "stage(<feature-id>): <stage-id> passed"   # find the commit SHA
git reset --hard <sha>
```

This is destructive — confirm with the user before running it, same as any other hard reset.
