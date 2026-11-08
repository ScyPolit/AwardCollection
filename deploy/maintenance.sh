#!/bin/sh
set -eu
umask 077
project="${AWARD_COLLECTION_PROJECT_DIR:-/opt/awardcollection-v1-test/app}"
action="${1:-all}"
case "$action" in backup|cleanup|all) ;; *) echo "Expected backup, cleanup or all" >&2; exit 2 ;; esac
cd "$project"
mkdir -p runtime
exec 9>runtime/maintenance.lock
flock -n 9 || { echo "Another maintenance job is running; no backup was created" >&2; exit 1; }

notify_failure() {
  result=$?
  trap - EXIT
  if [ "$result" -ne 0 ]; then
    echo "maintenance failed: action=$action code=$result" >&2
    docker compose -p awardcollection-v1-test exec -T api python manage.py shell -c "from django.contrib.auth import get_user_model; from awards.models import Notification; Notification.objects.bulk_create([Notification(user=u,title='本机维护失败',body='备份或清理任务失败，请管理员检查服务器 runtime/maintenance.log；原证书未删除。') for u in get_user_model().objects.filter(is_superuser=True,is_active=True)])" >/dev/null 2>&1 || true
  fi
  exit "$result"
}
trap notify_failure EXIT

if [ "$action" = backup ] || [ "$action" = all ]; then
  base="/opt/awardcollection-v1-test/backups"
  mkdir -p "$base"
  target=$(mktemp -d "$base/$(date -u +%Y%m%d-%H%M%S)-XXXXXX")
  key="$project/runtime/backup-encryption.key"
  if [ ! -s "$key" ]; then
    openssl rand -base64 48 >"$key"
    chmod 600 "$key"
  fi
  test -s .env
  test -s secrets/db_password.txt
  docker compose -p awardcollection-v1-test exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$target/database.dump"
  level="${BACKUP_COMPRESSLEVEL:-1}"
  case "$level" in [0-9]) ;; *) echo "BACKUP_COMPRESSLEVEL must be 0..9" >&2; exit 2 ;; esac
  media_code='import os,sys,tarfile; from pathlib import Path; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz",compresslevel=int(os.environ["BACKUP_COMPRESSLEVEL"])); [t.add(str(p),arcname=p.name) for p in Path("/srv/media").iterdir() if p.name!="temporary"]; t.close()'
  docker compose -p awardcollection-v1-test exec -T -e BACKUP_COMPRESSLEVEL="$level" api python -c "$media_code" >"$target/media.tar.gz"
  config_code='import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); t.add(".env"); t.add("secrets/db_password.txt"); t.close()'
  python3 -c "$config_code" | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass "file:$key" -out "$target/deployment-config.tar.gz.enc"
  python3 -c 'import sys,tarfile; from pathlib import Path; p=Path(sys.argv[1]); assert (p/"database.dump").read_bytes()[:5]==b"PGDMP"; t=tarfile.open(p/"media.tar.gz"); assert t.getmembers()' "$target"
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$key" -in "$target/deployment-config.tar.gz.enc" | python3 -c 'import sys,tarfile; t=tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz"); assert {".env","secrets/db_password.txt"}.issubset({m.name for m in t})'
  if docker compose -p awardcollection-v1-test exec -T web test -s /etc/award-tls/server.key 2>/dev/null; then
    docker compose -p awardcollection-v1-test exec -T web tar czf - -C /etc/award-tls server.crt server.key | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass "file:$key" -out "$target/tls.tar.gz.enc"
  else
    # A maintenance window pauses web before backup. Read its existing TLS volume
    # through a one-off container without starting nginx or publishing ports.
    docker compose -p awardcollection-v1-test run --rm --no-deps --entrypoint tar web czf - -C /etc/award-tls server.crt server.key | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass "file:$key" -out "$target/tls.tar.gz.enc"
  fi
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$key" -in "$target/tls.tar.gz.enc" | python3 -c 'import sys,tarfile;t=tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz");assert {"server.crt","server.key"}.issubset({m.name for m in t})'
  (cd "$target" && sha256sum database.dump media.tar.gz deployment-config.tar.gz.enc >SHA256SUMS)
  if [ -s "$target/tls.tar.gz.enc" ]; then (cd "$target" && sha256sum tls.tar.gz.enc >>SHA256SUMS); fi
  touch "$target/COMPLETE"
  printf '%s\n' "$target" >runtime/last-backup-path
  echo "BACKUP_COMPLETE=$target"
fi
if [ "$action" = cleanup ] || [ "$action" = all ]; then
  docker compose -p awardcollection-v1-test exec -T api python manage.py cleanup_runtime --days 7
fi
