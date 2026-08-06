#!/usr/bin/env python3
"""Deterministic tests for the spec-anchor checks and the two validate_spec
minors they shipped with — no LLM, no network, stdlib only.

Run:  python3 test_validate_workflow_anchor.py     (exit 0 on pass, 1 on failure)

Same conventions as test_requirement_surface.py: inline fixtures (never the
repo's real specs, which get repaired and regrown), and assertions on external
behavior only — here that means the scripts' real stdout and real exit code,
obtained by running them as subprocesses out of a throwaway run folder. Nothing
imports validate_workflow.py's internals, because the thing under test is
partly *how it resolves its own import*, which an in-process import would
quietly paper over.

Two tests exist specifically to pin that import path (the carried obligation):
ImportPath.test_source_has_no_path_surgery reads the source, and
ImportPath.test_resolves_extractor_as_a_same_directory_sibling proves the
resolution empirically by running the script from an unrelated cwd with no
PYTHONPATH, then deleting the sibling and watching the anchored case fail.

The validate_spec cases live here rather than in a second file because they are
the same change: the anchor triple and the chain marker are the two ends of one
absent-is-WARN / partial-is-FAIL rule.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from requirement_surface import EXTRACTOR_VERSION, extract_surface

SCRIPTS = Path(__file__).resolve().parent
VALIDATE_WORKFLOW = SCRIPTS / "validate_workflow.py"
VALIDATE_SPEC = SCRIPTS / "validate_spec.py"
REQUIREMENT_SURFACE = SCRIPTS / "requirement_surface.py"

RAISE_COMMIT = "4f1c0b9e2d7a5c3b8e6f0a1d2c3b4a5968778899"

SPEC = """# [demo] Spec — Demo

## Functional Requirements

* [ ] Customer can cancel any order in `paid` status.

## AC Coverage Map

| AC | Source | Covered by (files/steps) |
|----|--------|--------------------------|
| AC-1 | US-1 | `src/demo.js` |
"""

# Three stages in a chain: tests written, frozen, then implemented. Structurally
# sound on purpose — every FAIL a test below asserts must come from the anchor
# checks, never from the graph.
STAGES = """
stages:
  - id: write-tests
    depends_on: []
    write_scope: ["tests/demo.test.js"]
    exit_criteria:
      type: artifact_exists
      artifact: tests/demo.test.js
    on_fail:
      action: reworking
      reason: the tests could not be written
  - id: freeze-tests
    depends_on: [write-tests]
    write_scope: ["tests/demo.test.js"]
    freeze_after: true
    exit_criteria:
      type: command
      run: "true"
    on_fail:
      action: reworking
      reason: the freeze could not be taken
  - id: implement
    depends_on: [freeze-tests]
    write_scope: ["src/demo.js"]
    exit_criteria:
      type: command
      run: "true"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 3
