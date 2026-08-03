#!/usr/bin/env python3
"""Deterministic tests for the exam harness and its fail-closed provenance helpers.

These stay in the skill; they are never emitted into an exam dir (the same
convention test_requirement_surface.py follows).

Why origin_key is pinned here rather than in a fifth file: its failure mode is
silent cross-wiring — two repos keyed to one exam dir, so a gate certifies one
feature's delivery against another's evidence and nothing looks wrong. That
deserves a regression test, and the skill keeps one test file.

Run:  python3 test_exam_harness.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import exam_harness as H          # noqa: E402
import exam_anchor as A           # noqa: E402
import exam_delta as D            # noqa: E402
import exam_paths as P            # noqa: E402

PY = sys.executable

# A CLI seam that exits with the code it is told and echoes a marker.
TARGET = (
    "import sys\n"
    "print('total: ' + sys.argv[2] if len(sys.argv) > 2 else 'total: 0')\n"
    "sys.exit(int(sys.argv[1]))\n"
)

EXAM_TEMPLATE = '''\
from exam_harness import check, expect, expect_contains, Cli, repo_root, run_main

EXAM = "fixture-feature"
ANCHOR = {{"raise_commit": "a" * 40, "surface_hash": "b" * 64,
          "extractor_version": 1}}
REPO = repo_root(default={repo!r})
SEAM = Cli(argv_prefix=[{py!r}, "target.py"], cwd=REPO)


@check(id="C-0", ac="—", cls="must-hold", provenance="—")
def c0(seam):
    """harness smoke — the declared seam answers"""
    r = seam.call([{smoke_exit!r}])
    expect(r.exit_code, 0, "smoke exit")


@check(id="C-1", ac="AC-1", cls="must-flip", provenance="US-1")
def c1(seam):
    """the seam answers 0 and prints a total"""
    r = seam.call(["0", "40"])
    expect(r.exit_code, 0, "exit")
    expect_contains(r.stdout, "total: 40", "total line")


@check(id="C-2", ac="AC-2", cls="must-flip", provenance="inferred")
def c2(seam):
    """a behavioral red: the seam answers, the answer is wrong"""
    r = seam.call(["1"])
    expect(r.exit_code, 0, "exit", "target --broken")


@check(id="C-3", ac="AC-3", cls="unexaminable", provenance="ID§2",
       unexaminable="fires only on disk-full; the CLI seam cannot induce it")
def c3(seam):
    """an unexaminable AC is a row, never an omission"""


run_main(SEAM)
'''


def _fixture(tmp, smoke_exit="0"):
    tmp = Path(tmp)
    (tmp / "target.py").write_text(TARGET)
    (tmp / "exam_harness.py").write_text((HERE / "exam_harness.py").read_text())
    (tmp / "exam.py").write_text(EXAM_TEMPLATE.format(
        repo=str(tmp), py=PY, smoke_exit=smoke_exit))
    # the quoted External Interface block --audit-seam compares against
    (tmp / "manifest.md").write_text(
        "# Exam manifest — fixture-feature\n\n## Read rule\n\n```\n"
        f"* **Primary (new):** `{PY} target.py` — args -> exit code\n"
        "```\n\n## Checks\n")
    return tmp


def _run(tmp, *args, opt=False):
    argv = [PY, "-B"] + (["-O"] if opt else []) + ["exam.py"] + list(args)
    p = subprocess.run(argv, cwd=str(tmp), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True)
    return p.returncode, p.stdout, p.stderr


def _chk(id, cls, fn, ac="AC-x", provenance="US-1", unexaminable=None):
    return H.Check(id, ac, cls, provenance, unexaminable, fn)


class TestDiscriminator(unittest.TestCase):
    """behavioral iff CheckFailure AND the seam was reached — mechanical."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        Path(self.tmp, "target.py").write_text(TARGET)
        self.seam = H.Cli([PY, "target.py"], cwd=self.tmp)

    def test_pass(self):
        row = H.run_check(self.seam, _chk("C-1", "must-flip",
                                          lambda s: H.expect(
                                              s.call(["0"]).exit_code, 0, "exit")))
        self.assertEqual(row["result"], "pass")
        self.assertIsNone(row["red_kind"])
        self.assertTrue(row["seam_reached"])

    def test_behavioral_red_reaches_the_seam(self):
        row = H.run_check(self.seam, _chk("C-1", "must-flip",
                                          lambda s: H.expect(
                                              s.call(["3"]).exit_code, 0, "exit")))
        self.assertEqual((row["result"], row["red_kind"]),
                         ("fail", "behavioral"))
        self.assertTrue(row["signature"].startswith("CheckFailure: exit 3 != 0"))

    def test_seam_unavailable_is_infrastructure(self):
        dead = H.Cli(["/nonexistent/kestra-exam-binary"], cwd=self.tmp)
        row = H.run_check(dead, _chk("C-1", "must-flip",
                                     lambda s: s.call([])))
        self.assertEqual((row["result"], row["red_kind"]),
                         ("fail", "infrastructure"))
        self.assertFalse(row["seam_reached"])
        self.assertIn("SeamUnavailable", row["signature"])

    def test_checkfailure_before_any_call_is_infrastructure(self):
        """An expectation about a call that never happened proves nothing."""
        def never_calls(seam):
            H.expect(1, 0, "an expectation with no seam call behind it")
        row = H.run_check(self.seam, _chk("C-1", "must-flip", never_calls))
        self.assertEqual(row["red_kind"], "infrastructure")

    def test_unexpected_exception_is_infrastructure(self):
        def boom(seam):
            seam.call(["0"])
            raise KeyError("a bug in the check itself")
        row = H.run_check(self.seam, _chk("C-1", "must-flip", boom))
        self.assertEqual((row["result"], row["red_kind"]),
                         ("fail", "infrastructure"))
        self.assertTrue(row["signature"].startswith("KeyError:"))

    def test_unexaminable_runs_nothing(self):
        def must_not_run(seam):
            raise AssertionError("an unexaminable check must never be invoked")
        row = H.run_check(self.seam, _chk("C-9", "unexaminable", must_not_run,
                                          unexaminable="cannot be induced"))
        self.assertEqual(row["result"], "unexaminable")
        self.assertIsNone(row["red_kind"])


