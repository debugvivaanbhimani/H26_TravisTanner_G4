#!/usr/bin/env bash
# Re-run the verification in this capsule on your own machine.
# usage: ./replay.sh [patch]   (default: patches/combined.patch)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PATCH="${1:-$HERE/patches/combined.patch}"
WORK="$(mktemp -d)"
git clone -q https://github.com/rishrek/LinkWatch "$WORK/repo"
cd "$WORK/repo"
git checkout -q f52f3930c8e7c33d934ccf614955a38e26984bd5
echo "== ORIGINAL dependencies =="
uv venv -q -p 3.12 .venv-orig
uv pip install -q -p .venv-orig/bin/python -r requirements-dev.txt -r requirements.txt
.venv-orig/bin/python -m pip --version >/dev/null 2>&1 || true
PYTHONPATH=. .venv-orig/bin/python -m pytest -q -p no:cacheprovider || true
echo "== REPLACEMENT dependencies ($PATCH) =="
git apply "$PATCH"
uv venv -q -p 3.12 .venv-new
uv pip install -q -p .venv-new/bin/python -r requirements-dev.txt -r requirements.txt pytest
PYTHONPATH=. .venv-new/bin/python -m pytest -q -p no:cacheprovider
