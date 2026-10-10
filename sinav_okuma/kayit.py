"""Okunan satırları bu uygulamanın tablolarına yazar."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from sinav_okuma.models import Sinav, SinavSatiri, SinavSoru
from sinav_okuma.okuma import PuanSatiri


def sonuclari_yaz(sinav: Sinav, satirlar: list[PuanSatiri], *, dosya_adi: str, notlar: list[str]) -> int:
    """Bu sınavın önceki okumasını siler, yeni satırları koyar."""
    with transaction.atomic():
        sinav.satirlar.all().delete()
        nesneler = [
            SinavSatiri(
                sinav=sinav,
                satir_no=satir.satir_no,
                ogrenci_no=(satir.ogrenci_no or "")[:32],
                ad=(satir.ad or "")[:200],
                kitapcik=(satir.kitapcik or "")[:4],
                sinif_metni=(satir.sinif_metni or "")[:120],
                uyarilar="\n".join(satir.uyarilar),
                cevaplar=satir.cevaplar,
                puanlandi=satir.puanlandi,
                dogru=satir.dogru if satir.puanlandi else 0,
                yanlis=satir.yanlis if satir.puanlandi else 0,
                bos=satir.bos if satir.puanlandi else 0,
                net=Decimal(satir.net) if satir.puanlandi else Decimal("0"),
                puan=Decimal(satir.puan) if satir.puan else None,
            )
            for satir in satirlar
        ]
        SinavSatiri.objects.bulk_create(nesneler)
        sorular = []
        for kayit, satir in zip(nesneler, satirlar):
            if not satir.puanlandi:
                continue
            for soru in satir.sorular:
                sorular.append(
                    SinavSoru(
                        satir=kayit,
                        ders_key=soru["ders_key"][:40],
                        soru_no=int(soru["soru_no"]),
                        sonuc=soru["sonuc"][:10],
                        konu_ad=(soru.get("konu_ad") or "")[:300],
                        sira=int(soru.get("sira") or 0),
                    )
                )
        if sorular:
            SinavSoru.objects.bulk_create(sorular, batch_size=500)
        sinav.son_dosya = (dosya_adi or "")[:255]
        sinav.okuma_notu = "\n".join(notlar)
        sinav.save(update_fields=["son_dosya", "okuma_notu", "guncellenme"])
    return len(nesneler)
