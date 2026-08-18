"""Basit, bakımı kolay giriş deneme sınırlayıcı.

Django'nun varsayılan cache framework'ünü (harici bağımlılık/Redis
gerektirmez) kullanır. IP + kullanıcı adı kombinasyonuna göre sayaç tutar;
böylece aynı okul/kurum ağındaki (paylaşılan IP) farklı kullanıcılar
birbirini kilitlemez, ama tek bir hesaba karşı tekrarlı deneme yavaşlatılır.

Kalıcı/otomatik hesap kilitleme YAPILMAZ — sayaç, son başarısız denemeden
PENCERE_SANIYE kadar sonra kendiliğinden sıfırlanır (cache TTL). Bu; bir
saldırganın meşru bir kullanıcıyı süresiz kilitleyerek DoS yapmasını önler.

Not: Varsayılan cache backend'i (LocMemCache) süreç-içi bellektedir; birden
fazla gunicorn worker'ı arasında paylaşılmaz. Bu nedenle koruma tam değil
(bir istemci farklı worker'lara denk gelerek limiti kısmen aşabilir) — daha
güçlü/paylaşımlı bir çözüm (Redis) sonraki sprint için not edilmiştir.
"""

from __future__ import annotations

from django.core.cache import cache

MAX_DENEME = 5
PENCERE_SANIYE = 5 * 60  # 5 dakika
_CACHE_ANAHTAR_ONEKI = "giris_deneme"


def _istemci_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _anahtar(request, kullanici_adi: str) -> str | None:
    ip = _istemci_ip(request)
    if not ip:
        return None
    return f"{_CACHE_ANAHTAR_ONEKI}:{ip}:{(kullanici_adi or '').strip().lower()}"


def limit_asildi_mi(request, kullanici_adi: str) -> bool:
    """Bu IP+kullanıcı adı kombinasyonu şu an cooldown'da mı?"""
    anahtar = _anahtar(request, kullanici_adi)
    if not anahtar:
        return False
    return cache.get(anahtar, 0) >= MAX_DENEME


def basarisiz_deneme_kaydet(request, kullanici_adi: str) -> None:
    anahtar = _anahtar(request, kullanici_adi)
    if not anahtar:
        return
    sayac = cache.get(anahtar, 0) + 1
    cache.set(anahtar, sayac, timeout=PENCERE_SANIYE)


def basarili_giris_sifirla(request, kullanici_adi: str) -> None:
    anahtar = _anahtar(request, kullanici_adi)
    if anahtar:
        cache.delete(anahtar)
