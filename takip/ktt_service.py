"""KTT sorguları ve yardımcılar."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.db.models import Avg, Count, Max, Q, QuerySet, Sum
from django.utils.timezone import localdate

from takip.filter_utils import get_int_list, qs_filtre_id
from takip.models import Ders, EtutHocasi, KttSinav, KttSonucu, SinifSube, Talebe
from takip.permissions.service import can
from takip.user_helpers import etut_hocasi_for_user


def _etut_hocasi(user: User) -> EtutHocasi | None:
    return etut_hocasi_for_user(user)


def ktt_tam_yetki(user: User) -> bool:
    return user.is_superuser or can(user, "ktt", "delete")


def yetkili_ktt_sinavlari(user: User) -> QuerySet[KttSinav]:
    from takip.permissions.scope import tum_talebe_kapsami_var

    qs = (
        KttSinav.objects.filter(aktif=True)
        .select_related("ders", "ders__brans", "etut_hocasi", "olusturan", "konu_katalog")
        .annotate(sonuc_sayisi=Count("sonuclar"))
    )

    if not can(user, "ktt", "view"):
        return KttSinav.objects.none()

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    hoca = _etut_hocasi(user)
    q = Q()
    if hoca:
        q |= Q(etut_hocasi=hoca)
    ortak = ktt_sinif_paylasim_q(user)
    if ortak:
        q |= ortak
    if not q:
        return KttSinav.objects.none()
    return qs.filter(q).distinct()


def ktt_olusturabilir(user: User) -> bool:
    return can(user, "ktt", "create")


def ktt_duzenleyebilir(user: User, ktt: KttSinav) -> bool:
    if not can(user, "ktt", "edit"):
        return False

    if ktt_tam_yetki(user):
        return True

    hoca = _etut_hocasi(user)
    return hoca is not None and ktt.etut_hocasi_id == hoca.id


def ktt_sonuc_girebilir(user: User, ktt: KttSinav) -> bool:
    if not can(user, "ktt", "edit"):
        return False
    if ktt_duzenleyebilir(user, ktt):
        return True
    return yetkili_ktt_sinavlari(user).filter(pk=ktt.pk).exists()


def ktt_silebilir(user: User, ktt: KttSinav) -> bool:
    if not can(user, "ktt", "view"):
        return False
    if ktt_tam_yetki(user) or can(user, "ktt", "delete"):
        return True
    if not (can(user, "ktt", "create") or can(user, "ktt", "edit")):
        return False
    if ktt.olusturan_id == user.id:
        return True
    hoca = _etut_hocasi(user)
    return hoca is not None and ktt.etut_hocasi_id == hoca.id


def _nehari_siniflari(user: User) -> list[SinifSube] | None:
    from takip.permissions.scope import yetkili_talebeler
    from takip.permissions.service import kullanici_rol_slugleri

    if "nehari_mesul" not in kullanici_rol_slugleri(user):
        return None
    sinif_ids = (
        yetkili_talebeler(user)
        .exclude(sinif_sube_id__isnull=True)
        .values_list("sinif_sube_id", flat=True)
        .distinct()
    )
    return list(SinifSube.objects.filter(pk__in=sinif_ids, aktif=True).order_by("sinif", "sube"))


def ktt_sinif_secenekleri(user: User) -> list[SinifSube]:
    from takip.permissions.scope import tum_talebe_kapsami_var

    nehari_siniflar = _nehari_siniflari(user)
    if nehari_siniflar is not None:
        return nehari_siniflar

    if user.is_superuser or tum_talebe_kapsami_var(user) or ktt_tam_yetki(user):
        return list(SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"))

    hoca = _etut_hocasi(user)
    if hoca:
        secilen = list(
            hoca.sorumlu_sinif_subeler.filter(aktif=True).order_by("sinif", "sube")
        )
        if secilen:
            return secilen

        siniflar = (
            Talebe.objects.filter(etut_hocasi=hoca, aktif=True)
            .exclude(sinif="")
            .values_list("sinif", "sube")
            .distinct()
        )
        seen: set[str] = set()
        fallback: list[SinifSube] = []
        for sinif, sube in siniflar:
            etiket = f"{sinif}-{sube}"
            if etiket in seen:
                continue
            seen.add(etiket)
            obj, _ = SinifSube.objects.get_or_create(
                sinif=sinif, sube=sube, defaults={"aktif": True}
            )
            fallback.append(obj)
        if fallback:
            return sorted(fallback, key=lambda s: (s.sinif, s.sube))

    return []


def ktt_sinif_etiketleri(user: User) -> set[str]:
    return {f"{ss.sinif}-{ss.sube}" for ss in ktt_sinif_secenekleri(user)}


def ktt_hoca_sinif_etiketleri(user: User) -> set[str]:
    """Paylaşım için yalnızca hocanın zimmetindeki sınıflar (idare kapsamı hariç)."""
    nehari_siniflar = _nehari_siniflari(user)
    if nehari_siniflar is not None:
        return {f"{ss.sinif}-{ss.sube}" for ss in nehari_siniflar}

    hoca = _etut_hocasi(user)
    if not hoca:
        return set()
    secilen = list(hoca.sorumlu_sinif_subeler.filter(aktif=True))
    if secilen:
        return {f"{ss.sinif}-{ss.sube}" for ss in secilen}

    siniflar = (
        Talebe.objects.filter(etut_hocasi=hoca, aktif=True)
        .exclude(sinif="")
        .values_list("sinif", "sube")
        .distinct()
    )
    return {f"{sinif}-{sube}" for sinif, sube in siniflar if sinif}


def ktt_sinif_paylasim_q(user: User) -> Q | None:
    """Aynı sınıf seviyesine / hedef şubeye bakan hocaların sınavlarını paylaş."""
    etiketler = ktt_hoca_sinif_etiketleri(user)
    if not etiketler:
        return None
    q = Q()
    seviyeler = {
        etiket.split("-", 1)[0].strip()
        for etiket in etiketler
        if etiket.split("-", 1)[0].strip()
    }
    if seviyeler:
        q |= Q(sinif_seviyesi__in=seviyeler)
    for etiket in etiketler:
        q |= Q(hedef_siniflar__regex=rf"(^|,\s*){re.escape(etiket)}(,|$)")
    return q


def ktt_hedef_sinif_listesi(hedef_siniflar: str) -> list[str]:
    return [s.strip() for s in (hedef_siniflar or "").split(",") if s.strip()]


def hedef_sinifa_gore_talebeler(
    talebeler: QuerySet[Talebe],
    *,
    hedef_siniflar: str,
    sinif_seviyesi: str,
) -> QuerySet[Talebe]:
    etiketler = ktt_hedef_sinif_listesi(hedef_siniflar)
    if etiketler:
        q = Q()
        for etiket in etiketler:
            parca = etiket.split("-", 1)
            if len(parca) == 2:
                sinif, sube = parca[0].strip(), parca[1].strip()
                q |= Q(sinif=sinif, sube=sube) | Q(
                    sinif_sube__sinif=sinif, sinif_sube__sube=sube
                )
            else:
                q |= Q(sinif=etiket) | Q(sinif_sube__sinif=etiket)
        return talebeler.filter(q)
    seviye = (sinif_seviyesi or "").strip()
    if seviye:
        return talebeler.filter(Q(sinif=seviye) | Q(sinif_sube__sinif=seviye))
    return talebeler


def ktt_sinif_secimlerini_dogrula(user: User, secilen: list[str]) -> tuple[list[str], str | None]:
    izinli = ktt_sinif_etiketleri(user)
    temiz = [s.strip() for s in secilen if s and s.strip()]
    if not temiz:
        return [], "En az bir sınıf seçin."
    if not izinli:
        return [], "Size tanımlı sınıf bulunamadı. Kurum idaresine başvurun."
    gecersiz = [s for s in temiz if s not in izinli]
    if gecersiz:
        return [], "Seçilen sınıflardan bazıları için yetkiniz yok."
    return temiz, None


def hedef_siniflar_kaydet(ktt: KttSinav, secilen: list[str]) -> None:
    temiz = [s.strip() for s in secilen if s and s.strip()]
    ktt.hedef_siniflar = ", ".join(temiz)
    if temiz:
        ktt.sinif_seviyesi = temiz[0].split("-", 1)[0].strip()
    elif not ktt.sinif_seviyesi:
        ktt.sinif_seviyesi = "7"


def seed_ktt_demo() -> None:
    """Örnek KTT sınavları ve sonuçları."""
    hoca = EtutHocasi.objects.filter(ad_soyad__icontains="Yahya").first()
    if not hoca or not hoca.user_id:
        return

    sinif_7a, _ = SinifSube.objects.get_or_create(
        sinif="7", sube="A", defaults={"aktif": True}
    )
    sinif_7b, _ = SinifSube.objects.get_or_create(
        sinif="7", sube="B", defaults={"aktif": True}
    )
    hoca.sorumlu_sinif_subeler.add(sinif_7a, sinif_7b)

    ders_map = {
        ad: Ders.objects.filter(ad=ad, aktif=True).first()
        for ad in (
            "Türkçe",
            "Matematik",
            "Fen Bilimleri",
            "Sosyal Bilgiler",
            "Din Kültürü",
        )
    }

    bugun = localdate()
    ornekler = [
        ("Paragrafın Yapısı", "Türkçe", 20, 0),
        ("Tam Sayı Problemleri", "Matematik", 14, 1),
        ("Rasyonel Sayılar", "Matematik", 17, 2),
        ("Güneş Sistemi", "Fen Bilimleri", 12, 3),
        ("Osmanlı Devlet Teşkilatı", "Sosyal Bilgiler", 16, 4),
        ("Namaz Vakitleri", "Din Kültürü", 15, 5),
        ("Edebî Sanatlar", "Türkçe", 20, 6),
        ("Paragraf", "Türkçe", 52, 7),
    ]

    hedef = "7-A, 7-B"
    talebeler = list(
        Talebe.objects.filter(etut_hocasi=hoca, aktif=True).order_by("ad_soyad")
    )

    for ad, ders_ad, soru, gun_farki in ornekler:
        ders = ders_map.get(ders_ad)
        if not ders:
            continue

        ktt, _ = KttSinav.objects.update_or_create(
            ad=ad,
            etut_hocasi=hoca,
            defaults={
                "ders": ders,
                "sinif_seviyesi": "7",
                "hedef_siniflar": hedef,
                "sinav_tarihi": bugun - timedelta(days=gun_farki),
                "soru_sayisi": soru,
                "veliye_goster": True,
                "aktif": True,
                "olusturan": hoca.user,
            },
        )

        for i, talebe in enumerate(talebeler):
            dogru = max(0, soru - i * 2 - (gun_farki % 3))
            yanlis = min(3, soru - dogru)
            bos = soru - dogru - yanlis
            KttSonucu.objects.update_or_create(
                ktt=ktt,
                talebe=talebe,
                defaults={
                    "dogru": dogru,
                    "yanlis": yanlis,
                    "bos": bos,
                    "kaydeden": hoca.user,
                },
            )


def ktt_gercek_katilim(sonuc: KttSonucu | None, soru_sayisi: int) -> bool:
    if not sonuc:
        return False
    return not (
        int(sonuc.dogru or 0) == 0
        and int(sonuc.yanlis or 0) == 0
        and int(sonuc.bos or 0) == int(soru_sayisi or 0)
    )


def ktt_hedef_talebeleri(user: User, ktt: KttSinav) -> QuerySet[Talebe]:
    from takip.permissions.scope import yetkili_talebeler

    talebeler = yetkili_talebeler(user, aktif_only=True)
    return hedef_sinifa_gore_talebeler(
        talebeler,
        hedef_siniflar=ktt.hedef_siniflar,
        sinif_seviyesi=ktt.sinif_seviyesi,
    ).order_by("ad_soyad")


def ktt_sonuc_talebeleri(user: User, ktt: KttSinav) -> QuerySet[Talebe]:
    return ktt_hedef_talebeleri(user, ktt).exclude(
        id__in=ktt.haric_talebeler.values_list("pk", flat=True)
    )


def ktt_katilmayan_talebeler(user: User, ktt: KttSinav) -> QuerySet[Talebe]:
    talebeler = list(ktt_sonuc_talebeleri(user, ktt))
    if not talebeler:
        return Talebe.objects.none()

    mevcut = {
        s.talebe_id: s
        for s in KttSonucu.objects.filter(ktt=ktt, talebe__in=talebeler)
    }
    soru_sayisi = int(ktt.soru_sayisi or 0)
    katilmayan_ids = [
        talebe.id
        for talebe in talebeler
        if not ktt_gercek_katilim(mevcut.get(talebe.id), soru_sayisi)
    ]
    if not katilmayan_ids:
        return Talebe.objects.none()
    return Talebe.objects.filter(id__in=katilmayan_ids).order_by("ad_soyad")


def ktt_katilmayanlari_haric_yap(ktt: KttSinav, talebeler) -> int:
    talebe_list = list(talebeler)
    if not talebe_list:
        return 0

    ktt.haric_talebeler.add(*talebe_list)
    KttSonucu.objects.filter(
        ktt=ktt,
        talebe__in=talebe_list,
        dogru=0,
        yanlis=0,
        bos=ktt.soru_sayisi,
    ).delete()
    return len(talebe_list)


def yetkili_ktt_sonuclari(user: User) -> QuerySet[KttSonucu]:
    if not can(user, "ktt", "view"):
        return KttSonucu.objects.none()

    qs = KttSonucu.objects.filter(ktt__aktif=True).select_related(
        "ktt",
        "ktt__ders",
        "ktt__etut_hocasi",
        "talebe",
        "talebe__sinif_sube",
        "talebe__etut_hocasi",
    )

    if user.is_superuser:
        return qs

    from takip.permissions.scope import tum_talebe_kapsami_var

    if tum_talebe_kapsami_var(user):
        return qs

    hoca = _etut_hocasi(user)
    if not hoca:
        return KttSonucu.objects.none()

    return qs.filter(ktt_id__in=yetkili_ktt_sinavlari(user).values("pk"))


def ktt_rapor_filtre_secenekleri(user: User) -> dict:
    sinavlar = yetkili_ktt_sinavlari(user)
    from takip.permissions.scope import yetkili_talebeler

    talebeler = yetkili_talebeler(user, aktif_only=True).order_by("ad_soyad")
    ders_ids = sinavlar.values_list("ders_id", flat=True).distinct()
    dersler = Ders.objects.filter(id__in=ders_ids, aktif=True).order_by("sira", "ad")

    return {
        "sinif_subeler": ktt_sinif_secenekleri(user),
        "dersler": list(dersler),
        "ktt_sinavlari": list(sinavlar.order_by("-sinav_tarihi", "-id")[:100]),
        "talebeler": list(talebeler),
    }


def ktt_rapor_filtrele(
    qs: QuerySet[KttSonucu],
    *,
    sinif_sube_id: str | None = None,
    sinif_sube_ids: list[int] | None = None,
    ders_id: str | None = None,
    ders_ids: list[int] | None = None,
    ktt_id: str | None = None,
    ktt_ids: list[int] | None = None,
    talebe_id: str | None = None,
    talebe_ids: list[int] | None = None,
    baslangic: str | None = None,
    bitis: str | None = None,
) -> QuerySet[KttSonucu]:
    qs = qs_filtre_id(qs, "talebe__sinif_sube_id", sinif_sube_id, sinif_sube_ids)
    qs = qs_filtre_id(qs, "ktt__ders_id", ders_id, ders_ids)
    qs = qs_filtre_id(qs, "ktt_id", ktt_id, ktt_ids)
    qs = qs_filtre_id(qs, "talebe_id", talebe_id, talebe_ids)
    if baslangic:
        qs = qs.filter(ktt__sinav_tarihi__gte=baslangic)
    if bitis:
        qs = qs.filter(ktt__sinav_tarihi__lte=bitis)
    return qs


def ktt_test_soru_toplami(qs: QuerySet[KttSonucu]) -> int:
    """Filtredeki her testin soru sayısı bir kez sayılır."""
    toplam = KttSinav.objects.filter(pk__in=qs.values("ktt_id")).aggregate(
        toplam=Sum("soru_sayisi")
    )
    return int(toplam["toplam"] or 0)


def _tr_sayi(deger, ondalik: int = 2, kirp: bool = True) -> str:
    if isinstance(deger, Decimal):
        sayi = deger
    else:
        sayi = Decimal(str(deger or 0))
    sayi = sayi.quantize(Decimal(10) ** -ondalik)
    metin = f"{sayi:.{ondalik}f}".replace(".", ",")
    if ondalik and kirp:
        metin = metin.rstrip("0").rstrip(",")
    return metin or "0"


def _ktt_rapor_sayilari(
    *,
    test: int,
    dogru: int,
    yanlis: int,
    bos: int,
    net,
    ort_puan,
    ort_net,
    max_puan,
) -> dict:
    soru = int(dogru or 0) + int(yanlis or 0) + int(bos or 0)
    if soru:
        basari = Decimal(int(dogru or 0)) * Decimal(100) / Decimal(soru)
    else:
        basari = Decimal(0)
    return {
        "toplam_sonuc": int(test or 0),
        "toplam_soru": soru,
        "toplam_dogru": int(dogru or 0),
        "toplam_yanlis": int(yanlis or 0),
        "toplam_bos": int(bos or 0),
        "toplam_net": _tr_sayi(net, 2),
        "basari": _tr_sayi(basari, 1),
        "ortalama_puan": round(float(ort_puan or 0), 1),
        "ortalama_net": round(float(ort_net or 0), 1),
        "en_yuksek_puan": round(float(max_puan or 0), 1),
    }


def ktt_rapor_ozet_metni(test: int, soru: int, dogru: int, yanlis: int, bos: int) -> str:
    return (
        f"{int(test)} test · {int(soru)} soru · {int(dogru)} doğru · "
        f"{int(yanlis)} yanlış · {int(bos)} boş"
    )


def ktt_rapor_istatistik(kaynak) -> dict:
    """Çözülen soru, kağıtlardaki doğru+yanlış+boş toplamıdır."""
    if isinstance(kaynak, QuerySet):
        agg = kaynak.aggregate(
            toplam=Count("id"),
            ort_puan=Avg("puan"),
            ort_net=Avg("net"),
            max_puan=Max("puan"),
            dogru=Sum("dogru"),
            yanlis=Sum("yanlis"),
            bos=Sum("bos"),
            net=Sum("net"),
        )
        return _ktt_rapor_sayilari(
            test=agg["toplam"] or 0,
            dogru=agg["dogru"] or 0,
            yanlis=agg["yanlis"] or 0,
            bos=agg["bos"] or 0,
            net=agg["net"] or 0,
            ort_puan=agg["ort_puan"],
            ort_net=agg["ort_net"],
            max_puan=agg["max_puan"],
        )

    satirlar = list(kaynak)
    test = len(satirlar)
    dogru = yanlis = bos = 0
    net = Decimal(0)
    puanlar: list[Decimal] = []
    for sonuc in satirlar:
        dogru += int(sonuc.dogru or 0)
        yanlis += int(sonuc.yanlis or 0)
        bos += int(sonuc.bos or 0)
        net += Decimal(sonuc.net or 0)
        puanlar.append(Decimal(sonuc.puan or 0))
    ort_puan = (sum(puanlar, Decimal(0)) / test) if test else Decimal(0)
    ort_net = (net / test) if test else Decimal(0)
    max_puan = max(puanlar) if puanlar else Decimal(0)
    return _ktt_rapor_sayilari(
        test=test,
        dogru=dogru,
        yanlis=yanlis,
        bos=bos,
        net=net,
        ort_puan=ort_puan,
        ort_net=ort_net,
        max_puan=max_puan,
    )


def ktt_rapor_talebe_satirlari(sonuclar) -> list[dict]:
    """Seçilen aralıktaki kağıtları talebeye göre, ada göre sıralı toplar."""
    kovalar: dict[int, dict] = {}
    for sonuc in sonuclar:
        talebe = sonuc.talebe
        satir = kovalar.get(talebe.pk)
        if satir is None:
            satir = {
                "talebe": talebe,
                "testler": [],
                "dersler": {},
                "test": 0,
                "soru": 0,
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
                "net": Decimal(0),
            }
            kovalar[talebe.pk] = satir
        dogru = int(sonuc.dogru or 0)
        yanlis = int(sonuc.yanlis or 0)
        bos = int(sonuc.bos or 0)
        soru = dogru + yanlis + bos
        satir["testler"].append(
            {
                "ad": sonuc.ktt.ad,
                "tarih": sonuc.ktt.sinav_tarihi,
                "ders": sonuc.ktt.ders.ad if sonuc.ktt.ders_id else "",
                "soru": soru,
                "dogru": dogru,
                "yanlis": yanlis,
                "bos": bos,
                "net": _tr_sayi(sonuc.net, 2),
                "ktt_id": sonuc.ktt_id,
            }
        )
        ders = sonuc.ktt.ders if sonuc.ktt.ders_id else None
        ders_anahtar = ders.pk if ders else 0
        kova = satir["dersler"].get(ders_anahtar)
        if kova is None:
            kova = {
                "ad": ders.ad if ders else "Ders yok",
                "sira": ders.sira if ders else 10_000,
                "soru": 0,
                "dogru": 0,
                "yanlis": 0,
                "bos": 0,
                "net": Decimal(0),
            }
            satir["dersler"][ders_anahtar] = kova
        kova["soru"] += soru
        kova["dogru"] += dogru
        kova["yanlis"] += yanlis
        kova["bos"] += bos
        kova["net"] += Decimal(sonuc.net or 0)
        satir["test"] += 1
        satir["soru"] += soru
        satir["dogru"] += dogru
        satir["yanlis"] += yanlis
        satir["bos"] += bos
        satir["net"] += Decimal(sonuc.net or 0)

    sirali = sorted(
        kovalar.values(),
        key=lambda satir: (satir["talebe"].ad_soyad or "").casefold(),
    )
    for satir in sirali:
        if satir["soru"]:
            basari = Decimal(satir["dogru"]) * Decimal(100) / Decimal(satir["soru"])
        else:
            basari = Decimal(0)
        satir["basari"] = _tr_sayi(basari, 1)
        yuzde = basari.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if yuzde > 100:
            yuzde = Decimal("100.0")
        if yuzde < 0:
            yuzde = Decimal("0.0")
        satir["basari_tam"] = int(yuzde.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        satir["basari_cember"] = f"{yuzde:.1f}"
        satir["basari_bosluk"] = f"{(Decimal('100.0') - yuzde):.1f}"
        satir["net_tam"] = _tr_sayi(satir["net"], 2, kirp=False)
        satir["net"] = _tr_sayi(satir["net"], 2)
        dersler = sorted(
            satir["dersler"].values(),
            key=lambda ders: (ders["sira"], (ders["ad"] or "").casefold()),
        )
        kalan_pay = Decimal("100")
        for sira_no, ders in enumerate(dersler):
            ham_net = ders["net"]
            ders["net_tam"] = _tr_sayi(ham_net, 2, kirp=False)
            ders["net"] = _tr_sayi(ham_net, 2)
            if ders["soru"]:
                ders_yuzde = (
                    Decimal(ders["dogru"]) * Decimal(100) / Decimal(ders["soru"])
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            else:
                ders_yuzde = Decimal(0)
            ders["basari"] = int(ders_yuzde)
            ders["renk"] = _ktt_ders_rengi(ders["ad"])
            if not satir["soru"]:
                pay = Decimal(0)
            elif sira_no == len(dersler) - 1:
                pay = kalan_pay
            else:
                pay = (
                    Decimal(ders["soru"]) * Decimal(100) / Decimal(satir["soru"])
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                kalan_pay -= pay
            if pay < 0:
                pay = Decimal(0)
            ders["pay"] = f"{pay:.2f}"
        satir["dersler"] = dersler
        satir["ozet"] = ktt_rapor_ozet_metni(
            satir["test"],
            satir["soru"],
            satir["dogru"],
            satir["yanlis"],
            satir["bos"],
        )
    return sirali


def ktt_rapor_pdf_adi(ad_soyad: str, baslangic: str = "", bitis: str = "") -> str:
    ad = re.sub(r'[\\/:*?"<>|\r\n]+', " ", (ad_soyad or "").strip())
    ad = re.sub(r"\s+", " ", ad).strip() or "Talebe"
    bas = (baslangic or "").strip()
    bit = (bitis or "").strip()
    if bas or bit:
        aralik = f"{bas or 'baslangic'}_{bit or 'bitis'}"
    else:
        aralik = "tum-aralik"
    return f"{ad}_{aralik}.pdf"


def ktt_rapor_zip_adi(baslangic: str = "", bitis: str = "") -> str:
    bas = (baslangic or "").strip()
    bit = (bitis or "").strip()
    if bas or bit:
        aralik = f"{bas or 'baslangic'}_{bit or 'bitis'}"
    else:
        aralik = "tum-aralik"
    return f"ktt-talebe-raporlari_{aralik}.zip"


def ktt_hafta_cozulen_soru(user: User, gun=None) -> int:
    """Bu hafta (pazartesi–pazar) sonucu girilmiş testlerin soru toplamı."""
    gun = gun or localdate()
    baslangic = gun - timedelta(days=gun.weekday())
    bitis = baslangic + timedelta(days=6)
    qs = yetkili_ktt_sonuclari(user).filter(
        ktt__sinav_tarihi__gte=baslangic,
        ktt__sinav_tarihi__lte=bitis,
    )
    return ktt_test_soru_toplami(qs)


_KTT_HAFTA_DERSLERI: tuple[str, ...] = (
    "Türkçe",
    "Paragraf",
    "Matematik",
    "Fen",
    "Sosyal",
    "Din",
    "İngilizce",
)


def _ktt_ders_kovasi(ad: str) -> str:
    """KTT ders adını haftalık şeridin kovasına bağlar."""
    ham = (ad or "").casefold()
    for eski, yeni in (
        ("ı", "i"),
        ("i̇", "i"),
        ("ş", "s"),
        ("ğ", "g"),
        ("ü", "u"),
        ("ö", "o"),
        ("ç", "c"),
    ):
        ham = ham.replace(eski, yeni)
    if "paragraf" in ham:
        return "Paragraf"
    if "ingiliz" in ham:
        return "İngilizce"
    if "turkce" in ham:
        return "Türkçe"
    if "matematik" in ham:
        return "Matematik"
    if "fen" in ham:
        return "Fen"
    if "sosyal" in ham:
        return "Sosyal"
    if ham.startswith("din"):
        return "Din"
    return ""


_KTT_DERS_RENK = {
    "Türkçe": "#2f6fd6",
    "Matematik": "#0a2350",
    "Paragraf": "#5aa9e6",
    "Fen": "#1e9e8a",
    "İngilizce": "#c9a84c",
    "Sosyal": "#3e6b8a",
    "Din": "#8a7560",
}
_KTT_RENK_YEDEK = ("#2f6fd6", "#0a2350", "#5aa9e6", "#1e9e8a", "#c9a84c")


def _ktt_ders_rengi(ad: str) -> str:
    kova = _ktt_ders_kovasi(ad)
    if kova in _KTT_DERS_RENK:
        return _KTT_DERS_RENK[kova]
    anahtar = (ad or "").casefold()
    return _KTT_RENK_YEDEK[sum(ord(harf) for harf in anahtar) % len(_KTT_RENK_YEDEK)]


def ktt_hafta_ders_sorulari(user: User, gun=None) -> list[dict]:
    """Bu hafta çözülen soru, ders ders. Toplam, başlıktaki hafta sayısıyla aynıdır."""
    gun = gun or localdate()
    baslangic = gun - timedelta(days=gun.weekday())
    bitis = baslangic + timedelta(days=6)
    qs = yetkili_ktt_sonuclari(user).filter(
        ktt__sinav_tarihi__gte=baslangic,
        ktt__sinav_tarihi__lte=bitis,
    )
    kovalar = {etiket: 0 for etiket in _KTT_HAFTA_DERSLERI}
    diger: dict[str, int] = {}
    sinavlar = KttSinav.objects.filter(pk__in=qs.values("ktt_id")).select_related("ders")
    for sinav in sinavlar:
        ad = sinav.ders.ad if sinav.ders_id else ""
        kova = _ktt_ders_kovasi(ad)
        soru = int(sinav.soru_sayisi or 0)
        if kova:
            kovalar[kova] += soru
        else:
            diger[ad or "Diğer"] = diger.get(ad or "Diğer", 0) + soru
    satirlar = [{"etiket": etiket, "soru": kovalar[etiket]} for etiket in _KTT_HAFTA_DERSLERI]
    for etiket, soru in diger.items():
        satirlar.append({"etiket": etiket, "soru": soru})
    return satirlar


def _hafta_ders_satirlari(kovalar: dict[str, int]) -> list[dict]:
    satirlar = [
        {"etiket": etiket, "soru": int(kovalar.get(etiket, 0))}
        for etiket in _KTT_HAFTA_DERSLERI
    ]
    for etiket, soru in kovalar.items():
        if etiket not in _KTT_HAFTA_DERSLERI:
            satirlar.append({"etiket": etiket, "soru": int(soru)})
    return satirlar


def _sinif_basligi(seviye: str) -> str:
    if not seviye:
        return "Sınıf belirtilmemiş"
    if seviye.isdigit():
        return f"{seviye}. sınıflar"
    return seviye


def _seviye_sirasi(seviye: str) -> tuple:
    if seviye.isdigit():
        return (0, int(seviye), seviye)
    if not seviye:
        return (2, 0, "")
    return (1, 0, seviye)


def _ktt_hafta_cumle(baslik: str, dersler: list[dict]) -> str:
    """Sınıf adı başlıkta durur; cümle yalnız ders ve adet söyler."""
    del baslik
    dolu = [ders for ders in dersler if ders["soru"]]
    if not dolu:
        return "Bu hafta soru çözülmedi."
    parcalar = [f"{ders['etiket']} {ders['soru']}" for ders in dolu]
    if len(parcalar) == 1:
        liste = parcalar[0]
    else:
        liste = ", ".join(parcalar[:-1]) + " ve " + parcalar[-1]
    return f"{liste} çözüldü."


def ktt_hafta_sinif_ozeti(user: User, gun=None) -> dict:
    """Bu haftanın soru toplamı, sınıf seviyesine göre. Her test bir kez sayılır."""
    gun = gun or localdate()
    baslangic = gun - timedelta(days=gun.weekday())
    bitis = baslangic + timedelta(days=6)
    qs = yetkili_ktt_sonuclari(user).filter(
        ktt__sinav_tarihi__gte=baslangic,
        ktt__sinav_tarihi__lte=bitis,
    )
    gruplar: dict[str, dict[str, int]] = {}
    sinavlar = KttSinav.objects.filter(pk__in=qs.values("ktt_id")).select_related("ders")
    for sinav in sinavlar:
        seviye = (sinav.sinif_seviyesi or "").strip()
        kovalar = gruplar.setdefault(seviye, {})
        ad = sinav.ders.ad if sinav.ders_id else ""
        kova = _ktt_ders_kovasi(ad) or (ad or "Diğer")
        kovalar[kova] = kovalar.get(kova, 0) + int(sinav.soru_sayisi or 0)

    siniflar = []
    for seviye in sorted(gruplar, key=_seviye_sirasi):
        dersler = _hafta_ders_satirlari(gruplar[seviye])
        baslik = _sinif_basligi(seviye)
        siniflar.append(
            {
                "seviye": seviye,
                "baslik": baslik,
                "toplam": sum(ders["soru"] for ders in dersler),
                "dersler": dersler,
                "cumle": _ktt_hafta_cumle(baslik, dersler),
            }
        )
    return {
        "baslangic": baslangic,
        "bitis": bitis,
        "toplam": sum(sinif["toplam"] for sinif in siniflar),
        "siniflar": siniflar,
    }


def ktt_rapor_grupla(sonuclar) -> list[dict]:
    """Sonuç satırlarını teste göre toplar. Sıra, gelen listenin tarih sırasını korur."""
    gruplar: list[dict] = []
    index: dict[int, dict] = {}
    for sonuc in sonuclar:
        ktt = sonuc.ktt
        grup = index.get(ktt.pk)
        if grup is None:
            grup = {"ktt": ktt, "sonuclar": []}
            index[ktt.pk] = grup
            gruplar.append(grup)
        grup["sonuclar"].append(sonuc)
    return gruplar


def ktt_rapor_filtre_dict(request) -> dict:
    return {
        "sinif_sube": get_int_list(request.GET, "sinif_sube"),
        "ders": get_int_list(request.GET, "ders"),
        "ktt": get_int_list(request.GET, "ktt"),
        "talebe": get_int_list(request.GET, "talebe"),
        "baslangic": request.GET.get("baslangic", ""),
        "bitis": request.GET.get("bitis", ""),
    }


def ktt_rapor_filtre_etiketleri(filtre: dict, secenekler: dict) -> dict:
    def _etiketler(items, secilen, goster):
        idler = secilen if isinstance(secilen, list) else ([secilen] if secilen else [])
        if not idler:
            return "Tümü"
        adlar = []
        for item in items:
            if item.id in idler or str(item.id) in {str(x) for x in idler}:
                adlar.append(goster(item))
        return ", ".join(adlar) if adlar else "Tümü"

    return {
        "sinif": _etiketler(
            secenekler.get("sinif_subeler", []),
            filtre.get("sinif_sube"),
            str,
        ),
        "ders": _etiketler(
            secenekler.get("dersler", []),
            filtre.get("ders"),
            lambda item: item.ad,
        ),
        "ktt": _etiketler(
            secenekler.get("ktt_sinavlari", []),
            filtre.get("ktt"),
            lambda item: item.ad,
        ),
        "talebe": _etiketler(
            secenekler.get("talebeler", []),
            filtre.get("talebe"),
            lambda item: item.ad_soyad,
        ),
        "baslangic": filtre.get("baslangic") or "Tüm tarihler",
        "bitis": filtre.get("bitis") or "Bugün",
        "baslangic_yazi": _ktt_tarih_yaz(filtre.get("baslangic") or "", "Tüm tarihler"),
        "bitis_yazi": _ktt_tarih_yaz(filtre.get("bitis") or "", "Bugün"),
    }


def _ktt_tarih_yaz(metin: str, bos: str = "") -> str:
    ham = (metin or "").strip()
    if not ham:
        return bos
    try:
        return datetime.strptime(ham, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return ham
