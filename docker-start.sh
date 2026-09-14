#!/bin/bash
set -euo pipefail

python manage.py migrate --no-input
python manage.py seed_ktt_konu_havuzu
python manage.py backfill_ktt_konu_eslestirme
python manage.py backfill_dini_tamamlanma_tarihi
python manage.py ensure_veli_hesaplari

if [ -n "${ADMIN_PASSWORD:-}" ]; then
  python manage.py reset_admin --username "${ADMIN_USERNAME:-admin}" --password "$ADMIN_PASSWORD"
fi

if [ "${RUN_SEED_WAVE0:-}" = "true" ]; then
  python manage.py seed_wave0
fi

# cairo/pango gunicorn --preload ile fork sonrası bozulabiliyor
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 \
  --threads 2 \
  --timeout 90
