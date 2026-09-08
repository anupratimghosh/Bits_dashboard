#!/usr/bin/env bash
# Dump every table of the BITS MySQL database to db_export/ as a gzipped .sql file.
# Reads credentials from .env (never hard-code them here).
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
DB="${1:-$BITS_DB_NAME}"
OUT="db_export/${DB}_$(date +%F).sql.gz"
mkdir -p db_export
mysqldump -h"$BITS_DB_HOST" -P"$BITS_DB_PORT" -u"$BITS_DB_USER" -p"$BITS_DB_PASSWORD" \
  --single-transaction --routines --triggers --set-gtid-purged=OFF \
  "$DB" | gzip -9 > "$OUT"
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"