class TestSummary(unittest.TestCase):
    """The exit ladder: 2 (harness) dominates 1 (behavioral) dominates 0."""

    def _rows(self, *triples):
        return [{"id": i, "class": c, "result": r,
                 "red_kind": k, "signature": ""} for i, c, r, k in triples]

    def test_all_pass(self):
        s = H.summarize(self._rows(("C-0", "must-hold", "pass", None),
                                   ("C-1", "must-flip", "pass", None)))
        self.assertEqual(s["exit_code"], 0)
        self.assertEqual(s["unproven"], 1)  # born green at red-proof time

    def test_behavioral_fail_is_one(self):
        s = H.summarize(self._rows(("C-0", "must-hold", "pass", None),
                                   ("C-1", "must-flip", "fail", "behavioral")))
        self.assertEqual(s["exit_code"], 1)
        self.assertEqual(s["unproven"], 0)

    def test_infrastructure_red_is_two(self):
        s = H.summarize(self._rows(
            ("C-0", "must-hold", "pass", None),
            ("C-1", "must-flip", "fail", "infrastructure")))
        self.assertEqual(s["exit_code"], 2)
        self.assertEqual(s["unproven"], 1)

    def test_red_smoke_is_two(self):
        s = H.summarize(self._rows(("C-0", "must-hold", "fail", "behavioral"),
                                   ("C-1", "must-flip", "blocked", None)))
        self.assertEqual(s["exit_code"], 2)
        self.assertEqual(s["unproven"], 1)


