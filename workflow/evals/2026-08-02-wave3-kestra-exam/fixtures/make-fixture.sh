#!/bin/sh
# Build the throwaway fixture repo for the Wave-3 kestra-exam eval.
#
# Everything lands under $KX_ROOT (default /tmp/kx36) — nothing is written inside
# the skill repo, and the real user-level exams root is never touched (the eval
# redirects it with KESTRA_EXAMS_ROOT, echoed on every exam_paths.py run).
#
# Four commits on `main` plus one on `broken`, so the eval has three real tree
# states to run the same exam against:
#
#   c0      the tally CLI before the feature exists
#   RAISE   spec(tally-refund): write 0-spec.md from a hand-written idea
#   IMPL    --refund and the malformed-amount refusal implemented
#   BROKEN  (branch `broken`) one AC violated: the refund test is a typo
#
# The origin URL is a host-shaped placeholder that is never contacted. A
# `file://` or bare-path origin cannot be keyed at all — see
# logs/no-origin.log, leg 9b — so it is not usable as a fixture origin.
#
# Writes $KX_ROOT/shas.env with RAISE / IMPL / BROKEN.
set -eu

ROOT=${KX_ROOT:-/tmp/kx36}
FIX=$(cd "$(dirname "$0")" && pwd)
R="$ROOT/repo"
RUN="$R/workflows/runs/tally-refund"

GIT="git -c user.name=kestra-exam-eval -c user.email=eval@example.test"

rm -rf "$ROOT"
mkdir -p "$R/src" "$R/data" "$RUN"

cat > "$R/data/mixed.csv" <<'CSV'
type,amount
sale,100
refund,30
sale,20
CSV

cat > "$R/data/bad.csv" <<'CSV'
type,amount
sale,100
sale,oops
CSV

cat > "$R/data/empty.csv" <<'CSV'
type,amount
CSV

# ---------------------------------------------------------------- c0: pre-feature
cat > "$R/src/tally.py" <<'PY'
#!/usr/bin/env python3
"""tally — sum the amount column of a CSV."""
import csv
import sys


def main(argv):
    if len(argv) != 1:
        print("usage: tally.py <csv>", file=sys.stderr)
        return 1
    total = 0
    with open(argv[0], newline="") as fh:
        for row in csv.DictReader(fh):
            total += int(row["amount"])
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PY

$GIT init -q -b main "$R"
$GIT -C "$R" remote add origin https://git.example.test/kx-fixture/tally.git
$GIT -C "$R" add -A
$GIT -C "$R" commit -q -m "add the tally CLI and its sample data"

# ------------------------------------------------------------- RAISE: spec only
cp "$FIX/0-spec.md" "$RUN/0-spec.md"
$GIT -C "$R" add -A
$GIT -C "$R" commit -q -m "spec(tally-refund): write 0-spec.md from a hand-written idea"
RAISE=$($GIT -C "$R" rev-parse HEAD)

# --------------------------------------------------------------- IMPL: the feature
cat > "$R/src/tally.py" <<'PY'
#!/usr/bin/env python3
"""tally — sum the amount column of a CSV; --refund subtracts refund rows."""
import csv
import sys

USAGE = "usage: tally.py [--refund] <csv>"


def main(argv):
    refund, args = False, []
    for a in argv:
        if a == "--refund":
            refund = True
        elif a.startswith("--"):
            print(f"{USAGE}\nunknown option: {a}", file=sys.stderr)
            return 1
        else:
            args.append(a)
    if len(args) != 1:
        print(USAGE, file=sys.stderr)
        return 1
    total = 0
    with open(args[0], newline="") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            raw = (row.get("amount") or "").strip()
            try:
                amount = int(raw)
            except ValueError:
                print(f"malformed amount on line {line_no}: {raw!r}",
                      file=sys.stderr)
                return 2
            if refund and (row.get("type") or "").strip() == "refund":
                total -= amount
            else:
                total += amount
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PY
$GIT -C "$R" add -A
$GIT -C "$R" commit -q -m "implement --refund and the malformed-amount refusal"
IMPL=$($GIT -C "$R" rev-parse HEAD)

# ------------------------------------------- BROKEN: exactly one AC violated
$GIT -C "$R" checkout -q -b broken
sed 's/== "refund"/== "refunded"/' "$R/src/tally.py" > "$R/src/tally.py.new"
mv "$R/src/tally.py.new" "$R/src/tally.py"
$GIT -C "$R" add -A
$GIT -C "$R" commit -q -m "fixture: regress the refund test so exactly one AC is violated"
BROKEN=$($GIT -C "$R" rev-parse HEAD)
$GIT -C "$R" checkout -q main

cat > "$ROOT/shas.env" <<ENV
RAISE=$RAISE
IMPL=$IMPL
BROKEN=$BROKEN
REPO=$R
RUN=$RUN
ENV

echo "fixture built at $ROOT"
$GIT -C "$R" log --oneline --all --decorate
echo "--- shas.env ---"
cat "$ROOT/shas.env"
