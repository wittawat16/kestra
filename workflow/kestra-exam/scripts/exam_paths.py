#!/usr/bin/env python3
"""Where an exam lives, and which pointer transport records it — one owner.

WHY THIS FILE EXISTS
    Deriving the exam directory is repeated deterministic work whose hand-redo
    has a silent failure mode: two clones, forks, or same-named repos on
    different hosts cross-wiring onto one exam dir, so a gate certifies feature
    A's delivery against feature B's evidence and nothing looks wrong. The key
    comes from the `origin` URL because that is the one identifier a clone
    cannot accidentally share, and there is deliberately **no fallback naming**
    — a repo with no origin gets a hard stop, not a basename.

    Layout:
        ~/.kestra/exams/<origin-key>/<feature-slug>/     the exam (its own git repo)
        ~/.kestra/exams/<origin-key>/<feature-slug>.pointer      local transport
        ~/.kestra/exams/<origin-key>/<feature-slug>.pointer.log   its edit log
    The pointer is a *sibling* of the exam dir, never inside it, so the pointer
    is not one of the artifacts whose hashes it records.

ORIGIN KEY — full path join, a surfaced correction to `<host>__<owner>__<repo>`
    Last-two-segments keying collides on nested groups: `gitlab.x/team/sub/repo`
    and `gitlab.x/other/sub/repo` both key to `gitlab.x__sub__repo`, which is
    exactly the cross-wiring the key exists to prevent. Every path segment is
    joined instead. For any two-segment host (GitHub, always) the result is
    byte-identical to the last-two rule, so nothing written against that rule
    changes.

TRANSPORT — chosen mechanically, never downgraded silently
    github.com + `gh` authenticated + issues enabled  ⇒ GitHub pointer ticket.
    Any other host, or issues disabled                ⇒ local pointer file.
    github.com but `gh` missing or unauthenticated    ⇒ HARD STOP. A downgrade
    that happens by itself is the failure class this design exists to kill;
    `--local-pointer` makes the same choice honest.

Usage:
    python3 exam_paths.py <repo-root> <run-dir> [--local-pointer] [--no-transport]

Exit 0 with `key: value` lines on stdout · 1 on a hard stop · 3 on usage error.
"""
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SCP_RE = re.compile(r"^(?:[^@/]+@)?([^/:]+):(.+)$")
_KEY_SAFE = re.compile(r"[^a-z0-9._-]")

NO_ORIGIN = """FAIL: no `origin` remote on {repo} — kestra-exam refuses to create an exam.
The exam directory is keyed by the origin URL so two clones or forks sharing a
directory basename cannot cross-wire onto one exam dir. There is no fallback
naming: add an origin remote (`git remote add origin <url>`), or run without an
exam — the exam is opt-in on kestra-build's full mode."""

NO_AUTH = """FAIL: origin is on github.com but `gh` is not authenticated — refusing to
downgrade the pointer to a local file silently. Run `gh auth login`, or pass
`--local-pointer` to choose the weaker transport deliberately (its named
residual is in references/gate-procedure.md)."""


class PathError(Exception):
    """A hard stop: nothing is created, exit 1."""