class TestBlocking(unittest.TestCase):
    def test_red_c0_blocks_every_other_check(self):
        tmp = tempfile.mkdtemp()
        Path(tmp, "target.py").write_text(TARGET)
        seam = H.Cli([PY, "target.py"], cwd=tmp)
        checks = [_chk("C-0", "must-hold",
                       lambda s: H.expect(s.call(["7"]).exit_code, 0, "smoke"),
                       ac="—"),
                  _chk("C-1", "must-flip",
                       lambda s: H.expect(s.call(["0"]).exit_code, 0, "exit"))]
        rows = H._execute(seam, checks, [])
        self.assertEqual([r["result"] for r in rows], ["fail", "blocked"])


class TestCli(unittest.TestCase):
    """The end-to-end contract, driven the way a gate drives it."""

    @classmethod
    def setUpClass(cls):
        cls.dir = _fixture(tempfile.mkdtemp())
        cls.broken = _fixture(tempfile.mkdtemp(), smoke_exit="9")

    def test_human_run_exits_one_on_a_behavioral_red(self):
        code, out, _ = _run(self.dir)
        self.assertEqual(code, 1, out)
        self.assertTrue(out.splitlines()[2].startswith("C-0 "), out)
        self.assertIn("unexaminable 1", out)
        self.assertFalse((self.dir / "__pycache__").exists())

    def test_json_shape(self):
        code, out, _ = _run(self.dir, "--json")
        self.assertEqual(code, 1)
        d = json.loads(out)
        self.assertEqual(set(d) >= {"exam", "anchor", "seam", "started_at",
                                    "duration_s", "smoke", "checks",
                                    "summary"}, True)
        self.assertEqual(d["seam"], {"kind": "cli",
                                     "target": f"{PY} target.py"})
        self.assertEqual(d["smoke"], {"id": "C-0", "result": "pass"})
        for row in d["checks"]:
            self.assertIn(row["result"], H.RESULTS)
            self.assertIn(row["red_kind"], H.RED_KINDS + (None,))
            self.assertIn(row["class"], H.CHECK_CLASSES)
        c2 = next(r for r in d["checks"] if r["id"] == "C-2")
        self.assertEqual(c2["red_kind"], "behavioral")
        self.assertEqual(c2["signature"],
                         "CheckFailure: exit 1 != 0 @ target --broken")
        self.assertEqual(d["summary"]["exit_code"], 1)
        self.assertEqual(d["summary"]["unexaminable"], 1)
        self.assertEqual(d["summary"]["unproven"], 1)  # C-1 born green

    def test_only_always_runs_c0(self):
        code, out, _ = _run(self.dir, "--only", "C-1", "--json")
        d = json.loads(out)
        self.assertEqual([r["id"] for r in d["checks"]], ["C-0", "C-1"])
        self.assertEqual(code, 0)

    def test_only_rejects_an_undeclared_check(self):
        code, _, err = _run(self.dir, "--only", "C-99")
        self.assertEqual(code, 3)
        self.assertIn("does not declare", err)

    def test_red_c0_exits_two_and_blocks(self):
        code, out, _ = _run(self.broken, "--json")
        self.assertEqual(code, 2, out)
        d = json.loads(out)
        self.assertEqual(d["smoke"]["result"], "fail")
        self.assertEqual({r["result"] for r in d["checks"] if r["id"] != "C-0"},
                         {"blocked", "unexaminable"})

    def test_list_touches_no_seam(self):
        broken = _fixture(tempfile.mkdtemp())
        os.remove(broken / "target.py")
        code, out, err = _run(broken, "--list")
        self.assertEqual(code, 0, err)
        self.assertIn("C-0", out)
        self.assertIn("unexaminable", out)

    def test_audit_seam_matches_the_manifest_quote(self):
        code, out, err = _run(self.dir, "--audit-seam")
        self.assertEqual(code, 0, err)
        self.assertIn("appears verbatim", out)

    def test_audit_seam_fails_on_a_stale_quote(self):
        tmp = _fixture(tempfile.mkdtemp())
        (tmp / "manifest.md").write_text(
            "## Read rule\n\n```\n* **Primary:** `python3 other.py`\n```\n")
        code, _, err = _run(tmp, "--audit-seam")
        self.assertEqual(code, 1)
        self.assertIn("did not declare", err)

    def test_repo_flag_redirects_the_seam(self):
        clone = _fixture(tempfile.mkdtemp())
        code, out, _ = _run(self.dir, "--repo", str(clone), "--json")
        self.assertEqual(json.loads(out)["seam"]["target"], f"{PY} target.py")
        self.assertEqual(code, 1)

    def test_optimize_flag_is_refused(self):
        code, _, err = _run(self.dir, opt=True)
        self.assertEqual(code, 3)
        self.assertIn("assertions disabled", err)

    def test_unknown_argument_is_usage(self):
        code, _, err = _run(self.dir, "--verbose")
        self.assertEqual(code, 3)
        self.assertIn("unknown argument", err)


