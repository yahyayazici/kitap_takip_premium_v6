"""Akademik müdahale sorguları ve yardımcılar."""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.db.models import Count, QuerySet

from takip.filter_utils import qs_filtre_id
from takip.models import AkademikMudahale, MudahaleTuru, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can

DEFAULT_MUDAHALE_TURLERI: tuple[tuple[str, str, str, list], ...] = (
    ("Ek Ders", "📘", "#2563EB", []),
    ("Birebir Etüt", "👨‍🏫", "#7C3AED", []),
    ("Eksik Konu Çalışması", "📖", "#059669", []),
    ("Konu Tekrarı", "🔁", "#0891B2", []),
    (
        "Soru Çözümü",
        "📝",
        "#D97706",
        [
            {"key": "kaynak", "label": "Kaynak", "type": "text"},
            {"key": "sayfa", "label": "Sayfa", "type": "text"},
            {"key": "soru_araligi", "label": "Soru aralığı", "type": "text"},
            {
                "key": "cozulen_soru",
                "label": "Çözülen soru sayısı",
                "type": "number",
            },
        ],
    ),
    ("Yaprak Test", "📄", "#DC2626", []),
    ("Deneme Analizi Sonrası Çalışma", "📊", "#4F46E5", []),
    (
        "Kitap Okuma",
        "📚",
        "#0D9488",
        [
            {"key": "kitap_adi", "label": "Kitap adı", "type": "text"},
            {"key": "sayfa_araligi", "label": "Sayfa aralığı", "type": "text"},
        ],
    ),
    ("Video Destekli Çalışma", "🎥", "#9333EA", []),
    ("Ödevlendirme", "🏠", "#64748B", []),
)


def seed_mudahale_turleri() -> None:
    for sira, (ad, ikon, renk, sema) in enumerate(DEFAULT_MUDAHALE_TURLERI, start=1):
        MudahaleTuru.objects.update_or_create(
            ad=ad,
            defaults={
                "ikon": ikon,
                "renk": renk,
                "sira": sira,
                "aktif": True,
                "form_semasi": sema,
            },
        )


def aktif_mudahale_turleri() -> QuerySet[MudahaleTuru]:
    return MudahaleTuru.objects.filter(aktif=True).order_by("sira", "ad")


def mudahale_tam_yetki(user: User) -> bool:
    return user.is_superuser or can(user, "akademik_mudahale", "delete")


def yetkili_mudahaleler(user: User) -> QuerySet[AkademikMudahale]:
    if not can(user, "akademik_mudahale", "view"):
        return AkademikMudahale.objects.none()

    qs = AkademikMudahale.objects.select_related(
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
        "ders",
        "mudahale_turu",
        "olusturan",
    )

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def mudahale_olusturabilir(user: User) -> bool:
    return can(user, "akademik_mudahale", "create")


def mudahale_duzenleyebilir(user: User, mudahale: AkademikMudahale) -> bool:
    if not can(user, "akademik_mudahale", "edit"):
        return False
    return yetkili_mudahaleler(user).filter(pk=mudahale.pk).exists()


def mudahale_silebilir(user: User, mudahale: AkademikMudahale) -> bool:
    if not can(user, "akademik_mudahale", "delete"):
        return False
    return yetkili_mudahaleler(user).filter(pk=mudahale.pk).exists()


def ek_alanlari_topla(post_data, tur: MudahaleTuru) -> dict:
    ek: dict = {}
    for alan in tur.form_semasi or []:
        key = alan.get("key")
        if not key:
            continue
        deger = post_data.get(f"ek_{key}", "").strip()
        if deger:
            ek[key] = deger
    return ek


def talebe_akademik_ozet(talebe: Talebe) -> dict:
    kayitlar = AkademikMudahale.objects.filter(talebe=talebe)
    bugun = date.today()
    ay_basi = bugun.replace(day=1)
    onceki_ay_son = ay_basi - timedelta(days=1)
    onceki_ay_basi = onceki_ay_son.replace(day=1)

    toplam = kayitlar.count()
    bu_ay = kayitlar.filter(tarih__gte=ay_basi).count()
    gecen_ay = kayitlar.filter(
        tarih__gte=onceki_ay_basi,
        tarih__lte=onceki_ay_son,
    ).count()

    ders_dagilimi = list(
        kayitlar.filter(ders__isnull=False)
        .values("ders__ad")
        .annotate(adet=Count("id"))
        .order_by("-adet")[:6]
    )
    en_cok_ders = ders_dagilimi[0]["ders__ad"] if ders_dagilimi else None

    return {
        "toplam": toplam,
        "bu_ay": bu_ay,
        "gecen_ay": gecen_ay,
        "en_cok_ders": en_cok_ders,
        "ders_dagilimi": ders_dagilimi,
    }


