#!/bin/sh
set -eu
: "${BACKUP_DIR:?Set BACKUP_DIR to one completed backup}"
: "${RESTORE_DATABASE_URL:?Set RESTORE_DATABASE_URL to an isolated empty database}"
test -f "$BACKUP_DIR/COMPLETE"
(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
pg_restore --clean --if-exists --no-owner --dbname="$RESTORE_DATABASE_URL" "$BACKUP_DIR/database.dump"
mkdir -p "${RESTORE_MEDIA_ROOT:?Set isolated RESTORE_MEDIA_ROOT}"
tar -C "$RESTORE_MEDIA_ROOT" -xzf "$BACKUP_DIR/media.tar.gz"
echo "isolated restore completed"