"""

STATE = {
    "stages": {sid: {"status": "pending"} for sid in
               ("write-tests", "freeze-tests", "implement")},
    "test_hash": None,
}


def surface_hash(text=SPEC):
    return extract_surface(text).surface_hash


def workflow_yaml(anchor=None, spec_name="0-spec.md", extra=""):
    """A structurally sound workflow.yaml, with `anchor` rendered verbatim as the
    spec_anchor block body (None ⇒ no spec_anchor key at all)."""
    head = f"feature: demo\nsource_spec: {spec_name}\n"
    if anchor is not None:
        head += "spec_anchor:\n"
        for key, value in anchor.items():
            head += f"  {key}: {value}\n"
    return head + "mode: full\n" + extra + STAGES


def run(script, target, cwd, *args):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run([sys.executable, str(script), str(target), *args],
                          capture_output=True, text=True, env=env, cwd=str(cwd))
    return proc.returncode, proc.stdout + proc.stderr


class RunFolder:
    """A throwaway run folder holding byte copies of the two scripts, plus an
    unrelated directory to invoke them from — the shape kestra-build commits."""

    def __init__(self, anchor=None, spec=SPEC, with_extractor=True, **kwargs):
        self.root = Path(tempfile.mkdtemp())
        self.dir = self.root / "run"
        self.elsewhere = self.root / "elsewhere"
        self.dir.mkdir()
        self.elsewhere.mkdir()
        (self.dir / "0-spec.md").write_text(spec)
        (self.dir / "workflow.yaml").write_text(workflow_yaml(anchor, **kwargs))
        (self.dir / "state.json").write_text(json.dumps(STATE))
        shutil.copy(VALIDATE_WORKFLOW, self.dir / "validate_workflow.py")
        if with_extractor:
            shutil.copy(REQUIREMENT_SURFACE, self.dir / "requirement_surface.py")

    def validate(self):
        return run(self.dir / "validate_workflow.py", self.dir, self.elsewhere)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def valid_anchor(**overrides):
    anchor = {"raise_commit": RAISE_COMMIT,
              "surface_hash": surface_hash(),
              "extractor_version": EXTRACTOR_VERSION}
    anchor.update(overrides)
    return {k: v for k, v in anchor.items() if v is not None}


class AnchorMatrix(unittest.TestCase):
    """WARN/FAIL split — absent anchor is a WARN, any partial or stale one FAILs."""

    def check(self, anchor, expect_exit, expect_in, expect_not_in=(), **kwargs):
        folder = RunFolder(anchor, **kwargs)
        try:
            code, out = folder.validate()
            self.assertEqual(code, expect_exit, out)
            for needle in ([expect_in] if isinstance(expect_in, str) else expect_in):
                self.assertIn(needle, out)
            for needle in expect_not_in:
                self.assertNotIn(needle, out)
        finally:
            folder.close()

    def test_absent_anchor_warns_and_passes(self):
        self.check(None, 0,
                   ["WARN: no spec_anchor", "PASS —"],
                   expect_not_in=["FAIL"])

    def test_complete_valid_anchor_is_silent(self):
        self.check(valid_anchor(), 0, "PASS —",
                   expect_not_in=["FAIL", "spec_anchor"])

    def test_each_missing_key_is_a_partial_anchor_fail(self):
        for key in ("raise_commit", "surface_hash", "extractor_version"):
            with self.subTest(key):
                self.check(valid_anchor(**{key: None}), 1,
                           [f"FAIL: spec_anchor is partial — '{key}' is missing"])

    def test_abbreviated_raise_commit_fails(self):
        self.check(valid_anchor(raise_commit="4f1c0b9"), 1,
                   ["FAIL: spec_anchor.raise_commit is not a full 40-hex commit SHA"])

    def test_short_surface_hash_fails(self):
        self.check(valid_anchor(surface_hash="deadbeef"), 1,
                   ["FAIL: spec_anchor.surface_hash is not a 64-hex sha256"])

    def test_non_integer_extractor_version_fails(self):
        self.check(valid_anchor(extractor_version="v1"), 1,
                   ["FAIL: spec_anchor.extractor_version is not a positive integer"])

    def test_version_mismatch_is_not_comparable(self):
        self.check(valid_anchor(extractor_version=EXTRACTOR_VERSION + 1), 1,
                   ["are not comparable; re-fold"],
                   # the hashes must NOT be diffed across versions
                   expect_not_in=["recomputed now"])

    def test_moved_surface_fails_with_both_hashes(self):
        moved = SPEC.replace("in `paid` status", "in any status")
        folder = RunFolder(valid_anchor(), spec=moved)
        try:
            code, out = folder.validate()
            self.assertEqual(code, 1, out)
            self.assertIn("the spec moved since the fold; re-fold", out)
            self.assertIn(surface_hash()[:12], out)
            self.assertIn(surface_hash(moved)[:12], out)
        finally:
            folder.close()

    def test_unlocatable_spec_fails_when_anchored(self):
        # An anchor nobody can recompute is a fabricated anchor that passes. The
        # spec is committed into the run folder, so resolve_spec_path's basename
        # candidate hits for every real artifact regardless of the caller's cwd.
        self.check(valid_anchor(), 1,
                   ["FAIL: source_spec 'missing/elsewhere.md' not found",
                    "passes unchecked"],
                   expect_not_in=["PASS —"], spec_name="missing/elsewhere.md")

    def test_unclosed_fence_is_a_false_fresh_fail(self):
        truncated = SPEC.replace("## AC Coverage Map", "```\n## AC Coverage Map")
        folder = RunFolder(valid_anchor(surface_hash=surface_hash()), spec=truncated)
        try:
            code, out = folder.validate()
            self.assertEqual(code, 1, out)
            self.assertIn("cannot be extracted honestly", out)
        finally:
            folder.close()

    def test_empty_progress_field_fails(self):
        folder = RunFolder(None)
        try:
            wf = (folder.dir / "workflow.yaml").read_text().replace(
                '      run: "true"\n    on_fail:\n      action: fixing',
                '      run: "true"\n      progress:\n    on_fail:\n      action: fixing')
            (folder.dir / "workflow.yaml").write_text(wf)
            code, out = folder.validate()
            self.assertEqual(code, 1, out)
            self.assertIn("stage 'implement' exit_criteria.progress is empty", out)
        finally:
            folder.close()


class WriteScopeFrame(unittest.TestCase):
    """write_scope is matched against `git diff --name-only HEAD`, so it can only ever
    be repo-root-relative. The refusal has to teach that, not merely refuse."""

    def scope(self, entry):
        """Validate a run whose implement stage declares exactly `entry`."""
        folder = RunFolder(None)
        self.addCleanup(folder.close)
        path = folder.dir / "workflow.yaml"
        old, new = 'write_scope: ["src/demo.js"]', f'write_scope: ["{entry}"]'
        text = path.read_text()
        assert old in text, f"pattern absent: {old!r}"
        path.write_text(text.replace(old, new, 1))
        return folder.validate()

    def test_each_out_of_frame_prefix_fails(self):
        for entry in ("./src/demo.js", "../sibling/src/demo.js", "/tmp/src/demo.js"):
            with self.subTest(entry=entry):
                code, out = self.scope(entry)
                self.assertEqual(code, 1, out)
                self.assertIn(
                    f"stage 'implement' write_scope entry is not repo-root-relative: "
                    f"'{entry}'", out)

    def test_the_refusal_names_the_git_basis(self):
        # The teaching half is the whole reason this is a FAIL and not a WARN — an
        # author who never opened workflow-schema.md learns the frame from the message.
        code, out = self.scope("./src/demo.js")
        self.assertEqual(code, 1, out)
        self.assertIn("git diff --name-only HEAD", out)

    def test_dotfile_directory_scope_is_not_flagged(self):
        code, out = self.scope(".github/workflows/**")
        self.assertEqual(code, 0, out)
        self.assertIn("PASS —", out)
        self.assertNotIn("repo-root-relative", out)

    def test_interior_dotdot_is_not_flagged(self):
        # Prefix-only by design. Documented so nobody quietly upgrades the check into
        # a path normaliser without deciding to.
        code, out = self.scope("src/../src/demo.js")
        self.assertEqual(code, 0, out)


class ImportPath(unittest.TestCase):
    """The extractor must come from the run folder's own copy — sibling file, no
    path setup. Asserted twice: statically and empirically."""

    def test_source_has_no_path_surgery(self):
        source = VALIDATE_WORKFLOW.read_text()
        self.assertIn("from requirement_surface import", source)
        for banned in ("sys.path", "importlib", "__file__"):
            self.assertNotIn(banned, source,
                             f"{banned} in validate_workflow.py — the extractor must resolve "
                             f"as a same-directory sibling and only as that")

    def test_resolves_extractor_as_a_same_directory_sibling(self):
        # Run from an unrelated cwd with no PYTHONPATH: the only way the import
        # can succeed is the script's own directory.
        folder = RunFolder(valid_anchor())
        try:
            code, out = folder.validate()
            self.assertEqual(code, 0, out)
            self.assertIn("PASS —", out)
        finally:
            folder.close()

    def test_missing_sibling_fails_when_anchored_warns_when_not(self):
        anchored = RunFolder(valid_anchor(), with_extractor=False)
        try:
            code, out = anchored.validate()
            self.assertEqual(code, 1, out)
            self.assertIn("requirement_surface.py is not beside this script", out)
        finally:
            anchored.close()

        standalone = RunFolder(None, with_extractor=False)
        try:
            code, out = standalone.validate()
            self.assertEqual(code, 0, out)
            self.assertIn("WARN: no spec_anchor", out)
            self.assertNotIn("FAIL", out)
        finally:
            standalone.close()


MARKER = "> Spec-ticket: https://github.com/o/r/issues/47"

BARE_SPEC = """# [demo] Spec — Demo

