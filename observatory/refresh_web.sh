#!/usr/bin/env bash
# Daily refresh of the static site's data (web/data/*.json).
#
#   bash observatory/refresh_web.sh              # pull, fetch prices, rebuild panels, export JSON
#   bash observatory/refresh_web.sh --no-pull    # use the working tree as is
#   bash observatory/refresh_web.sh --momentum   # also rerun build_momentum.py (needs data/bhav/, slow)
#
# Steps:
#   1. git pull --ff-only: the latest raw NSE/NSDL captures from the capture PC and the paper marks.
#   2. python build.py: fetch_all (Yahoo/FRED prices, about 20 instruments), then rebuild data/curated/.
#      The new raw price snapshots stay local (binary parquet; Hark's push path is text only).
#   3. optional: python build_momentum.py (only with --momentum and when data/bhav/ exists).
#   4. python export_web.py --no-ensure: write web/data/*.json and run checks.py.
#   5. Report what changed. Only web/data/*.json is meant to be pushed; anything else is flagged.
#
# Never pushes. The caller (Hark's daily runner) pushes web/data/*.json, within the push permission
# Devansh has given.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PY="${PYTHON:-python}"
PULL=1; MOM=0
for a in "$@"; do
  case "$a" in
    --no-pull) PULL=0 ;;
    --momentum) MOM=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

cd "$ROOT"
if [[ $PULL == 1 ]]; then
  echo "== git pull --ff-only"
  git pull --ff-only --quiet
fi
echo "== at commit $(git rev-parse --short HEAD)"

cd "$HERE"
echo "== build.py (fetch prices + rebuild curated panels)"
"$PY" build.py | grep -E "^fetched|FAILED|^flows:|common window" || true

if [[ $MOM == 1 ]]; then
  if [[ -d data/bhav ]]; then
    echo "== build_momentum.py"
    "$PY" build_momentum.py
  else
    echo "== build_momentum.py skipped: data/bhav/ not present (regenerate with build_bhav.py)"
  fi
fi

echo "== export_web.py"
"$PY" export_web.py --no-ensure

cd "$ROOT"
echo "== changed tracked files"
CHANGED="$(git status --porcelain --untracked-files=all -- web/data)"
echo "${CHANGED:-  (web/data unchanged)}"
OTHER="$(git status --porcelain --untracked-files=no | grep -v ' web/data/' || true)"
if [[ -n "$OTHER" ]]; then
  echo "!! tracked files outside web/data changed (do NOT push these without Devansh's go):"
  echo "$OTHER"
fi
echo "== push candidates (web/data/*.json)"
TOTAL=0
for f in web/data/*.json; do
  if [[ -n "$(git status --porcelain -- "$f")" ]]; then
    s=$(wc -c < "$f"); TOTAL=$((TOTAL + s)); awk -v f="$f" -v s="$s" 'BEGIN { printf "  %-26s %8.1f KB\n", f, s / 1024 }'
  fi
done
awk -v t="$TOTAL" 'BEGIN { printf "  total to push: %.1f KB\n", t / 1024 }'
