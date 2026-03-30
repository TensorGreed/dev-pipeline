#!/usr/bin/env bash
set -euo pipefail

REPO_PATH="${1:-.}"
CONFIG="${2:-config/settings.example.yaml}"
BASE_BRANCH="${3:-main}"

python -m app.cli run \
  --repo "$REPO_PATH" \
  --requirement-file app/examples/sample_requirement.md \
  --base-branch "$BASE_BRANCH" \
  --config "$CONFIG"
