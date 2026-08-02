#!/usr/bin/env python3
"""The kestra-exam runner library — one owner of every runner mechanic.

Files: this module is `exam_harness.py`; its deterministic tests are
`test_exam_harness.py`, beside it in the skill's scripts/ directory (tests stay
in the skill, they are never emitted into an exam dir).

No third-party dependencies. `subprocess`, `urllib.request`, `importlib` and
nothing else — a fresh `python3` must be enough, forever, because an exam is
read years after it was written.

WHY THIS FILE EXISTS
    An exam has two halves with opposite properties. The checks are per-feature
    judgment and belong in a small, reviewable `exam.py`. The runner — run
    order, the reached/behavioral discriminator, the exit-code ladder, the JSON
    contract — must be *byte-identical across every exam*, because a gate that
    reads two exams has to compare like with like. So the runner is a library,
    not a template: `exam.py` is header + ANCHOR + SEAM + checks, and every
    mechanic lives here.

    A byte copy of this file is placed in each exam dir at creation and
    committed there (copy-per-run, the same argument `requirement_surface.py`
    makes in its own docstring): a gate reading this exam in six months must not
    get a different answer because a skill was reinstalled in between.

WHY NOT unittest
    `unittest` exposes no per-check id, class or provenance, and its
    failure/error split keys on the exception type rather than on whether the
    seam was reached — which is the exact discrimination an exam needs, since a
    red that never reached the seam proves nothing about the feature.

THE THREE SEAM KINDS ARE CLOSED
    `Cli`, `Http`, `Module`. kestra-exam deliberately does not parse a spec's
    `## External Interface` prose into a seam: that is a fragile parser sitting
    at the one place where a false-fail is permanent. The agent reads the
    section and encodes exactly one seam object. A fourth kind is a hard stop —
    name it and extend this file deliberately.

BARE `assert` IS BANNED IN AN exam.py
    `python3 -O` strips `assert`, so every check would be born green: the exact
    laundering an exam exists to prevent. Use `expect` / `expect_true` /
    `expect_contains`, which raise `CheckFailure`. The mechanical backstop is
    here: this harness refuses to run at all when `__debug__` is False.

Usage (from an exam dir):
    python3 exam.py                    # human table, C-0 first
    python3 exam.py --json             # the machine contract, one object
    python3 exam.py --only C-3 C-7     # delta subset; C-0 always runs too
    python3 exam.py --list             # declared checks; touches no seam
    python3 exam.py --audit-seam       # SEAM target vs manifest.md's quoted EI block
    python3 exam.py --repo <path>      # run against a disposable clone

Exit codes — four, because "the harness is broken" and "the feature fails" are
different answers and one non-zero collapses them:
    0  every check passed
    1  at least one behavioral fail (the seam answered, the answer was wrong)
    2  harness: C-0 red, or any infrastructure red (the seam was never reached)
    3  usage, `__debug__` off, or an unreadable/malformed exam
"""
import importlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

HARNESS_VERSION = 1

# Closed vocabularies. Anything outside them is a malformed exam, not a variant.
CHECK_CLASSES = ("must-flip", "must-hold", "unexaminable")
RESULTS = ("pass", "fail", "blocked", "unexaminable")
RED_KINDS = ("behavioral", "infrastructure")

CliResult = namedtuple("CliResult", "exit_code stdout stderr")
HttpResult = namedtuple("HttpResult", "status headers body")
ModuleResult = namedtuple("ModuleResult", "value exc")


class CheckFailure(Exception):
    """The seam answered and the answer was wrong — a behavioral red."""


class SeamUnavailable(Exception):
    """The seam could not be reached at all — an infrastructure red."""


class ExamMalformed(Exception):
    """The exam declares something this harness cannot run honestly (exit 3)."""


# --------------------------------------------------------------------------
# expect* — the only sanctioned way for a check to fail
# --------------------------------------------------------------------------

def _show(value):
    return repr(value) if isinstance(value, str) else str(value)


def _at(where):
    return f" @ {where}" if where else ""


def expect(actual, expected, label, where=None):
    """Fail unless actual == expected.

    `label` names what was compared, `where` the call it came from — together
    they are the failure signature a manifest row carries verbatim, e.g.
    `expect(r.exit_code, 0, "exit", "tally --refund")` →
    `CheckFailure: exit 1 != 0 @ tally --refund`."""
    if actual != expected:
        raise CheckFailure(
            f"{label} {_show(actual)} != {_show(expected)}{_at(where)}")


