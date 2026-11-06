#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py cache_builtin_fonts
python manage.py collectstatic --noinput >/dev/null
exec "$@"
