# The exam script contract — `exam.py`, the harness, and the machine output

Read this before writing the first check, and again when a red's *kind* is in question. `SKILL.md`
carries every rule; this file carries every field.

`exam.py` is per-feature and agent-authored. `exam_harness.py` is a **library**, byte-identical in
every exam dir — never a template to adapt. That split is what makes two exams comparable: the
checks are judgment, the runner is not.

---

## 1. The whole shape of an `exam.py`

```python
from exam_harness import (check, expect, expect_contains, expect_true, Cli,
                          repo_root, run_main)

EXAM = "order-cancellation-refund"          # the feature slug, required
ANCHOR = {"raise_commit": "1f2a9c04…",      # 40-hex
          "surface_hash": "9a1c4e77b210…",  # 64-hex
          "extractor_version": 1}
REPO = repo_root(default="/Users/me/src/kestra")
SEAM = Cli(argv_prefix=["python3", "src/tally.py"], cwd=REPO)


@check(id="C-0", ac="—", cls="must-hold", provenance="—")
def c0(seam):
    """harness smoke — the declared seam answers"""
    expect(seam.call([]).exit_code, 0, "smoke exit", "tally")


@check(id="C-3", ac="AC-4", cls="must-flip", provenance="inferred")
def c3(seam):
    """Refund rows subtract from the total."""
    r = seam.call(["--refund", "fixtures/mixed.csv"])
    expect(r.exit_code, 0, "exit", "tally --refund")
    expect_contains(r.stdout, "total: 40", "total line", "tally --refund")


@check(id="C-14", ac="AC-13", cls="unexaminable", provenance="ID§2",
       unexaminable="invariant fires only on disk-full; the CLI seam cannot "
                    "induce it")
def c14(seam):
    """the disk-full invariant"""


run_main(SEAM)
```

Nothing else belongs in the file — no helper functions that reach past the seam, no imports from the
repo under test, no reading of `src/`. `EXAM` and `ANCHOR` are required; without them the harness
exits 3 (`unanchored exam cannot certify anything`).

`repo_root(default=…)` is read at **import** time so a module-level `SEAM` sees `--repo <clone>`.
That is what lets one exam file be driven against a disposable clone for the red proof and against
the working tree at the gate, with no second file to drift.

---

## 2. `@check` — order of appearance is run order

| Argument | Values | Notes |
|---|---|---|
| `id` | `C-<n>` | `C-0` is reserved for the smoke check and is **required** |
| `ac` | the Coverage Map's `AC` cell, or `—` for C-0 | this *is* the AC→check map |
| `cls` | `must-flip` \| `must-hold` \| `unexaminable` | closed set; anything else exits 3 |
| `provenance` | the Coverage Map's `Source` cell verbatim | `inferred` marks a check whose requirement originated in a spec pass |
| `unexaminable` | one sentence, or absent | present **iff** `cls="unexaminable"` — enforced |

The check's first docstring line is its title, used by `--list` and the human table.

An `unexaminable` check has no body and is never invoked. It counts in neither pass nor fail, appears
in coverage, and stays `unexaminable` even when a red C-0 blocks everything else — it never depended
on the seam, so blocking it would be noise.

**`C-0` runs first, in every mode, including `--only`.** A delta red proof with no smoke is void by
exactly the same rule as a full one.

---

## 3. Assertions — `expect*` only, `assert` banned

`python3 -O` strips `assert`, so a check written with one would be **born green** — the exact
laundering an exam exists to prevent. The mechanical backstop is that `exam_harness` refuses to run
when `__debug__` is False (exit 3).

| Helper | Fails when | Signature it produces |
|---|---|---|
| `expect(actual, expected, label, where=None)` | `actual != expected` | `CheckFailure: exit 1 != 0 @ tally --refund` |
| `expect_true(condition, label, where=None)` | `condition` is falsy | `CheckFailure: total is positive not satisfied @ …` |
| `expect_contains(haystack, needle, label, where=None)` | `needle not in haystack` | `CheckFailure: total line missing 'total: 40' @ …` |

`label` names what was compared; `where` names the call it came from. The failure signature a manifest
row carries is `type(exc).__name__ + ": " + first line`, truncated to 120 characters, and it is copied
**verbatim** from `red-proof.json` — never retyped.

---

## 4. The three seam kinds are closed

kestra-exam deliberately does **not** NL-parse `## External Interface`. Read the section, encode one
seam object. A fourth kind is a hard stop: *name it and extend `exam_harness.py` deliberately.*

| Kind | Construction | `seam.call(…)` returns | `reached` becomes True when | Infrastructure red when |
|---|---|---|---|---|
| `Cli` | `Cli(argv_prefix, cwd, env=None, timeout=30)` | `CliResult(exit_code, stdout, stderr)` | the subprocess exited, any code | `FileNotFoundError` / `PermissionError` / `NotADirectoryError` on spawn, or the timeout elapsed |
| `Http` | `Http(base_url, boot=(), ready_path="/", timeout=10, cwd=None, env=None)` | `HttpResult(status, headers, body)` | a response was received, any status | connection refused, DNS failure, boot failure, ready timeout |
| `Module` | `Module(import_path, entry, sys_path=())` | `ModuleResult(value, exc)` | the entry function was entered | `ImportError`, `AttributeError`, a non-callable entry |