def expect_true(condition, label, where=None):
    """Fail unless condition is truthy — the general form, since `assert` is banned."""
    if not condition:
        raise CheckFailure(f"{label} not satisfied{_at(where)}")


def expect_contains(haystack, needle, label, where=None):
    """Fail unless `needle` occurs in `haystack`."""
    if needle not in haystack:
        raise CheckFailure(f"{label} missing {_show(needle)}{_at(where)}")


# --------------------------------------------------------------------------
# @check — declaration order is run order
# --------------------------------------------------------------------------

class Check:
    __slots__ = ("id", "ac", "cls", "provenance", "unexaminable", "fn", "title")

    def __init__(self, id, ac, cls, provenance, unexaminable, fn):
        self.id, self.ac, self.cls = id, ac, cls
        self.provenance, self.unexaminable, self.fn = provenance, unexaminable, fn
        doc = (fn.__doc__ or "").strip().splitlines()
        self.title = doc[0].strip() if doc else fn.__name__


REGISTRY = []
_DECL_ERRORS = []


def check(id, ac, cls, provenance, unexaminable=None):
    """Register a check. Order of appearance in exam.py is the run order.

    id          `C-<n>`; `C-0` is reserved for the harness smoke check.
    ac          the AC id from the spec's Coverage Map, or `-` for C-0.
    cls         must-flip (red at creation, green at the gate) | must-hold
                (green at both) | unexaminable (runs nothing).
    provenance  mirrors the Coverage Map `Source` cell; `inferred` marks a
                check derived from an `inferred` requirement line.
    unexaminable  one sentence naming *why the declared seam cannot induce the
                condition* — required for, and only for, cls="unexaminable".
    """
    def deco(fn):
        if cls not in CHECK_CLASSES:
            _DECL_ERRORS.append(f"{id}: class {cls!r} not in {CHECK_CLASSES}")
        if not (isinstance(id, str) and id.startswith("C-") and id[2:].isdigit()):
            _DECL_ERRORS.append(f"{id!r}: check id must match C-<n>")
        if (cls == "unexaminable") != bool(unexaminable):
            _DECL_ERRORS.append(
                f"{id}: cls='unexaminable' and a non-empty unexaminable= reason "
                "go together or not at all — an unexaminable AC is a row with a "
                "reason, never an omission")
        if any(c.id == id for c in REGISTRY):
            _DECL_ERRORS.append(f"{id}: duplicate check id")
        REGISTRY.append(Check(id, ac, cls, provenance, unexaminable, fn))
        return fn
    return deco


# --------------------------------------------------------------------------
# The three seam kinds
# --------------------------------------------------------------------------

class _Seam:
    kind = None

    def __init__(self):
        # Set False before every call, True the instant the underlying
        # invocation yields a Result. This flag *is* the red-kind
        # discriminator — mechanical, never editorial.
        self.reached = False

    def target(self):
        raise NotImplementedError

    def close(self):
        pass


class Cli(_Seam):
    """A command-line seam. reached ⇔ the subprocess exited (any exit code)."""
    kind = "cli"

    def __init__(self, argv_prefix, cwd, env=None, timeout=30):
        super().__init__()
        self.argv_prefix = [str(a) for a in argv_prefix]
        self.cwd = str(cwd)
        self.env = env          # merged over os.environ, so a seam declaring
        self.timeout = timeout  # one variable need not restate PATH

    def target(self):
        return " ".join(self.argv_prefix)

    def call(self, args=()):
        argv = self.argv_prefix + [str(a) for a in args]
        env = None if self.env is None else {**os.environ, **self.env}
        try:
            p = subprocess.run(argv, cwd=self.cwd, env=env, timeout=self.timeout,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True)
        except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
            raise SeamUnavailable(f"cannot spawn {self.target()}: {e}") from None
        except subprocess.TimeoutExpired:
            raise SeamUnavailable(
                f"{self.target()} did not exit within {self.timeout}s — the seam "
                "produced no result") from None
        self.reached = True
        return CliResult(p.returncode, p.stdout, p.stderr)


