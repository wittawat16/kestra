import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ACTIVE = (
    "kestra-spec", "kestra-build", "kestra-run", "kestra-exam", "givename",
    "meta-designer", "meta-dev", "meta-qa", "meta-test-review", "meta-review",
    "meta-security", "meta-devops", "meta-debug", "meta-spec", "meta-test-writer",
    "meta-orc",
)
RETIRED = ("meta-pm", "meta-ba", "meta-sa", "meta-architect")


class InstallCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args):
        env = {**os.environ, "HOME": str(self.home)}
        return subprocess.run(
            ["bash", "./install.sh", *args], cwd=REPO, env=env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

    def target(self, project=False):
        return (self.project if project else self.home) / ".claude" / "skills"

    def check(self, project=False, *args):
        scope = ["--project", str(self.project)] if project else []
        return self.run_install("--check", *scope, *args)

    def install(self, project=False, link=False):
        args = (["--project", str(self.project)] if project else [])
        if link:
            args.append("--link")
        result = self.run_install(*args)
        self.assertEqual(result.returncode, 0, result.stdout)
        return self.target(project)

    @staticmethod
    def fingerprint(path):
        if not path.exists() and not path.is_symlink():
            return "<absent>"
        digest = hashlib.sha256()
        for item in sorted([path, *path.rglob("*")], key=lambda p: str(p)):
            rel = "." if item == path else str(item.relative_to(path))
            digest.update(rel.encode())
            if item.is_symlink():
                digest.update(b"L" + os.readlink(item).encode())
            elif item.is_file():
                digest.update(b"F" + item.read_bytes())
                digest.update(str(stat.S_IMODE(item.stat().st_mode)).encode())
            elif item.is_dir():
                digest.update(b"D")
        return digest.hexdigest()

    def assert_clean_result(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)
        for name in ACTIVE:
            self.assertIn(name, result.stdout)

    def test_current_copy_and_canonical_link_in_global_and_project_scopes(self):
        for project in (False, True):
            with self.subTest(transport="copy", project=project):
                self.install(project)
                self.assert_clean_result(self.check(project))
            with self.subTest(transport="link", project=project):
                shutil.rmtree(self.target(project), ignore_errors=True)
                self.install(project, link=True)
                self.assert_clean_result(self.check(project))

    def test_aggregate_drift_reports_all_findings(self):
        target = self.install()
        skill_file = target / "kestra-spec" / "SKILL.md"
        skill_file.write_text(skill_file.read_text() + "changed\n")
        shutil.rmtree(target / "kestra-build")
        (target / "extra-skill").mkdir()
        (target / "extra-skill" / "x").write_text("x")
        (target / "meta-pm").mkdir()
        wrong = self.root / "wrong"
        wrong.mkdir()
        shutil.rmtree(target / "kestra-run")
        (target / "kestra-run").symlink_to(wrong)
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        for marker in ("kestra-spec", "kestra-build", "extra-skill", "meta-pm"):
            self.assertIn(marker, result.stdout)
        self.assertRegex(result.stdout, r"(?i)(problem|drift|missing|retired)")

    def test_cache_and_unrelated_skill_are_ignored(self):
        target = self.install()
        cache = target / "kestra-spec" / "__pycache__"
        cache.mkdir()
        (cache / "x.pyc").write_bytes(b"cache")
        (target / "kestra-spec" / "junk.pyc").write_bytes(b"cache")
        (target / "kestra-spec" / ".DS_Store").write_bytes(b"finder")
        (target / "my-personal-skill").mkdir()
        self.assert_clean_result(self.check())

    def test_invalid_combinations_exit_two_and_do_not_mutate(self):
        target = self.install()
        before = (self.fingerprint(target), self.fingerprint(REPO))
        for flag in ("--link", "--force", "--update", "--uninstall"):
            with self.subTest(flag=flag):
                result = self.run_install("--check", flag)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(before, (self.fingerprint(target), self.fingerprint(REPO)))

    def test_no_mutation_and_missing_project_target(self):
        source_before = self.fingerprint(REPO)
        result = self.check(project=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertFalse(self.target(True).exists())
        self.assertEqual(source_before, self.fingerprint(REPO))

    def test_wrong_and_dangling_symlinks_are_drift(self):
        target = self.install(link=True)
        wrong = self.root / "other-checkout"
        wrong.mkdir()
        link = target / "kestra-spec"
        link.unlink()
        link.symlink_to(wrong)
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        link.unlink()
        link.symlink_to(self.root / "missing")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_unreadable_entry_is_drift(self):
        target = self.install()
        unreadable = target / "kestra-spec" / "SKILL.md"
        original = stat.S_IMODE(unreadable.stat().st_mode)
        try:
            unreadable.chmod(0)
            result = self.check()
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("kestra-spec", result.stdout)
        finally:
            unreadable.chmod(original)

    def test_existing_force_link_uninstall_smoke(self):
        self.install()
        forced = self.run_install("--force")
        self.assertEqual(forced.returncode, 0, forced.stdout)
        shutil.rmtree(self.target())
        self.install(link=True)
        removed = self.run_install("--uninstall")
        self.assertEqual(removed.returncode, 0, removed.stdout)
        self.assertFalse(any((self.target() / name).exists() or (self.target() / name).is_symlink()
                             for name in ACTIVE))

    def test_bilingual_docs_state_same_check_contract(self):
        english = (REPO / "README.md").read_text()
        thai = (REPO / "README-th.md").read_text()
        for text in (english, thai):
            self.assertIn("--check", text)
            self.assertIn("--project", text)
            self.assertIn("exit", text.lower())


if __name__ == "__main__":
    unittest.main()
