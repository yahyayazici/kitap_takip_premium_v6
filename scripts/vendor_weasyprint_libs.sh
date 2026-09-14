#!/usr/bin/env bash
# Native Python runtime'da root apt-get yoksa .deb dosyalarını açıp
# vendor/pdf-libs altına koyar. Docker imajında gerekmez.
set -u
DEST="${PWD}/vendor/pdf-libs"
mkdir -p "$DEST" vendor/debs

if ! command -v apt-get >/dev/null 2>&1 || ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "weasyprint libs: apt-get/dpkg-deb yok, atlanıyor"
  exit 0
fi

PKGS=(
  libpango-1.0-0
  libpangocairo-1.0-0
  libpangoft2-1.0-0
  libharfbuzz0b
  libharfbuzz-subset0
  libcairo2
  libgdk-pixbuf-2.0-0
  libffi8
  libglib2.0-0
  libfontconfig1
  libfreetype6
  libpixman-1-0
  libpng16-16
  libfribidi0
  libthai0
  libdatrie1
  libxcb1
  libxcb-render0
  libxcb-shm0
  libxext6
  libxrender1
  libx11-6
)

(
  cd vendor/debs
  apt-get download "${PKGS[@]}" || true
  shopt -s nullglob
  for deb in *.deb; do
    dpkg-deb -x "$deb" "$DEST"
  done
)

if find "$DEST" -name 'libpango-1.0.so*' | grep -q .; then
  echo "weasyprint libs: $DEST"
else
  echo "weasyprint libs: pango bulunamadı (Docker runtime gerekir)"
fi