## Functional Requirements

* [ ] Customer can cancel any order in `paid` status.
"""

FILES_SPEC = """# [demo] Spec — Demo

## Files to Touch

| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| `{path}` | edit | yes | the build entrypoint |
"""


class SpecMarkerFences(unittest.TestCase):
    """A 'Spec-ticket:' line inside a code fence is an example — never a marker,
    never a misplacement. One rule, both sides of the first '## '."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def spec(self, text):
        # requirement_surface.py must sit beside the script under test, exactly as
        # it does in a real run folder — that is what makes the scan fence-aware.
        path = self.root / "0-spec.md"
        path.write_text(text)
        return run(VALIDATE_SPEC, path, self.root)

    def test_fenced_marker_below_the_first_h2_is_not_a_misplacement(self):
        code, out = self.spec(BARE_SPEC + f"\n```\n{MARKER}\n```\n")
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", out)
        self.assertNotIn("outside the preamble", out)

    def test_fenced_marker_in_the_preamble_reads_standalone(self):
        code, out = self.spec(f"# [demo] Spec — Demo\n\n```\n{MARKER}\n```\n"
                              + BARE_SPEC.split("\n", 1)[1])
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", out)
        # Standalone ⇒ the five conditional checks report as WARN, not FAIL.
        self.assertIn("WARN: no 'AC Coverage Map' section found", out)

    def test_unfenced_marker_below_the_first_h2_still_fails(self):
        # Non-vacuity: the fence-awareness must not have disabled the check.
        code, out = self.spec(BARE_SPEC + f"\n{MARKER}\n")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: 'Spec-ticket:' line outside the preamble", out)

    def test_duplicate_heading_is_reported_as_itself(self):
        # The SurfaceError arm used to print "unclosed code fence" for every
        # cause, so a duplicated heading was reported as something it was not.
        code, out = self.spec(f"# [demo] Spec — Demo\n\n{MARKER}\n"
                              + BARE_SPEC.split("\n", 1)[1]
                              + "\n## Functional Requirements\n\n- [ ] FR-2\n")
        self.assertEqual(code, 1, out)
        self.assertIn("appears twice", out)
        self.assertNotIn("unclosed code fence", out)

    def test_unfenced_preamble_marker_still_chains(self):
        code, out = self.spec(f"# [demo] Spec — Demo\n\n{MARKER}\n"
                              + BARE_SPEC.split("\n", 1)[1])
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: no 'AC Coverage Map' section found", out)


CONTRACT_SPEC = f"""# [demo] Spec — Demo

{{marker}}

## External Interface

* Primary: `python3 demo.py`.

## Functional Requirements

* [ ] AC-1.

## AC Coverage Map

| AC | Source | Covered by (files/steps) |
|----|--------|--------------------------|
| AC-1 | US-1 | `demo.py` |

## Exit Criteria

**Stop condition:** all checks pass — **or** two consecutive attempt rounds pass without the
relevant progress number below moving, at which point stop and summon the human rather than attempt
a third.

* progress: passing checks — must reach 5, from a baseline of 0.

## Mode Prediction

* **kestra-build mode:** `full` — integration crosses three modules.
"""


