#!/usr/bin/env bash
# Consistent, timestamped backup of the atlas database.
#
#   scripts/backup_database.sh [destination-directory]
#
# Uses the SQLite backup API (via .backup) rather than copying the file, so a
# running pipeline cannot produce a torn snapshot.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="${UAV_DB_PATH:-$ROOT/data/uav_atlas.sqlite}"
DEST="${1:-$ROOT/data/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [ ! -f "$DB" ]; then
  echo "no database at $DB - nothing to back up" >&2
  exit 1
fi

mkdir -p "$DEST"
TARGET="$DEST/uav_atlas-$STAMP.sqlite"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '$TARGET'"
else
  python3 - "$DB" "$TARGET" <<'PY'
import sqlite3, sys
source, target = sys.argv[1], sys.argv[2]
src = sqlite3.connect(source)
dst = sqlite3.connect(target)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
PY
fi

gzip -f "$TARGET"
echo "backup written: $TARGET.gz ($(du -h "$TARGET.gz" | cut -f1))"

# Keep the 10 most recent backups.
ls -1t "$DEST"/uav_atlas-*.sqlite.gz 2>/dev/null | tail -n +11 | xargs -r rm --
echo "retained: $(ls -1 "$DEST"/uav_atlas-*.sqlite.gz 2>/dev/null | wc -l) backup(s)"
