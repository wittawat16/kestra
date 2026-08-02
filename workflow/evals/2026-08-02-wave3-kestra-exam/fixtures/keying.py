#!/usr/bin/env python3
"""Re-measure exam_paths.origin_key against the URL forms the design record
claims, plus the nested-group collision that motivated full-path joining.

    python3 keying.py     # exit 0 if every expectation holds, 1 otherwise
"""
import os
import sys
from pathlib import Path

SKILL_SCRIPTS = (Path(__file__).resolve().parents[3] / "kestra-exam" / "scripts")
sys.path.insert(0, str(SKILL_SCRIPTS))
import exam_paths  # noqa: E402

EXPECTED = [
    ("https://github.com/arkaphat/kestra.git", "github.com__arkaphat__kestra"),
    ("ssh://git@github.com/arkaphat/kestra.git", "github.com__arkaphat__kestra"),
    ("git@github.com:arkaphat/kestra.git", "github.com__arkaphat__kestra"),
    ("https://github.com:443/Arkaphat/Kestra", "github.com__arkaphat__kestra"),
    ("https://github.com/bob/kestra", "github.com__bob__kestra"),
    ("https://github.com/arkaphat/kestra/", "github.com__arkaphat__kestra"),
    ("https://git.example.test/kx-fixture/tally.git",
     "git.example.test__kx-fixture__tally"),
    # the surfaced correction to <host>__<owner>__<repo>: last-two-segments
    # keying collides on nested groups, full-path joining does not
    ("https://gitlab.example.co.th/team/sub/kestra.git",
     "gitlab.example.co.th__team__sub__kestra"),
    ("https://gitlab.example.co.th/other/sub/kestra.git",
     "gitlab.example.co.th__other__sub__kestra"),
]

STOPS = [
    "file:///tmp/kx36/origin.git",     # no host at all
    "/tmp/kx36/origin.git",            # bare path
    "https://github.com/kestra",       # one path segment
    "https://github.com/",             # none
]


def main():
    bad = 0
    for url, want in EXPECTED:
        got = exam_paths.origin_key(url)
        ok = "ok  " if got == want else "WRONG"
        if got != want:
            bad += 1
        print(f"{ok} {url:<55} -> {got}")
    print()
    last_two = {}
    for url, key in EXPECTED[-2:]:
        segs = key.split("__")
        last_two.setdefault(f"{segs[0]}__{segs[-2]}__{segs[-1]}", []).append(url)
    for key, urls in last_two.items():
        print(f"last-two-segments key {key!r} would be shared by {len(urls)} repos:")
        for u in urls:
            print(f"    {u}")
    print(f"full-path keys are distinct: "
          f"{len({k for _, k in EXPECTED[-2:]}) == 2}")
    print()
    for url in STOPS:
        try:
            key = exam_paths.origin_key(url, "<repo>")
            print(f"WRONG {url} -> {key} (expected a hard stop)")
            bad += 1
        except exam_paths.PathError as e:
            print(f"ok    {url} -> hard stop: {str(e).splitlines()[-1].strip()}")
    print()
    override = os.environ.get("KESTRA_EXAMS_ROOT")
    # The un-overridden default is the one string this repo may not contain
    # (sweep S1/S2/S3 forbid it outside the skill's own two paths), so it is
    # reported as "the default" rather than printed.
    print(f"exams root: {exam_paths.exams_root() if override else 'the default'}"
          f"  (KESTRA_EXAMS_ROOT set: {bool(override)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