def rapor_istatistikleri(qs: QuerySet[AkademikMudahale]) -> dict:
    toplam = qs.count()
    ogrenci_sayisi = qs.values("talebe_id").distinct().count()
    ortalama = round(toplam / ogrenci_sayisi, 1) if ogrenci_sayisi else 0

    en_cok_ders = (
        qs.filter(ders__isnull=False)
        .values("ders__ad")
        .annotate(adet=Count("id"))
        .order_by("-adet")
        .first()
    )
    en_cok_konu = (
        qs.exclude(konu="")
        .values("konu")
        .annotate(adet=Count("id"))
        .order_by("-adet")
        .first()
    )

    return {
        "toplam_mudahale": toplam,
        "ogrenci_sayisi": ogrenci_sayisi,
        "ortalama_mudahale": ortalama,
        "en_cok_ders": en_cok_ders["ders__ad"] if en_cok_ders else None,
        "en_cok_konu": en_cok_konu["konu"] if en_cok_konu else None,
    }


def mudahaleleri_filtrele(
    qs: QuerySet[AkademikMudahale],
    *,
    talebe: str | None = None,
    talebe_id: str | None = None,
    talebe_ids: list[int] | None = None,
    sinif_sube: str | None = None,
    sinif_sube_id: str | None = None,
    sinif_sube_ids: list[int] | None = None,
    ders: str | None = None,
    ders_id: str | None = None,
    ders_ids: list[int] | None = None,
    tur: str | None = None,
    tur_id: str | None = None,
    tur_ids: list[int] | None = None,
    konu: str | None = None,
    olusturan: str | None = None,
    olusturan_id: str | None = None,
    olusturan_ids: list[int] | None = None,
    baslangic: str | None = None,
    bitis: str | None = None,
) -> QuerySet[AkademikMudahale]:
    talebe_id = talebe_id or talebe
    sinif_sube_id = sinif_sube_id or sinif_sube
    ders_id = ders_id or ders
    tur_id = tur_id or tur
    olusturan_id = olusturan_id or olusturan
    qs = qs_filtre_id(qs, "talebe_id", talebe_id, talebe_ids)
    qs = qs_filtre_id(qs, "talebe__sinif_sube_id", sinif_sube_id, sinif_sube_ids)
    qs = qs_filtre_id(qs, "ders_id", ders_id, ders_ids)
    qs = qs_filtre_id(qs, "mudahale_turu_id", tur_id, tur_ids)
    if konu:
        qs = qs.filter(konu__icontains=konu)
    qs = qs_filtre_id(qs, "olusturan_id", olusturan_id, olusturan_ids)
    if baslangic:
        qs = qs.filter(tarih__gte=baslangic)
    if bitis:
        qs = qs.filter(tarih__lte=bitis)
    return qs


def mudahale_sinif_secenekleri(user: User):
    from takip.ktt_service import ktt_sinif_secenekleri

    return ktt_sinif_secenekleri(user)


def mudahale_toplu_sinif_olustur(
    user: User,
    *,
    sinif_sube_id: int,
    mudahale_turu: MudahaleTuru,
    ders,
    konu: str,
    sure_dakika: int,
    degerlendirme_notu: str,
    veliye_goster: bool,
    ek_alanlar: dict,
    tarih: date | None = None,
) -> int:
    """Seçilen sınıftaki tüm yetkili talebelere aynı müdahale kaydını ekler."""
    from takip.models import SinifSube

    if not SinifSube.objects.filter(pk=sinif_sube_id, aktif=True).exists():
        return 0

    talebeler = yetkili_talebeler(user, aktif_only=True).filter(
        sinif_sube_id=sinif_sube_id
    )
    if not talebeler.exists():
        return 0

    kayit_tarihi = tarih or date.today()
    kayitlar = [
        AkademikMudahale(
            talebe=talebe,
            ders=ders,
            konu=konu or "",
            mudahale_turu=mudahale_turu,
            tarih=kayit_tarihi,
            sure_dakika=sure_dakika or 0,
            olusturan=user,
            degerlendirme_notu=degerlendirme_notu or "",
            veliye_goster=veliye_goster,
            ek_alanlar=ek_alanlar or {},
        )
        for talebe in talebeler
    ]
    AkademikMudahale.objects.bulk_create(kayitlar)
    return len(kayitlar)


