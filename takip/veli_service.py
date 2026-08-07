"""Veli paneli — erişim ve talebe özet verisi."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils.timezone import localdate

from takip.dini_ders_takip_service import talebe_ilerleme_ozeti
from takip.models import (
    AkademikMudahale,
    DiniDersKonu,
    DiniDersKonuKaydi,
    DiniDersTakipAlani,
    Duyuru,
    GunlukSoruKaydi,
    KttSonucu,
    Talebe,
    TalebePersonelNotu,
    VeliHesap,
    VeliTalebeBaglantisi,
    Zimmet,
)
from takip.ogretmen_not_service import talebe_ogretmen_notlari
from takip.deneme_service import BRANS_ETIKETLERI, talebe_deneme_sonuclari
from takip.yazili_takip_service import talebe_yazili_sonuclari
from takip.duyuru_service import veli_duyurulari
from takip.soru_takip_service import aylik_ozet, haftalik_ozet


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

    if PersonelProfili.objects.filter(user=user).exists():
        return False

    hesap = veli_hesabi_for_user(user)
    return bool(hesap and hesap.aktif)


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


def talebe_veli_ozeti(talebe: Talebe) -> dict:
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

    ktt_sonuclari = list(
        KttSonucu.objects.filter(
            talebe=talebe,
            ktt__veliye_goster=True,
            ktt__aktif=True,
        )
        .select_related("ktt", "ktt__ders")
        .order_by("-ktt__sinav_tarihi", "-id")[:10]
    )

    deneme_sonuclari = list(talebe_deneme_sonuclari(talebe)[:10])

    yazili_sonuclari = list(talebe_yazili_sonuclari(talebe)[:20])

    personel_notlari = list(
        TalebePersonelNotu.objects.filter(
            talebe=talebe,
            veliye_goster=True,
        )
        .order_by("-olusturulma")[:5]
    )

    return {
        "talebe": talebe,
        "zimmetler": aktif_zimmetler(talebe),
        "haftalik_soru": hafta,
        "aylik_soru": ay,
        "mudahaleler": mudahaleler,
        "soru_kayitlari": soru_kayitlari,
        "ktt_sonuclari": ktt_sonuclari,
        "deneme_sonuclari": deneme_sonuclari,
        "deneme_brans_etiketleri": BRANS_ETIKETLERI,
        "yazili_sonuclari": yazili_sonuclari,
        "ogretmen_notlari": list(talebe_ogretmen_notlari(talebe)),
        "dini_ders_ozet": talebe_ilerleme_ozeti(talebe),
        "personel_notlari": personel_notlari,
    }


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
        "duyurular": list(veli_duyurulari()[:5]),
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

    hafta = haftalik_ozet(talebe)
    dini_yuzde = _dini_ders_toplam_yuzde(talebe)
    mudahale_sayisi = AkademikMudahale.objects.filter(
        talebe=talebe,
        veliye_goster=True,
        tarih__gte=localdate() - timedelta(days=30),
    ).count()

    return {
        "son_deneme": son_deneme,
        "son_ktt": son_ktt,
        "haftalik_soru": hafta,
        "dini_ders_yuzde": dini_yuzde,
        "mudahale_sayisi": mudahale_sayisi,
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
        alanlar.append(
            {
                "id": alan.id,
                "ad": alan.ad,
                "tamamlanan": tamamlanan,
                "toplam": len(konu_list),
                "yuzde": round(100 * tamamlanan / len(konu_list)) if konu_list else 0,
                "konular": konu_list,
            }
        )

    return {
        "genel_yuzde": round(100 * tamamlanan_konu / toplam_konu) if toplam_konu else 0,
        "tamamlanan": tamamlanan_konu,
        "toplam": toplam_konu,
        "alanlar": alanlar,
    }


def talebe_sinif_goster(talebe: Talebe) -> str:
    if talebe.sinif_sube_id:
        return str(talebe.sinif_sube)
    if talebe.sube:
        return f"{talebe.sinif} / {talebe.sube}"
    return talebe.sinif or "—"


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