class SpecConditionalObligations(unittest.TestCase):
    """Marked specs hard-gate the complete template facts; unmarked specs warn."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def spec(self, text):
        path = self.root / "0-spec.md"
        path.write_text(text)
        return run(VALIDATE_SPEC, path, self.root)

    def test_complete_marked_contract_passes(self):
        code, out = self.spec(CONTRACT_SPEC.format(marker=MARKER))
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", out)

    def test_marked_mode_without_reason_fails(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            " — integration crosses three modules.", "")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: the mode-prediction line records no reason", out)

    def test_unmarked_mode_without_reason_warns(self):
        text = CONTRACT_SPEC.format(marker="").replace(
            " — integration crosses three modules.", "")
        code, out = self.spec(text)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN: the mode-prediction line records no reason", out)

    def test_marked_stop_without_no_progress_clause_fails(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            " — **or** two consecutive attempt rounds pass without the\n"
            "relevant progress number below moving, at which point stop and summon the human "
            "rather than attempt\n"
            "a third.", "")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: '## Exit Criteria' stop condition is missing", out)

    def test_marked_malformed_progress_fragment_fails(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            "* progress: passing checks — must reach 5, from a baseline of 0.",
            "* progress: checks look better.")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: '## Exit Criteria' has 1 incomplete progress fragment", out)

    def test_unmarked_malformed_exit_criteria_warns(self):
        text = CONTRACT_SPEC.format(marker="").replace(
            "* progress: passing checks — must reach 5, from a baseline of 0.",
            "* progress: checks look better.")
        code, out = self.spec(text)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN: '## Exit Criteria' has 1 incomplete progress fragment", out)

    def test_marked_wrapped_progress_fragment_passes(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            "* progress: passing checks — must reach 5, from a baseline of 0.",
            "* progress: passing checks — must reach 5,\n  from a baseline of 0.")
        code, out = self.spec(text)
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", out)

    def test_marked_non_numeric_progress_fails(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            "passing checks — must reach 5, from a baseline of 0.",
            "test state — must reach green, from a baseline of red.")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: '## Exit Criteria' has 1 non-numeric progress fragment", out)

    def test_unmarked_non_numeric_progress_warns(self):
        text = CONTRACT_SPEC.format(marker="").replace(
            "passing checks — must reach 5, from a baseline of 0.",
            "test state — must reach green, from a baseline of red.")
        code, out = self.spec(text)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN: '## Exit Criteria' has 1 non-numeric progress fragment", out)

    def test_fenced_mode_example_does_not_satisfy_marked_contract(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            "* **kestra-build mode:** `full` — integration crosses three modules.",
            "```\n* **kestra-build mode:** `full` — example only.\n```")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: no recorded mode-prediction fact", out)

    def test_fenced_exit_example_does_not_satisfy_marked_contract(self):
        block = ("**Stop condition:** all checks pass — **or** two consecutive attempt rounds pass "
                 "without the\nrelevant progress number below moving, at which point stop and "
                 "summon the human rather than attempt\na third.\n\n"
                 "* progress: passing checks — must reach 5, from a baseline of 0.")
        text = CONTRACT_SPEC.format(marker=MARKER).replace(block, f"```\n{block}\n```")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: '## Exit Criteria' stop condition is missing", out)

    def test_fenced_source_table_does_not_satisfy_marked_contract(self):
        table = ("| AC | Source | Covered by (files/steps) |\n"
                 "|----|--------|--------------------------|\n"
                 "| AC-1 | US-1 | `demo.py` |")
        text = CONTRACT_SPEC.format(marker=MARKER).replace(table, f"```\n{table}\n```")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: no 'Source' column", out)

    def test_fenced_external_interface_does_not_satisfy_marked_contract(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            "* Primary: `python3 demo.py`.",
            "```\n* Primary: `python3 demo.py`.\n```")
        code, out = self.spec(text)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: '## External Interface' is empty", out)

    def assert_placeholder_is_conditional(self, old, placeholder, message):
        for marker, level, code in ((MARKER, "FAIL", 1), ("", "WARN", 0)):
            with self.subTest(marker=bool(marker), placeholder=placeholder):
                text = CONTRACT_SPEC.format(marker=marker).replace(old, placeholder)
                actual, out = self.spec(text)
                self.assertEqual(actual, code, out)
                self.assertIn(f"{level}: {message}", out)

    def test_external_interface_scaffold_is_not_content(self):
        self.assert_placeholder_is_conditional(
            "* Primary: `python3 demo.py`.",
            "*(the seam the tests may drive — and only this seam.)*",
            "'## External Interface' still carries its template scaffold")

    def test_external_helper_may_remain_beside_real_content(self):
        text = CONTRACT_SPEC.format(marker=MARKER).replace(
            "* Primary: `python3 demo.py`.",
            "*(the seam the tests may drive — and only this seam.)*\n"
            "* Primary: `python3 demo.py`.")
        code, out = self.spec(text)
        self.assertEqual(code, 0, out)
        self.assertNotIn("template scaffold", out)

    def test_source_scaffold_is_not_provenance(self):
        self.assert_placeholder_is_conditional(
            "| AC-1 | US-1 | `demo.py` |",
            "| AC-1 | [US-n / ID§x / TD / FN / OOS / PS / IDEA§x / Q<n> / ⚠ inferred] | `demo.py` |",
            "1 AC Coverage Map row(s) still carry the template Source scaffold")

    def test_mode_reason_scaffold_is_not_a_reason(self):
        self.assert_placeholder_is_conditional(
            "integration crosses three modules.",
            "[the reason that decided it]",
            "the mode-prediction line still carries its template reason scaffold")

    def test_stop_scaffold_is_not_a_completion_clause(self):
        self.assert_placeholder_is_conditional(
            "all checks pass",
            "[completion clause]",
            "'## Exit Criteria' stop condition still carries its template completion scaffold")

    def test_progress_scaffold_is_not_a_moving_number(self):
        self.assert_placeholder_is_conditional(
            "passing checks",
            "[the number that must move]",
            "'## Exit Criteria' has 1 progress fragment(s) with the template metric scaffold")

    def test_single_shot_scaffold_is_not_a_check(self):
        self.assert_placeholder_is_conditional(
            "* progress: passing checks — must reach 5, from a baseline of 0.",
            "* Single-shot pass/fail, no progress number: "
            "[the checks that deliberately carry none].",
            "'## Exit Criteria' single-shot bullet still carries its template scaffold")


class SpecExtensionlessPaths(unittest.TestCase):
    """`Makefile` is a path claim, not prose — shape decides, not the extension."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def spec(self, path_cell):
        path = self.root / "0-spec.md"
        path.write_text(FILES_SPEC.format(path=path_cell))
        return run(VALIDATE_SPEC, path, self.root)

    def test_missing_extensionless_path_fails(self):
        for name in ("Makefile", "Dockerfile", "LICENSE", "Justfile"):
            with self.subTest(name):
                code, out = self.spec(name)
                self.assertEqual(code, 1, out)
                self.assertIn(f"FAIL: Files to Touch row '{name}' marked 'edit' "
                              f"but the path does not exist on disk", out)

    def test_present_extensionless_path_passes(self):
        (self.root / "Makefile").write_text("all:\n\t@true\n")
        code, out = self.spec("Makefile")
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", out)
        self.assertNotIn("names no file path", out)

    def test_prose_and_placeholder_cells_still_warn(self):
        for cell in ("*(none — illustrative spec, no repo attached)*", "TBD", "n/a", "-"):
            with self.subTest(cell):
                code, out = self.spec(cell)
                self.assertEqual(code, 0, out)
                self.assertNotIn("FAIL", out)
                self.assertTrue(re.search(r"WARN: Files to Touch row 1 names no file path", out),
                                out)

    def test_missing_extensioned_path_still_fails(self):
        code, out = self.spec("src/demo.js")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: Files to Touch row 'src/demo.js'", out)


