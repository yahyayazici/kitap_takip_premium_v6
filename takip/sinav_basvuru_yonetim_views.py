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
from takip.sinav_salon_service import (
    YerlesimHatasi,
    kelebek_yerlestir,
    salon_ozeti,
    salonlari_kaydet,
    yerlesim_bul,
)
from takip.sinav_sonuc_models import SinavSonuc
from takip.sinav_sonuc_service import (
    DERSLER,
    VARSAYILAN_MESAJ,
    KarneHatasi,
    excel_onizle,
    karne_kaydet,
    mesaj_doldur,
    sonuc_mesaji_sablonu,
    sonuclari_arka_planda_gonder,
    sonuclari_kaydet,
    toplu_karne_kaydet,
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


BOLUMLER = ("genel", "basvurular", "salonlar", "sonuclar", "bildirimler", "ayarlar")


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

        if action == "salon_kaydet":
            _salon_kaydet(request)
            return _geri(request, "salonlar")

        if action.startswith("sonuc_") or action.startswith("karne_") or action.startswith("karar_"):
            _sonuc_islemi(request, action)
            return _geri(request, "sonuclar")

        if action == "kelebek":
            try:
                sonuc = kelebek_yerlestir(SINAV_BASVURU_BASLIK)
            except YerlesimHatasi as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"{sonuc['ogrenci']} öğrenci kelebek sistemiyle {sonuc['salon']} salona yerleştirildi.",
                )
            return _geri(request, "salonlar")

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
            "salon": salon_ozeti(SINAV_BASVURU_BASLIK) if bolum == "salonlar" else None,
            "sonuc": _sonuc_baglami(request) if bolum == "sonuclar" else None,
        },
    )


SONUC_ONIZLEME_KEY = "seviye_tespit_sonuc_onizleme"


def _secili_sonuc_basvurulari(request):
    ids = [int(i) for i in request.POST.getlist("basvuru_ids") if i.isdigit()]
    return SinavBasvuru.objects.filter(pk__in=ids, sinav_adi=SINAV_BASVURU_BASLIK)


