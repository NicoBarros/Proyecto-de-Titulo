#!/usr/bin/env bash
set -o errexit

python manage.py migrate --no-input
python manage.py createcachetable
python manage.py collectstatic --no-input
python manage.py crear_admin

exec gunicorn leica_project.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