TICKET_ID = "demo-1"
TICKET_BODY = """## What to build

Write the demo module.

## Acceptance criteria

- [ ] AC-1

## Blocked by

- nothing
"""


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ac_hash(ac_ids=("AC-1",), spec=SPEC):
    """`ticket-fold.md` §3 F3's definition, spelled out here rather than imported:
    a test that computed this by calling the code under test could not tell a
    changed hash from a changed formula."""
    rows = [row for ac_id, row in extract_surface(spec).ac_rows if ac_id in ac_ids]
    return hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


def embedded_block(body, tid=TICKET_ID, hex_=None, indent="      "):
    lines = ([f"<!-- ticket:begin {tid} sha256:{hex_ or sha_text(body)} -->"]
             + body.splitlines() + [f"<!-- ticket:end {tid} -->"])
    return "\n".join((indent + ln) if ln else "" for ln in lines)


class SeparationGuard(unittest.TestCase):
    """--separation-guard — the writer/implementer split, read off what each stage
    recorded about its own spawn. Post-run, so it needs a populated state.json."""

    WORKFLOW = """feature: demo
mode: full

stages:
  - id: generate-tests
    depends_on: []
  - id: implement-demo
    depends_on: [generate-tests]
"""

    def guard(self, spawns, workflow=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "workflow.yaml").write_text(workflow or self.WORKFLOW)
        (root / "state.json").write_text(json.dumps({"stages": {
            sid: {"status": "passed", "metrics": {"spawn_type": spawn}} if spawn
            else {"status": "passed"} for sid, spawn in spawns.items()}}))
        shutil.copy(VALIDATE_WORKFLOW, root / "validate_workflow.py")
        shutil.copy(REQUIREMENT_SURFACE, root / "requirement_surface.py")
        return run(root / "validate_workflow.py", root, root, "--separation-guard")

    def test_two_fresh_spawns_pass(self):
        code, out = self.guard({"generate-tests": "fresh", "implement-demo": "fresh"})
        self.assertEqual(code, 0, out)
        self.assertIn("PASS — separation guard", out)

    def test_inline_controller_fails_even_with_distinct_labels(self):
        # The run this guard exists to catch: two different labels, one actor.
        code, out = self.guard({"generate-tests": "inline-controller-fallback-after-x",
                                "implement-demo": "controller-fallback-after-y"})
        self.assertEqual(code, 1, out)
        self.assertIn("stage 'generate-tests' recorded spawn_type", out)
        self.assertIn("stage 'implement-demo' recorded spawn_type", out)

    def test_absent_metrics_is_not_a_pass(self):
        code, out = self.guard({"generate-tests": None, "implement-demo": "fresh"})
        self.assertEqual(code, 1, out)
        self.assertIn("recorded spawn_type None", out)

    def test_resumed_is_not_fresh(self):
        code, out = self.guard({"generate-tests": "fresh", "implement-demo": "resumed"})
        self.assertEqual(code, 1, out)
        self.assertIn("'implement-demo'", out)

    def test_a_workflow_with_neither_stage_cannot_certify(self):
        code, out = self.guard({"review": "fresh"},
                               workflow="feature: demo\nmode: full\n\nstages:\n"
                                        "  - id: review\n    depends_on: []\n")
        self.assertEqual(code, 1, out)
        self.assertIn("declares neither", out)

    def test_default_mode_never_reads_spawn_type(self):
        # The guard is opt-in: an unanchored, metrics-less workflow still passes.
        folder = RunFolder(None)
        self.addCleanup(folder.close)
        code, out = folder.validate()
        self.assertEqual(code, 0, out)
        self.assertNotIn("spawn_type", out)


