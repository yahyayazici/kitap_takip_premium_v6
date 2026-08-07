"""Öğretmen paneli — örnek arayüz verisi ve yardımcılar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from takip.veli_randevu_service import ogretmen_randevu_listesi
from takip.models import EtutHocasi, SinifSube, Talebe
from takip.user_helpers import etut_hocasi_for_user


@dataclass(frozen=True)
class OgretmenSinifKarti:
    id: int
    etiket: str
    ogrenci_sayisi: int
    slug: str


def ogretmen_hocasi_for_user(user: User) -> EtutHocasi | None:
    if not user.is_authenticated:
        return None

    hoca = etut_hocasi_for_user(user)
    if hoca and hoca.aktif:
        return hoca

    try:
        profil = user.personel_profili
    except Exception:
        return None

    if profil.aktif and profil.etut_hocasi_id and profil.etut_hocasi.aktif:
        return profil.etut_hocasi

    return None


def kullanici_ogretmen_mi(user: User) -> bool:
    return ogretmen_hocasi_for_user(user) is not None


def ogretmen_paneli_kullanicisi_mi(user: User) -> bool:
    """Yalnızca öğretmen paneline giden hesaplar (personel/idareci değil)."""
    if not kullanici_ogretmen_mi(user):
        return False
    if user.is_superuser:
        return False
    try:
        profil = user.personel_profili
    except Exception:
        return True
    return not profil.aktif


def _hafta_araligi(ref: date | None = None) -> tuple[int, date, date]:
    ref = ref or timezone.localdate()
    yil_bas = date(ref.year, 8, 1)
    if ref < yil_bas:
        yil_bas = date(ref.year - 1, 8, 1)
    hafta_no = ((ref - yil_bas).days // 7) + 1
    pazartesi = ref - timedelta(days=ref.weekday())
    pazar = pazartesi + timedelta(days=6)
    return hafta_no, pazartesi, pazar


def _demo_siniflar(hoca: EtutHocasi) -> list[OgretmenSinifKarti]:
    siniflar = list(hoca.sorumlu_sinif_subeler.filter(aktif=True).order_by("sinif", "sube"))
    kartlar: list[OgretmenSinifKarti] = []

    for sinif in siniflar:
        sayi = Talebe.objects.filter(sinif_sube=sinif, aktif=True, etut_hocasi=hoca).count()
        etiket = f"{sinif.sinif}-{sinif.sube}"
        kartlar.append(
            OgretmenSinifKarti(
                id=sinif.id,
                etiket=etiket,
                ogrenci_sayisi=sayi,
                slug=etiket.lower().replace(" ", ""),
            )
        )

    if kartlar:
        return kartlar

    return [
        OgretmenSinifKarti(id=801, etiket="8-A", ogrenci_sayisi=9, slug="8-a"),
        OgretmenSinifKarti(id=802, etiket="8-B", ogrenci_sayisi=8, slug="8-b"),
    ]


def _demo_ogrenciler(sinif_etiket: str) -> list[dict[str, Any]]:
    demo_8a = [
        "Ahmet Arif Demirci",
        "Ebubekir Başpınar",
        "Ahmed Enes Güneş",
        "Muhammed Ali Yıldız",
        "Ömer Faruk Kaya",
        "Yusuf Emre Çelik",
        "Abdullah Arslan",
        "Mehmet Emin Öztürk",
        "İbrahim Halil Şahin",
    ]
    demo_8b = [
        "Ali Rıza Demir",
        "Hasan Hüseyin Aktaş",
        "Emirhan Polat",
        "Burak Yılmaz",
        "Enes Korkmaz",
        "Salih Aksoy",
        "Hamza Doğan",
        "Kerem Aydın",
    ]

    isimler = demo_8b if sinif_etiket.upper().endswith("B") else demo_8a

    sinif = SinifSube.objects.filter(aktif=True).order_by("sinif", "sube").first()
    qs = Talebe.objects.none()
    if sinif:
        qs = Talebe.objects.filter(sinif_sube=sinif, aktif=True).order_by("ad_soyad")

    ogrenciler = list(qs[: len(isimler)])
    sonuc = []
    for idx, isim in enumerate(isimler):
        if idx < len(ogrenciler):
            talebe = ogrenciler[idx]
            sonuc.append({"id": talebe.id, "ad_soyad": talebe.ad_soyad})
        else:
            sonuc.append({"id": 9000 + idx, "ad_soyad": isim})
    return sonuc


def ogretmen_dashboard_verisi(hoca: EtutHocasi) -> dict[str, Any]:
    siniflar = _demo_siniflar(hoca)
    hafta_no, baslangic, bitis = _hafta_araligi()
    toplam_ogrenci = sum(s.ogrenci_sayisi for s in siniflar)

    duyurular = list(veli_duyurulari()[:2])
    if not duyurular:
        duyurular = [
            {
                "baslik": "Yeni Dönem",
                "ozet": "Yeni eğitim döneminde tüm öğrenci ve öğretmenlerimize başarılar dileriz.",
                "tarih_goster": "13.07.2026",
                "yeni": True,
            }
        ]

    return {
        "hoca": hoca,
        "siniflar": siniflar,
        "toplam_sinif": len(siniflar),
        "toplam_ogrenci": toplam_ogrenci,
        "hafta_no": hafta_no,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
        "bugun": timezone.localdate(),
        "duyurular": duyurular,
        "program_gunler": _program_gunleri(),
        "randevular": ogretmen_randevu_listesi(hoca.user),
    }


def _program_gunleri() -> list[dict[str, Any]]:
    return [
        {
            "gun": "Salı",
            "dersler": [
                {"saat": "14:40 - 15:20", "sinif": "5-A", "ders": "Sosyal Bilgiler"},
                {"saat": "15:30 - 16:10", "sinif": "6-B", "ders": "Sosyal Bilgiler"},
                {"saat": "16:20 - 17:00", "sinif": "7-A", "ders": "Sosyal Bilgiler"},
                {"saat": "17:10 - 17:50", "sinif": "7-B", "ders": "Sosyal Bilgiler"},
            ],
        },
        {
            "gun": "Çarşamba",
            "dersler": [
                {"saat": "14:40 - 15:20", "sinif": "5-B", "ders": "Sosyal Bilgiler"},
                {"saat": "15:30 - 16:10", "sinif": "5-A", "ders": "Sosyal Bilgiler"},
                {"saat": "16:20 - 17:00", "sinif": "8-A", "ders": "Sosyal Bilgiler"},
            ],
        },
    ]


def ogretmen_program_verisi(hoca: EtutHocasi) -> dict[str, Any]:
    hafta_no, baslangic, bitis = _hafta_araligi()
    return {
        "hoca": hoca,
        "gunler": _program_gunleri(),
        "hafta_no": hafta_no,
        "hafta_baslangic": baslangic,
        "hafta_bitis": bitis,
    }


def seed_ogretmen_panel_demo() -> None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user, created = User.objects.get_or_create(username="kemal")
    if created:
        user.set_password("Kemal123!")
        user.save()

    hoca, _ = EtutHocasi.objects.get_or_create(
        user=user,
        defaults={"ad_soyad": "Kemal Demirci"},
    )
    if hoca.ad_soyad != "Kemal Demirci":
        hoca.ad_soyad = "Kemal Demirci"
        hoca.save(update_fields=["ad_soyad"])

    siniflar = list(SinifSube.objects.filter(aktif=True).order_by("sinif", "sube")[:2])
    if len(siniflar) >= 2:
        hoca.sorumlu_sinif_subeler.set(siniflar)
