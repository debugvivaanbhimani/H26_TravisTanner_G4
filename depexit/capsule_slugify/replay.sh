#!/usr/bin/env bash
# Re-run the verification in this capsule on your own machine.
# usage: ./replay.sh [patch]   (default: patches/combined.patch)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PATCH="${1:-$HERE/patches/combined.patch}"
WORK="$(mktemp -d)"
git clone -q https://github.com/un33k/python-slugify "$WORK/repo"
cd "$WORK/repo"
git checkout -q 54d81f63dfe1e5a35a726d212ee9f4fd5e2b3233
echo "== ORIGINAL dependencies =="
uv venv -q -p 3.12 .venv-orig
uv pip install -q -p .venv-orig/bin/python -e .
.venv-orig/bin/python -m pip --version >/dev/null 2>&1 || true
PYTHONPATH=. .venv-orig/bin/python -m pytest -q -p no:cacheprovider || true
echo "== REPLACEMENT dependencies ($PATCH) =="
git apply "$PATCH"
uv venv -q -p 3.12 .venv-new
uv pip install -q -p .venv-new/bin/python -e . pytest
PYTHONPATH=. .venv-new/bin/python -m pytest -q -p no:cacheprovider