class SlicedFolder(RunFolder):
    """A run folder for a *sliced* fold: 0-spec.md + tickets/<id>.md + a tickets[]
    map + the ticket embedded in the owning stage's brief. Built clean, then
    mutated per test with edit_workflow/edit_ticket — the same shape the eval's
    hand-edit routes use, so a test and a leg of the eval mean the same thing."""

    def __init__(self, spec=SPEC, body=TICKET_BODY, anchor=True, with_extractor=True):
        fold_anchor = valid_anchor(surface_hash=surface_hash(spec))
        super().__init__(fold_anchor if anchor else None, spec=spec,
                         with_extractor=with_extractor)
        self.body = body
        (self.dir / "tickets").mkdir()
        self.ticket = self.dir / "tickets" / f"{TICKET_ID}.md"
        self.ticket.write_text(body)
        head = f"feature: demo\nsource_spec: 0-spec.md\n"
        if anchor:
            head += "spec_anchor:\n"
            for key, value in fold_anchor.items():
                head += f"  {key}: {value}\n"
        head += ("mode: full\n\ntickets:\n"
                 f"  - id: {TICKET_ID}\n"
                 f"    ref: tickets/{TICKET_ID}.md\n"
                 f"    body_sha256: {sha_text(body)}\n"
                 f"    ac_hash: {ac_hash(spec=spec)}\n"
                 f"    verified_against: {RAISE_COMMIT}\n"
                 f'    verified_at: "2026-08-02T09:14:03Z"\n')
        stages = STAGES.replace(
            "  - id: implement\n    depends_on: [freeze-tests]\n",
            "  - id: implement\n    depends_on: [freeze-tests]\n    brief: |\n"
            + embedded_block(body) + "\n\n      Implement per the block above.\n")
        (self.dir / "workflow.yaml").write_text(head + stages)

    def _edit(self, path, old, new):
        text = path.read_text()
        assert old in text, f"pattern absent: {old!r}"
        path.write_text(text.replace(old, new, 1))

    def edit_workflow(self, old, new):
        self._edit(self.dir / "workflow.yaml", old, new)

    def edit_ticket(self, old, new):
        self._edit(self.ticket, old, new)


