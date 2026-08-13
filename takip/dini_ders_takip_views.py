"""Dini ders takip — toplu çizelge ve rapor."""

from __future__ import annotations

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.timezone import localdate

from takip.dini_ilerleme_service import (
    DURUM_ETIKETLERI,
    beklenen_yuzde,
    gruplar_karsilastirma,
    grup_saglik_ozeti,
    rapor_talebe_satirlari,
)
from takip.dini_ders_takip_service import (
    cizelge_sidebar_ozeti,
    duzenleyebilir,
    kayitlari_kaydet,
    temizle_sahte_devam_kayitlari,
    konular_for,
    rapor_ozeti,
    son_islenen_konular,
    talebe_matris_satirlari,
    yetkili_dini_talebeler,
)
from takip.models import DiniDersSeviyesi, DiniDersTakipAlani
from takip.permissions.decorators import require_permission
from takip.permissions.scope import tum_talebe_kapsami_var
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user


@login_required
@require_permission("dini_ders_takip", "view")
def dini_ders_panel(request):
    seviyeler = DiniDersSeviyesi.objects.filter(aktif=True).order_by("sira", "ad")
    alanlar = DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad")

    hoca = etut_hocasi_for_user(request.user)
    seviye_kilitli = False
    # Etüt hocası: yalnızca kendisine atanmış dini seviyeler
    if hoca and not request.user.is_superuser and not tum_talebe_kapsami_var(request.user):
        atanan = list(
            hoca.sorumlu_dini_ders_seviyeleri.filter(aktif=True).order_by("sira", "ad")
        )
        if atanan:
            seviyeler = DiniDersSeviyesi.objects.filter(
                pk__in=[s.pk for s in atanan]
            ).order_by("sira", "ad")
            if len(atanan) == 1:
                seviye_kilitli = True

    seviye_id = request.GET.get("seviye") or request.POST.get("seviye_id")
    alan_id = request.GET.get("alan") or request.POST.get("alan_id")

    if seviye_kilitli:
        seviye_id = str(seviyeler.first().pk)
    elif seviye_id and not seviyeler.filter(pk=seviye_id).exists():
        seviye_id = None

    # Örnek görünüm: seçim yoksa ilk dolu seviye + alan
    if not seviye_id and not request.POST:
        for s in seviyeler:
            if yetkili_dini_talebeler(request.user).filter(dini_ders_seviyesi=s).exists():
                seviye_id = str(s.pk)
                break
        if not seviye_id and seviyeler.exists():
            seviye_id = str(seviyeler.first().pk)
    # Seçili seviyede konu listesi (alan) olanları göster
    seviye_secili = seviyeler.filter(pk=seviye_id).first() if seviye_id else None
    if seviye_secili:
        alan_ids = list(
            DiniDersTakipAlani.objects.filter(
                aktif=True,
                konular__seviye=seviye_secili,
                konular__aktif=True,
            )
            .distinct()
            .values_list("id", flat=True)
        )
        if alan_ids:
            alanlar = alanlar.filter(pk__in=alan_ids)

    if not alan_id and not request.POST and alanlar.exists():
        # Seçili seviyede konu olan ilk alan
        if seviye_secili:
            for a in alanlar:
                if konular_for(seviye_secili, a).exists():
                    alan_id = str(a.pk)
                    break
        if not alan_id:
            alan_id = str(alanlar.first().pk)

    seviye = None
    alan = None
    konular = []
    talebeler = yetkili_dini_talebeler(request.user).none()
    talebe_satirlari = []
    sidebar_ozet = None
    son_kayitlar = []
    beklenen_yuzde_deger = None

    if seviye_id and alan_id:
        seviye = seviyeler.filter(pk=seviye_id).first()
        alan = alanlar.filter(pk=alan_id).first()
        if seviye and alan:
            konular = list(konular_for(seviye, alan))
            talebeler = (
                yetkili_dini_talebeler(request.user)
                .filter(dini_ders_seviyesi=seviye)
                .order_by("ad_soyad")
            )

            talebe_ids = list(talebeler.values_list("id", flat=True))
            konu_ids = [k.id for k in konular]

            if duzenleyebilir(request.user):
                # Eski kayıt mantığından kalan boş "devam" kabuklarını temizle
                temizle_sahte_devam_kayitlari(talebe_ids, konu_ids)

            if request.method == "POST" and duzenleyebilir(request.user):
                durumlar: dict[tuple[int, int], str] = {}
                for key, value in request.POST.items():
                    if key.startswith("d_"):
                        parts = key.split("_")
                        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                            val = (value or "bos").strip().lower()
                            if val not in {"bos", "devam", "tamam"}:
                                val = "bos"
                            durumlar[(int(parts[1]), int(parts[2]))] = val
                    elif key.startswith("k_"):
                        # Eski checkbox uyumu
                        parts = key.split("_")
                        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                            durumlar[(int(parts[1]), int(parts[2]))] = "tamam"
                guncellenen = kayitlari_kaydet(
                    request.user,
                    talebe_ids,
                    konu_ids,
                    durumlar,
                )
                messages.success(
                    request,
                    f"Çizelge kaydedildi ({guncellenen} değişiklik).",
                )
                return redirect(
                    f"{request.path}?seviye={seviye.pk}&alan={alan.pk}"
                )

            talebe_satirlari = talebe_matris_satirlari(talebeler, konular)
            sidebar_ozet = cizelge_sidebar_ozeti(talebeler, konular)
            son_kayitlar = son_islenen_konular(talebeler, konular)
            beklenen_yuzde_deger = beklenen_yuzde(seviye, alan)

    ornek_cizelge_link = None
    seviye_ornek = seviyeler.filter(ad="Seviye 1").first()
    alan_ornek = alanlar.filter(ad="Sure Ezberi").first()
    if seviye_ornek and alan_ornek:
        ornek_cizelge_link = (
            f"{request.path}?seviye={seviye_ornek.pk}&alan={alan_ornek.pk}"
        )

    return render(
        request,
        "dini_ders_panel.html",
        {
            "seviyeler": seviyeler,
            "alanlar": alanlar,
            "seviye": seviye,
            "alan": alan,
            "konular": konular,
            "talebeler": talebeler,
            "talebe_satirlari": talebe_satirlari,
            "sidebar_ozet": sidebar_ozet,
            "son_kayitlar": son_kayitlar,
            "duzenleyebilir": duzenleyebilir(request.user),
            "ornek_cizelge_link": ornek_cizelge_link,
            "seviye_kilitli": seviye_kilitli,
            "beklenen_yuzde_deger": beklenen_yuzde_deger,
        },
    )


