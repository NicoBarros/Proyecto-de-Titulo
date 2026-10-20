#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py crear_admin

if [ "$CARGAR_DATOS_DEMO" = "true" ]; then
  python manage.py seed
fi
