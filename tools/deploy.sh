#!/usr/bin/env bash
# Deploy without letting the Vercel CLI see the git remote.
#
# The repo is pabbuneelam/website, which this Vercel account cannot access.
# When the CLI finds that remote it tries to connect the project to it and the
# deployment stalls in "Building" forever -- no logs, status UNKNOWN. First
# deploys survive only because the project does not exist yet.
#
# ponytail: staging copy. The real fix is connecting the repo to Vercel, which
# needs the repo owner. Delete this the day that happens.
#
#   tools/deploy.sh api        -> slate-demo   (FastAPI)
#   tools/deploy.sh ui         -> slate-ui     (Vite SPA)
set -euo pipefail

TARGET="${1:?usage: deploy.sh api|ui}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

case "$TARGET" in
  api)
    PROJECT=slate-demo
    rsync -a --exclude '.git' --exclude '.venv' --exclude 'frontend' \
          --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.vercel' \
          --exclude 'tests' --exclude 'node_modules' \
          "$ROOT/" "$STAGE/"
    # The repo vercel.json builds the frontend, which this stage deliberately
    # does not contain -- the SPA is its own project. Write the API's own
    # config instead of shipping one that runs `cd frontend` into thin air.
    #
    # buildCommand must be set, not omitted: the Vercel project stored the
    # frontend build command from an earlier deploy, and an absent key inherits
    # that stored setting rather than clearing it.
    cat > "$STAGE/vercel.json" <<'JSON'
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "echo 'api project: no frontend build step'",
  "functions": {
    "slate/api.py": {
      "excludeFiles": "{tests/**,tools/**,.venv/**,docs/**}"
    }
  }
}
JSON
    ;;
  ui)
    PROJECT=slate-ui
    rsync -a --exclude '.git' --exclude 'node_modules' --exclude 'dist' \
          --exclude '.vercel' "$ROOT/frontend/" "$STAGE/"
    EXTRA=(--build-env "VITE_API_BASE=${VITE_API_BASE:-https://slate-demo-six.vercel.app}")
    ;;
  *) echo "usage: deploy.sh api|ui" >&2; exit 2 ;;
esac

cd "$STAGE"
git rev-parse --git-dir >/dev/null 2>&1 && { echo "staging dir is inside a repo; aborting" >&2; exit 1; }
vercel link --project "$PROJECT" --yes >/dev/null
exec vercel deploy --prod --yes "${EXTRA[@]:-}"
