#!/bin/sh
set -eu
if [ "$(id -u)" = "0" ]; then
  mkdir -p /srv/media /srv/backups
  chown -R award:award /srv/media /srv/backups
  exec gosu award "$0" "$@"
fi
python manage.py migrate --noinput
python manage.py cache_builtin_fonts
python manage.py collectstatic --noinput >/dev/null
exec "$@"