def _sonuc_islemi(request, action: str) -> None:
    if action == "sonuc_excel":
        dosya = request.FILES.get("excel")
        if not dosya:
            messages.error(request, "Excel dosyası seçin.")
            return
        onizleme = excel_onizle(dosya, SINAV_BASVURU_BASLIK)
        if not onizleme["satirlar"]:
            messages.error(request, " ".join(onizleme["hatalar"]) or "Excel'de öğrenci satırı bulunamadı.")
            return
        request.session[SONUC_ONIZLEME_KEY] = onizleme
        return

    if action == "sonuc_excel_iptal":
        request.session.pop(SONUC_ONIZLEME_KEY, None)
        return

    if action == "sonuc_excel_kaydet":
        onizleme = request.session.get(SONUC_ONIZLEME_KEY)
        if not onizleme:
            messages.error(request, "Önizleme bulunamadı; Excel'i yeniden yükleyin.")
            return
        secimler = {}
        for satir in onizleme["satirlar"]:
            deger = request.POST.get(f"eslesme_{satir['satir_no']}", "")
            secimler[satir["satir_no"]] = int(deger) if deger.isdigit() else None
        adet = sonuclari_kaydet(SINAV_BASVURU_BASLIK, onizleme["satirlar"], secimler)
        request.session.pop(SONUC_ONIZLEME_KEY, None)
        atlanan = len(onizleme["satirlar"]) - adet
        messages.success(
            request,
            f"{adet} öğrencinin sonucu kaydedildi" + (f", {atlanan} satır atlandı." if atlanan else "."),
        )
        return

    if action == "karne_yukle":
        basvuru = get_object_or_404(
            SinavBasvuru, pk=request.POST.get("basvuru_id"), sinav_adi=SINAV_BASVURU_BASLIK
        )
        dosya = request.FILES.get("karne")
        if not dosya:
            messages.error(request, "Dosya seçin.")
            return
        try:
            karne_kaydet(basvuru, dosya)
        except KarneHatasi as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"{basvuru.ad_soyad} karnesi yüklendi.")
        return

    if action == "karne_toplu":
        dosyalar = request.FILES.getlist("karneler")
        if not dosyalar:
            messages.error(request, "Dosya seçin.")
            return
        sonuc = toplu_karne_kaydet(SINAV_BASVURU_BASLIK, dosyalar)
        if sonuc["yuklenen"]:
            messages.success(request, f"{len(sonuc['yuklenen'])} karne yüklendi.")
        if sonuc["eslesmeyen"]:
            messages.warning(
                request,
                "Adı bir öğrenciyle eşleşmeyen dosyalar (satırdan tek tek yükleyin): "
                + ", ".join(sonuc["eslesmeyen"][:15])
                + (" …" if len(sonuc["eslesmeyen"]) > 15 else ""),
            )
        for hata in sonuc["hatali"][:5]:
            messages.error(request, hata)
        return

    if action == "karar_satir":
        say = 0
        for anahtar, deger in request.POST.items():
            if not anahtar.startswith("karar_") or deger not in ("", "kazandi", "kazanamadi"):
                continue
            pk = anahtar.removeprefix("karar_")
            if not pk.isdigit():
                continue
            say += SinavBasvuru.objects.filter(
                pk=int(pk), sinav_adi=SINAV_BASVURU_BASLIK
            ).exclude(sonuc_karar=deger).update(sonuc_karar=deger)
        if say:
            messages.success(request, "Karar kaydedildi.")
        return

    if action == "karar_toplu":
        karar = request.POST.get("toplu_karar", "")
        if karar not in ("", "kazandi", "kazanamadi"):
            return
        say = _secili_sonuc_basvurulari(request).update(sonuc_karar=karar)
        etiket = {"kazandi": "Kazandı", "kazanamadi": "Kazanamadı"}.get(karar, "Karar yok")
        messages.success(request, f"{say} öğrenci “{etiket}” işaretlendi.")
        return

    if action == "sonuc_mesaj":
        metin = request.POST.get("sonuc_mesaji", "").strip()
        takvim = guncel_takvim()
        if not takvim:
            messages.error(request, "Önce Ayarlar'dan sınav takvimini girin.")
            return
        takvim.sonuc_mesaji = "" if metin == VARSAYILAN_MESAJ else metin
        takvim.save(update_fields=["sonuc_mesaji", "guncellenme"])
        messages.success(request, "Mesaj kaydedildi.")
        return

    if action == "sonuc_gonder":
        if request.POST.get("kapsam") == "bekleyen":
            qs = SinavSonuc.objects.filter(basvuru__sinav_adi=SINAV_BASVURU_BASLIK)
        else:
            qs = SinavSonuc.objects.filter(basvuru__in=_secili_sonuc_basvurulari(request))
        hazir = [
            s.pk
            for s in qs.exclude(karne="").exclude(karne_surum=0)
            if s.gonderilen_surum != s.karne_surum
        ]
        if not hazir:
            messages.error(request, "Gönderilecek yeni karne yok. Önce karne yükleyin.")
            return
        sonuclari_arka_planda_gonder(hazir)
        messages.success(
            request,
            f"{len(hazir)} veliye sonuç gönderiliyor. Birkaç dakika içinde listede “Gönderildi” görünür.",
        )
        return

    messages.error(request, "Geçersiz işlem.")


def _sonuc_baglami(request) -> dict:
    basvurular = (
        SinavBasvuru.objects.filter(sinav_adi=SINAV_BASVURU_BASLIK)
        .select_related("sonuc")
        .annotate(bildirim_cihaz=Count("push_abonelikleri", distinct=True))
    )
    toplam = basvurular.count()
    sinif = request.GET.get("sinif", "").strip()
    karar = request.GET.get("karar", "").strip()
    if sinif:
        basvurular = basvurular.filter(sinif=sinif)
    if karar == "yok":
        basvurular = basvurular.filter(sonuc_karar="")
    elif karar:
        basvurular = basvurular.filter(sonuc_karar=karar)

    satirlar = []
    dersler_var: set[str] = set()
    for b in basvurular:
        sonuc = getattr(b, "sonuc", None)
        if sonuc and sonuc.branslar:
            dersler_var.update(sonuc.branslar)
        satirlar.append({"b": b, "s": sonuc})
    satirlar.sort(
        key=lambda r: (
            r["s"].genel_sira if r["s"] and r["s"].genel_sira else 10**6,
            r["b"].ad_soyad.casefold(),
        )
    )
    dersler = [(kod, ad, kisa) for kod, ad, kisa in DERSLER if kod in dersler_var]
    for r in satirlar:
        branslar = (r["s"].branslar if r["s"] else {}) or {}
        r["netler"] = [branslar.get(kod, {}).get("net", "") for kod, _, _ in dersler]

    tum = SinavSonuc.objects.filter(basvuru__sinav_adi=SINAV_BASVURU_BASLIK)
    guncel = SinavBasvuru.objects.filter(sinav_adi=SINAV_BASVURU_BASLIK)
    sablon = sonuc_mesaji_sablonu(SINAV_BASVURU_BASLIK)
    ornek = satirlar[0]["b"] if satirlar else None
    bekleyen = sum(
        1 for s in tum.exclude(karne="").exclude(karne_surum=0).only("karne_surum", "gonderilen_surum")
        if s.gonderilen_surum != s.karne_surum
    )
    return {
        "satirlar": satirlar,
        "dersler": dersler,
        "toplam": toplam,
        "veri": tum.filter(veri_var=True).count(),
        "karne": tum.exclude(karne="").count(),
        "gonderilen": tum.exclude(gonderim_zamani=None).count(),
        "bekleyen": bekleyen,
        "kazandi": guncel.filter(sonuc_karar="kazandi").count(),
        "kazanamadi": guncel.filter(sonuc_karar="kazanamadi").count(),
        "sinif": sinif,
        "karar": karar,
        "onizleme": request.session.get(SONUC_ONIZLEME_KEY),
        "adaylar": list(guncel.order_by("ad_soyad").values("pk", "ad_soyad", "sinif")),
        "mesaj": sablon,
        "mesaj_ornek": mesaj_doldur(sablon, ornek) if ornek else "",
    }