@login_required
@require_permission("dini_ders_takip", "view")
def dini_ders_rapor(request):
    if request.GET.get("format") == "excel" and can(
        request.user, "dini_ders_takip", "export_excel"
    ):
        return dini_ders_excel(request)

    seviyeler = DiniDersSeviyesi.objects.filter(aktif=True).order_by("sira", "ad")
    alanlar = DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad")

    seviye_id = request.GET.get("seviye")
    alan_id = request.GET.get("alan")
    seviye = seviyeler.filter(pk=seviye_id).first() if seviye_id else None
    alan = alanlar.filter(pk=alan_id).first() if alan_id else None

    talebeler = yetkili_dini_talebeler(request.user)
    rapor_ozet = rapor_ozeti(talebeler, seviye=seviye, alan=alan)
    satirlar = rapor_talebe_satirlari(talebeler, seviye, alan)

    grup_karsilastirma = []
    grup_ozetleri = []
    if seviye:
        if request.user.is_superuser or tum_talebe_kapsami_var(request.user):
            grup_karsilastirma = gruplar_karsilastirma(seviye.id)
        if alan:
            hoca_ids = {
                hoca_id
                for hoca_id in talebeler.filter(dini_ders_hocasi_id__isnull=False)
                .values_list("dini_ders_hocasi_id", flat=True)
                if hoca_id
            }
            from takip.models import EtutHocasi

            hoca_map = {
                h.id: h
                for h in EtutHocasi.objects.filter(pk__in=list(hoca_ids))
            }
            for hoca_id in hoca_ids:
                saglik = grup_saglik_ozeti(hoca_id, seviye.id, alan=alan)
                alan_saglik = saglik["alanlar"][0] if saglik.get("alanlar") else None
                if not alan_saglik:
                    continue
                hoca = hoca_map.get(hoca_id)
                durum_listesi = [
                    {
                        "kod": kod,
                        "adet": adet,
                        "etiket": DURUM_ETIKETLERI.get(kod, (kod, "muted"))[0],
                        "sinif": DURUM_ETIKETLERI.get(kod, (kod, "muted"))[1],
                    }
                    for kod, adet in alan_saglik.get("durum_dagilimi", {}).items()
                ]
                fark = alan_saglik.get("plan_fark", 0)
                if fark > 0:
                    fark_metni = f"{fark} puan önde"
                elif fark < 0:
                    fark_metni = f"{abs(fark)} puan geride"
                else:
                    fark_metni = "Plana uygun"
                grup_ozetleri.append(
                    {
                        "hoca_id": hoca_id,
                        "hoca_ad": hoca.ad_soyad if hoca else "—",
                        "durum_listesi": durum_listesi,
                        "plan_fark_metni": fark_metni,
                        **alan_saglik,
                    }
                )

    beklenen_genel = beklenen_yuzde(seviye, alan) if seviye and alan else None

    return render(
        request,
        "dini_ders_rapor.html",
        {
            "seviyeler": seviyeler,
            "alanlar": alanlar,
            "seviye": seviye,
            "alan": alan,
            "rapor_ozet": rapor_ozet,
            "satirlar": satirlar,
            "grup_karsilastirma": grup_karsilastirma,
            "grup_ozetleri": grup_ozetleri,
            "beklenen_genel": beklenen_genel,
            "durum_etiketleri": DURUM_ETIKETLERI,
        },
    )