def _git(args, cwd):
    try:
        p = subprocess.run(["git", "-C", str(cwd)] + args,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
    except FileNotFoundError:
        raise PathError("FAIL: `git` not found on PATH") from None
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def origin_url(repo_root):
    """The origin URL, or a hard stop. Non-zero exit and empty output are the
    same answer: there is no origin."""
    code, out, _ = _git(["remote", "get-url", "origin"], repo_root)
    if code != 0 or not out:
        raise PathError(NO_ORIGIN.format(repo=repo_root))
    return out


def origin_key(url, repo_root="<repo>"):
    """`<host>__<seg>__<seg>…`, lowercased and sanitized. Raises PathError when
    the URL parses but cannot be keyed (fewer than two path segments) — the same
    stop as no origin at all, with the cause appended."""
    u = url.strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    u = u.rstrip("/")
    m = _SCP_RE.match(u)
    if m and "://" not in u:
        host, path = m.group(1), m.group(2)
    else:
        parts = urllib.parse.urlsplit(u)
        host, path = parts.hostname or "", parts.path
    host, path = host.lower(), path.lower()
    segments = [s for s in path.split("/") if s]
    if not host or len(segments) < 2:
        raise PathError(
            NO_ORIGIN.format(repo=repo_root)
            + f"\n  — the origin URL yields fewer than two path segments ({url})")
    return _KEY_SAFE.sub("-", host + "__" + "__".join(segments))


def feature_slug(run_dir):
    """The `<feature-id>` kestra-spec already used for the run folder — read
    from the path passed in, never invented."""
    slug = Path(str(run_dir).rstrip("/")).name
    if not SLUG_RE.match(slug):
        raise PathError(
            f"FAIL: run folder basename {slug!r} is not a usable feature slug "
            r"(needs ^[a-z0-9][a-z0-9-]{0,63}$) — rename the run folder "
            f"({run_dir}); kestra-exam never invents a slug.")
    return slug


def exams_root():
    """`~/.kestra/exams` unless KESTRA_EXAMS_ROOT overrides it. The override
    exists for fixtures and evals; it is echoed on every run so a redirected
    root can never be mistaken for the real one."""
    env = os.environ.get("KESTRA_EXAMS_ROOT")
    return Path(env).expanduser() if env else Path.home() / ".kestra" / "exams"


def assert_no_remote(exam_dir):
    """An exam repo has no remote, ever — a remote republishes the evidence."""
    if not (Path(exam_dir) / ".git").exists():
        return
    code, out, _ = _git(["remote"], exam_dir)
    if code == 0 and out:
        raise PathError(
            f"FAIL: the exam repo {exam_dir} has remotes ({out.split()}) — an "
            "exam is local evidence and is never pushed. Remove them "
            "(`git -C <exam-dir> remote remove <name>`) before continuing.")


def transport(key, force_local=False):
    """"github" or "local". Raises PathError rather than downgrading silently."""
    host = key.split("__")[0]
    segments = key.split("__")[1:]
    if force_local or host != "github.com":
        return "local", None
    chain_repo = "/".join(segments[-2:])
    try:
        auth = subprocess.run(["gh", "auth", "status"],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise PathError(NO_AUTH.replace("is not authenticated",
                                        "is not installed")) from None
    if auth.returncode != 0:
        raise PathError(NO_AUTH)
    view = subprocess.run(
        ["gh", "repo", "view", chain_repo, "--json", "hasIssuesEnabled",
         "--jq", ".hasIssuesEnabled"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if view.returncode != 0:
        raise PathError(
            f"FAIL: cannot determine the pointer transport for {chain_repo}: "
            f"`gh repo view` exited {view.returncode}. Refusing to downgrade to "
            "a local pointer silently; retry the lookup or pass "
            "`--local-pointer` deliberately.")
    issues_enabled = view.stdout.strip()
    if issues_enabled == "true":
        return "github", chain_repo
    if issues_enabled == "false":
        return "local", chain_repo
    raise PathError(
        f"FAIL: cannot determine the pointer transport for {chain_repo}: "
        f"`gh repo view` returned {issues_enabled!r}, not true or false. "
        "Refusing to downgrade to a local pointer silently; retry the lookup "
        "or pass `--local-pointer` deliberately.")


def derive(repo_root, run_dir, force_local=False, with_transport=True):
    url = origin_url(repo_root)
    key = origin_key(url, repo_root)
    slug = feature_slug(run_dir)
    root = exams_root()
    exam_dir = root / key / slug
    assert_no_remote(exam_dir)
    out = {
        "origin_url": url,
        "origin_key": key,
        "feature_slug": slug,
        "exams_root": str(root),
        "exams_root_overridden": "yes" if os.environ.get(
            "KESTRA_EXAMS_ROOT") else "no",
        "exam_dir": str(exam_dir),
        "pointer_file": str(root / key / (slug + ".pointer")),
        "pointer_log": str(root / key / (slug + ".pointer.log")),
        "exam_dir_exists": "yes" if exam_dir.is_dir() else "no",
    }
    if with_transport:
        kind, chain_repo = transport(key, force_local)
        out["transport"] = kind
        out["chain_repo"] = chain_repo or "-"
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) != 2 or flags - {"--local-pointer", "--no-transport"}:
        print(__doc__.rsplit("Usage:", 1)[-1].strip(), file=sys.stderr)
        sys.exit(3)
    try:
        fields = derive(args[0], args[1],
                        force_local="--local-pointer" in flags,
                        with_transport="--no-transport" not in flags)
    except PathError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    for k, v in fields.items():
        print(f"{k}: {v}")
    sys.exit(0)


if __name__ == "__main__":
    main()