class TicketFoldMatrix(unittest.TestCase):
    """§A4 — the tickets[] map and the embedded blocks. Every case asserts a
    *named* disagreement, because "some FAIL appeared" would pass even if the
    check that fired were the wrong one."""

    def setUp(self):
        self.folder = SlicedFolder()
        self.addCleanup(self.folder.close)

    def assertFail(self, needle):
        code, out = self.folder.validate()
        self.assertEqual(code, 1, out)
        self.assertIn(needle, out)

    def test_clean_sliced_fold_passes_silently(self):
        code, out = self.folder.validate()
        self.assertEqual(code, 0, out)
        self.assertIn("PASS —", out)
        self.assertNotIn("FAIL", out)

    def test_sliced_fold_without_spec_anchor_fails(self):
        folder = SlicedFolder(anchor=False)
        self.addCleanup(folder.close)
        code, out = folder.validate()
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: sliced fold has no spec_anchor", out)

    def test_unlocatable_spec_fails_both_the_anchor_and_every_ac_hash(self):
        # _load_surface returning None skipped every per-ticket ac_hash compare
        # silently; both checks must now name their own unverifiable recompute.
        self.folder.edit_workflow("source_spec: 0-spec.md",
                                  "source_spec: missing/elsewhere.md")
        code, out = self.folder.validate()
        self.assertEqual(code, 1, out)
        self.assertIn("spec_anchor.surface_hash", out)
        self.assertIn("passes unchecked", out)
        self.assertIn("every one of them passes unverified", out)

    def test_wrapped_ticket_ac_normalizes_as_one_logical_unit(self):
        spec = SPEC.replace("| AC-1 | US-1 |", "| AC-1 works across lines | US-1 |")
        body = TICKET_BODY.replace("- [ ] AC-1", "- [ ] AC-1 works\n  across lines")
        folder = SlicedFolder(spec=spec, body=body)
        self.addCleanup(folder.close)
        folder.edit_workflow(
            f"ac_hash: {ac_hash(spec=spec)}",
            f"ac_hash: {ac_hash(ac_ids=('AC-1 works across lines',), spec=spec)}")
        code, out = folder.validate()
        self.assertEqual(code, 0, out)
        self.assertIn("PASS —", out)
        self.assertNotIn("FAIL", out)

    def test_refold_guard_refuses_live_state_before_overwrite(self):
        state_path = self.folder.dir / "state.json"
        state = json.loads(state_path.read_text())
        state["stages"]["implement"]["status"] = "passed"
        state_path.write_text(json.dumps(state))
        proc = subprocess.run(
            [sys.executable, str(self.folder.dir / "validate_workflow.py"),
             str(self.folder.dir), "--refold-guard"],
            capture_output=True, text=True, cwd=str(self.folder.elsewhere))
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("FAIL: refusing to re-fold — stages [implement] are past 'pending'", out)

    def test_refold_guard_accepts_initial_pending_state(self):
        proc = subprocess.run(
            [sys.executable, str(self.folder.dir / "validate_workflow.py"),
             str(self.folder.dir), "--refold-guard"],
            capture_output=True, text=True, cwd=str(self.folder.elsewhere))
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("PASS — re-fold guard: every existing stage is pending", out)

    def test_refold_guard_rejects_non_object_state_without_traceback(self):
        (self.folder.dir / "state.json").write_text("[]")
        proc = subprocess.run(
            [sys.executable, str(self.folder.dir / "validate_workflow.py"),
             str(self.folder.dir), "--refold-guard"],
            capture_output=True, text=True, cwd=str(self.folder.elsewhere))
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("FAIL: refusing to re-fold — state.json root is not an object", out)
        self.assertNotIn("Traceback", out)

    def test_refold_guard_rejects_missing_or_malformed_stages(self):
        for state in ({}, {"stages": None}, {"stages": []}, {"stages": {}}):
            with self.subTest(state=state):
                (self.folder.dir / "state.json").write_text(json.dumps(state))
                proc = subprocess.run(
                    [sys.executable, str(self.folder.dir / "validate_workflow.py"),
                     str(self.folder.dir), "--refold-guard"],
                    capture_output=True, text=True, cwd=str(self.folder.elsewhere))
                out = proc.stdout + proc.stderr
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn("FAIL: refusing to re-fold — state.json.stages is not a "
                              "non-empty object", out)
                self.assertNotIn("Traceback", out)

    def test_refold_guard_requires_exact_workflow_state_stage_ids(self):
        state_path = self.folder.dir / "state.json"
        original = json.loads(state_path.read_text())
        cases = []
        missing = json.loads(json.dumps(original))
        del missing["stages"]["implement"]
        cases.append(missing)
        extra = json.loads(json.dumps(original))
        extra["stages"]["ghost"] = {"status": "pending"}
        cases.append(extra)
        for state in cases:
            with self.subTest(stage_ids=sorted(state["stages"])):
                state_path.write_text(json.dumps(state))
                proc = subprocess.run(
                    [sys.executable, str(self.folder.dir / "validate_workflow.py"),
                     str(self.folder.dir), "--refold-guard"],
                    capture_output=True, text=True, cwd=str(self.folder.elsewhere))
                out = proc.stdout + proc.stderr
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn("FAIL: refusing to re-fold — workflow/state stage ids differ", out)

    # --- the four hand-edit routes of ticket-fold.md §4, each with its own message
    def test_route_a_brief_only_edit(self):
        self.folder.edit_workflow("Write the demo module.", "Write the demo module!")
        self.assertFail("embedded ticket block does not match tickets/demo-1.md — the brief was "
                        "hand-edited; re-fold")

    def test_route_a_brief_only_rewrap_is_not_verbatim(self):
        self.folder.edit_workflow("Write the demo module.",
                                  "Write the demo\n      module.")
        self.assertFail("embedded ticket block does not match tickets/demo-1.md — the brief was "
                        "hand-edited; re-fold")

    def test_route_b_file_only_edit(self):
        self.folder.edit_ticket("Write the demo module.", "Write the demo module!")
        self.assertFail("body changed since the fold")

    def test_route_c_file_and_block_and_delimiter_hex(self):
        for edit in (self.folder.edit_ticket, self.folder.edit_workflow):
            edit("Write the demo module.", "Write the demo module!")
        self.folder.edit_workflow(f"sha256:{sha_text(TICKET_BODY)}",
                                  f"sha256:{sha_text(self.folder.ticket.read_text())}")
        self.assertFail("body_sha256")

    def test_route_d_all_three_consistently_still_fails_on_the_ac_row(self):
        # The three hashes *can* be made to agree; they then describe an AC the
        # spec's Coverage Map does not contain, which is where the fold refuses.
        for edit in (self.folder.edit_ticket, self.folder.edit_workflow):
            edit("- [ ] AC-1", "- [ ] AC-9")
        new = self.folder.ticket.read_text()
        self.folder.edit_workflow(f"sha256:{sha_text(TICKET_BODY)}", f"sha256:{sha_text(new)}")
        self.folder.edit_workflow(f"body_sha256: {sha_text(TICKET_BODY)}",
                                  f"body_sha256: {sha_text(new)}")
        self.assertFail('ticket demo-1 AC 1 "AC-9" matches no row in the spec\'s AC Coverage Map')

    # --- the map's own fields
    def test_stale_ac_hash_fails(self):
        self.folder.edit_workflow(f"ac_hash: {ac_hash()}", f"ac_hash: {'0' * 64}")
        self.assertFail("≠ recomputed")

    def test_verified_against_must_equal_raise_commit(self):
        self.folder.edit_workflow(f"verified_against: {RAISE_COMMIT}",
                                  f"verified_against: {'1' * 40}")
        self.assertFail("≠ spec_anchor.raise_commit")

    def test_each_missing_marker_field_is_a_partial_entry(self):
        for key, line in (("body_sha256", f"    body_sha256: {sha_text(TICKET_BODY)}\n"),
                          ("ac_hash", f"    ac_hash: {ac_hash()}\n"),
                          ("verified_against", f"    verified_against: {RAISE_COMMIT}\n"),
                          ("verified_at", '    verified_at: "2026-08-02T09:14:03Z"\n')):
            with self.subTest(key):
                folder = SlicedFolder()
                try:
                    folder.edit_workflow(line, "")
                    code, out = folder.validate()
                    self.assertEqual(code, 1, out)
                    self.assertIn(f"tickets['{TICKET_ID}'] is partial — '{key}' is missing", out)
                finally:
                    folder.close()

    def test_ref_is_not_graded(self):
        # The one field the schema declares ungraded: dropping it changes nothing.
        self.folder.edit_workflow(f"    ref: tickets/{TICKET_ID}.md\n", "")
        code, out = self.folder.validate()
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", out)

    def test_malformed_raise_commit_is_reported_once(self):
        # One defect, one FAIL: cross-checking three tickets against an anchor whose
        # own shape already FAILed would report the same fact four times.
        self.folder.edit_workflow(f"raise_commit: {RAISE_COMMIT}", "raise_commit: 4f1c0b9")
        code, out = self.folder.validate()
        self.assertEqual(code, 1, out)
        self.assertIn("not a full 40-hex commit SHA", out)
        self.assertNotIn("verified_against", out)

    def test_non_iso_verified_at_fails(self):
        self.folder.edit_workflow('verified_at: "2026-08-02T09:14:03Z"',
                                  'verified_at: "2026-08-02 09:14"')
        self.assertFail("verified_at is not ISO-8601 UTC")

    # --- map ↔ files ↔ briefs, in every direction
    def test_file_with_no_map_entry_fails(self):
        (self.folder.dir / "tickets" / "demo-2.md").write_text(TICKET_BODY)
        self.assertFail("tickets/demo-2.md exists but no tickets[] entry names it")

    def test_map_entry_with_no_file_fails(self):
        self.folder.ticket.unlink()
        self.assertFail(f"tickets[] entry '{TICKET_ID}' has no tickets/{TICKET_ID}.md")

    def test_ticket_embedded_in_no_brief_fails(self):
        self.folder.edit_workflow("<!-- ticket:begin", "<!-- was-a-ticket:begin")
        self.assertFail(f"ticket '{TICKET_ID}' is embedded in no stage brief")

    def test_ticket_block_relocated_outside_stage_brief_fails(self):
        block = embedded_block(TICKET_BODY)
        self.folder.edit_workflow(block, "")
        workflow = self.folder.dir / "workflow.yaml"
        workflow.write_text(workflow.read_text() + "\nevidence: |\n"
                            + embedded_block(TICKET_BODY, indent="  ") + "\n")
        self.assertFail(f"ticket '{TICKET_ID}' block is not inside exactly one stage brief")

    def test_same_ticket_may_appear_once_in_two_stage_briefs(self):
        self.folder.edit_workflow(
            "  - id: freeze-tests\n    depends_on: [write-tests]\n",
            "  - id: freeze-tests\n    brief: |\n"
            + embedded_block(TICKET_BODY)
            + "\n\n      Verify the same ticket against the frozen tests.\n"
            "    depends_on: [write-tests]\n")
        code, out = self.folder.validate()
        self.assertEqual(code, 0, out)
        self.assertIn("PASS —", out)
        self.assertNotIn("FAIL", out)

    def test_unclosed_delimiter_is_a_partial_delimiter(self):
        self.folder.edit_workflow(f"<!-- ticket:end {TICKET_ID} -->", "")
        self.assertFail("a ticket:begin delimiter has no matching ticket:end")

    def test_two_blocks_in_one_stage_have_no_unambiguous_owner(self):
        second = TICKET_BODY.replace("demo module", "second module")
        (self.folder.dir / "tickets" / "demo-2.md").write_text(second)
        self.folder.edit_workflow(
            "\n      Implement per the block above.",
            "\n" + embedded_block(second, tid="demo-2") + "\n\n      Implement both.")
        self.folder.edit_workflow(
            f"  - id: {TICKET_ID}\n",
            f"  - id: demo-2\n    ref: tickets/demo-2.md\n"
            f"    body_sha256: {sha_text(second)}\n    ac_hash: {ac_hash()}\n"
            f"    verified_against: {RAISE_COMMIT}\n"
            f'    verified_at: "2026-08-02T09:14:03Z"\n  - id: {TICKET_ID}\n')
        self.assertFail("embeds 2 ticket blocks")

    def test_block_for_a_ticket_absent_from_the_map_fails(self):
        self.folder.edit_workflow(f"  - id: {TICKET_ID}\n", "  - id: demo-2\n")
        self.assertFail(f"embeds ticket '{TICKET_ID}' which is absent from tickets:")

    # --- the parser trap, and the degradation posture
    def test_parser_trap_sequence_in_a_body_warns_but_passes(self):
        folder = SlicedFolder(body=TICKET_BODY.replace("Write the demo module.",
                                                       "Write the demo module, see #47"))
        self.addCleanup(folder.close)
        code, out = folder.validate()
        self.assertEqual(code, 0, out)
        self.assertIn("embedded ticket body contains ' #'", out)
        self.assertNotIn("FAIL", out)

    def test_sliced_set_without_the_extractor_cannot_be_verified(self):
        # Not-run is not passed: an ac_hash nobody recomputed proves nothing.
        folder = SlicedFolder(anchor=False, with_extractor=False)
        self.addCleanup(folder.close)
        code, out = folder.validate()
        self.assertEqual(code, 1, out)
        self.assertIn("carries a sliced ticket set but requirement_surface.py is not beside this "
                      "script", out)

    def test_monolithic_workflow_triggers_no_fold_check(self):
        folder = RunFolder(valid_anchor())
        self.addCleanup(folder.close)
        code, out = folder.validate()
        self.assertEqual(code, 0, out)
        for absent in ("tickets[", "ticket:begin", "ac_hash"):
            self.assertNotIn(absent, out)


if __name__ == "__main__":
    unittest.main()
