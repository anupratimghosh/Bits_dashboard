#!/usr/bin/env bash
# Restore a dump produced by export_db.sh into a local MySQL database.
#   ./restore_db.sh db_export/bits_research_p3_2026-09-08.sql.gz [target_db_name]
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
DUMP="${1:?usage: ./restore_db.sh <dump.sql.gz> [target_db]}"
DB="${2:-$BITS_DB_NAME}"
mysql -h"$BITS_DB_HOST" -P"$BITS_DB_PORT" -u"$BITS_DB_USER" -p"$BITS_DB_PASSWORD" \
  -e "CREATE DATABASE IF NOT EXISTS \`$DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
gunzip -c "$DUMP" | mysql -h"$BITS_DB_HOST" -P"$BITS_DB_PORT" -u"$BITS_DB_USER" -p"$BITS_DB_PASSWORD" "$DB"
echo "Restored $DUMP into $DB"
