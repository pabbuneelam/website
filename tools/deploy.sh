#!/usr/bin/env bash
# Deploy without letting the Vercel CLI see the git remote.
#
# The repo is pabbuneelam/website, which this Vercel account cannot access.
# When the CLI finds that remote it tries to connect the project to it and the
# deployment stalls in "Building" forever -- no logs, status UNKNOWN.
#
# ponytail: staging copy. The real fix is connecting the repo to Vercel, which
# needs the repo owner. Delete this the day that happens (#10).
#
#   tools/deploy.sh        -> slate-demo: FastAPI, serving the built SPA
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

rsync -a --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
      --exclude '.pytest_cache' --exclude '.vercel' --exclude 'tests' \
      --exclude 'node_modules' --exclude 'frontend/dist' --exclude 'slate/static' \
      "$ROOT/" "$STAGE/"

cd "$STAGE"
git rev-parse --git-dir >/dev/null 2>&1 && { echo "staging dir is inside a repo; aborting" >&2; exit 1; }
vercel link --project slate-demo --yes >/dev/null
exec vercel deploy --prod --yes