def talebe_panel_verisi(user: User) -> list[dict]:
    talebeler = yetkili_talebeler(user, aktif_only=True).select_related("sinif_sube")
    veri = []
    for t in talebeler.order_by("ad_soyad"):
        if t.sinif_sube_id:
            sinif_etiket = f"{t.sinif_sube.sinif}-{t.sinif_sube.sube}"
            sinif_sube_id = t.sinif_sube_id
        else:
            sinif_etiket = f"{t.sinif}-{t.sube}".strip("-")
            sinif_sube_id = None
        veri.append(
            {
                "id": t.id,
                "ad_soyad": t.ad_soyad,
                "talebe_no": t.talebe_no or "",
                "sinif_sube_id": sinif_sube_id,
                "sinif_etiket": sinif_etiket,
            }
        )
    return veri


def seed_akademik_mudahale_demo() -> None:
    from takip.models import Ders, EtutHocasi, SinifSube

    hoca = EtutHocasi.objects.filter(ad_soyad__icontains="Yahya").first()
    if not hoca or not hoca.user_id:
        return

    sinif_7a, _ = SinifSube.objects.get_or_create(
        sinif="7", sube="A", defaults={"aktif": True}
    )
    sinif_7b, _ = SinifSube.objects.get_or_create(
        sinif="7", sube="B", defaults={"aktif": True}
    )

    talebe_veriler = [
        ("Ahmet Yılmaz", sinif_7a, "1034"),
        ("Mehmet Kaya", sinif_7a, "1035"),
        ("Yusuf Akın", sinif_7b, "1036"),
    ]
    talebeler = []
    for ad, ss, no in talebe_veriler:
        t, _ = Talebe.objects.get_or_create(
            ad_soyad=ad,
            defaults={
                "sinif": ss.sinif,
                "sube": ss.sube,
                "sinif_sube": ss,
                "talebe_no": no,
                "etut_hocasi": hoca,
                "aktif": True,
            },
        )
        guncelle = False
        if t.sinif_sube_id != ss.id:
            t.sinif_sube = ss
            t.sinif = ss.sinif
            t.sube = ss.sube
            guncelle = True
        if not t.talebe_no:
            t.talebe_no = no
            guncelle = True
        if t.etut_hocasi_id != hoca.id:
            t.etut_hocasi = hoca
            guncelle = True
        if guncelle:
            t.save()
        talebeler.append(t)

    tur_deneme = MudahaleTuru.objects.filter(ad="Deneme Analizi Sonrası Çalışma").first()
    tur_ek = MudahaleTuru.objects.filter(ad="Ek Ders").first()
    tur_soru = MudahaleTuru.objects.filter(ad="Soru Çözümü").first()
    tur_tekrar = MudahaleTuru.objects.filter(ad="Konu Tekrarı").first()
    matematik = Ders.objects.filter(ad="Matematik", aktif=True).first()
    turkce = Ders.objects.filter(ad="Türkçe", aktif=True).first()

    bugun = date.today()
    ornekler = [
        (talebeler[0], tur_deneme, turkce, "Paragrafın Yapısı", 45, 2),
        (talebeler[0], tur_soru, matematik, "Tam Sayı Problemleri", 40, 1),
        (talebeler[1], tur_ek, matematik, "Rasyonel Sayılar", 50, 0),
        (talebeler[1], tur_tekrar, turkce, "Fiilimsiler", 30, 3),
        (talebeler[2], tur_deneme, matematik, "Deneme Analizi", 60, 1),
    ]

    for talebe, tur, ders, konu, sure, gun_farki in ornekler:
        if not tur:
            continue
        AkademikMudahale.objects.update_or_create(
            talebe=talebe,
            mudahale_turu=tur,
            konu=konu,
            tarih=bugun - timedelta(days=gun_farki),
            defaults={
                "ders": ders,
                "sure_dakika": sure,
                "degerlendirme_notu": f"{konu} konusunda birebir çalışma yapıldı.",
                "veliye_goster": True,
                "olusturan": hoca.user,
            },
        )
