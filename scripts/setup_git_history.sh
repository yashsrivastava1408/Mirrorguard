#!/usr/bin/env bash
# Creates the git history for work that was done before the repository existed:
#
#   main      the project base only (idea, architecture, roadmap)
#   develop   the full project, with one merge per phase
#   phase-N   one branch per phase
#
# Run it once, from the project root, in a folder that has no .git yet:
#
#   bash scripts/setup_git_history.sh
#
# It only runs local git commands. It never pushes anything.
# It does not change, move or delete any file in this folder. The history is
# built in a temporary folder and only the finished .git folder is moved here.
set -euo pipefail

ROOT="$(pwd)"
SNAPSHOTS="$ROOT/.phase-snapshots"

if [ -e "$ROOT/.git" ]; then
  echo "This folder already has a git repository. Nothing was changed." >&2
  exit 1
fi
if [ ! -f "$SNAPSHOTS/00-base.tgz" ] || [ ! -f "$ROOT/pyproject.toml" ]; then
  echo "Run this from the MirrorGuard project root (the snapshots folder is missing)." >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

# Make the folder hold exactly one snapshot, then commit it.
apply_snapshot() {
  local archive="$1" message="$2"
  find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  tar -xzf "$archive"
  git add -A
  git commit -q -m "$message"
}

phase() {
  local number="$1" branch="$2" message="$3"
  git checkout -q -b "$branch" develop
  apply_snapshot "$SNAPSHOTS/0${number}-phase-${number}.tgz" "Phase ${number}: ${message}"
  git checkout -q develop
  git merge -q --no-ff "$branch" -m "Merge ${branch} into develop"
  echo "  phase ${number} done"
}

git init -q -b main
echo "Creating history..."
apply_snapshot "$SNAPSHOTS/00-base.tgz" "Project base: overview, architecture and roadmap"
git checkout -q -b develop

phase 1 phase-1-rubric-personas      "scoring rubric, personas and scenarios"
phase 2 phase-2-benchmark-engine     "persona simulator, judge and benchmark runner"
phase 3 phase-3-judge-validation     "tools to compare the judge with human labels"
phase 4 phase-4-guardrail-proxy      "risk scorer, steering, policy and the proxy API"
phase 5 phase-5-guardrail-evaluation "benchmark with the guardrail off and on, Hinglish scenarios"
phase 6 phase-6-high-risk-protection "hold, check and rewrite high-risk replies"
phase 7 phase-7-dashboard            "dashboard and its API endpoints"
phase 8 phase-8-enterprise           "tenants, keys, roles, audit log, masking, retention"
phase 9 phase-9-deploy               "migrations, Docker, CI and load test"

# Hand the finished history to the project folder. Its files are left exactly as they are.
mv "$WORK/.git" "$ROOT/.git"
cd "$ROOT"

echo
echo "Done. You are on 'develop', which holds the full project."
echo "'main' holds only the base."
git --no-pager log --oneline --graph --all | head -30
echo
if [ -n "$(git status --porcelain)" ]; then
  echo "These files were changed after the last phase snapshot and are not committed yet:"
  git status --short
  echo
fi
echo "To publish (only when you want to):"
echo "  git remote add origin <your repository address>"
echo "  git push -u origin main develop"
echo "  git push origin --all        # also pushes the phase branches"
