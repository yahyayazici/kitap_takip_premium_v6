"""AI tetikleyicili bildirimler — erken uyarı, deneme, veli brifing, öğretmen not."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.timezone import localdate

from takip.ai_gateway import ai_platform_aktif_mi
from takip.bildirim_models import Bildirim
from takip.bildirim_service import bildirim_gonder, bildirim_gonder_coklu
from takip.models import EtutHocasi, PersonelProfili, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var
from takip.wave0_models import VeliTalebeBaglantisi

logger = logging.getLogger(__name__)

KAYNAK_ERKEN_UYARI = "AiErkenUyari"
KAYNAK_DENEME = "AiDenemePaketi"
KAYNAK_VELI_BRIFING = "AiVeliHaftalik"
KAYNAK_OGRETMEN_NOT = "AiOgretmenNotVeli"


def ai_bildirim_aktif() -> bool:
    return ai_platform_aktif_mi()


def kurum_yoneticileri() -> list[User]:
    """Tam talebe kapsamına sahip idareci / mesul personel."""
    users: dict[int, User] = {}
    for profil in PersonelProfili.objects.filter(aktif=True).select_related("user"):
        user = profil.user
        if not user or not user.is_active:
            continue
        if user.is_superuser or tum_talebe_kapsami_var(user):
            users[user.pk] = user
    return list(users.values())


def veli_kullanicilari(talebe: Talebe) -> list[User]:
    qs = VeliTalebeBaglantisi.objects.filter(
        talebe=talebe,
        veli__aktif=True,
    ).select_related("veli__user")
    return [b.veli.user for b in qs if b.veli.user.is_active]


def _hafta_kaynak_id(bugun: date | None = None) -> int:
    bugun = bugun or localdate()
    hafta = bugun.isocalendar()[1]
    return bugun.year * 100 + hafta


def erken_uyari_bildirimleri() -> int:
    """Risk skoru yüksek öğrenciler için idareciye haftalık erken uyarı."""
    if not ai_bildirim_aktif():
        return 0

    alicilar = kurum_yoneticileri()
    if not alicilar:
        return 0

    from takip.ai_context import _mudahale_adaylari

    rep = alicilar[0]
    adaylar = _mudahale_adaylari(rep, limit=8)
    if not adaylar:
        return 0

    bugun = localdate()
    isimler = ", ".join(a["ad_soyad"] for a in adaylar[:5])
    ek = f" (+{len(adaylar) - 5} daha)" if len(adaylar) > 5 else ""
    mesaj = (
        f"{len(adaylar)} öğrenci risk sinyali taşıyor: {isimler}{ek}.\n"
        "Paneldeki Erken Uyarı şeridine bakın."
    )

    try:
        link = reverse("dashboard")
    except Exception:
        link = "/"

    return bildirim_gonder_coklu(
        alicilar,
        baslik=f"AI Erken Uyarı · {len(adaylar)} öğrenci",
        mesaj=mesaj,
        tur=Bildirim.Tur.SISTEM,
        link=link,
        bitis=bugun + timedelta(days=7),
        kaynak_model=KAYNAK_ERKEN_UYARI,
        kaynak_id=_hafta_kaynak_id(bugun),
        dedupe=True,
    )


def deneme_sonrasi_bildirimleri(deneme, user, sonuc_sayisi: int) -> None:
    """Deneme aktarımı sonrası AI analizi üret ve personeli bilgilendir."""
    if not ai_bildirim_aktif() or sonuc_sayisi <= 0:
        return

    from takip.models import DenemeSonucu
    from takip.ai_service import deneme_zekasi_analizi

    sonuclar = DenemeSonucu.objects.filter(deneme=deneme).select_related(
        "talebe", "talebe__etut_hocasi__user"
    )

    ozet = f"{sonuc_sayisi} öğrenci sonucu aktarıldı."
    try:
        analiz = deneme_zekasi_analizi(user, deneme, sonuclar, yenile=True)
        if analiz.bolumler:
            ozet = analiz.bolumler[0].icerik[:400]
    except Exception:
        logger.exception("Deneme AI paketi üretilemedi deneme=%s", deneme.pk)

    try:
        link = reverse("yonetim:deneme_detay", kwargs={"pk": deneme.pk})
    except Exception:
        link = f"/yonetim/deneme/{deneme.pk}/"

    alicilar = kurum_yoneticileri()
    if user and getattr(user, "pk", None):
        birlesik = {u.pk: u for u in alicilar}
        birlesik[user.pk] = user
        alicilar = list(birlesik.values())

    bildirim_gonder_coklu(
        alicilar,
        baslik=f"Deneme Zekası hazır · {deneme.ad}",
        mesaj=ozet,
        tur=Bildirim.Tur.SISTEM,
        link=link,
        olusturan=user,
        kaynak_model=KAYNAK_DENEME,
        kaynak_id=deneme.pk,
        dedupe=False,
    )

    etut_user_ids: set[int] = set()
    for sonuc in sonuclar:
        hoca = getattr(sonuc.talebe, "etut_hocasi", None)
        if hoca and hoca.user_id and hoca.aktif:
            etut_user_ids.add(hoca.user_id)

    if etut_user_ids:
        etut_users = User.objects.filter(pk__in=etut_user_ids, is_active=True)
        bildirim_gonder_coklu(
            etut_users,
            baslik=f"Yeni deneme sonuçları · {deneme.ad}",
            mesaj=(
                f"{sonuc_sayisi} öğrenci sonucu yüklendi. "
                "AI analizi deneme detay sayfasında."
            ),
            tur=Bildirim.Tur.SISTEM,
            link=link,
            olusturan=user,
            kaynak_model=KAYNAK_DENEME,
            kaynak_id=deneme.pk * 10000 + 1,
            dedupe=False,
        )


def ogretmen_not_sonrasi_veli_bildirimleri(
    hoca: EtutHocasi,
    ders,
    hafta_baslangic: date,
    hafta_no: int,
    kayitlar: list[dict],
    *,
    olusturan: User | None = None,
) -> list[dict[str, Any]]:
    """Öğretmen not kaydı sonrası veliye bildirim + öğretmen için taslak listesi."""
    if not ai_bildirim_aktif():
        return []

    from takip.ai_service import veli_not_mesaj_taslagi

    taslaklar: list[dict[str, Any]] = []
    for satir in kayitlar:
        ogrenci = satir["ogrenci"]
        if satir.get("yok"):
            continue

        mesaj = veli_not_mesaj_taslagi(
            ogrenci,
            katilim=satir["katilim"],
            takip=satir["takip"],
            disiplin=satir["disiplin"],
            aciklama=satir["aciklama"],
            ders_ad=ders.ad,
            hafta_no=hafta_no,
            hoca_ad=hoca.ad_soyad,
        )
        taslaklar.append(
            {
                "talebe_id": ogrenci.id,
                "ad_soyad": ogrenci.ad_soyad,
                "mesaj": mesaj,
            }
        )

        veliler = veli_kullanicilari(ogrenci)
        if not veliler:
            continue

        try:
            link = reverse("veli_talebe_dashboard", kwargs={"talebe_id": ogrenci.id})
        except Exception:
            link = f"/veli/talebe/{ogrenci.id}/"

        bildirim_gonder_coklu(
            veliler,
            baslik=f"{ogrenci.ad_soyad} · {hafta_no}. hafta ders notu",
            mesaj=mesaj,
            tur=Bildirim.Tur.SISTEM,
            link=link,
            olusturan=olusturan or hoca.user,
            kaynak_model=KAYNAK_OGRETMEN_NOT,
            kaynak_id=ogrenci.id * 1000 + hafta_baslangic.toordinal() % 100000,
            dedupe=True,
        )

    return taslaklar


def veli_haftalik_brifing_gonder(*, yenile: bool = False) -> int:
    """Aktif velilere haftalık AI özet bildirimi (Pazar cron)."""
    if not ai_bildirim_aktif():
        return 0

    from takip.ai_service import veli_haftalik_ozet

    bugun = localdate()
    kaynak_id = _hafta_kaynak_id(bugun)
    sayac = 0

    baglantilar = VeliTalebeBaglantisi.objects.filter(
        veli__aktif=True,
        talebe__durum=Talebe.Durum.AKTIF,
    ).select_related("veli__user", "talebe")

    seen: set[tuple[int, int]] = set()
    for bag in baglantilar:
        key = (bag.veli_id, bag.talebe_id)
        if key in seen:
            continue
        seen.add(key)

        veli_user = bag.veli.user
        if not veli_user or not veli_user.is_active:
            continue

        talebe = bag.talebe
        try:
            ozet = veli_haftalik_ozet(talebe, user=veli_user, yenile=yenile)
            parcalar = [b.icerik for b in ozet.bolumler[:3] if b.icerik]
            mesaj = "\n\n".join(parcalar) or "Haftalık özet hazırlandı."
        except Exception:
            logger.exception("Veli brifing üretilemedi talebe=%s", talebe.pk)
            continue

        try:
            link = reverse("veli_talebe_dashboard", kwargs={"talebe_id": talebe.id})
        except Exception:
            link = f"/veli/talebe/{talebe.id}/"

        if bildirim_gonder(
            veli_user,
            baslik=f"{talebe.ad_soyad} · Haftalık AI Özeti",
            mesaj=mesaj[:1500],
            tur=Bildirim.Tur.SISTEM,
            link=link,
            bitis=bugun + timedelta(days=7),
            kaynak_model=KAYNAK_VELI_BRIFING,
            kaynak_id=talebe.id * 10000 + kaynak_id,
            dedupe=True,
        ):
            sayac += 1

    return sayac
