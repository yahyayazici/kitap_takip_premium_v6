#!/bin/bash
set -euo pipefail

python manage.py migrate --no-input

# Bu doldurmalar her açılışta tekrar çalışır. Biri kilitlenirse sağlık
# kontrolü geçmez ve Render'daki kurulum dönmeye devam eder. 90 saniyede
# bitmezse site yine de ayağa kalkar; komut bir sonraki açılışta sürer.
soft() {
  python -c '
import subprocess, sys
cmd = sys.argv[1:]
try:
    result = subprocess.run(cmd, timeout=90)
except subprocess.TimeoutExpired:
    print("süre doldu, site açılışına devam:", " ".join(cmd), flush=True)
    sys.exit(0)
sys.exit(result.returncode)
' "$@"
}

soft python manage.py seed_ktt_konu_havuzu
soft python manage.py backfill_ktt_konu_eslestirme
soft python manage.py backfill_dini_tamamlanma_tarihi
soft python manage.py ensure_veli_hesaplari
soft python manage.py seed_ekran_sablonlari

if [ -n "${ADMIN_PASSWORD:-}" ]; then
  python manage.py reset_admin --username "${ADMIN_USERNAME:-admin}" --password "$ADMIN_PASSWORD"
fi

if [ "${RUN_SEED_WAVE0:-}" = "true" ]; then
  python manage.py seed_wave0
fi

python - <<'PY'
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from takip.pdf_utils import probe_weasyprint

ok, msg = probe_weasyprint()
print(f"weasyprint-smoke: {msg}", flush=True)
if not ok:
    raise SystemExit(f"WeasyPrint çalışmıyor: {msg}")
PY

# E-kitap soru taraması burada BAŞLATILMAZ. Aynı küçük makinede PDF/OCR
# gunicorn'un 2 işçisini dakikalarca bekletiyordu; giriş ve tıklama kuyruğa
# düşüyordu. Tarama yönetimdeki "Soruları bul" ile ya da elle
# `ekitap_sorulari_bul` komutuyla çalışır.

# cairo/pango gunicorn --preload ile fork sonrası bozulabiliyor
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 \
  --threads 2 \
  --timeout 90
