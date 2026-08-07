#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input

if [ -n "${ADMIN_PASSWORD:-}" ]; then
  python manage.py reset_admin --username "${ADMIN_USERNAME:-admin}" --password "$ADMIN_PASSWORD"
fi

if [ "${RUN_SEED_WAVE0:-}" = "true" ]; then
  python manage.py seed_wave0
  python manage.py seed_dini_ders_mufredat
fi