class Http(_Seam):
    """An HTTP seam. reached ⇔ a response was received (any status)."""
    kind = "http"

    def __init__(self, base_url, boot=(), ready_path="/", timeout=10,
                 cwd=None, env=None):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.boot = [str(a) for a in boot]
        self.ready_path = ready_path
        self.timeout = timeout
        self.cwd = None if cwd is None else str(cwd)
        self.env = env
        self._proc = None

    def target(self):
        return self.base_url

    def _request(self, path, method="GET", body=None, headers=None):
        req = urllib.request.Request(self.base_url + path, data=body,
                                     headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return HttpResult(r.status, dict(r.headers), r.read().decode(
                    "utf-8", "replace"))
        except urllib.error.HTTPError as e:  # a response *was* received
            return HttpResult(e.code, dict(e.headers or {}),
                              e.read().decode("utf-8", "replace"))

    def _ensure_up(self):
        if self.boot and self._proc is None:
            env = None if self.env is None else {**os.environ, **self.env}
            try:
                self._proc = subprocess.Popen(
                    self.boot, cwd=self.cwd, env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                raise SeamUnavailable(f"cannot boot {self.boot[0]}: {e}") from None
        deadline = time.time() + self.timeout
        last = "no attempt"
        while time.time() < deadline:
            try:
                self._request(self.ready_path)
                return
            except Exception as e:            # not up yet, or never will be
                last = f"{type(e).__name__}: {e}"
                time.sleep(0.1)
        raise SeamUnavailable(
            f"{self.base_url}{self.ready_path} not ready within {self.timeout}s "
            f"({last})")

    def call(self, path, method="GET", body=None, headers=None):
        self._ensure_up()
        try:
            r = self._request(path, method, body, headers)
        except Exception as e:
            raise SeamUnavailable(
                f"no response from {self.base_url}{path}: "
                f"{type(e).__name__}: {e}") from None
        self.reached = True
        return r

    def close(self):
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


class Module(_Seam):
    """An in-process seam. reached ⇔ the entry function was entered.

    Import and attribute resolution are infrastructure; anything the entry
    function itself raises is behavior, and comes back as Result.exc so a check
    can assert on it."""
    kind = "module"

    def __init__(self, import_path, entry, sys_path=()):
        super().__init__()
        self.import_path, self.entry = import_path, entry
        self.sys_path = [str(p) for p in sys_path]

    def target(self):
        return f"{self.import_path}.{self.entry}"

    def call(self, *args, **kwargs):
        for p in reversed(self.sys_path):
            if p not in sys.path:
                sys.path.insert(0, p)
        try:
            mod = importlib.import_module(self.import_path)
            fn = getattr(mod, self.entry)
        except (ImportError, AttributeError) as e:
            raise SeamUnavailable(
                f"cannot resolve {self.target()}: {type(e).__name__}: {e}"
            ) from None
        if not callable(fn):
            raise SeamUnavailable(f"{self.target()} is not callable")
        self.reached = True
        try:
            return ModuleResult(fn(*args, **kwargs), None)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            return ModuleResult(None, e)


SEAM_KINDS = (Cli, Http, Module)


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------

def repo_root(default=None):
    """The repo the seam is driven against — `--repo <path>` wins, else default.

    Read at import time so a module-level `SEAM = Cli(..., cwd=REPO)` sees the
    flag; that is what makes `--repo <disposable-clone>` work for a red proof
    without a second exam file."""
    argv = sys.argv[1:]
    if "--repo" in argv:
        i = argv.index("--repo")
        if i + 1 >= len(argv):
            print("FAIL: --repo needs a path", file=sys.stderr)
            sys.exit(3)
        path = Path(argv[i + 1])
    elif default is not None:
        path = Path(default)
    else:
        print("FAIL: no --repo given and repo_root() has no default",
              file=sys.stderr)
        sys.exit(3)
    if not path.is_dir():
        print(f"FAIL: repo root is not a directory: {path}", file=sys.stderr)
        sys.exit(3)
    return str(path.resolve())


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _signature(exc):
    line = str(exc).splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {line}"[:120]


def run_check(seam, chk):
    """Run one check and classify it. The only place a red kind is decided.

    behavioral      iff CheckFailure was raised AND the seam was reached.
    infrastructure  SeamUnavailable, any non-CheckFailure exception, or a
                    CheckFailure raised without the seam ever being reached
                    (an expectation about a call that never happened)."""
    if chk.cls == "unexaminable":
        return {"result": "unexaminable", "red_kind": None, "signature": "",
                "seam_reached": False, "duration_s": 0.0}
    seam.reached = False
    t0 = time.time()

    def out(result, red_kind, signature):
        return {"result": result, "red_kind": red_kind, "signature": signature,
                "seam_reached": seam.reached,
                "duration_s": round(time.time() - t0, 3)}
    try:
        chk.fn(seam)
    except CheckFailure as e:
        return out("fail", "behavioral" if seam.reached else "infrastructure",
                   _signature(e))
    except SeamUnavailable as e:
        return out("fail", "infrastructure", _signature(e))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        return out("fail", "infrastructure", _signature(e))
    return out("pass", None, "")


def _order(checks, only):
    """C-0 first, always, then declaration order — filtered by --only.

    C-0 runs regardless of --only because a delta red proof with no smoke is
    void by exactly the same rule as a full one."""
    smoke = [c for c in checks if c.id == "C-0"]
    rest = [c for c in checks if c.id != "C-0"]
    if only:
        rest = [c for c in rest if c.id in only]
    return smoke + rest


def _execute(seam, checks, only):
    rows, blocked = [], False
    for chk in _order(checks, only):
        # An unexaminable row never depended on the seam, so a broken harness
        # does not block it — it stays unexaminable, which is the honest answer.
        if blocked and chk.cls != "unexaminable":
            row = {"result": "blocked", "red_kind": None, "signature": "",
                   "seam_reached": False, "duration_s": 0.0}
        else:
            row = run_check(seam, chk)
            if chk.id == "C-0" and row["result"] != "pass":
                blocked = True   # a harness that cannot reach the seam reds
                                 # everything indiscriminately
        row.update({"id": chk.id, "ac": chk.ac, "class": chk.cls,
                    "provenance": chk.provenance})
        if chk.unexaminable:
            row["unexaminable"] = chk.unexaminable
        rows.append(row)
    return rows


def summarize(rows):
    """Counts + the exit code. `unproven` counts D8's three producers as
    measured by *this* run: a must-flip check that produced no behavioral red,
    i.e. passed, red infrastructure, or blocked by a red C-0. It is the number
    a red proof reports; at gate time the same arithmetic is expected to equal
    the must-flip total, which is why only red-proof.json fills a manifest's
    Red-proof cells."""
    s = {r: sum(1 for row in rows if row["result"] == r) for r in RESULTS}
    s["unproven"] = sum(1 for row in rows if row["class"] == "must-flip"
                        and not (row["result"] == "fail"
                                 and row["red_kind"] == "behavioral"))
    smoke = next((r for r in rows if r["id"] == "C-0"), None)
    infra = any(r["red_kind"] == "infrastructure" for r in rows)
    if (smoke is None) or smoke["result"] != "pass" or infra:
        s["exit_code"] = 2
    elif s["fail"]:
        s["exit_code"] = 1
    else:
        s["exit_code"] = 0
    return s


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

def _quoted_ei_block(manifest_path):
    """The fenced text under `## Read rule` in manifest.md — the verbatim
    External Interface quote `--audit-seam` compares the seam target against."""
    lines = manifest_path.read_text().splitlines()
    out, in_section, fence = [], False, None
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip().lower() == "## read rule"
            continue
        if not in_section:
            continue
        stripped = line.strip()
        if fence is None and (stripped.startswith("```") or stripped.startswith("~~~")):
            fence = stripped[:3]
        elif fence is not None and stripped.startswith(fence):
            fence = None
        elif fence is not None:
            out.append(line)
    return "\n".join(out)


def _audit_seam(seam, exam_dir):
    manifest = exam_dir / "manifest.md"
    if not manifest.exists():
        print(f"FAIL: no manifest.md beside exam.py at {exam_dir}",
              file=sys.stderr)
        return 3
    block = _quoted_ei_block(manifest)
    if not block.strip():
        print("FAIL: manifest.md has no fenced External Interface quote under "
              "'## Read rule' — --audit-seam has nothing to compare against",
              file=sys.stderr)
        return 3
    target = seam.target()
    if target in block:
        print(f"OK: seam target {target!r} appears verbatim in manifest.md's "
              "quoted External Interface block")
        return 0
    print(f"FAIL: seam target {target!r} does not appear in manifest.md's "
          "quoted External Interface block — the exam drives a seam the spec "
          "did not declare, or the quote is stale", file=sys.stderr)
    return 1


def _list(seam, checks):
    print(f"seam: {seam.kind} · {seam.target()}")
    for chk in _order(checks, None):
        print(f"{chk.id:<6} {chk.ac:<8} {chk.cls:<13} {chk.provenance:<12} "
              f"{chk.title}")
    return 0


def _emit_human(meta, rows, summary):
    print(f"exam: {meta['exam']}   seam: {meta['seam']['kind']} · "
          f"{meta['seam']['target']}")
    print(f"anchor: surface {meta['anchor'].get('surface_hash', '')[:12]} @ "
          f"raise {meta['anchor'].get('raise_commit', '')[:12]} "
          f"· extractor v{meta['anchor'].get('extractor_version')}")
    for r in rows:
        flag = r["result"].upper() if r["result"] != "pass" else "pass"
        tail = r["signature"] or r.get("unexaminable", "")
        print(f"{r['id']:<6} {r['ac']:<8} {r['class']:<13} {flag:<13} "
              f"{r['red_kind'] or '-':<15} {r['duration_s']:>6.2f}s  {tail}")
    print(f"pass {summary['pass']} · fail {summary['fail']} · blocked "
          f"{summary['blocked']} · unexaminable {summary['unexaminable']} · "
          f"unproven {summary['unproven']} · exit {summary['exit_code']}")


def _main(seam, checks, argv):
    if not __debug__:
        print("FAIL: this exam was run with assertions disabled (`python3 -O` "
              "or PYTHONOPTIMIZE). Refusing: -O strips `assert`, so a check "
              "that used one would be born green. Re-run without -O.",
              file=sys.stderr)
        return 3
    if _DECL_ERRORS:
        for e in _DECL_ERRORS:
            print(f"FAIL: malformed check declaration — {e}", file=sys.stderr)
        return 3
    if not isinstance(seam, SEAM_KINDS):
        print("FAIL: unknown seam kind "
              f"{type(seam).__name__!r} — kestra-exam closes the seam set at "
              "Cli, Http and Module. Name the new kind and extend "
              "exam_harness.py deliberately; do not improvise one in exam.py.",
              file=sys.stderr)
        return 3
    if not checks:
        print("FAIL: exam declares no checks", file=sys.stderr)
        return 3
    if not any(c.id == "C-0" for c in checks):
        print("FAIL: exam declares no C-0 — every exam carries the harness "
              "smoke check, or a red proof cannot be told apart from a broken "
              "harness.", file=sys.stderr)
        return 3

    main_mod = sys.modules.get("__main__")
    exam_slug = getattr(main_mod, "EXAM", None)
    anchor = getattr(main_mod, "ANCHOR", None)
    if not isinstance(exam_slug, str) or not isinstance(anchor, dict):
        print("FAIL: exam.py must define EXAM = '<feature-slug>' and "
              "ANCHOR = {'raise_commit':…, 'surface_hash':…, "
              "'extractor_version':…} at module level — an unanchored exam "
              "cannot certify anything.", file=sys.stderr)
        return 3

    only, mode, i = [], "run", 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            mode = "json"
        elif a == "--list":
            mode = "list"
        elif a == "--audit-seam":
            mode = "audit"
        elif a == "--repo":
            i += 1  # already consumed by repo_root() at import time
        elif a == "--only":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                only.append(argv[i])
                i += 1
            continue
        else:
            print(f"FAIL: unknown argument {a!r}. "
                  "Usage: exam.py [--json|--list|--audit-seam] "
                  "[--only C-3 C-7] [--repo <path>]", file=sys.stderr)
            return 3
        i += 1

    unknown = [o for o in only if not any(c.id == o for c in checks)]
    if unknown:
        print(f"FAIL: --only names checks this exam does not declare: "
              f"{' '.join(unknown)}", file=sys.stderr)
        return 3

    exam_dir = Path(getattr(main_mod, "__file__", ".")).resolve().parent
    if mode == "list":
        return _list(seam, checks)
    if mode == "audit":
        return _audit_seam(seam, exam_dir)

    started, t0 = _now_iso(), time.time()
    try:
        rows = _execute(seam, checks, only)
    finally:
        seam.close()
    summary = summarize(rows)
    meta = {"exam": exam_slug, "anchor": anchor,
            "seam": {"kind": seam.kind, "target": seam.target()},
            "started_at": started, "duration_s": round(time.time() - t0, 3)}
    smoke = next(r for r in rows if r["id"] == "C-0")
    if mode == "json":
        print(json.dumps({**meta,
                          "harness_version": HARNESS_VERSION,
                          "smoke": {"id": "C-0", "result": smoke["result"]},
                          "checks": rows, "summary": summary}, indent=2))
    else:
        _emit_human(meta, rows, summary)
    return summary["exit_code"]


def run_main(seam, checks=None, argv=None):
    """The whole CLI. `checks` defaults to the @check registry, whose order of
    appearance is the run order — pass a list only from the harness's own
    tests, never from an exam.py, so the declaration cannot disagree with the
    run."""
    sys.exit(_main(seam, REGISTRY if checks is None else checks,
                   sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    print(__doc__)
    print("This is a library. Run an exam.py that imports it.")
    sys.exit(3)
