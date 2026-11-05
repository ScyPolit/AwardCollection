#!/bin/sh
set -eu
stamp=$(date +%Y%m%d-%H%M%S)
target="${BACKUP_ROOT:-/srv/backups}/$stamp"
mkdir -p "$target"
pg_dump "$DATABASE_URL" --format=custom --file="$target/database.dump"
tar -C "${MEDIA_ROOT:-/srv/media}" -czf "$target/media.tar.gz" protected
sha256sum "$target/database.dump" "$target/media.tar.gz" > "$target/SHA256SUMS"
touch "$target/COMPLETE"
echo "$target"
