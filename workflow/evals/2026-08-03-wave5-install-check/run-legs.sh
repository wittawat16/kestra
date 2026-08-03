#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

bash -n install.sh
python3 -B -m unittest discover -s tests -p 'test_install_check.py'
python3 -B workflow/runs/install-check/validate_spec.py workflow/runs/install-check/0-spec.md .
python3 -B workflow/runs/install-check/validate_workflow.py workflow/runs/install-check
git diff --check -- install.sh README.md README-th.md workflow/evals/2026-08-03-wave5-install-check
