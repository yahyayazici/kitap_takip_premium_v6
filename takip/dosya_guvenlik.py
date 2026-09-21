"""Paylaşılan dosya güvenliği yardımcıları — magic number tespiti, özet.

Güvenlik notu
-------------
Dosya türü **uzantıya güvenilerek** belirlenmez. Her yüklemede içeriğin ilk
baytlarına (magic number) bakılır; uzantı ile içerik uyuşmazsa dosya
reddedilir. Bu, ``.jpg`` adıyla yüklenen bir HTML/SVG dosyasının medya
adresinden servis edilip tarayıcıda script çalıştırmasını (XSS) engeller.
SVG hiç kabul edilmez — script barındırabilen tek görsel formatıdır.

Bu modül ``ekran_media_service.py``'den çıkarılmıştır; Ekran ve Akıllı
Tahta modülleri aynı tespit mantığını burada paylaşır — aynı görevi yapan
kod tekrar edilmez.
"""

from __future__ import annotations

import hashlib

from django.core.files.uploadedfile import UploadedFile


def ilk_baytlar(dosya: UploadedFile, uzunluk: int = 32) -> bytes:
    dosya.seek(0)
    bas = dosya.read(uzunluk)
    dosya.seek(0)
    return bas


def icerik_turu_tespit_et(bas: bytes) -> str | None:
    """Magic number'dan gerçek türü çıkarır; tanınmazsa None."""
    if bas.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if bas.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if bas[:4] == b"RIFF" and bas[8:12] == b"WEBP":
        return "webp"
    if bas.startswith(b"%PDF-"):
        return "pdf"
    if bas[4:8] == b"ftyp":
        return "mp4"
    if bas.startswith(b"\x1a\x45\xdf\xa3"):  # EBML → webm / mkv
        return "webm"
    return None


def dosya_ozeti(dosya: UploadedFile) -> str:
    """Bellek şişirmeden SHA-256 — dedup anahtarı."""
    ozet = hashlib.sha256()
    dosya.seek(0)
    for parca in iter(lambda: dosya.read(1024 * 1024), b""):
        ozet.update(parca)
    dosya.seek(0)
    return ozet.hexdigest()
