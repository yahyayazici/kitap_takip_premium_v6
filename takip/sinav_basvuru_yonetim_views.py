"""Sınav başvuruları — yönetim paneli."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST

from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
from takip.models import (
    SinavBasvuru,
    SinavBasvuruDurum,
    SinavBasvuruMesajLog,
    SinavBasvuruMesajSablon,
)
from takip.sinav_basvuru_mesaj_service import (
    basvuru_mesaji_gonder,
    basvurularda_mesaj_gonder,
    durum_icin_mesaj_an,
)
from takip.whatsapp_service import telefon_normalize, whatsapp_yapilandirilmis
from takip.yonetim_views import yonetici_gerekli

MANUEL_ANLAR = (
    SinavBasvuruMesajSablon.AnKodu.SINAV_DAVETI,
    SinavBasvuruMesajSablon.AnKodu.SONUC_BILDIRIMI,
    SinavBasvuruMesajSablon.AnKodu.BASVURU_ALINDI,
    SinavBasvuruMesajSablon.AnKodu.KABUL,
    SinavBasvuruMesajSablon.AnKodu.RED,
)


def _aktif_durumlar():
    return SinavBasvuruDurum.objects.filter(aktif=True).order_by("sira", "ad")


def _tum_durumlar():
    return SinavBasvuruDurum.objects.annotate(
        basvuru_sayisi=Count("basvurular")
    ).order_by("sira", "ad")


def _filtreli_basvurular(request):
    basvurular = SinavBasvuru.objects.select_related("durum").all()
    durum = request.GET.get("durum", "").strip()
    arama = request.GET.get("q", "").strip()

    if durum.isdigit():
        basvurular = basvurular.filter(durum_id=int(durum))
    elif durum:
        basvurular = basvurular.filter(durum__kod=durum)

    if arama:
        basvurular = basvurular.filter(
            Q(ad_soyad__icontains=arama)
            | Q(baba_telefon__icontains=arama)
            | Q(anne_telefon__icontains=arama)
            | Q(baba_adi__icontains=arama)
            | Q(anne_adi__icontains=arama)
            | Q(il__icontains=arama)
            | Q(ilce__icontains=arama)
        )
    return basvurular, durum, arama


def _durum_degistir_ve_mesaj(basvuru: SinavBasvuru, yeni_durum: SinavBasvuruDurum) -> None:
    onceki = basvuru.durum_id
    if onceki == yeni_durum.pk:
        return
    basvuru.durum = yeni_durum
    basvuru.save(update_fields=["durum", "guncellenme"])
    an = durum_icin_mesaj_an(yeni_durum)
    if an:
        try:
            basvuru_mesaji_gonder(basvuru, an, sadece_aktif=True)
        except Exception:  # noqa: BLE001
            pass


@yonetici_gerekli
@require_http_methods(["GET", "POST"])
def sinav_basvuru_listesi(request):
    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "durum_ekle":
            ad = request.POST.get("durum_ad", "").strip()
            kod = slugify(request.POST.get("durum_kod", "").strip() or ad, allow_unicode=True)
            mesaj_an = request.POST.get("mesaj_an_kodu", "").strip()
            if not ad or not kod:
                messages.error(request, "Durum adı gerekli.")
            elif SinavBasvuruDurum.objects.filter(kod=kod).exists():
                messages.error(request, "Bu kod zaten var.")
            else:
                sira = (SinavBasvuruDurum.objects.count() + 1) * 10
                SinavBasvuruDurum.objects.create(
                    ad=ad,
                    kod=kod,
                    sira=sira,
                    aktif=True,
                    mesaj_an_kodu=mesaj_an,
                )
                messages.success(request, f"“{ad}” durumu eklendi.")
            return redirect("yonetim:sinav_basvuru_listesi")

        if action == "durum_sil":
            durum_id = request.POST.get("durum_id", "").strip()
            durum = get_object_or_404(SinavBasvuruDurum, pk=durum_id)
            if durum.basvurular.exists():
                messages.error(
                    request,
                    f"“{durum.ad}” durumunda başvuru var; silinemez. Pasif yapın.",
                )
            else:
                ad = durum.ad
                durum.delete()
                messages.success(request, f"“{ad}” silindi.")
            return redirect("yonetim:sinav_basvuru_listesi")

        if action == "durum_toggle":
            durum = get_object_or_404(
                SinavBasvuruDurum, pk=request.POST.get("durum_id")
            )
            durum.aktif = not durum.aktif
            durum.save(update_fields=["aktif", "guncellenme"])
            messages.success(
                request,
                f"“{durum.ad}” {'aktif' if durum.aktif else 'pasif'} yapıldı.",
            )
            return redirect("yonetim:sinav_basvuru_listesi")

        if action == "toplu_durum":
            durum_id = request.POST.get("toplu_durum_id", "").strip()
            ids = request.POST.getlist("basvuru_ids")
            if not durum_id:
                messages.error(request, "Toplu uygulama için durum seçin.")
                return redirect("yonetim:sinav_basvuru_listesi")
            if not ids:
                messages.error(request, "En az bir başvuru seçin.")
                return redirect("yonetim:sinav_basvuru_listesi")
            yeni = get_object_or_404(SinavBasvuruDurum, pk=durum_id, aktif=True)
            qs = SinavBasvuru.objects.filter(pk__in=ids).select_related("durum")
            say = 0
            for basvuru in qs:
                if basvuru.durum_id != yeni.pk:
                    _durum_degistir_ve_mesaj(basvuru, yeni)
                    say += 1
            messages.success(request, f"{say} başvurunun durumu “{yeni.ad}” yapıldı.")
            return redirect("yonetim:sinav_basvuru_listesi")

        if action == "satir_durumlar":
            aktif_ids = set(
                SinavBasvuruDurum.objects.filter(aktif=True).values_list("pk", flat=True)
            )
            say = 0
            for key, val in request.POST.items():
                if not key.startswith("durum_"):
                    continue
                try:
                    basvuru_id = int(key.replace("durum_", "", 1))
                    durum_id = int(val)
                except (TypeError, ValueError):
                    continue
                if durum_id not in aktif_ids:
                    continue
                basvuru = SinavBasvuru.objects.filter(pk=basvuru_id).select_related(
                    "durum"
                ).first()
                if not basvuru or basvuru.durum_id == durum_id:
                    continue
                yeni = SinavBasvuruDurum.objects.get(pk=durum_id)
                _durum_degistir_ve_mesaj(basvuru, yeni)
                say += 1
            messages.success(request, f"{say} durum güncellendi.")
            return redirect("yonetim:sinav_basvuru_listesi")

        messages.error(request, "Geçersiz işlem.")
        return redirect("yonetim:sinav_basvuru_listesi")

    basvurular, durum, arama = _filtreli_basvurular(request)
    manuel_sablonlar = SinavBasvuruMesajSablon.objects.filter(
        an_kodu__in=MANUEL_ANLAR
    ).order_by("sira")

    return render(
        request,
        "yonetim/sinav_basvuru_listesi.html",
        {
            "basvurular": basvurular,
            "durum_filtre": durum,
            "arama": arama,
            "durumlar": _aktif_durumlar(),
            "tum_durumlar": _tum_durumlar(),
            "manuel_sablonlar": manuel_sablonlar,
            "whatsapp_aktif": whatsapp_yapilandirilmis(),
            "mesaj_an_secenekleri": SinavBasvuruMesajSablon.AnKodu.choices,
        },
    )


@yonetici_gerekli
def sinav_basvuru_excel(request):
    basvurular, _, _ = _filtreli_basvurular(request)
    satirlar = []
    for b in basvurular:
        satirlar.append(
            [
                b.ad_soyad,
                b.baba_adi,
                b.baba_telefon,
                telefon_normalize(b.baba_telefon),
                b.anne_adi,
                b.anne_telefon,
                telefon_normalize(b.anne_telefon),
                b.il,
                b.ilce,
                b.dogum_tarihi.strftime("%d.%m.%Y") if b.dogum_tarihi else "",
                b.sinav_adi,
                b.durum.ad if b.durum_id else "",
                b.olusturulma.strftime("%d.%m.%Y %H:%M") if b.olusturulma else "",
            ]
        )

    icerik = basit_rapor_xlsx(
        baslik="Sınav Başvuruları",
        alt_baslik="WhatsApp / SMS kampanya listesi",
        kolon_basliklari=[
            "Ad soyad",
            "Baba adı",
            "Baba tel",
            "Baba tel (90…)",
            "Anne adı",
            "Anne tel",
            "Anne tel (90…)",
            "İl",
            "İlçe",
            "Doğum tarihi",
            "Sınav",
            "Durum",
            "Başvuru zamanı",
        ],
        satirlar=satirlar,
        durum_kolonlari=[11],
        vurgu_kolonlari=[0],
        genislikler=[18, 14, 14, 14, 14, 14, 14, 10, 12, 12, 22, 12, 16],
    )
    return excel_http_yanit(icerik, "sinav-basvurulari.xlsx")


@yonetici_gerekli
@require_POST
def sinav_basvuru_toplu_mesaj(request):
    an_kodu = request.POST.get("an_kodu", "").strip()
    ids = request.POST.getlist("basvuru_ids")
    if an_kodu not in SinavBasvuruMesajSablon.AnKodu.values:
        messages.error(request, "Geçersiz mesaj anı.")
        return redirect("yonetim:sinav_basvuru_listesi")

    qs = SinavBasvuru.objects.filter(pk__in=ids)
    if not qs.exists():
        messages.error(request, "Mesaj için başvuru seçin.")
        return redirect("yonetim:sinav_basvuru_listesi")

    ozet = basvurularda_mesaj_gonder(qs, an_kodu, sadece_aktif=False)
    messages.success(
        request,
        (
            f"Mesaj işlemi: {ozet['toplam']} deneme — "
            f"{ozet['gonderildi']} gönderildi, "
            f"{ozet['hata']} hata, "
            f"{ozet['atlandi']} atlandı."
        ),
    )
    return redirect("yonetim:sinav_basvuru_listesi")


@yonetici_gerekli
@require_http_methods(["GET", "POST"])
def sinav_basvuru_detay(request, pk):
    basvuru = get_object_or_404(
        SinavBasvuru.objects.select_related("durum"), pk=pk
    )
    onceki_durum_id = basvuru.durum_id

    if request.method == "POST":
        action = request.POST.get("action", "kaydet").strip()
        if action == "mesaj_gonder":
            an_kodu = request.POST.get("an_kodu", "").strip()
            if an_kodu in SinavBasvuruMesajSablon.AnKodu.values:
                loglar = basvuru_mesaji_gonder(
                    basvuru, an_kodu, sadece_aktif=False
                )
                ok = sum(
                    1
                    for log in loglar
                    if log.durum == SinavBasvuruMesajLog.Durum.GONDERILDI
                )
                messages.success(
                    request,
                    f"Mesaj: {ok}/{len(loglar)} gönderildi.",
                )
            else:
                messages.error(request, "Geçersiz mesaj anı.")
            return redirect("yonetim:sinav_basvuru_detay", pk=basvuru.pk)

        yeni_durum_id = request.POST.get("durum", "").strip()
        notlar = request.POST.get("notlar", "").strip()
        yeni = None
        if yeni_durum_id.isdigit():
            yeni = SinavBasvuruDurum.objects.filter(pk=int(yeni_durum_id)).first()
            if (
                yeni
                and not yeni.aktif
                and yeni.pk != onceki_durum_id
            ):
                messages.error(request, "Pasif duruma geçilemez.")
                return redirect("yonetim:sinav_basvuru_detay", pk=basvuru.pk)
        if yeni:
            basvuru.durum = yeni
        basvuru.notlar = notlar
        basvuru.save(update_fields=["durum", "notlar", "guncellenme"])

        if yeni and yeni.pk != onceki_durum_id:
            an = durum_icin_mesaj_an(yeni)
            if an:
                try:
                    basvuru_mesaji_gonder(basvuru, an, sadece_aktif=True)
                except Exception:  # noqa: BLE001
                    messages.warning(
                        request,
                        "Durum kaydedildi; WhatsApp mesajı gönderilemedi.",
                    )

        messages.success(request, "Başvuru güncellendi.")
        return redirect("yonetim:sinav_basvuru_detay", pk=basvuru.pk)

    loglar = basvuru.mesaj_loglari.select_related("sablon").all()[:40]
    manuel_sablonlar = SinavBasvuruMesajSablon.objects.filter(
        an_kodu__in=MANUEL_ANLAR
    ).order_by("sira")

    return render(
        request,
        "yonetim/sinav_basvuru_detay.html",
        {
            "basvuru": basvuru,
            "durumlar": _aktif_durumlar(),
            "mesaj_loglari": loglar,
            "manuel_sablonlar": manuel_sablonlar,
            "whatsapp_aktif": whatsapp_yapilandirilmis(),
        },
    )


@yonetici_gerekli
@require_POST
def sinav_basvuru_sil(request, pk):
    basvuru = get_object_or_404(SinavBasvuru, pk=pk)
    ad = basvuru.ad_soyad
    basvuru.delete()
    messages.success(request, f"{ad} başvurusu silindi.")
    return redirect("yonetim:sinav_basvuru_listesi")