* `Cli.call(args)` takes a list appended to `argv_prefix`. `env` is merged **over** `os.environ`, so a
  seam declaring one variable need not restate `PATH`.
* A `Cli` timeout is an infrastructure red, not behavioral: the process never exited, so no result
  exists and a hung seam proves nothing about the requirement.
* `Http.call(path, method="GET", body=None, headers=None)` boots lazily on the first call and is torn
  down by the harness in a `finally`. An HTTP 4xx/5xx **is** a result — status codes are behavior.
* `Module.call(*args, **kwargs)` returns the entry's exception in `Result.exc` rather than raising, so
  a check can assert on it. `reached` is set immediately before invoking the entry, which is the
  closest observable approximation of "entered".

`seam.target()` is what `--audit-seam` compares and what `--json` reports: `" ".join(argv_prefix)`
for `Cli`, `base_url` for `Http`, `import_path.entry` for `Module`.

---

## 5. The red-kind discriminator — mechanical, not editorial

The harness sets `seam.reached = False` before each check and `True` the instant an invocation yields
a Result. Then:

```
behavioral      iff CheckFailure was raised AND seam.reached is True
infrastructure  SeamUnavailable, OR any non-CheckFailure exception,
                OR CheckFailure with seam.reached False
```

The third arm matters: an expectation written about a call that never happened is not evidence about
the feature. Treating it as behavioral would let a check that forgot to call the seam count as a red
proof.

**A note the design's own eval surfaced:** for a `Cli(["python3", "src/tally.py"])` seam, deleting
`src/tally.py` still spawns the interpreter, which exits 2 — so C-0's red reads **behavioral**, not
infrastructure. That is correct on both counts: the seam did answer, and the void rule keys on C-0's
*result*, never on its red kind. Do not "fix" this by inspecting the message.

---

## 6. Modes and the exit ladder

| Invocation | Does |
|---|---|
| `python3 exam.py` | human table, C-0 first |
| `python3 exam.py --json` | one JSON object — the machine contract |
| `python3 exam.py --only C-3 C-7` | that subset **plus C-0**; an undeclared id exits 3 |
| `python3 exam.py --list` | id / ac / class / provenance / title, and the seam target; **touches no seam** |
| `python3 exam.py --audit-seam` | the seam target must appear verbatim in `manifest.md`'s quoted EI block |
| `python3 exam.py --repo <path>` | drive a disposable clone instead of the default root |

Four exit codes, because "the harness is broken" and "the feature fails" are different answers and one
non-zero collapses them:

| Code | Meaning |
|---|---|
| `0` | every check passed |
| `1` | ≥1 behavioral fail — the seam answered, the answer was wrong |
| `2` | harness: C-0 red, **or** any infrastructure red |
| `3` | usage, `__debug__` off, or a malformed/unreadable exam |

`--audit-seam` uses `1` for a mismatch (the exam drives a seam the spec did not declare, or the quote
is stale) and `3` when there is no manifest or no fenced quote to compare against.

---

## 7. `--json`, the machine contract

Closed vocabularies: `result` ∈ `pass|fail|blocked|unexaminable`; `red_kind` ∈
`behavioral|infrastructure|null`.

```json
{"exam": "order-cancellation-refund",
 "anchor": {"raise_commit": "1f2a…", "surface_hash": "9a1c…", "extractor_version": 1},
 "seam": {"kind": "cli", "target": "python3 src/tally.py"},
 "started_at": "2026-08-02T14:02:55Z", "duration_s": 0.41, "harness_version": 1,
 "smoke": {"id": "C-0", "result": "pass"},
 "checks": [{"id": "C-3", "ac": "AC-4", "class": "must-flip", "provenance": "inferred",
             "result": "fail", "signature": "CheckFailure: exit 1 != 0 @ tally --refund",
             "red_kind": "behavioral", "seam_reached": true, "duration_s": 0.03}],
 "summary": {"pass": 4, "fail": 1, "blocked": 0, "unexaminable": 1, "unproven": 0,
             "exit_code": 1}}
```

* `smoke` is a convenience pointer at C-0; **C-0 also appears in `checks`**, so `summary` is derivable
  from the array alone.
* An `unexaminable` row carries an extra `"unexaminable": "<reason>"` field.
* `summary.unproven` counts `must-flip` checks that produced **no behavioral red** in *this* run —
  which is exactly the three `unproven` producers when the run is a red proof. At gate time the same
  arithmetic is expected to equal the must-flip total, which is precisely why a manifest's Red-proof
  cells are filled from `red-proof.json` and from nothing else.

---

## 8. Malformed-exam hard stops (all exit 3)

`class` outside the closed set · a check id that is not `C-<n>` · a duplicate id · `unexaminable`
without a reason or a reason without the class · no `C-0` · no checks at all · missing `EXAM` /
`ANCHOR` · a `SEAM` that is not one of the three kinds · an unknown argument · `__debug__` off.

Every one of these is reported as `FAIL: …` on stderr before any seam is touched, so a malformed exam
can never emit a green run.
