#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py seed_ktt_konu_havuzu
python manage.py backfill_ktt_konu_eslestirme
python manage.py backfill_dini_tamamlanma_tarihi

if [ -n "${ADMIN_PASSWORD:-}" ]; then
  python manage.py reset_admin --username "${ADMIN_USERNAME:-admin}" --password "$ADMIN_PASSWORD"
fi

if [ "${RUN_SEED_WAVE0:-}" = "true" ]; then
  python manage.py seed_wave0
fi