MAKS_SALON = 40
MAKS_MASA = 200


def _salon_kaydet(request) -> None:
    adlar = request.POST.getlist("salon_ad")
    masalar = request.POST.getlist("salon_masa")
    satirlar = []
    for i, (ad, masa) in enumerate(zip(adlar, masalar), start=1):
        ad = (ad or "").strip()[:60] or f"Salon {i}"
        try:
            adet = int(masa)
        except (TypeError, ValueError):
            adet = 0
        if adet <= 0:
            continue
        satirlar.append((ad, min(adet, MAKS_MASA)))
    if len(satirlar) > MAKS_SALON:
        messages.error(request, f"En fazla {MAKS_SALON} salon girilebilir.")
        return
    try:
        masa_kisi = int(request.POST.get("masa_kisi", "1"))
    except ValueError:
        masa_kisi = 1
    yerlesim_vardi = salon_ozeti(SINAV_BASVURU_BASLIK)["yerlesim_var"]
    degisti = salonlari_kaydet(SINAV_BASVURU_BASLIK, satirlar, masa_kisi)
    if degisti and yerlesim_vardi:
        messages.warning(
            request,
            "Salonlar kaydedildi. Masa düzeni değiştiği için yerleşim sıfırlandı; kelebek sistemini yeniden çalıştırın.",
        )
    else:
        messages.success(request, "Salonlar kaydedildi.")


YAZDIRMA_TURLERI = {
    "kapi": "Kapı listesi",
    "yoklama": "Yoklama listesi",
    "etiket": "Masa etiketleri",
    "oturma": "Oturma planı",
}


@yonetici_gerekli
def seviye_tespit_salon_yazdir(request):
    tur = request.GET.get("tur", "kapi")
    if tur not in YAZDIRMA_TURLERI:
        tur = "kapi"
    ozet = salon_ozeti(SINAV_BASVURU_BASLIK)
    kartlar = [k for k in ozet["salonlar"] if k["yerlesimler"]]
    salon_id = request.GET.get("salon", "")
    if salon_id.isdigit():
        kartlar = [k for k in kartlar if k["salon"].pk == int(salon_id)]
    for kart in kartlar:
        kart["alfabetik"] = sorted(
            kart["yerlesimler"], key=lambda y: y.basvuru.ad_soyad.casefold()
        )
    return render(
        request,
        "yonetim/seviye_tespit_yazdir.html",
        {
            "tur": tur,
            "tur_adi": YAZDIRMA_TURLERI[tur],
            "kartlar": kartlar,
            "sinav_adi": SINAV_BASVURU_BASLIK,
            "takvim": guncel_takvim(),
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
            "yerlesim": yerlesim_bul(basvuru),
            "sonuc": SinavSonuc.objects.filter(basvuru=basvuru).first(),
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


@yonetici_gerekli
def seviye_tespit_karne(request, pk):
    import os

    from django.http import FileResponse, Http404

    sonuc = get_object_or_404(SinavSonuc.objects.select_related("basvuru"), basvuru_id=pk)
    if not sonuc.karne:
        raise Http404
    try:
        dosya = sonuc.karne.open("rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    uzanti = os.path.splitext(sonuc.karne.name)[1].lower()
    yanit = FileResponse(dosya, filename=f"{sonuc.basvuru.ad_soyad} - Sonuç{uzanti}")
    yanit["Cache-Control"] = "private, no-store"
    return yanit
