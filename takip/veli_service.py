"""Veli paneli — erişim ve talebe özet verisi."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Avg, Count, QuerySet, Sum
from django.utils.timezone import localdate

from takip.dini_ders_takip_service import talebe_ilerleme_ozeti
from takip.dini_ilerleme_service import talebe_alan_analizleri
from takip.models import (
    AkademikMudahale,
    DiniDersKonu,
    DiniDersKonuKaydi,
    DiniDersTakipAlani,
    Duyuru,
    GunlukSoruDersSatiri,
    GunlukSoruKaydi,
    HaftalikSohbetMevzuu,
    KttSonucu,
    NamazYoklamaKaydi,
    Talebe,
    TalebePersonelNotu,
    VeliHesap,
    VeliTalebeBaglantisi,
    Zimmet,
)
from takip.ogretmen_not_models import OgretmenSinavNotu, OgretmenSinifYoklama
from takip.ogretmen_not_service import talebe_ogretmen_notlari
from takip.deneme_service import BRANS_ETIKETLERI, talebe_deneme_performans_ozeti, talebe_deneme_sonuclari
from takip.yazili_takip_service import talebe_yazili_sonuclari
from takip.duyuru_service import veli_duyurulari
from takip.soru_takip_service import aylik_ozet, haftalik_ozet


def _hafta_pazartesi(referans: date | None = None) -> date:
    bugun = referans or localdate()
    return bugun - timedelta(days=bugun.weekday())


def veli_hesabi_for_user(user: User) -> VeliHesap | None:
    if not user.is_authenticated:
        return None
    try:
        return user.veli_hesabi
    except VeliHesap.DoesNotExist:
        return None


def kullanici_veli_mi(user: User) -> bool:
    if not user.is_authenticated or user.is_superuser:
        return False

    from takip.models import PersonelProfili

    # user.personel_profili Django'nun reverse-OneToOne descriptor'ı —
    # aynı istekte başka bir yerde zaten okunmuşsa (çoğu zaman öyle)
    # ekstra sorgu atmadan, instance-cache'ten döner.
    try:
        user.personel_profili
    except PersonelProfili.DoesNotExist:
        pass
    else:
        return False

    hesap = veli_hesabi_for_user(user)
    return bool(hesap and hesap.aktif)


def veli_talebe_ozet_etiketi(veli: VeliHesap | None) -> str:
    """Header alt satırı: talebe adı / adları."""
    if not veli:
        return "Veli"
    adlar = list(veli_talebeleri(veli).values_list("ad_soyad", flat=True)[:3])
    if not adlar:
        return "Veli"
    if len(adlar) == 1:
        return adlar[0]
    if len(adlar) == 2:
        return f"{adlar[0]} · {adlar[1]}"
    return f"{adlar[0]} · {adlar[1]}…"


def veli_talebeleri(veli: VeliHesap) -> QuerySet[Talebe]:
    return (
        Talebe.objects.filter(
            veli_baglantilari__veli=veli,
            durum=Talebe.Durum.AKTIF,
        )
        .select_related(
            "sinif_sube",
            "etut_hocasi",
            "dini_ders_hocasi",
            "dini_ders_seviyesi",
        )
        .order_by("ad_soyad")
    )


def veli_talebe_getir(veli: VeliHesap, talebe_id: int) -> Talebe | None:
    return veli_talebeleri(veli).filter(pk=talebe_id).first()


def aktif_zimmetler(talebe: Talebe) -> list[Zimmet]:
    return list(
        Zimmet.objects.filter(talebe=talebe, durum="okunuyor")
        .select_related("kitap")
        .order_by("-id")
    )


def _not_ortalamasi(qs: QuerySet[OgretmenSinavNotu]) -> Decimal | None:
    agg = qs.aggregate(ort=Avg("puan"))
    if agg["ort"] is None:
        return None
    return Decimal(agg["ort"]).quantize(Decimal("0.1"))


def _veli_yazili_sonuclari_guvenli(talebe: Talebe) -> list:
    """Yazılı tablosu migration bekliyorsa boş liste döner."""
    from django.db.utils import OperationalError, ProgrammingError

    try:
        return list(talebe_yazili_sonuclari(talebe)[:20])
    except (OperationalError, ProgrammingError):
        return []


def talebe_veli_ozeti(talebe: Talebe, *, sinav_verisi: bool = False) -> dict:
    bugun = localdate()
    hafta = haftalik_ozet(talebe, bugun)
    ay = aylik_ozet(talebe, bugun)

    mudahaleler = list(
        AkademikMudahale.objects.filter(talebe=talebe, veliye_goster=True)
        .select_related("mudahale_turu", "ders")
        .order_by("-tarih", "-id")[:10]
    )

    soru_kayitlari = list(
        GunlukSoruKaydi.objects.filter(talebe=talebe)
        .order_by("-tarih", "-id")[:7]
    )

    personel_notlari = list(
        TalebePersonelNotu.objects.filter(
            talebe=talebe,
            veliye_goster=True,
        )
        .order_by("-olusturulma")[:5]
    )

    ozet = {
        "talebe": talebe,
        "zimmetler": aktif_zimmetler(talebe),
        "haftalik_soru": hafta,
        "aylik_soru": ay,
        "mudahaleler": mudahaleler,
        "soru_kayitlari": soru_kayitlari,
        "dini_ders_ozet": talebe_ilerleme_ozeti(talebe),
        "personel_notlari": personel_notlari,
        "ktt_sonuclari": [],
        "deneme_sonuclari": [],
        "deneme_performans": None,
        "deneme_brans_etiketleri": BRANS_ETIKETLERI,
        "yazili_sonuclari": [],
        "ogretmen_notlari": [],
    }

    if sinav_verisi:
        ozet["ktt_sonuclari"] = list(
            KttSonucu.objects.filter(
                talebe=talebe,
                ktt__veliye_goster=True,
                ktt__aktif=True,
            )
            .select_related("ktt", "ktt__ders")
            .order_by("-ktt__sinav_tarihi", "-id")[:10]
        )
        ozet["deneme_sonuclari"] = list(talebe_deneme_sonuclari(talebe)[:10])
        ozet["deneme_performans"] = talebe_deneme_performans_ozeti(talebe)
        ozet["yazili_sonuclari"] = _veli_yazili_sonuclari_guvenli(talebe)
        ozet["ogretmen_notlari"] = list(talebe_ogretmen_notlari(talebe, limit=50))
        from takip.ktt_akilli_service import veli_akademik_gelisim

        ozet["akademik_gelisim"] = veli_akademik_gelisim(talebe)

    return ozet


def talebe_veli_mudahaleleri(talebe: Talebe) -> list[AkademikMudahale]:
    return list(
        AkademikMudahale.objects.filter(talebe=talebe, veliye_goster=True)
        .select_related("mudahale_turu", "ders")
        .order_by("-tarih", "-id")[:20]
    )


def veli_dashboard_verisi(veli: VeliHesap) -> dict:
    talebeler = list(veli_talebeleri(veli))
    kartlar = []
    for talebe in talebeler:
        hafta = haftalik_ozet(talebe)
        mudahale_sayisi = AkademikMudahale.objects.filter(
            talebe=talebe,
            veliye_goster=True,
            tarih__gte=localdate() - timedelta(days=30),
        ).count()
        kartlar.append(
            {
                "talebe": talebe,
                "haftalik_soru": hafta,
                "son_mudahale_sayisi": mudahale_sayisi,
                "dini_ders_yuzde": _dini_ders_toplam_yuzde(talebe),
            }
        )

    return {
        "veli": veli,
        "talebeler": talebeler,
        "kartlar": kartlar,
        "duyurular": list(veli_duyurulari()[:8]),
    }


def _dini_ders_toplam_yuzde(talebe: Talebe) -> int:
    ozet = talebe_ilerleme_ozeti(talebe)
    if not ozet:
        return 0
    toplam = sum(o["toplam"] for o in ozet)
    tamamlanan = sum(o["tamamlanan"] for o in ozet)
    return round(100 * tamamlanan / toplam) if toplam else 0


def talebe_yakinlik(veli: VeliHesap, talebe: Talebe) -> str:
    bag = VeliTalebeBaglantisi.objects.filter(veli=veli, talebe=talebe).first()
    if not bag:
        return "Veli"
    return bag.get_yakinlik_display()


def talebe_kpi_ozeti(talebe: Talebe) -> dict:
    denemeler = talebe_deneme_sonuclari(talebe)
    son_deneme = denemeler.first() if denemeler.exists() else None

    ktt_qs = KttSonucu.objects.filter(
        talebe=talebe,
        ktt__veliye_goster=True,
        ktt__aktif=True,
    ).select_related("ktt", "ktt__ders")
    son_ktt = ktt_qs.order_by("-ktt__sinav_tarihi", "-id").first()

    hafta_bas = _hafta_pazartesi()
    tum_notlar = OgretmenSinavNotu.objects.filter(talebe=talebe, veliye_goster=True)
    haftalik_ders_ort = _not_ortalamasi(tum_notlar.filter(hafta_baslangic=hafta_bas))
    etut_qs = tum_notlar
    if talebe.etut_hocasi_id:
        etut_qs = tum_notlar.filter(etut_hocasi_id=talebe.etut_hocasi_id)
    etut_ders_ort = _not_ortalamasi(etut_qs.filter(hafta_baslangic=hafta_bas))
    if etut_ders_ort is None:
        etut_ders_ort = _not_ortalamasi(etut_qs)

    hafta = haftalik_ozet(talebe)
    dini_yuzde = _dini_ders_toplam_yuzde(talebe)
    mudahale_sayisi = AkademikMudahale.objects.filter(
        talebe=talebe,
        veliye_goster=True,
        tarih__gte=localdate() - timedelta(days=30),
    ).count()

    aktif_hafta_notlari = list(
        tum_notlar.filter(hafta_baslangic=hafta_bas)
        .select_related("ders", "etut_hocasi")
        .order_by("ders__ad")[:12]
    )

    return {
        "son_deneme": son_deneme,
        "son_ktt": son_ktt,
        "haftalik_ders_ort": haftalik_ders_ort,
        "etut_ders_ort": etut_ders_ort,
        "haftalik_soru": hafta,
        "dini_ders_yuzde": dini_yuzde,
        "dini_ders_detay": dini_ders_mufredat_detay(talebe),
        "mudahale_sayisi": mudahale_sayisi,
        "aktif_hafta_baslangic": hafta_bas,
        "aktif_hafta_bitis": hafta_bas + timedelta(days=6),
        "aktif_hafta_notlari": aktif_hafta_notlari,
    }


def dini_ders_mufredat_detay(talebe: Talebe) -> dict | None:
    if not talebe.dini_ders_seviyesi_id:
        return None

    tamamlanan_ids = set(
        DiniDersKonuKaydi.objects.filter(
            talebe=talebe,
            tamamlandi=True,
        ).values_list("konu_id", flat=True)
    )

    analizler = talebe_alan_analizleri(talebe)
    analiz_map = {a.alan_id: a for a in analizler}

    alanlar = []
    toplam_konu = 0
    tamamlanan_konu = 0

    for alan in DiniDersTakipAlani.objects.filter(aktif=True).order_by("sira", "ad"):
        konular = list(
            DiniDersKonu.objects.filter(
                alan=alan,
                seviye=talebe.dini_ders_seviyesi,
                aktif=True,
            ).order_by("sira", "ad")
        )
        if not konular:
            continue

        konu_list = [
            {
                "id": konu.id,
                "ad": konu.ad,
                "tamamlandi": konu.id in tamamlanan_ids,
            }
            for konu in konular
        ]
        tamamlanan = sum(1 for k in konu_list if k["tamamlandi"])
        toplam_konu += len(konu_list)
        tamamlanan_konu += tamamlanan

        ozet = analiz_map.get(alan.id)
        alan_analiz = None
        if ozet:
            alan_analiz = {
                "talebe_yuzde": ozet.talebe_yuzde,
                "grup_ortalama": ozet.grup_ortalama,
                "beklenen_yuzde": ozet.beklenen_yuzde,
                "grup_fark_puan": ozet.grup_fark_puan,
                "plan_fark_puan": ozet.plan_fark_puan,
                "durum_etiket": ozet.durum_etiket,
                "durum_sinif": ozet.durum_sinif,
                "karsilastirma_metni": ozet.karsilastirma_metni,
                "durum_aciklama": ozet.durum_aciklama,
                "son_30_gun": ozet.son_30_gun,
                "siradaki_konu": ozet.siradaki_konu,
                "son_hareket": ozet.son_hareket,
            }

        alanlar.append(
            {
                "id": alan.id,
                "ad": alan.ad,
                "tamamlanan": tamamlanan,
                "toplam": len(konu_list),
                "yuzde": round(100 * tamamlanan / len(konu_list)) if konu_list else 0,
                "konular": konu_list,
                "analiz": alan_analiz,
            }
        )

    return {
        "genel_yuzde": round(100 * tamamlanan_konu / toplam_konu) if toplam_konu else 0,
        "tamamlanan": tamamlanan_konu,
        "toplam": toplam_konu,
        "alanlar": alanlar,
        "analizler": [
            {
                "alan_id": a.alan_id,
                "alan_ad": a.alan_ad,
                "talebe_yuzde": a.talebe_yuzde,
                "grup_ortalama": a.grup_ortalama,
                "beklenen_yuzde": a.beklenen_yuzde,
                "durum_etiket": a.durum_etiket,
                "durum_sinif": a.durum_sinif,
                "karsilastirma_metni": a.karsilastirma_metni,
                "durum_aciklama": a.durum_aciklama,
            }
            for a in analizler
        ],
    }


def talebe_sinif_goster(talebe: Talebe) -> str:
    if talebe.sinif_sube_id:
        return str(talebe.sinif_sube)
    if talebe.sube:
        return f"{talebe.sinif} / {talebe.sube}"
    return talebe.sinif or "—"


def talebe_soru_detay(talebe: Talebe, gun: int = 14) -> dict:
    bitis = localdate()
    baslangic = bitis - timedelta(days=gun - 1)
    kayitlar = (
        GunlukSoruKaydi.objects.filter(
            talebe=talebe,
            tarih__gte=baslangic,
            tarih__lte=bitis,
        )
        .prefetch_related("ders_satirlari__ders")
        .order_by("-tarih")
    )
    satirlar = GunlukSoruDersSatiri.objects.filter(kayit__in=kayitlar).select_related(
        "ders", "kayit"
    )
    ders_ozet = list(
        satirlar.values("ders__ad")
        .annotate(
            toplam_soru=Sum("toplam_soru"),
            dogru=Sum("dogru"),
            yanlis=Sum("yanlis"),
            bos=Sum("bos"),
            net=Sum("net"),
        )
        .order_by("-toplam_soru")
    )
    return {
        "baslangic": baslangic,
        "bitis": bitis,
        "haftalik": haftalik_ozet(talebe),
        "aylik": aylik_ozet(talebe),
        "kayitlar": list(kayitlar),
        "ders_ozet": ders_ozet,
    }


def talebe_haftalik_notlar(talebe: Talebe, hafta_baslangic: date | None = None) -> dict:
    from takip.ogretmen_not_models import OgretmenHaftalikKonu

    aktif = _hafta_pazartesi()
    secili = hafta_baslangic or aktif
    notlar = list(
        OgretmenSinavNotu.objects.filter(
            talebe=talebe,
            veliye_goster=True,
            hafta_baslangic=secili,
        )
        .select_related("ders", "etut_hocasi")
        .order_by("ders__ad")
    )
    konu_map: dict[tuple[int, int], str] = {}
    if talebe.sinif_sube_id:
        for k in OgretmenHaftalikKonu.objects.filter(
            sinif_sube_id=talebe.sinif_sube_id,
            hafta_baslangic=secili,
        ):
            konu_map[(k.etut_hocasi_id, k.ders_id)] = (k.konu or "").strip()
    for n in notlar:
        n.haftalik_konu = konu_map.get((n.etut_hocasi_id, n.ders_id), "") or "—"

    arsiv_haftalar = list(
        OgretmenSinavNotu.objects.filter(talebe=talebe, veliye_goster=True)
        .values_list("hafta_baslangic", flat=True)
        .distinct()
        .order_by("-hafta_baslangic")[:16]
    )
    return {
        "aktif_hafta": aktif,
        "secili_hafta": secili,
        "secili_hafta_bitis": secili + timedelta(days=6),
        "notlar": notlar,
        "ortalama": _not_ortalamasi(
            OgretmenSinavNotu.objects.filter(
                talebe=talebe, veliye_goster=True, hafta_baslangic=secili
            )
        ),
        "arsiv_haftalar": arsiv_haftalar,
        "arsiv_modu": secili != aktif,
    }


def talebe_yoklama_30_gun(talebe: Talebe) -> dict:
    bitis = localdate()
    baslangic = bitis - timedelta(days=29)
    kayitlar = list(
        OgretmenSinifYoklama.objects.filter(
            talebe=talebe,
            tarih__gte=baslangic,
            tarih__lte=bitis,
            yok=True,
        )
        .select_related("etut_hocasi")
        .order_by("-tarih")
    )
    gun_sayisi = 30
    yok_gun = len({k.tarih for k in kayitlar})
    return {
        "baslangic": baslangic,
        "bitis": bitis,
        "kayitlar": kayitlar,
        "yok_gun": yok_gun,
        "var_gun": max(gun_sayisi - yok_gun, 0),
        "katilim_yuzde": round(100 * (gun_sayisi - yok_gun) / gun_sayisi) if gun_sayisi else 0,
    }


def talebe_namaz_30_gun(talebe: Talebe) -> dict:
    bitis = localdate()
    baslangic = bitis - timedelta(days=29)
    kayitlar = list(
        NamazYoklamaKaydi.objects.filter(
            talebe=talebe,
            oturum__tarih__gte=baslangic,
            oturum__tarih__lte=bitis,
        )
        .select_related("oturum")
        .order_by("-oturum__tarih", "oturum__vakit")
    )
    ozet = (
        NamazYoklamaKaydi.objects.filter(
            talebe=talebe,
            oturum__tarih__gte=baslangic,
            oturum__tarih__lte=bitis,
        )
        .values("durum")
        .annotate(adet=Count("id"))
    )
    return {
        "baslangic": baslangic,
        "bitis": bitis,
        "kayitlar": kayitlar,
        "ozet": {row["durum"]: row["adet"] for row in ozet},
        "toplam": len(kayitlar),
    }


def aktif_sohbet_mevzulari(limit: int = 8) -> list[HaftalikSohbetMevzuu]:
    return list(
        HaftalikSohbetMevzuu.objects.filter(aktif=True).order_by(
            "-hafta_baslangic", "-id"
        )[:limit]
    )


def seed_veli_demo() -> None:
    from django.contrib.auth.models import User

    from takip.models import DiniDersSeviyesi, VeliKisi

    talebe = Talebe.objects.filter(ad_soyad="Ahmet Yılmaz").first()
    if not talebe:
        talebe = Talebe.objects.filter(durum=Talebe.Durum.AKTIF).first()
    if not talebe:
        return

    seviye = DiniDersSeviyesi.objects.filter(ad="Seviye 1").first()
    if seviye and not talebe.dini_ders_seviyesi_id:
        talebe.dini_ders_seviyesi = seviye
        talebe.save(update_fields=["dini_ders_seviyesi"])

    VeliKisi.objects.get_or_create(
        talebe=talebe,
        ad_soyad="Ayşe Yılmaz",
        defaults={
            "yakinlik": VeliKisi.Yakinlik.ANNE,
            "telefon": "05551234567",
            "birincil": True,
        },
    )

    user, _ = User.objects.get_or_create(username="veli")
    user.set_password("Veli123!")
    user.is_staff = False
    user.is_superuser = False
    user.save()

    veli, _ = VeliHesap.objects.update_or_create(
        user=user,
        defaults={
            "ad_soyad": "Ayşe Yılmaz",
            "telefon": "05551234567",
            "aktif": True,
        },
    )

    VeliTalebeBaglantisi.objects.update_or_create(
        veli=veli,
        talebe=talebe,
        defaults={"yakinlik": VeliKisi.Yakinlik.ANNE},
    )

    Duyuru.objects.update_or_create(
        baslik="Veli paneli aktif",
        defaults={
            "ozet": "Öğrencinizin akademik gelişimini veli panelinden takip edebilirsiniz.",
            "kategori": Duyuru.Kategori.EGITIM,
            "hedef_kitle": Duyuru.HedefKitle.VELI,
            "ton": Duyuru.Ton.VIOLET,
            "sira": 1,
            "baslangic": localdate(),
            "aktif": True,
            "olusturan": User.objects.filter(username="admin").first(),
        },
    )