class TestMalformedExam(unittest.TestCase):
    def _exam(self, body):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "target.py").write_text(TARGET)
        (tmp / "exam_harness.py").write_text(
            (HERE / "exam_harness.py").read_text())
        (tmp / "exam.py").write_text(body)
        return _run(tmp)

    def test_unknown_seam_kind_is_a_hard_stop(self):
        code, _, err = self._exam(
            "from exam_harness import check, run_main\n"
            "EXAM = 'x'\nANCHOR = {}\n"
            "class Ftp:\n    kind = 'ftp'\n    def close(self): pass\n"
            "@check(id='C-0', ac='-', cls='must-hold', provenance='-')\n"
            "def c0(seam):\n    'smoke'\n"
            "run_main(Ftp())\n")
        self.assertEqual(code, 3)
        self.assertIn("closes the seam set", err)

    def test_missing_anchor_is_a_hard_stop(self):
        code, _, err = self._exam(
            "from exam_harness import check, Cli, run_main\n"
            "@check(id='C-0', ac='-', cls='must-hold', provenance='-')\n"
            "def c0(seam):\n    'smoke'\n"
            "run_main(Cli(['true'], cwd='.'))\n")
        self.assertEqual(code, 3)
        self.assertIn("unanchored exam", err)

    def test_missing_c0_is_a_hard_stop(self):
        code, _, err = self._exam(
            "from exam_harness import check, Cli, run_main\n"
            "EXAM = 'x'\nANCHOR = {'raise_commit': 'a'}\n"
            "@check(id='C-1', ac='AC-1', cls='must-flip', provenance='-')\n"
            "def c1(seam):\n    'no smoke'\n"
            "run_main(Cli(['true'], cwd='.'))\n")
        self.assertEqual(code, 3)
        self.assertIn("declares no C-0", err)

    def test_unexaminable_without_a_reason_is_a_hard_stop(self):
        code, _, err = self._exam(
            "from exam_harness import check, Cli, run_main\n"
            "EXAM = 'x'\nANCHOR = {'raise_commit': 'a'}\n"
            "@check(id='C-0', ac='-', cls='must-hold', provenance='-')\n"
            "def c0(seam):\n    'smoke'\n"
            "@check(id='C-1', ac='AC-1', cls='unexaminable', provenance='-')\n"
            "def c1(seam):\n    'no reason given'\n"
            "run_main(Cli(['true'], cwd='.'))\n")
        self.assertEqual(code, 3)
        self.assertIn("never an omission", err)


