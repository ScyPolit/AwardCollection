#!/bin/sh
set -eu
umask 077
project="${AWARD_COLLECTION_PROJECT_DIR:-/opt/awardcollection-v1-test/app}"
action="${1:-all}"
case "$action" in backup|cleanup|all) ;; *) echo "Expected backup, cleanup or all" >&2; exit 2 ;; esac
cd "$project"
mkdir -p runtime
exec 9>runtime/maintenance.lock
flock -n 9 || exit 0

notify_failure() {
  result=$?
  trap - EXIT
  if [ "$result" -ne 0 ]; then
    echo "maintenance failed: action=$action code=$result" >&2
    docker compose -p awardcollection-v1-test exec -T api python manage.py shell -c +      "from django.contrib.auth import get_user_model; from awards.models import Notification; Notification.objects.bulk_create([Notification(user=u,title='本机维护失败',body='备份或清理任务失败，请管理员检查服务器 runtime/maintenance.log；原证书未删除。') for u in get_user_model().objects.filter(is_superuser=True,is_active=True)])" +      >/dev/null 2>&1 || true
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
  docker compose -p awardcollection-v1-test exec -T db sh -c +    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$target/database.dump"
  docker compose -p awardcollection-v1-test exec -T api +    tar -C /srv/media --exclude=./temporary -czf - . >"$target/media.tar.gz"
  tar -C "$project" -czf - .env secrets/db_password.txt |
    openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass "file:$key" +      -out "$target/deployment-config.tar.gz.enc"
  (cd "$target" && sha256sum database.dump media.tar.gz deployment-config.tar.gz.enc >SHA256SUMS)
  touch "$target/COMPLETE"
  printf '%s\n' "$target" >runtime/last-backup-path
  echo "BACKUP_COMPLETE=$target"
fi
if [ "$action" = cleanup ] || [ "$action" = all ]; then
  docker compose -p awardcollection-v1-test exec -T api +    python manage.py cleanup_runtime --days 7
fi
