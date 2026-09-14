#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
LIBDIR=""
for candidate in \
  "$ROOT/vendor/pdf-libs/usr/lib/x86_64-linux-gnu" \
  "$ROOT/vendor/pdf-libs/usr/lib/aarch64-linux-gnu"
do
  if [ -d "$candidate" ]; then
    LIBDIR="$candidate"
    break
  fi
done
if [ -n "$LIBDIR" ]; then
  export LD_LIBRARY_PATH="${LIBDIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
if [ -d "$ROOT/vendor/pdf-libs/etc/fonts" ]; then
  export FONTCONFIG_PATH="$ROOT/vendor/pdf-libs/etc/fonts${FONTCONFIG_PATH:+:$FONTCONFIG_PATH}"
fi
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 \
  --threads 2 \
  --timeout 90
