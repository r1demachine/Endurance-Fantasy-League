#!/usr/bin/env bash
set -euo pipefail

if [[ "${RESTORE_CONFIRM:-}" != "YES" ]]; then
  echo "Refusing to restore without RESTORE_CONFIRM=YES."
  echo "Restore into a fresh or intentionally selected database; this can overwrite existing data."
  exit 2
fi

: "${BACKUP_AGE_IDENTITY_FILE:?Set BACKUP_AGE_IDENTITY_FILE to the age private identity file}"
: "${RESTORE_DATABASE_URL:?Set RESTORE_DATABASE_URL to the target PostgreSQL URL}"
: "${BACKUP_FILE:?Set BACKUP_FILE to the downloaded .sql.gz.age backup file}"

if [[ ! -r "$BACKUP_AGE_IDENTITY_FILE" || ! -r "$BACKUP_FILE" ]]; then
  echo "Backup file or age identity file is not readable." >&2
  exit 2
fi

# The age private identity must be stored separately from the backup bucket and repo.
age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "$BACKUP_FILE" \
  | gzip --decompress \
  | psql "$RESTORE_DATABASE_URL" --set ON_ERROR_STOP=1
