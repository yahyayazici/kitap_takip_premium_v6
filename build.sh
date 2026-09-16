#!/usr/bin/env bash
set -o errexit

# Native Python runtime: Pango/Cairo .deb'lerini vendor/pdf-libs altına açmayı dene.
# Docker imajında apt zaten kurulu olduğu için bu adım no-op / yedek.
if [ -f scripts/vendor_weasyprint_libs.sh ]; then
  bash scripts/vendor_weasyprint_libs.sh || true
fi

pip install -r requirements.txt
python3 scripts/build_css_bundle.py
python manage.py collectstatic --no-input
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