class TestOriginKey(unittest.TestCase):
    """The six URL forms, plus the nested-group collision full-path join fixes."""

    def test_forms_agree(self):
        for url, want in [
            ("https://github.com/arkaphat/kestra.git",
             "github.com__arkaphat__kestra"),
            ("ssh://git@github.com/arkaphat/kestra.git",
             "github.com__arkaphat__kestra"),
            ("git@github.com:arkaphat/kestra.git",
             "github.com__arkaphat__kestra"),
            ("https://github.com:443/Arkaphat/Kestra",
             "github.com__arkaphat__kestra"),
            ("https://github.com/arkaphat/kestra/",
             "github.com__arkaphat__kestra"),
            ("https://github.com/bob/kestra", "github.com__bob__kestra"),
        ]:
            self.assertEqual(P.origin_key(url), want, url)

    def test_nested_groups_do_not_collide(self):
        a = P.origin_key("https://gitlab.example.co.th/team/sub/kestra.git")
        b = P.origin_key("https://gitlab.example.co.th/other/sub/kestra.git")
        self.assertNotEqual(a, b)
        self.assertEqual(a, "gitlab.example.co.th__team__sub__kestra")

    def test_fewer_than_two_segments_is_a_hard_stop(self):
        with self.assertRaises(P.PathError) as cm:
            P.origin_key("https://github.com/kestra")
        self.assertIn("fewer than two path segments", str(cm.exception))

    def test_slug_must_be_conventional(self):
        self.assertEqual(P.feature_slug("/x/workflows/runs/order-refund"),
                         "order-refund")
        with self.assertRaises(P.PathError):
            P.feature_slug("/x/workflows/runs/Order_Refund")


class TestPointerTransport(unittest.TestCase):
    def test_github_lookup_failure_is_a_hard_stop(self):
        responses = [SimpleNamespace(returncode=0),
                     SimpleNamespace(returncode=1, stdout="",
                                     stderr="lookup failed")]
        with patch.object(P.subprocess, "run", side_effect=responses):
            with self.assertRaises(P.PathError) as cm:
                P.transport("github.com__owner__repo")
        self.assertIn("pointer transport", str(cm.exception))

    def test_explicit_issues_disabled_uses_local_transport(self):
        responses = [SimpleNamespace(returncode=0),
                     SimpleNamespace(returncode=0, stdout="false\n", stderr="")]
        with patch.object(P.subprocess, "run", side_effect=responses):
            self.assertEqual(P.transport("github.com__owner__repo"),
                             ("local", "owner/repo"))


class TestCreatableAnchor(unittest.TestCase):
    def _paths(self):
        root = Path(tempfile.mkdtemp())
        run_dir, exam_dir = root / "feature", root / "exam"
        run_dir.mkdir()
        exam_dir.mkdir()
        (exam_dir / "manifest.md").write_text("present")
        return root, run_dir, exam_dir

    def test_same_surface_with_moved_raise_or_version_is_refused(self):
        root, run_dir, exam_dir = self._paths()
        recorded = {"raise_commit": "1" * 40,
                    "surface_hash": "a" * 64,
                    "extractor_version": "1"}
        with patch.object(A, "_git", return_value=(0, str(root), "")), \
                patch.object(A, "read_manifest_anchor", return_value=recorded), \
                patch.object(A, "compute_now", return_value=("a" * 64, 2)), \
                patch.object(A, "discover_raise", return_value="2" * 40):
            with self.assertRaises(A.Refused):
                A.assert_creatable(run_dir, exam_dir)

    def test_exact_anchor_triple_is_idempotent(self):
        root, run_dir, exam_dir = self._paths()
        recorded = {"raise_commit": "1" * 40,
                    "surface_hash": "a" * 64,
                    "extractor_version": "1"}
        with patch.object(A, "_git", return_value=(0, str(root), "")), \
                patch.object(A, "read_manifest_anchor", return_value=recorded), \
                patch.object(A, "compute_now", return_value=("a" * 64, 1)), \
                patch.object(A, "discover_raise", return_value="1" * 40):
            code, message = A.assert_creatable(run_dir, exam_dir)
        self.assertEqual(code, 0)
        self.assertIn("idempotent", message)


