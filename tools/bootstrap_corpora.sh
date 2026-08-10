#!/usr/bin/env bash
# Optional helper: re-copy corpora from sibling CC-FBR if present.
# Primary state lives under data/corpora/; this only refreshes from the old tree.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${CC_FBR_ROOT:-$ROOT/../CC-FBR}"
ORD_DST="$ROOT/data/corpora/ordinance"
ACTS_DST="$ROOT/data/corpora/acts"

if [[ ! -d "$SRC/Income Tax Ordinance, 2001" || ! -d "$SRC/Acts_fbr/Acts" ]]; then
  echo "CC-FBR source not found at: $SRC" >&2
  echo "Set CC_FBR_ROOT or keep corpora under data/corpora/ (already vendored)." >&2
  exit 1
fi

mkdir -p "$ORD_DST" "$ACTS_DST"
EXCL=(--exclude '.DS_Store' --exclude '.venv' --exclude '.ocrcache' --exclude 'node_modules' --exclude '__pycache__')

rsync -a --delete "${EXCL[@]}" "$SRC/Income Tax Ordinance, 2001/" "$ORD_DST/Income Tax Ordinance, 2001/"
rsync -a --delete "${EXCL[@]}" "$SRC/output/" "$ORD_DST/output/"
[[ -d "$SRC/reports" ]] && rsync -a --delete "${EXCL[@]}" "$SRC/reports/" "$ORD_DST/reports/"

rsync -a --delete "${EXCL[@]}" "$SRC/Acts_fbr/Acts/" "$ACTS_DST/Acts/"
rsync -a --delete "${EXCL[@]}" "$SRC/Acts_fbr/output/" "$ACTS_DST/output/"
[[ -d "$SRC/Acts_fbr/reports" ]] && rsync -a --delete "${EXCL[@]}" "$SRC/Acts_fbr/reports/" "$ACTS_DST/reports/"

echo "Vendored corpora:"
du -sh "$ORD_DST" "$ACTS_DST" "$ROOT/data/corpora"
