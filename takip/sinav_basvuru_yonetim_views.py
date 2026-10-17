"""Sınav başvuruları — yönetim paneli."""

from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST

from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
from takip.models import (
    SinavBasvuru,
    SinavBasvuruDurum,
    SinavBasvuruMesajLog,
    SinavBasvuruMesajSablon,
)
from config.branding import SINAV_BASVURU_BASLIK
from takip.push_bildirim_service import push_bildirim_aktif
from takip.sinav_basvuru_models import SINAV_BASVURU_SINIF_SECENEKLERI
from takip.sinav_bildirim_models import SinavBildirimLog, SinavTakvim
from takip.sinav_bildirim_service import (
    AN_BIR_GUN,
    AN_BITIS,
    AN_ETIKETLERI,
    AN_KAYIT,
    AN_SABAH,
    AN_UC_GUN,
    EPOSTA_ANLARI,
    guncel_takvim,
    sinav_eposta_aktif,
    zamanlanmis_anlar,
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


BOLUMLER = ("genel", "basvurular", "bildirimler", "ayarlar")


def _sinav_filtresi(request) -> str:
    """Parametre yoksa güncel sınav; "" (Tümü) seçilirse filtre yok."""
    if "sinav" in request.GET:
        return request.GET.get("sinav", "").strip()
    return SINAV_BASVURU_BASLIK


def _geri(request, bolum: str | None = None):
    bolum = bolum or request.POST.get("bolum") or request.GET.get("bolum") or "basvurular"
    if bolum not in BOLUMLER:
        bolum = "basvurular"
    return redirect(f"{reverse('yonetim:sinav_basvuru_listesi')}?bolum={bolum}")


def _filtreli_basvurular(request):
    basvurular = SinavBasvuru.objects.select_related("durum").annotate(
        bildirim_cihaz=Count("push_abonelikleri", distinct=True)
    )
    durum = request.GET.get("durum", "").strip()
    arama = request.GET.get("q", "").strip()
    sinav = _sinav_filtresi(request)
    sinif = request.GET.get("sinif", "").strip()

    if sinav:
        basvurular = basvurular.filter(sinav_adi=sinav)
    if sinif:
        basvurular = basvurular.filter(sinif=sinif)

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
            | Q(okul_adi__icontains=arama)
            | Q(veli_eposta__icontains=arama)
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

        if action == "takvim_kaydet":
            _takvim_kaydet(request)
            return _geri(request, "ayarlar")

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
            return _geri(request)

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
            return _geri(request)

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
            return _geri(request)

        if action == "toplu_durum":
            durum_id = request.POST.get("toplu_durum_id", "").strip()
            ids = request.POST.getlist("basvuru_ids")
            if not durum_id:
                messages.error(request, "Toplu uygulama için durum seçin.")
                return _geri(request)
            if not ids:
                messages.error(request, "En az bir başvuru seçin.")
                return _geri(request)
            yeni = get_object_or_404(SinavBasvuruDurum, pk=durum_id, aktif=True)
            qs = SinavBasvuru.objects.filter(pk__in=ids).select_related("durum")
            say = 0
            for basvuru in qs:
                if basvuru.durum_id != yeni.pk:
                    _durum_degistir_ve_mesaj(basvuru, yeni)
                    say += 1
            messages.success(request, f"{say} başvurunun durumu “{yeni.ad}” yapıldı.")
            return _geri(request)

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
            return _geri(request)

        messages.error(request, "Geçersiz işlem.")
        return _geri(request)

    bolum = request.GET.get("bolum", "genel")
    if bolum not in BOLUMLER:
        bolum = "genel"

    basvurular, durum, arama = _filtreli_basvurular(request)
    takvim = guncel_takvim()
    guncel = SinavBasvuru.objects.filter(sinav_adi=SINAV_BASVURU_BASLIK)
    cizelge = _zaman_cizelgesi(takvim, guncel)

    return render(
        request,
        "yonetim/seviye_tespit.html",
        {
            "bolum": bolum,
            "sinav_adi": SINAV_BASVURU_BASLIK,
            "takvim": takvim,
            "kalan": _kalan_metni(takvim),
            "genel": _genel_bakis(guncel),
            "zaman_cizelgesi": cizelge,
            "siradaki": next((z for z in cizelge if z["durum"] == "bekliyor"), None),
            "kanallar": {
                "bildirim": push_bildirim_aktif(),
                "eposta": sinav_eposta_aktif(),
                "takvim": takvim is not None,
            },
            "hatali_bildirimler": list(
                SinavBildirimLog.objects.filter(
                    basvuru__sinav_adi=SINAV_BASVURU_BASLIK
                )
                .exclude(push_hata="")
                .select_related("basvuru")[:10]
            ),
            "basvurular": basvurular,
            "basvuru_sayisi": guncel.count(),
            "durum_filtre": durum,
            "arama": arama,
            "sinav_filtre": _sinav_filtresi(request),
            "sinif_filtre": request.GET.get("sinif", "").strip(),
            "sinav_secenekleri": list(
                SinavBasvuru.objects.exclude(sinav_adi="")
                .order_by("sinav_adi")
                .values_list("sinav_adi", flat=True)
                .distinct()
            ),
            "sinif_secenekleri": SINAV_BASVURU_SINIF_SECENEKLERI,
            "durumlar": _aktif_durumlar(),
            "tum_durumlar": _tum_durumlar(),
        },
    )


def _takvim_kaydet(request) -> None:
    tz = timezone.get_current_timezone()
    try:
        gun = dt.date.fromisoformat(request.POST.get("tarih", "").strip())
        bas = dt.time.fromisoformat(request.POST.get("baslangic", "").strip())
        bit = dt.time.fromisoformat(request.POST.get("bitis", "").strip())
    except ValueError:
        messages.error(request, "Tarih ve saatleri kontrol edin.")
        return
    baslangic = dt.datetime.combine(gun, bas, tzinfo=tz)
    bitis = dt.datetime.combine(gun, bit, tzinfo=tz)
    if bitis <= baslangic:
        messages.error(request, "Bitiş saati başlangıçtan sonra olmalı.")
        return
    SinavTakvim.objects.update_or_create(
        sinav_adi=SINAV_BASVURU_BASLIK,
        defaults={
            "baslangic": baslangic,
            "bitis": bitis,
            "yer": request.POST.get("yer", "").strip()[:200],
            "bildirim_aktif": request.POST.get("bildirim_aktif") == "on",
        },
    )
    messages.success(request, "Sınav takvimi kaydedildi; hatırlatmalar yeni saatlere göre gidecek.")


def _kalan_metni(takvim: SinavTakvim | None) -> str:
    if not takvim:
        return ""
    simdi = timezone.localtime()
    bas = timezone.localtime(takvim.baslangic)
    bit = timezone.localtime(takvim.bitis)
    if simdi > bit:
        return "Sınav tamamlandı"
    if simdi >= bas:
        return "Sınav sürüyor"
    gun = (bas.date() - simdi.date()).days
    if gun == 0:
        return "Bugün"
    if gun == 1:
        return "Yarın"
    return f"{gun} gün kaldı"


def _genel_bakis(guncel) -> dict:
    toplam = guncel.count()
    sinif_sayilari = dict(
        guncel.exclude(sinif="")
        .order_by()
        .values("sinif")
        .annotate(n=Count("id", distinct=True))
        .values_list("sinif", "n")
    )
    en_cok = max(sinif_sayilari.values(), default=0)
    siniflar = [
        {
            "etiket": etiket,
            "sayi": sinif_sayilari.get(kod, 0),
            "oran": round(100 * sinif_sayilari.get(kod, 0) / en_cok) if en_cok else 0,
        }
        for kod, etiket in SINAV_BASVURU_SINIF_SECENEKLERI
    ]
    bildirim = guncel.filter(push_abonelikleri__isnull=False).distinct().count()
    takvim = guncel.filter(hatirlatma_turu="takvim").count()
    eposta = guncel.exclude(veli_eposta="").count()
    ilceler = list(
        guncel.order_by().values("ilce").annotate(n=Count("id", distinct=True)).order_by("-n", "ilce")[:5]
    )
    bugun = timezone.localdate()
    return {
        "toplam": toplam,
        "bugun": guncel.filter(olusturulma__date=bugun).count(),
        "bildirim": bildirim,
        "takvim": takvim,
        "eposta": eposta,
        "ulasilamayan": guncel.filter(push_abonelikleri__isnull=True)
        .exclude(hatirlatma_turu="takvim")
        .distinct()
        .count(),
        "siniflar": siniflar,
        "ilceler": ilceler,
        "son": list(guncel.select_related("durum").order_by("-olusturulma")[:6]),
    }


def _zaman_cizelgesi(takvim: SinavTakvim | None, guncel) -> list[dict]:
    loglar = SinavBildirimLog.objects.filter(basvuru__sinav_adi=SINAV_BASVURU_BASLIK)
    ozet = {
        row["an_kodu"]: row
        for row in loglar.order_by().values("an_kodu").annotate(
            kayit=Count("id"),
            cihaz=Count("id", filter=Q(gonderilen__gt=0)),
            eposta=Count("id", filter=Q(eposta_gonderildi=True)),
            hata=Count("id", filter=~Q(push_hata="")),
        )
    }
    takvim_anlari = {AN_UC_GUN, AN_BIR_GUN, AN_SABAH}
    simdi = timezone.now()
    satirlar = [
        {
            "kod": AN_KAYIT,
            "etiket": "Başvuru alındı",
            "zaman": None,
            "zaman_metni": "Başvuru anında",
            "durum": "surekli",
        }
    ]
    if takvim:
        for kod, plan in zamanlanmis_anlar(takvim):
            satirlar.append(
                {
                    "kod": kod,
                    "etiket": {
                        AN_UC_GUN: "Sınava 3 gün kaldı",
                        AN_BIR_GUN: "Sınav yarın",
                        AN_SABAH: "Bugün sınav günü",
                        AN_BITIS: "Sınav tamamlandı, teşekkürler",
                    }.get(kod, AN_ETIKETLERI.get(kod, kod)),
                    "zaman": plan,
                    "zaman_metni": "",
                    "durum": "gecti" if plan <= simdi else "bekliyor",
                }
            )
    for satir in satirlar:
        kod = satir["kod"]
        veri = ozet.get(kod, {})
        satir["kanallar"] = [
            k
            for k, var in (
                ("Bildirim", True),
                ("Takvim", kod in takvim_anlari),
                ("E-posta", kod in EPOSTA_ANLARI),
            )
            if var
        ]
        satir["cihaz"] = veri.get("cihaz", 0)
        satir["eposta"] = veri.get("eposta", 0)
        satir["hata"] = veri.get("hata", 0)
    return satirlar


@yonetici_gerekli
def sinav_basvuru_excel(request):
    basvurular, _, _ = _filtreli_basvurular(request)
    satirlar = []
    for b in basvurular:
        satirlar.append(
            [
                b.ad_soyad,
                b.get_sinif_display() if b.sinif else "",
                b.okul_adi,
                b.veli_eposta,
                b.get_hatirlatma_turu_display() if b.hatirlatma_turu else "",
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
            "Öğrenci ad soyad",
            "Sınıf",
            "Okul",
            "Veli e-posta",
            "Hatırlatma",
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
        durum_kolonlari=[15],
        vurgu_kolonlari=[0],
        genislikler=[18, 9, 20, 24, 14, 14, 14, 14, 14, 14, 14, 10, 12, 12, 22, 12, 16],
    )
    return excel_http_yanit(icerik, "sinav-basvurulari.xlsx")


@yonetici_gerekli
@require_POST
def sinav_basvuru_toplu_mesaj(request):
    an_kodu = request.POST.get("an_kodu", "").strip()
    ids = request.POST.getlist("basvuru_ids")
    if an_kodu not in SinavBasvuruMesajSablon.AnKodu.values:
        messages.error(request, "Geçersiz mesaj anı.")
        return _geri(request)

    qs = SinavBasvuru.objects.filter(pk__in=ids)
    if not qs.exists():
        messages.error(request, "Mesaj için başvuru seçin.")
        return _geri(request)

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
    return _geri(request)


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
            "bildirim_loglari": [
                {"log": log, "etiket": AN_ETIKETLERI.get(log.an_kodu, log.an_kodu)}
                for log in basvuru.bildirim_loglari.order_by("olusturulma")
            ],
            "bildirim_cihaz": basvuru.push_abonelikleri.count(),
        },
    )


@yonetici_gerekli
@require_POST
def sinav_basvuru_sil(request, pk):
    basvuru = get_object_or_404(SinavBasvuru, pk=pk)
    ad = basvuru.ad_soyad
    basvuru.delete()
    messages.success(request, f"{ad} başvurusu silindi.")
    return _geri(request)
