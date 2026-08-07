"""Rehberlik sorguları, istatistikler ve premium panel verisi."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from takip.models import (
    GorusmeDosyasi,
    GorusmeGorevi,
    GorusmeTuru,
    OgrenciGorusmesi,
    Talebe,
)
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can


DEFAULT_GORUSME_TURLERI: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("Veli Görüşmesi", "veli-gorusmesi", "veli", "iletisim", "👨‍👩‍👦", "#2563eb"),
    ("Öğrenci Görüşmesi", "ogrenci-gorusmesi", "ogrenci", "iletisim", "🎓", "#7c3aed"),
    ("Telefon Görüşmesi", "telefon", "telefon", "iletisim", "📞", "#0891b2"),
    ("WhatsApp Görüşmesi", "whatsapp", "whatsapp", "iletisim", "💬", "#059669"),
    ("Akademik Planlama", "akademik-planlama", "akademik", "rehberlik", "📚", "#ea580c"),
    ("Disiplin Görüşmesi", "disiplin-gorusmesi", "disiplin", "rehberlik", "⚠️", "#dc2626"),
    ("Din Eğitimi", "din-egitimi", "din", "rehberlik", "🕌", "#0d9488"),
    ("Genel Not", "genel-not", "genel", "rehberlik", "📝", "#64748b"),
)

REHBERLIK_ETIKET_ONERILERI: tuple[str, ...] = (
    "Akademik Destek",
    "Davranış",
    "Motivasyon",
    "Sınav Hazırlığı",
    "Disiplin Süreci",
    "Din Eğitimi",
    "Takip Gerekli",
)

ILETISIM_ETIKET_ONERILERI: tuple[str, ...] = (
    "Veli İletişimi",
    "Öğrenci Görüşmesi",
    "Telefon",
    "WhatsApp",
    "Bilgilendirme",
    "Devamsızlık",
    "Etüt Takibi",
)


@dataclass
class DurumKarti:
    kod: str
    etiket: str
    renk: str
    arka_plan: str


def seed_gorusme_turleri() -> None:
    for sira, (ad, kod, grup, alan, ikon, renk) in enumerate(
        DEFAULT_GORUSME_TURLERI, start=1
    ):
        GorusmeTuru.objects.update_or_create(
            ad=ad,
            defaults={
                "kod": kod,
                "grup": grup,
                "alan": alan,
                "ikon": ikon,
                "renk": renk,
                "sira": sira,
                "aktif": True,
            },
        )


def aktif_gorusme_turleri(*, alan: str | None = None) -> QuerySet[GorusmeTuru]:
    qs = GorusmeTuru.objects.filter(aktif=True).order_by("sira", "ad")
    if alan:
        qs = qs.filter(alan=alan)
    return qs


def iletisim_gorebilir(user: User) -> bool:
    return can(user, "veli_iletisim", "view")


def iletisim_duzenleyebilir(user: User) -> bool:
    return can(user, "veli_iletisim", "edit") or can(user, "veli_iletisim", "create")


def rehberlik_gorebilir(user: User) -> bool:
    return can(user, "rehberlik", "view")


def rehberlik_duzenleyebilir(user: User) -> bool:
    return can(user, "rehberlik", "edit") or can(user, "rehberlik", "create")


def yetkili_gorusmeler(user: User, *, alan: str | None = None) -> QuerySet[OgrenciGorusmesi]:
    if alan == GorusmeTuru.Alan.ILETISIM:
        if not iletisim_gorebilir(user):
            return OgrenciGorusmesi.objects.none()
    elif alan == GorusmeTuru.Alan.REHBERLIK:
        if not rehberlik_gorebilir(user):
            return OgrenciGorusmesi.objects.none()
    elif not (rehberlik_gorebilir(user) or iletisim_gorebilir(user)):
        return OgrenciGorusmesi.objects.none()

    qs = OgrenciGorusmesi.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
        "talebe__dini_ders_seviyesi",
        "tur",
        "kaydeden",
    ).prefetch_related("gorevler", "dosyalar")

    if alan:
        qs = qs.filter(tur__alan=alan)

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user, aktif_only=False).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def gorusmeleri_filtrele(
    qs: QuerySet[OgrenciGorusmesi],
    *,
    q: str | None = None,
    tur_id: str | None = None,
    talebe_id: str | None = None,
    etiket: str | None = None,
    takip: str | None = None,
) -> QuerySet[OgrenciGorusmesi]:
    if q:
        qs = qs.filter(
            Q(talebe__ad_soyad__icontains=q)
            | Q(ozet__icontains=q)
            | Q(detay__icontains=q)
            | Q(kararlar__icontains=q)
        )
    if tur_id:
        qs = qs.filter(tur_id=tur_id)
    if talebe_id:
        qs = qs.filter(talebe_id=talebe_id)
    if etiket:
        qs = qs.filter(etiketler__icontains=etiket)
    if takip == "1":
        qs = qs.filter(takip_gerekiyor=True)
    return qs


def veli_gorusmeleri(talebe) -> QuerySet[OgrenciGorusmesi]:
    return (
        OgrenciGorusmesi.objects.filter(
            talebe=talebe,
            veli_goster=True,
            tur__alan=GorusmeTuru.Alan.ILETISIM,
        )
        .select_related("tur", "kaydeden")
        .order_by("-tarih", "-saat", "-id")
    )


def _grup_say(qs: QuerySet[OgrenciGorusmesi], grup: str) -> int:
    return qs.filter(tur__grup=grup).count()


def talebe_istatistikler(
    qs: QuerySet[OgrenciGorusmesi],
    *,
    alan: str,
) -> list[dict]:
    bekleyen = qs.filter(takip_gerekiyor=True).count()
    if alan == GorusmeTuru.Alan.ILETISIM:
        return [
            {"ikon": "💬", "deger": qs.count(), "etiket": "Toplam İletişim"},
            {"ikon": "👨‍👩‍👦", "deger": _grup_say(qs, "veli"), "etiket": "Veli Görüşmesi"},
            {"ikon": "🎓", "deger": _grup_say(qs, "ogrenci"), "etiket": "Öğrenci Görüşmesi"},
            {"ikon": "📞", "deger": _grup_say(qs, "telefon"), "etiket": "Telefon"},
            {"ikon": "💬", "deger": _grup_say(qs, "whatsapp"), "etiket": "WhatsApp"},
            {"ikon": "⏳", "deger": bekleyen, "etiket": "Bekleyen Takip"},
        ]
    return [
        {"ikon": "💬", "deger": qs.count(), "etiket": "Toplam Görüşme"},
        {"ikon": "📚", "deger": _grup_say(qs, "akademik"), "etiket": "Akademik"},
        {"ikon": "⚠️", "deger": _grup_say(qs, "disiplin"), "etiket": "Disiplin"},
        {"ikon": "🕌", "deger": _grup_say(qs, "din"), "etiket": "Din Eğitimi"},
        {"ikon": "📝", "deger": _grup_say(qs, "genel"), "etiket": "Genel Not"},
        {"ikon": "⏳", "deger": bekleyen, "etiket": "Bekleyen Takip"},
    ]


def talebe_genel_durum(talebe: Talebe, gorusmeler: QuerySet[OgrenciGorusmesi]) -> DurumKarti:
    son = gorusmeler.first()
    if not son:
        return DurumKarti("pasif", "Pasif", "#64748b", "#f1f5f9")

    if son.genel_durum == OgrenciGorusmesi.GenelDurum.RISK:
        return DurumKarti("risk", "Riskli", "#dc2626", "#fef2f2")
    if son.takip_gerekiyor or son.genel_durum == OgrenciGorusmesi.GenelDurum.TAKIP:
        return DurumKarti("takip", "Takip Gerekiyor", "#ea580c", "#fff7ed")
    if son.genel_durum == OgrenciGorusmesi.GenelDurum.PASIF:
        return DurumKarti("pasif", "Pasif", "#64748b", "#f1f5f9")
    return DurumKarti("iyi", "İyi Durumda", "#16a34a", "#f0fdf4")


def etiket_dagilimi(qs: QuerySet[OgrenciGorusmesi]) -> list[dict]:
    sayac: dict[str, int] = {}
    for etiketler in qs.values_list("etiketler", flat=True)[:200]:
        for etiket in etiketler or []:
            sayac[etiket] = sayac.get(etiket, 0) + 1
    if not sayac:
        for tur_ad in qs.values_list("tur__ad", flat=True)[:50]:
            if tur_ad:
                sayac[tur_ad] = sayac.get(tur_ad, 0) + 1
    toplam = sum(sayac.values()) or 1
    renkler = ["#2563eb", "#7c3aed", "#059669", "#ea580c", "#dc2626", "#0d9488", "#64748b"]
    return [
        {
            "etiket": k,
            "adet": v,
            "yuzde": round(v * 100 / toplam, 1),
            "renk": renkler[i % len(renkler)],
        }
        for i, (k, v) in enumerate(sorted(sayac.items(), key=lambda x: -x[1])[:7])
    ]


def donut_stil(dagilim: list[dict]) -> str:
    if not dagilim:
        return "conic-gradient(#e2e8f0 0 100%)"
    parcalar = []
    baslangic = 0.0
    for item in dagilim:
        bitis = baslangic + item["yuzde"]
        parcalar.append(f"{item['renk']} {baslangic}% {bitis}%")
        baslangic = bitis
    return f"conic-gradient({', '.join(parcalar)})"


def gorusme_yapanlar(qs: QuerySet[OgrenciGorusmesi]) -> list[dict]:
    rows = (
        qs.exclude(kaydeden__isnull=True)
        .values("kaydeden__first_name", "kaydeden__last_name", "kaydeden__username")
        .annotate(adet=Count("id"))
        .order_by("-adet")[:6]
    )
    sonuc = []
    for row in rows:
        ad = f"{row['kaydeden__first_name']} {row['kaydeden__last_name']}".strip()
        if not ad:
            ad = row["kaydeden__username"]
        bas_harf = (ad[:1] or "?").upper()
        sonuc.append({"ad": ad, "bas_harf": bas_harf, "adet": row["adet"]})
    return sonuc


def sonraki_gorusme_bilgisi(qs: QuerySet[OgrenciGorusmesi]) -> dict | None:
    bugun = timezone.localdate()
    kayit = (
        qs.filter(sonraki_gorusme__isnull=False, sonraki_gorusme__gte=bugun)
        .order_by("sonraki_gorusme", "sonraki_gorusme_saat")
        .first()
    )
    if not kayit:
        return None
    return {
        "tarih": kayit.sonraki_gorusme,
        "saat": kayit.sonraki_gorusme_saat,
        "durum": "Planlandı" if kayit.takip_gerekiyor else "Bekliyor",
        "ozet": kayit.ozet,
    }


def takip_konulari(talebe: Talebe) -> list[dict]:
    gorevler = (
        GorusmeGorevi.objects.filter(talebe=talebe, tamamlandi=False)
        .select_related("gorusme")
        .order_by("durum", "-olusturulma")[:8]
    )
    return [
        {
            "baslik": g.baslik,
            "durum": g.get_durum_display(),
            "sorumlu": g.sorumlu or "—",
        }
        for g in gorevler
    ]


def yapilacaklar_listesi(gorusme: OgrenciGorusmesi) -> list[dict]:
    items = gorusme.yapilacaklar or []
    if isinstance(items, list) and items:
        return items
    gorevler = list(gorusme.gorevler.all())
    return [
        {"metin": g.baslik, "tamamlandi": g.tamamlandi, "sorumlu": g.sorumlu}
        for g in gorevler
    ]


def kararlar_listesi(gorusme: OgrenciGorusmesi) -> list[str]:
    if not gorusme.kararlar:
        return []
    return [s.strip() for s in gorusme.kararlar.splitlines() if s.strip()]


def gorevleri_kaydet(gorusme: OgrenciGorusmesi, yapilacaklar: list[dict]) -> None:
    gorusme.gorevler.all().delete()
    for item in yapilacaklar:
        metin = (item.get("metin") or "").strip()
        if not metin:
            continue
        GorusmeGorevi.objects.create(
            gorusme=gorusme,
            talebe=gorusme.talebe,
            baslik=metin,
            sorumlu=item.get("sorumlu", ""),
            tamamlandi=bool(item.get("tamamlandi")),
            durum=GorusmeGorevi.Durum.TAMAM if item.get("tamamlandi") else GorusmeGorevi.Durum.BEKLIYOR,
        )


def sorumlu_kisi(talebe: Talebe, alan: str, qs: QuerySet[OgrenciGorusmesi]) -> str:
    if alan == GorusmeTuru.Alan.ILETISIM:
        if talebe.etut_hocasi_id:
            return talebe.etut_hocasi.ad_soyad
        return "—"
    yapanlar = gorusme_yapanlar(qs)
    return yapanlar[0]["ad"] if yapanlar else "—"


def talebe_gorusme_paneli(
    user: User,
    talebe: Talebe,
    alan: str,
    *,
    filtre: dict | None = None,
) -> dict:
    filtre = filtre or {}
    tum_kayitlar = yetkili_gorusmeler(user, alan=alan).filter(talebe=talebe)
    qs = gorusmeleri_filtrele(
        tum_kayitlar,
        q=filtre.get("q"),
        tur_id=filtre.get("tur"),
        etiket=filtre.get("etiket"),
        takip=filtre.get("takip"),
    )
    qs = qs.order_by("-tarih", "-saat", "-id")
    dagilim = etiket_dagilimi(qs)
    diger_alan = (
        GorusmeTuru.Alan.REHBERLIK
        if alan == GorusmeTuru.Alan.ILETISIM
        else GorusmeTuru.Alan.ILETISIM
    )
    return {
        "talebe": talebe,
        "alan": alan,
        "gorusmeler": qs[:100],
        "durum": talebe_genel_durum(talebe, qs),
        "istatistikler": talebe_istatistikler(tum_kayitlar, alan=alan),
        "etiket_dagilimi": dagilim,
        "donut_stil": donut_stil(dagilim),
        "takip_konulari": takip_konulari(talebe) if alan == GorusmeTuru.Alan.REHBERLIK else [],
        "sonraki_gorusme": sonraki_gorusme_bilgisi(qs),
        "yapanlar": gorusme_yapanlar(tum_kayitlar),
        "sorumlu_ad": sorumlu_kisi(talebe, alan, tum_kayitlar),
        "diger_modul_sayisi": yetkili_gorusmeler(user, alan=diger_alan)
        .filter(talebe=talebe)
        .count(),
        "disiplin_sayisi": talebe.disiplin_kayitlari.count()
        if alan == GorusmeTuru.Alan.REHBERLIK
        else 0,
    }


def talebe_rehberlik_paneli(user: User, talebe: Talebe, *, filtre: dict | None = None) -> dict:
    return talebe_gorusme_paneli(
        user,
        talebe,
        GorusmeTuru.Alan.REHBERLIK,
        filtre=filtre,
    )


def gorusme_timeline_dt(gorusme: OgrenciGorusmesi) -> datetime:
    saat = gorusme.saat or time(9, 0)
    dt = datetime.combine(gorusme.tarih, saat)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def seed_rehberlik_demo() -> None:
    """Örnek görüşme kayıtları — demo ortamı için."""
    from django.contrib.auth.models import User

    seed_gorusme_turleri()
    admin = User.objects.filter(is_superuser=True).first()
    if not admin:
        return

    talebeler = list(Talebe.objects.filter(aktif=True).select_related("etut_hocasi")[:6])
    if not talebeler:
        return

    turler = {t.grup: t for t in aktif_gorusme_turleri()}
    if OgrenciGorusmesi.objects.exists():
        return

    ornekler = [
        ("veli", "Veli ile akademik durum görüşmesi", "Veli İletişimi", True, OgrenciGorusmesi.GenelDurum.TAKIP),
        ("ogrenci", "Motivasyon ve hedef belirleme", "Motivasyon", False, OgrenciGorusmesi.GenelDurum.IYI),
        ("telefon", "Veli bilgilendirme — devamsızlık", "Davranış", True, OgrenciGorusmesi.GenelDurum.RISK),
        ("akademik", "Etüt planı revizyonu", "Akademik Destek", True, OgrenciGorusmesi.GenelDurum.TAKIP),
        ("whatsapp", "Veli hızlı bilgi", "Veli İletişimi", False, OgrenciGorusmesi.GenelDurum.IYI),
    ]

    bugun = timezone.localdate()
    for i, talebe in enumerate(talebeler):
        for j, (grup, ozet, etiket, takip, durum) in enumerate(ornekler):
            tur = turler.get(grup)
            if not tur:
                continue
            tarih = bugun - timedelta(days=i + j + 1)
            gorusme = OgrenciGorusmesi.objects.create(
                talebe=talebe,
                tur=tur,
                kaydeden=admin,
                tarih=tarih,
                saat=time(10 + j, 30),
                ozet=ozet,
                detay=f"{talebe.ad_soyad} için {tur.ad.lower()} kaydı.",
                kararlar="Haftalık takip planı oluşturuldu\nVeli bilgilendirildi",
                yapilacaklar=[
                    {"metin": "Etüt programını güncelle", "tamamlandi": False},
                    {"metin": "Veli geri dönüşünü bekle", "tamamlandi": j % 2 == 0},
                ],
                etiketler=[etiket, "Takip Gerekli" if takip else "Genel"],
                veli_goster=grup in {"veli", "telefon", "whatsapp"},
                takip_gerekiyor=takip,
                genel_durum=durum,
                sonraki_gorusme=bugun if takip else None,
                sonraki_gorusme_saat=time(14, 0) if takip else None,
            )
            gorevleri_kaydet(gorusme, gorusme.yapilacaklar)