@login_required
@require_permission("dini_ders_takip", "export_excel")
def dini_ders_excel(request):
    from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit

    seviye_id = request.GET.get("seviye")
    alan_id = request.GET.get("alan")
    seviye = (
        DiniDersSeviyesi.objects.filter(pk=seviye_id).first()
        if seviye_id
        else None
    )
    alan = (
        DiniDersTakipAlani.objects.filter(pk=alan_id).first()
        if alan_id
        else None
    )

    talebeler = yetkili_dini_talebeler(request.user).order_by("ad_soyad")
    if seviye:
        talebeler = talebeler.filter(dini_ders_seviyesi=seviye)

    from takip.models import DiniDersKonu, DiniDersKonuKaydi

    konu_qs = DiniDersKonu.objects.filter(aktif=True).select_related(
        "alan", "seviye"
    )
    if seviye:
        konu_qs = konu_qs.filter(seviye=seviye)
    if alan:
        konu_qs = konu_qs.filter(alan=alan)

    kayit_map = {
        (k.talebe_id, k.konu_id): k
        for k in DiniDersKonuKaydi.objects.filter(
            talebe__in=talebeler,
            konu__in=konu_qs,
        ).select_related("talebe", "konu")
    }

    satirlar = []
    for talebe in talebeler:
        if not talebe.dini_ders_seviyesi_id:
            continue
        for konu in konu_qs.filter(seviye=talebe.dini_ders_seviyesi):
            kayit = kayit_map.get((talebe.id, konu.id))
            satirlar.append(
                [
                    (talebe.ad_soyad or "").upper(),
                    talebe.dini_ders_seviyesi.ad,
                    konu.alan.ad,
                    konu.ad,
                    "Tamamlandı" if kayit and kayit.tamamlandi else "Bekliyor",
                    kayit.guncellenme.strftime("%d.%m.%Y %H:%M") if kayit else "",
                ]
            )

    icerik = basit_rapor_xlsx(
        baslik="Dini Ders Takip Raporu",
        alt_baslik=localdate().strftime("%d.%m.%Y"),
        kolon_basliklari=["Ad-Soyad", "Seviye", "Alan", "Konu", "Durum", "Güncellenme"],
        satirlar=satirlar,
        sayfa_adi="Dini Ders",
        durum_kolonlari=[4],
        ortala_kolonlari=[1, 5],
        genislikler=[26, 14, 14, 22, 14, 16],
    )
    return excel_http_yanit(icerik, f"dini-ders-rapor_{localdate():%Y%m%d}.xlsx")
