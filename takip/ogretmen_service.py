"""Öğretmen paneli — örnek arayüz verisi ve yardımcılar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from takip.duyuru_service import ogretmen_duyurulari
from takip.veli_randevu_service import ogretmen_randevu_listesi
from takip.models import EtutHocasi, SinifSube, Talebe
from takip.user_helpers import etut_hocasi_for_user

# Haftalık not girişi: Pazar akşamı (İstanbul) kapanır
HAFTA_KAPANIS_SAAT = 20


@dataclass(frozen=True)
class OgretmenSinifKarti:
    id: int
    etiket: str
    ogrenci_sayisi: int
    slug: str


def ogretmen_hocasi_for_user(user: User) -> EtutHocasi | None:
    """Branş öğretmeni EtutHocasi — etüt/sınıf mesulü personel değil."""
    if not user.is_authenticated:
        return None

    # Personel hesabı (etüt mesulü vb.) öğretmen paneline düşmesin
    try:
        personel = user.personel_profili
    except Exception:
        personel = None
    if personel is not None and personel.aktif:
        return None

    hoca = etut_hocasi_for_user(user)
    if not hoca or not hoca.aktif:
        return None

    kayit = getattr(hoca, "personel_kaydi", None)
    if kayit is not None and kayit.aktif:
        return None

    return hoca


def kullanici_ogretmen_mi(user: User) -> bool:
    return ogretmen_hocasi_for_user(user) is not None


def ogretmen_paneli_kullanicisi_mi(user: User) -> bool:
    """Yalnızca branş öğretmeni paneline giden hesaplar (personel/idareci değil)."""
    if user.is_superuser:
        return False
    return kullanici_ogretmen_mi(user)


# Branş öğretmene PersonelProfili açmadan verilebilen ekstra RBAC roller
OGRETMEN_EKSTRA_ROL_SLUGLERI: frozenset[str] = frozenset({"rehber_ogretmeni"})


def ogretmen_ekstra_rol_slugleri(user: User) -> frozenset[str]:
    """Öğretmene atanmış ekstra roller (PersonelProfili yok; yalnızca KullaniciRol)."""
    if not user or not user.is_authenticated:
        return frozenset()

    from takip.wave0_models import KullaniciRol

    return frozenset(
        KullaniciRol.objects.filter(
            user=user,
            rol__aktif=True,
            rol__slug__in=OGRETMEN_EKSTRA_ROL_SLUGLERI,
        ).values_list("rol__slug", flat=True)
    )


def ogretmen_ekstra_rolu_var_mi(user: User) -> bool:
    return bool(ogretmen_ekstra_rol_slugleri(user))


def ogretmen_giris_url_adi(user: User) -> str:
    """Klasik öğretmen → not girişi; ekstra rol varsa ana sayfa."""
    if ogretmen_ekstra_rolu_var_mi(user):
        return "ogretmen_dashboard"
    return "ogretmen_not_girisi"


def ogretmen_brans_etiketi(hoca: EtutHocasi | None) -> str:
    """Header alt satırı: örn. 'Sosyal Bilgiler Öğretmeni'."""
    if not hoca:
        return "Öğretmen"

    from django.db.models import Count

    from takip.ogretmen_not_models import OgretmenSinavNotu

    # Önce panelde fiilen girdiği ders (daha doğru unvan)
    ders = (
        OgretmenSinavNotu.objects.filter(etut_hocasi=hoca)
        .values("ders__ad")
        .annotate(adet=Count("id"))
        .order_by("-adet")
        .values_list("ders__ad", flat=True)
        .first()
    )
    if ders:
        return f"{ders} Öğretmeni"

    try:
        profil = hoca.odeme_profili
        if profil and profil.brans_id and profil.brans.ad:
            return f"{profil.brans.ad} Öğretmeni"
    except Exception:
        pass

    return "Öğretmen"


def _hafta_araligi(ref: date | None = None) -> tuple[int, date, date]:
    ref = ref or timezone.localdate()
    yil_bas = date(ref.year, 8, 1)
    if ref < yil_bas:
        yil_bas = date(ref.year - 1, 8, 1)
    hafta_no = ((ref - yil_bas).days // 7) + 1
    pazartesi = ref - timedelta(days=ref.weekday())
    pazar = pazartesi + timedelta(days=6)
    return hafta_no, pazartesi, pazar


def aktif_hafta_baslangic(ref: date | None = None) -> date:
    """Aktif akademik haftanın pazartesi tarihi."""
    _, pazartesi, _ = _hafta_araligi(ref)
    return pazartesi


def hafta_kapanis_zamani(hafta_baslangic: date | None = None) -> datetime:
    """Seçilen (veya aktif) haftanın Pazar 20:00 kapanış anı (aware)."""
    baslangic = hafta_baslangic or aktif_hafta_baslangic()
    pazar = baslangic + timedelta(days=6)
    tz = timezone.get_current_timezone()
    return timezone.make_aware(
        datetime.combine(pazar, time(HAFTA_KAPANIS_SAAT, 0)),
        tz,
    )


def hafta_yazilabilir_mi(now: datetime | None = None) -> bool:
    """Öğretmenler yalnızca aktif haftada ve Pazar 20:00 öncesi yazabilir."""
    now = timezone.localtime(now or timezone.now())
    return now < hafta_kapanis_zamani(aktif_hafta_baslangic(now.date()))


def _demo_siniflar(hoca: EtutHocasi) -> list[OgretmenSinifKarti]:
    """Öğretmene zimmetli gerçek sınıflar. Atama yoksa boş liste (demo kart yok)."""
    siniflar = list(hoca.sorumlu_sinif_subeler.filter(aktif=True).order_by("sinif", "sube"))
    kartlar: list[OgretmenSinifKarti] = []

    for sinif in siniflar:
        sayi = Talebe.objects.filter(sinif_sube=sinif, aktif=True).count()
        etiket = f"{sinif.sinif}-{sinif.sube}"
        kartlar.append(
            OgretmenSinifKarti(
                id=sinif.id,
                etiket=etiket,
                ogrenci_sayisi=sayi,
                slug=etiket.lower().replace(" ", ""),
            )
        )

    return kartlar


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

    duyurular = list(ogretmen_duyurulari()[:8])

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
        "program_gunler": _program_gunleri(hoca),
        "randevular": ogretmen_randevu_listesi(hoca.user),
    }


def _program_gunleri(hoca: EtutHocasi | None = None) -> list[dict[str, Any]]:
    """Giriş yapan öğretmenin dershane programındaki gerçek dersleri."""
    if hoca is None:
        return []

    from takip.dershane_program_models import DershaneDersAtamasi, DershaneProgrami
    from takip.dershane_program_service import GUN_ADLARI, GUN_KISA

    program = (
        DershaneProgrami.objects.filter(aktif=True)
        .order_by("-baslangic_tarihi", "-id")
        .first()
    )
    if not program:
        return []

    ad = (hoca.ad_soyad or "").strip()
    if not ad:
        return []

    atamalar = (
        DershaneDersAtamasi.objects.filter(program=program)
        .filter(
            Q(ogretmen_adi__iexact=ad)
            | Q(ogretmen__ad_soyad__iexact=ad)
            | Q(ogretmen__etut_hocasi=hoca)
        )
        .select_related("saat_bloku", "etut_grubu", "ders", "ogretmen")
        .order_by("saat_bloku__gun", "saat_bloku__sira", "saat_bloku__baslangic_saati")
    )

    by_gun: dict[int, list[dict[str, str]]] = {}
    for atama in atamalar:
        blok = atama.saat_bloku
        if not blok:
            continue
        ders = atama.gorunen_ders
        if not ders or ders == "—":
            continue
        grup = atama.etut_grubu.etiket if atama.etut_grubu_id else ""
        by_gun.setdefault(blok.gun, []).append(
            {
                "saat": blok.saat_goster,
                "sinif": grup or (atama.etut_grubu.sinif_seviye if atama.etut_grubu_id else ""),
                "ders": ders,
            }
        )

    gunler = []
    for index, dersler in sorted(by_gun.items()):
        if index < 0 or index >= len(GUN_ADLARI):
            continue
        gunler.append(
            {
                "gun": GUN_ADLARI[index],
                "slug": GUN_KISA[index].lower(),
                "kisa": GUN_KISA[index],
                "dersler": dersler,
            }
        )
    return gunler


def ogretmen_program_verisi(hoca: EtutHocasi) -> dict[str, Any]:
    hafta_no, baslangic, bitis = _hafta_araligi()
    return {
        "hoca": hoca,
        "gunler": _program_gunleri(hoca),
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

    siniflar = list(
        SinifSube.objects.filter(aktif=True, sinif="8").order_by("sube")[:2]
    )
    if len(siniflar) < 2:
        siniflar = list(SinifSube.objects.filter(aktif=True).order_by("sinif", "sube")[:2])
    if siniflar:
        hoca.sorumlu_sinif_subeler.set(siniflar)