class TestExamCommitPin(unittest.TestCase):
    SHA = "3" * 40

    def check(self, status="", ignored=""):
        with patch.object(A, "_git", side_effect=[
                (0, self.SHA, ""), (0, status, ""), (0, ignored, "")]):
            A.check_exam_commit("/tmp/exam", {"exam_commit": self.SHA})

    def test_clean_pinned_commit_passes(self):
        self.check()

    def test_only_unstaged_manifest_verdict_append_may_be_dirty(self):
        self.check(" M manifest.md")

    def test_helper_tamper_is_refused(self):
        with self.assertRaises(A.Refused) as cm:
            self.check(" M exam_harness.py")
        self.assertIn("exam worktree has unpinned changes", str(cm.exception))

    def test_ignored_untracked_module_is_refused(self):
        with self.assertRaises(A.Refused) as cm:
            self.check(ignored="subprocess.py")
        self.assertIn("ignored unpinned paths", str(cm.exception))

    def test_missing_exam_commit_is_refused(self):
        with self.assertRaises(A.Refused):
            A.check_exam_commit("/tmp/exam", {})

    def test_real_git_allows_only_an_unstaged_manifest_append(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        (root / "manifest.md").write_text("# Manifest\n")
        (root / "exam.py").write_text("print('exam')\n")
        subprocess.run(["git", "-C", str(root), "add", "manifest.md", "exam.py"], check=True)
        subprocess.run([
            "git", "-C", str(root), "-c", "user.name=Kestra Test",
            "-c", "user.email=kestra@example.invalid", "commit", "-qm", "fixture"
        ], check=True)
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            text=True, capture_output=True).stdout.strip()
        (root / "manifest.md").write_text("# Manifest\n\nPASS\n")
        A.check_exam_commit(root, {"exam_commit": head})

    def test_real_git_refuses_an_ignored_untracked_module(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        (root / "manifest.md").write_text("# Manifest\n")
        subprocess.run(["git", "-C", str(root), "add", "manifest.md"], check=True)
        subprocess.run([
            "git", "-C", str(root), "-c", "user.name=Kestra Test",
            "-c", "user.email=kestra@example.invalid", "commit", "-qm", "fixture"
        ], check=True)
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            text=True, capture_output=True).stdout.strip()
        (root / ".git" / "info" / "exclude").write_text("subprocess.py\n")
        (root / "subprocess.py").write_text("# ignored import shadow\n")
        with self.assertRaises(A.Refused):
            A.check_exam_commit(root, {"exam_commit": head})


class TestDocumentedRecipes(unittest.TestCase):
    def test_s1_never_uses_a_scalar_pathspec(self):
        gate = (HERE.parent / "references" / "gate-procedure.md").read_text()
        self.assertNotIn("$EX", gate)

    def test_pointer_discovery_is_targeted_and_paginated(self):
        for path in (HERE.parent / "SKILL.md",
                     HERE.parent / "references" / "gate-procedure.md"):
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertIn("POINTER_PAGES=$(gh api --paginate --slurp", text)
                self.assertIn("repos/<chain-repo>/issues?state=all&per_page=100", text)
                self.assertIn("pointer-ticket search did not run", text)
                self.assertIn("$POINTER_PAGES\" | jq '[.[][]", text)
                self.assertNotIn("search/issues", text)
                self.assertNotIn("--label kestra-exam --state all --limit 100", text)

    def test_creation_recipe_propagates_copy_and_init_failure(self):
        skill = (HERE.parent / "SKILL.md").read_text()
        self.assertIn("cp $S/exam_harness.py $S/exam_anchor.py <exam-dir>/ &&", skill)
        self.assertIn("cp <extractor-dir>/requirement_surface.py <exam-dir>/ &&", skill)
        self.assertIn("FAIL: exam creation did not complete", skill)

    def test_all_regeneration_recipes_disable_bytecode(self):
        texts = {
            "skill": (HERE.parent / "SKILL.md").read_text(),
            "regeneration": (HERE.parent / "references" / "regeneration.md").read_text(),
            "delta": (HERE / "exam_delta.py").read_text(),
            "anchor": (HERE / "exam_anchor.py").read_text(),
        }
        for name, text in texts.items():
            with self.subTest(name=name):
                self.assertNotIn("python3 exam_delta.py", text)
                self.assertNotIn("python3 <skill>/scripts/exam_delta.py", text)
        self.assertNotIn("python3 exam.py --only", texts["regeneration"])


