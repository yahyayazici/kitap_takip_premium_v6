"""Personel toplantı — vazife senkronu, PDF, arşiv."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import AbstractBaseUser
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils.timezone import localdate

from config.branding import panel_branding_context
from takip.models import PersonelProfili
from takip.personel_toplanti_models import PersonelToplantiKarar, PersonelToplantisi
from takip.vazife_models import PersonelVazife


def sonraki_toplanti_no(*, yil: int | None = None) -> str:
    yil = yil or localdate().year
    prefix = f"PT-{yil}-"
    son = (
        PersonelToplantisi.objects.filter(toplanti_no__startswith=prefix)
        .order_by("-toplanti_no")
        .values_list("toplanti_no", flat=True)
        .first()
    )
    if son:
        try:
            seq = int(son.rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = PersonelToplantisi.objects.filter(tarih__year=yil).count() + 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"


def katilimci_satirlari(toplanti: PersonelToplantisi) -> list[str]:
    secilen = list(
        toplanti.katilimci_personeller.order_by("ad_soyad").values_list(
            "ad_soyad", flat=True
        )
    )
    if secilen:
        return secilen
    return [s.strip() for s in (toplanti.katilimcilar_metin or "").splitlines() if s.strip()]


@transaction.atomic
def karar_vazife_senkron(
    karar: PersonelToplantiKarar,
    *,
    atayan: AbstractBaseUser | None,
) -> PersonelVazife | None:
    """Yapılacak/takip kararını personele vazife olarak yansıt."""
    if not karar.vazife_gerekli_mi:
        if karar.vazife_id and karar.durum == PersonelToplantiKarar.Durum.IPTAL:
            v = karar.vazife
            v.durum = PersonelVazife.Durum.IPTAL
            v.save(update_fields=["durum", "guncellenme"])
        return karar.vazife

    toplanti = karar.toplanti
    baslik = (karar.metin or "").strip()[:200] or f"{toplanti.toplanti_no} kararı"
    aciklama = (
        f"Personel toplantısı {toplanti.toplanti_no} · {toplanti.baslik}\n"
        f"Tür: {karar.get_tur_display()}"
    )
    oncelik = (
        PersonelVazife.Oncelik.YUKSEK
        if karar.tur == PersonelToplantiKarar.Tur.TAKIP
        else PersonelVazife.Oncelik.NORMAL
    )
    bitis = karar.kontrol_tarihi or toplanti.tarih

    if karar.vazife_id:
        v = karar.vazife
        v.baslik = baslik
        v.aciklama = aciklama
        v.atanan = karar.sorumlu
        v.baslangic = toplanti.tarih
        v.bitis = bitis
        v.oncelik = oncelik
        if karar.durum == PersonelToplantiKarar.Durum.TAMAM:
            v.durum = PersonelVazife.Durum.TAMAMLANDI
        elif v.durum in {PersonelVazife.Durum.IPTAL, PersonelVazife.Durum.TAMAMLANDI}:
            v.durum = PersonelVazife.Durum.ATANDI
        v.save()
    else:
        v = PersonelVazife.objects.create(
            baslik=baslik,
            aciklama=aciklama,
            atanan=karar.sorumlu,
            atayan=atayan,
            baslangic=toplanti.tarih,
            bitis=bitis,
            oncelik=oncelik,
            durum=PersonelVazife.Durum.ATANDI,
            toplanti_karar=karar,
        )
        karar.vazife = v
        karar.save(update_fields=["vazife", "guncellenme"])

    if atayan:
        from takip.bildirim_service import vazife_bildirimi_gonder

        vazife_bildirimi_gonder(v, olusturan=atayan)
    return v


def tum_kararlari_senkron(toplanti: PersonelToplantisi, *, atayan) -> None:
    for karar in toplanti.kararlar.select_related("sorumlu", "vazife"):
        karar_vazife_senkron(karar, atayan=atayan)


def pdf_baglam(user, toplanti: PersonelToplantisi) -> dict:
    gundem = list(toplanti.gundem_maddeleri.order_by("sira", "id"))
    kararlar = list(
        toplanti.kararlar.select_related("sorumlu").order_by("sira", "id")
    )
    yapilacaklar = [
        k
        for k in kararlar
        if k.tur
        in (PersonelToplantiKarar.Tur.YAPILACAK, PersonelToplantiKarar.Tur.TAKIP)
    ]
    katilimcilar = katilimci_satirlari(toplanti)
    pdf_satir_sayisi = len(gundem) + len(yapilacaklar) + max(1, len(katilimcilar) // 3)
    return {
        "toplanti": toplanti,
        "gundem_maddeleri": gundem,
        "kararlar": kararlar,
        "yapilacaklar": yapilacaklar,
        "takipler": [k for k in kararlar if k.tur == PersonelToplantiKarar.Tur.TAKIP],
        "kararlar_sade": [k for k in kararlar if k.tur == PersonelToplantiKarar.Tur.KARAR],
        "katilimcilar": katilimcilar,
        "pdf_satir_sayisi": pdf_satir_sayisi,
        "bugun": localdate(),
        **panel_branding_context(),
    }


def tutanak_pdf_kaydet(toplanti: PersonelToplantisi, pdf_bytes: bytes) -> None:
    ad = f"{toplanti.toplanti_no.replace('/', '-')}_tutanak.pdf"
    if toplanti.tutanak_pdf:
        toplanti.tutanak_pdf.delete(save=False)
    toplanti.tutanak_pdf.save(ad, ContentFile(pdf_bytes), save=True)


def toplanti_tamamla(toplanti: PersonelToplantisi, *, atayan) -> None:
    toplanti.durum = PersonelToplantisi.Durum.TAMAMLANDI
    toplanti.arsivlandi = True
    toplanti.save(update_fields=["durum", "arsivlandi", "guncellenme"])
    tum_kararlari_senkron(toplanti, atayan=atayan)


def karar_sira_ver(toplanti: PersonelToplantisi) -> int:
    mevcut = toplanti.kararlar.aggregate(m=Max("sira")).get("m") or 0
    return mevcut + 1


def idareci_toplanti_ozet() -> dict:
    bugun = localdate()
    return {
        "toplam": PersonelToplantisi.objects.count(),
        "bu_ay": PersonelToplantisi.objects.filter(
            tarih__year=bugun.year,
            tarih__month=bugun.month,
        ).count(),
        "acik_karar": PersonelToplantiKarar.objects.exclude(
            durum__in=(
                PersonelToplantiKarar.Durum.TAMAM,
                PersonelToplantiKarar.Durum.IPTAL,
            )
        ).count(),
        "arsiv": PersonelToplantisi.objects.filter(arsivlandi=True).count(),
    }
