"""Ana sitenin (cinilisarayproje.com) sonuçları çekmesi için salt-okunur JSON API.

İstekler `Authorization: Bearer <OKUMA_API_TOKEN>` başlığı taşımalıdır.
"""

import hmac
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from okuma.models import Deneme
from okuma.services import analiz


def token_gerekli(view):
    @wraps(view)
    def sarici(request, *args, **kwargs):
        beklenen = settings.OKUMA_API_TOKEN
        gelen = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not beklenen or not hmac.compare_digest(gelen, beklenen):
            return JsonResponse({"hata": "yetkisiz"}, status=401)
        return view(request, *args, **kwargs)

    return sarici


def _f(d):
    return float(d) if d is not None else None


def saglik(request):
    return JsonResponse({"durum": "ok"})


@token_gerekli
def denemeler(request):
    veri = [
        {
            "id": d.pk,
            "ad": d.ad,
            "tarih": d.tarih.isoformat(),
            "sinif_seviyesi": d.sinif_seviyesi,
            "sinav_turu": d.sinav_turu,
            "hesaplanma": d.hesaplanma.isoformat() if d.hesaplanma else None,
        }
        for d in Deneme.objects.all()
    ]
    return JsonResponse({"denemeler": veri})


@token_gerekli
def deneme_sonuclari(request, pk):
    deneme = get_object_or_404(Deneme, pk=pk)
    testler = list(deneme.testler.all())
    sonuclar = deneme.sonuclar.select_related("ogrenci").prefetch_related("test_sonuclari").order_by("sira_kurum")
    kazanim_sonuclari = {}
    if request.GET.get("kazanim") == "1":
        for s in sonuclar:
            kazanim_sonuclari[s.pk] = [
                {"ders": k.ders, "kod": k.kazanim.kod, "kazanim": k.kazanim.metin, "oran": k.oran}
                for k in analiz.ogrenci_kazanimlari(s)
            ]
    return JsonResponse(
        {
            "deneme": {
                "id": deneme.pk,
                "ad": deneme.ad,
                "tarih": deneme.tarih.isoformat(),
                "puan_modu": deneme.puan_modu,
                "testler": [{"id": t.pk, "ders": t.ders, "soru_sayisi": t.soru_sayisi} for t in testler],
            },
            "sonuclar": [
                {
                    "numara": s.ogrenci.numara,
                    "dis_kimlik": s.ogrenci.dis_kimlik or None,
                    "ad_soyad": s.ogrenci.ad_soyad,
                    "sube": s.sube,
                    "kitapcik": s.kitapcik,
                    "dogru": s.dogru,
                    "yanlis": s.yanlis,
                    "bos": s.bos,
                    "net": _f(s.net),
                    "puan": _f(s.puan),
                    "sira_kurum": s.sira_kurum,
                    "sira_sube": s.sira_sube,
                    "katilimci": s.katilimci,
                    "yuzdelik": _f(s.yuzdelik),
                    "testler": [
                        {"test_id": ts.test_id, "dogru": ts.dogru, "yanlis": ts.yanlis, "bos": ts.bos, "net": _f(ts.net)}
                        for ts in s.test_sonuclari.all()
                    ],
                    **({"kazanimlar": kazanim_sonuclari[s.pk]} if kazanim_sonuclari else {}),
                }
                for s in sonuclar
            ],
        },
        json_dumps_params={"ensure_ascii": False},
    )
