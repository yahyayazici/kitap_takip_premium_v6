"""Akıllı Tahta dosyalarının erişim kontrollü, Range destekli servis ucu.

Neden ayrı bir görünüm (düz ``MEDIA_URL`` servisi değil)?
-----------------------------------------------------------
Bir akıllı tahta hesabı yalnızca KENDİ sınıf seviyesine hedeflenmiş ve
yayında olan dosyalara erişebilmeli; taslak/süresi dolmuş/başka seviyeye ait
dosyalar adres tahmin edilse bile açılmamalı. Bu yüzden dosya, düz statik
sunucudan değil, her istekte yetki kontrolü yapan bu görünümden servis
edilir. Range desteği (``ekran_viewer_views.ekran_medyasi`` ile aynı
teknik) video/PDF'te ileri-geri sarmayı mümkün kılar.
"""

from __future__ import annotations

import mimetypes
import os
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils._os import safe_join
from django.views.decorators.clickjacking import xframe_options_sameorigin

from takip.akilli_tahta_models import AkilliTahtaDosya
from takip.akilli_tahta_service import kullanici_tahta_mi, tam_yetkili

_MEDYA_ONBELLEK_SN = 60 * 60 * 24 * 30


def _dosya_parcasi(dosya, uzunluk: int, parca: int = 64 * 1024):
    try:
        kalan = uzunluk
        while kalan > 0:
            veri = dosya.read(min(parca, kalan))
            if not veri:
                break
            kalan -= len(veri)
            yield veri
    finally:
        dosya.close()


def _erisebilir_mi(request, dosya: AkilliTahtaDosya) -> bool:
    user = request.user
    if tam_yetkili(user) or dosya.yukleyen_id == user.id:
        return True
    if kullanici_tahta_mi(user):
        hesap = user.akilli_tahta_hesabi
        return dosya.gorunur_durum == "yayinda" and dosya.hedefliyor_mu(hesap.sinif_seviyesi)
    return False


@login_required
@xframe_options_sameorigin
def akilli_tahta_medyasi(request, pk: int):
    dosya = get_object_or_404(AkilliTahtaDosya, pk=pk)
    if not _erisebilir_mi(request, dosya):
        raise Http404("Dosya bulunamadı.")

    indir_istegi = request.GET.get("indir") == "1"
    if indir_istegi and not dosya.indirme_izni and not tam_yetkili(request.user):
        return HttpResponse("Bu dosya için indirme kapalı.", status=403)

    try:
        tam_yol = safe_join(str(settings.AKILLI_TAHTA_MEDIA_ROOT), dosya.dosya.name)
    except (SuspiciousFileOperation, ValueError):
        raise Http404("Dosya bulunamadı.")

    if not os.path.isfile(tam_yol):
        raise Http404("Dosya bulunamadı.")

    durum = os.stat(tam_yol)
    boyut = durum.st_size
    tur = dosya.mime or mimetypes.guess_type(tam_yol)[0] or "application/octet-stream"

    def baslikla(yanit):
        yanit["Accept-Ranges"] = "bytes"
        yanit["Cache-Control"] = f"private, max-age={_MEDYA_ONBELLEK_SN}"
        if indir_istegi:
            yanit["Content-Disposition"] = f'attachment; filename="{dosya.baslik}.{dosya.dosya_turu}"'
        return yanit

    aralik = request.META.get("HTTP_RANGE", "")
    eslesme = re.match(r"bytes=(\d*)-(\d*)$", aralik.strip()) if aralik else None

    if eslesme:
        bas_ham, son_ham = eslesme.groups()
        if bas_ham:
            bas = int(bas_ham)
            son = int(son_ham) if son_ham else boyut - 1
        elif son_ham:
            bas = max(0, boyut - int(son_ham))
            son = boyut - 1
        else:
            bas, son = 0, boyut - 1

        son = min(son, boyut - 1)
        if bas > son or bas >= boyut:
            yanit = HttpResponse(status=416)
            yanit["Content-Range"] = f"bytes */{boyut}"
            return baslikla(yanit)

        uzunluk = son - bas + 1
        acik_dosya = open(tam_yol, "rb")
        acik_dosya.seek(bas)
        yanit = StreamingHttpResponse(
            _dosya_parcasi(acik_dosya, uzunluk), status=206, content_type=tur
        )
        yanit["Content-Length"] = str(uzunluk)
        yanit["Content-Range"] = f"bytes {bas}-{son}/{boyut}"
        return baslikla(yanit)

    yanit = FileResponse(open(tam_yol, "rb"), content_type=tur)
    yanit["Content-Length"] = str(boyut)
    return baslikla(yanit)