class TestDeltaAnchorMovement(unittest.TestCase):
    def plan(self, now_version=1, new_raise="2" * 40,
             now_sections=None, old_sections=None, now_acs=None, old_acs=None,
             amap=None):
        root = Path(tempfile.mkdtemp())
        run_dir, exam_dir = root / "run", root / "exam"
        run_dir.mkdir()
        exam_dir.mkdir()
        (exam_dir / "manifest.md").write_text("present")
        recorded = {"raise_commit": "1" * 40,
                    "surface_hash": "a" * 64,
                    "extractor_version": "1", "generation": "1"}
        now_sections = now_sections or {"Functional Requirements": "same"}
        old_sections = old_sections or {"Functional Requirements": "same"}
        now_acs = now_acs or {"AC-1": "same"}
        old_acs = old_acs or {"AC-1": "same"}
        amap = amap or {"AC-1": ["C-1"]}
        patches = (
            patch.object(D, "_git", return_value=(0, str(root), "")),
            patch.object(D, "current_fingerprints",
                         return_value=(now_sections, now_acs)),
            patch.object(D, "recorded_fingerprints",
                         return_value=(old_sections, old_acs)),
            patch.object(D, "ac_to_checks", return_value=amap),
            patch.object(D, "read_manifest_anchor", return_value=recorded),
            patch.object(D, "compute_now", return_value=("a" * 64, now_version)),
            patch.object(D, "discover_raise",
                         side_effect=new_raise if isinstance(new_raise, Exception) else None,
                         return_value=None if isinstance(new_raise, Exception) else new_raise),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            return D.plan(run_dir, exam_dir)

    def test_raise_only_movement_reanchors(self):
        self.assertIn("scope: re-anchor", self.plan())

    def test_extractor_version_movement_forces_full_rederive(self):
        self.assertIn("scope: full", self.plan(now_version=2, new_raise="1" * 40))

    def test_full_seam_regeneration_deletes_removed_ac_checks(self):
        out = self.plan(
            new_raise="1" * 40,
            old_sections={"External Interface": "old"},
            now_sections={"External Interface": "new"},
            old_acs={"AC-1": "same", "AC-2": "gone"},
            now_acs={"AC-1": "same"},
            amap={"AC-1": ["C-1"], "AC-2": ["C-2"]})
        self.assertIn("scope: full", out)
        self.assertIn("regenerate: C-1", out)
        self.assertIn("delete:     C-2", out)
        self.assertNotIn("regenerate: C-1 C-2", out)

    def test_full_version_regeneration_deletes_removed_ac_checks(self):
        out = self.plan(
            now_version=2, new_raise="1" * 40,
            old_acs={"AC-1": "same", "AC-2": "gone"},
            now_acs={"AC-1": "same"},
            amap={"AC-1": ["C-1"], "AC-2": ["C-2"]})
        self.assertIn("scope: full", out)
        self.assertIn("regenerate: C-1", out)
        self.assertIn("delete:     C-2", out)

    def test_unresolved_raise_is_a_hard_stop(self):
        with self.assertRaises(D.Refused):
            self.plan(new_raise=D.Refused("raise is ambiguous"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
