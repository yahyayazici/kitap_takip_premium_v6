"""Sözel–sayısal deneme sorguları ve kayıt yardımcıları."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.db.models import Count, Q, QuerySet

from takip.ktt_service import (
    hedef_siniflar_kaydet as _hedef_siniflar_kaydet,
    ktt_sinif_secenekleri,
    ktt_sinif_secimlerini_dogrula,
    ktt_tam_yetki,
)
from takip.models import Talebe
from takip.permissions.service import can
from takip.ss_deneme_models import (
    BRANS_DERS_ADLARI,
    BRANS_ETIKETLERI,
    SAYISAL_BRANSLAR,
    SOZEL_BRANSLAR,
    TUM_BRANSLAR,
    SozelSayisalBransSonuc,
    SozelSayisalDeneme,
    SozelSayisalSonuc,
)
from takip.user_helpers import etut_hocasi_for_user


def yetkili_ss_denemeler(user: User) -> QuerySet[SozelSayisalDeneme]:
    from takip.permissions.scope import tum_talebe_kapsami_var

    qs = SozelSayisalDeneme.objects.filter(aktif=True).select_related(
        "etut_hocasi", "olusturan"
    ).annotate(sonuc_sayisi=Count("sonuclar"))

    if not can(user, "ktt", "view"):
        return SozelSayisalDeneme.objects.none()

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    hoca = etut_hocasi_for_user(user)
    if hoca:
        return qs.filter(etut_hocasi=hoca)
    return SozelSayisalDeneme.objects.none()


def ss_olusturabilir(user: User) -> bool:
    return can(user, "ktt", "create")


def ss_duzenleyebilir(user: User, deneme: SozelSayisalDeneme) -> bool:
    if not can(user, "ktt", "edit"):
        return False
    if ktt_tam_yetki(user):
        return True
    hoca = etut_hocasi_for_user(user)
    return hoca is not None and deneme.etut_hocasi_id == hoca.id


def ss_silebilir(user: User, deneme: SozelSayisalDeneme) -> bool:
    if not can(user, "ktt", "view"):
        return False
    if ktt_tam_yetki(user) or can(user, "ktt", "delete"):
        return True
    if not (can(user, "ktt", "create") or can(user, "ktt", "edit")):
        return False
    if deneme.olusturan_id == user.id:
        return True
    hoca = etut_hocasi_for_user(user)
    return hoca is not None and deneme.etut_hocasi_id == hoca.id


def ss_sinif_secenekleri(user: User):
    return ktt_sinif_secenekleri(user)


def ss_sinif_secimlerini_dogrula(user: User, secilen: list[str]):
    return ktt_sinif_secimlerini_dogrula(user, secilen)


def ss_hedef_siniflar_kaydet(deneme: SozelSayisalDeneme, secilen: list[str]) -> None:
    _hedef_siniflar_kaydet(deneme, secilen)


def ss_hedef_talebeleri(user: User, deneme: SozelSayisalDeneme) -> QuerySet[Talebe]:
    from takip.permissions.scope import yetkili_talebeler

    talebeler = yetkili_talebeler(user, aktif_only=True)

    if ktt_tam_yetki(user):
        talebeler = talebeler.filter(etut_hocasi=deneme.etut_hocasi)
    else:
        hoca = etut_hocasi_for_user(user)
        if not hoca or deneme.etut_hocasi_id != hoca.id:
            return Talebe.objects.none()

    etiketler = [s.strip() for s in (deneme.hedef_siniflar or "").split(",") if s.strip()]
    if etiketler:
        q = Q()
        for etiket in etiketler:
            parca = etiket.split("-", 1)
            if len(parca) == 2:
                q |= Q(sinif=parca[0].strip(), sube=parca[1].strip())
            else:
                q |= Q(sinif=etiket)
        if q:
            talebeler = talebeler.filter(q)

    return talebeler.order_by("ad_soyad")


def ss_sonuc_talebeleri(user: User, deneme: SozelSayisalDeneme) -> QuerySet[Talebe]:
    return ss_hedef_talebeleri(user, deneme).exclude(
        id__in=deneme.haric_talebeler.values_list("pk", flat=True)
    )


def _net(dogru: int, yanlis: int) -> Decimal:
    return SozelSayisalBransSonuc.net_hesapla(dogru, yanlis)


def _puan(net: Decimal, soru: int) -> Decimal:
    if soru <= 0:
        return Decimal("0.00")
    return (net * Decimal("100") / Decimal(soru)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def sonuc_katildi(sonuc: SozelSayisalSonuc | None, deneme: SozelSayisalDeneme) -> bool:
    if not sonuc:
        return False
    return not (
        int(sonuc.toplam_dogru or 0) == 0
        and int(sonuc.toplam_yanlis or 0) == 0
        and int(sonuc.toplam_bos or 0) == int(deneme.soru_sayisi)
    )


def brans_map(sonuc: SozelSayisalSonuc | None) -> dict[str, SozelSayisalBransSonuc]:
    if not sonuc:
        return {}
    return {b.brans: b for b in sonuc.brans_satirlari.all()}


def bolum_kodlari(bolum: str) -> tuple[str, ...]:
    if bolum == "sozel":
        return SOZEL_BRANSLAR
    if bolum == "sayisal":
        return SAYISAL_BRANSLAR
    return TUM_BRANSLAR


def bolum_etiket(bolum: str) -> str:
    return {
        "sozel": "Sözel",
        "sayisal": "Sayısal",
        "hepsi": "Sözel + Sayısal",
    }.get(bolum, "Sözel + Sayısal")


def siralama_alani(bolum: str) -> str:
    if bolum == "sozel":
        return "-sozel_net"
    if bolum == "sayisal":
        return "-sayisal_net"
    return "-toplam_net"


def sonuc_toplamlari_guncelle(sonuc: SozelSayisalSonuc) -> None:
    satirlar = list(sonuc.brans_satirlari.all())
    by_kod = {s.brans: s for s in satirlar}

    def topla(kodlar: tuple[str, ...]) -> tuple[int, int, int, Decimal]:
        d = y = b = 0
        for kod in kodlar:
            satir = by_kod.get(kod)
            if not satir:
                continue
            d += int(satir.dogru or 0)
            y += int(satir.yanlis or 0)
            b += int(satir.bos or 0)
        return d, y, b, _net(d, y)

    sz_d, sz_y, sz_b, sz_n = topla(SOZEL_BRANSLAR)
    sy_d, sy_y, sy_b, sy_n = topla(SAYISAL_BRANSLAR)
    t_d, t_y, t_b, t_n = topla(TUM_BRANSLAR)

    sonuc.sozel_dogru = sz_d
    sonuc.sozel_yanlis = sz_y
    sonuc.sozel_bos = sz_b
    sonuc.sozel_net = sz_n
    sonuc.sayisal_dogru = sy_d
    sonuc.sayisal_yanlis = sy_y
    sonuc.sayisal_bos = sy_b
    sonuc.sayisal_net = sy_n
    sonuc.toplam_dogru = t_d
    sonuc.toplam_yanlis = t_y
    sonuc.toplam_bos = t_b
    sonuc.toplam_net = t_n
    sonuc.puan = _puan(t_n, sonuc.deneme.soru_sayisi)
    sonuc.save(
        update_fields=[
            "sozel_dogru",
            "sozel_yanlis",
            "sozel_bos",
            "sozel_net",
            "sayisal_dogru",
            "sayisal_yanlis",
            "sayisal_bos",
            "sayisal_net",
            "toplam_dogru",
            "toplam_yanlis",
            "toplam_bos",
            "toplam_net",
            "puan",
            "guncellenme",
        ]
    )


def sirali_satirlar(user: User, deneme: SozelSayisalDeneme, bolum: str = "hepsi"):
    sonuclar = (
        SozelSayisalSonuc.objects.filter(deneme=deneme)
        .select_related("talebe", "talebe__sinif_sube")
        .prefetch_related("brans_satirlari")
        .order_by(siralama_alani(bolum), "talebe__ad_soyad")
    )
    kodlar = bolum_kodlari(bolum)
    kolonlar = [{"kod": kod, "etiket": BRANS_ETIKETLERI[kod]} for kod in kodlar]
    satirlar = []
    for sira, sonuc in enumerate(sonuclar, start=1):
        bmap = brans_map(sonuc)
        hucreler = []
        for kod in kodlar:
            br = bmap.get(kod)
            hucreler.append(
                {
                    "kod": kod,
                    "etiket": BRANS_ETIKETLERI[kod],
                    "dogru": br.dogru if br else 0,
                    "yanlis": br.yanlis if br else 0,
                    "bos": br.bos if br else 0,
                    "net": br.net if br else 0,
                }
            )
        satirlar.append(
            {
                "sira": sira,
                "sonuc": sonuc,
                "talebe": sonuc.talebe,
                "hucreler": hucreler,
            }
        )
    return satirlar, kolonlar


def ss_deneme_sonucu_soru_takibe_yansit(
    *,
    user: User,
    deneme: SozelSayisalDeneme,
    talebe: Talebe,
    yeni_brans: dict[str, tuple[int, int, int]] | None = None,
    onceki_brans: dict[str, tuple[int, int, int]] | None = None,
    silindi: bool = False,
) -> None:
    """
    Branş D/Y/B değerlerini sınav tarihindeki günlük soru takibine yansıtır.
    Aynı deneme tekrar kaydedilirse önceki katkı düşülür (çift sayım olmaz).
    """
    from takip.models import Ders, GunlukSoruDersSatiri, GunlukSoruKaydi

    tarih = deneme.sinav_tarihi
    if tarih is None or talebe is None:
        return

    kayit, _ = GunlukSoruKaydi.objects.get_or_create(
        talebe=talebe,
        tarih=tarih,
        defaults={"kaydeden": user},
    )
    not_ek = f"SS Deneme: {deneme.ad}"
    mevcut_not = (kayit.gunluk_not or "").strip()
    if not_ek not in mevcut_not:
        kayit.gunluk_not = f"{mevcut_not}\n{not_ek}".strip() if mevcut_not else not_ek
    kayit.kaydeden = user
    kayit.save(update_fields=["gunluk_not", "kaydeden", "guncellenme"])

    onceki_brans = onceki_brans or {}
    yeni_brans = {} if silindi else (yeni_brans or {})

    for kod in TUM_BRANSLAR:
        ders_ad = BRANS_DERS_ADLARI.get(kod)
        if not ders_ad:
            continue
        ders = Ders.objects.filter(ad=ders_ad, aktif=True).first()
        if not ders:
            continue

        o_d, o_y, o_b = onceki_brans.get(kod, (0, 0, 0))
        n_d, n_y, n_b = yeni_brans.get(kod, (0, 0, 0))

        satir = GunlukSoruDersSatiri.objects.filter(kayit=kayit, ders=ders).first()
        cur_d = int(satir.dogru or 0) if satir else 0
        cur_y = int(satir.yanlis or 0) if satir else 0
        cur_b = int(satir.bos or 0) if satir else 0

        yeni_d = max(0, cur_d - int(o_d or 0) + int(n_d or 0))
        yeni_y = max(0, cur_y - int(o_y or 0) + int(n_y or 0))
        yeni_b = max(0, cur_b - int(o_b or 0) + int(n_b or 0))
        yeni_toplam = yeni_d + yeni_y + yeni_b

        if yeni_toplam <= 0:
            if satir:
                satir.delete()
            continue

        GunlukSoruDersSatiri.objects.update_or_create(
            kayit=kayit,
            ders=ders,
            defaults={
                "toplam_soru": yeni_toplam,
                "dogru": yeni_d,
                "yanlis": yeni_y,
                "bos": yeni_b,
            },
        )
