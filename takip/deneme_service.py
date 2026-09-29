"""Deneme sorguları ve yardımcılar."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.db.models import Count, Q, QuerySet

from takip.models import DenemeSinavi, DenemeSonucu, Talebe
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can

BRANS_ETIKETLERI = {
    "turkce": "Türkçe",
    "matematik": "Matematik",
    "fen": "Fen Bilimleri",
    "sosyal": "Sosyal Bilgiler",
    "din": "Din Kültürü",
    "ingilizce": "İngilizce",
}

# Deneme detay tablosu — LGS 6 ders (Din dahil)
DENEME_DETAY_BRANSLAR: tuple[str, ...] = (
    "turkce",
    "matematik",
    "fen",
    "sosyal",
    "din",
    "ingilizce",
)

# Günlük soru takip eşlemesi — deneme branşları soru takipteki derslerle eşlenir
DENEME_BRANS_DERS_MAP: dict[str, str] = {
    kod: BRANS_ETIKETLERI[kod] for kod in DENEME_DETAY_BRANSLAR
}

LGS_KATSAYI: dict[str, Decimal] = {
    "turkce": Decimal("4"),
    "matematik": Decimal("4"),
    "fen": Decimal("4"),
    "sosyal": Decimal("1"),
    "din": Decimal("1"),
    "ingilizce": Decimal("1"),
}


def deneme_puan_branslardan(branslar: dict, sinif_seviyesi: str = "8") -> Decimal:
    """Excel puanı yoksa LGS katsayılarıyla 100–500 (8. sınıf) / 0–500 puan."""
    agirlikli = Decimal("0")
    max_w = Decimal("0")
    for kod, veri in (branslar or {}).items():
        katsayi = LGS_KATSAYI.get(kod, Decimal("1"))
        try:
            net = Decimal(str(veri.get("net") or 0))
        except Exception:
            net = Decimal("0")
        soru = int(veri.get("dogru") or 0) + int(veri.get("yanlis") or 0) + int(
            veri.get("bos") or 0
        )
        if soru <= 0 and net <= 0:
            continue
        if soru <= 0:
            continue
        agirlikli += net * katsayi
        max_w += Decimal(soru) * katsayi
    if max_w <= 0:
        return Decimal("0.00")
    if str(sinif_seviyesi or "").strip() == "8":
        taban, aralik = Decimal("100"), Decimal("400")
    else:
        taban, aralik = Decimal("0"), Decimal("500")
    return (taban + agirlikli / max_w * aralik).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def deneme_puan_sonuctan(sonuc: DenemeSonucu) -> Decimal:
    branslar = {
        b.brans: {
            "dogru": b.dogru,
            "yanlis": b.yanlis,
            "bos": b.bos,
            "net": b.net,
        }
        for b in sonuc.brans_satirlari.all()
    }
    seviye = ""
    deneme = getattr(sonuc, "deneme", None)
    if deneme is not None:
        seviye = deneme.sinif_seviyesi
    return deneme_puan_branslardan(branslar, seviye)


def eksik_deneme_puanlarini_doldur(sonuclar) -> list:
    """Aktarımda puan kolonu kaçtıysa netlerden doldur ve kaydet."""
    kayitlar = list(sonuclar)
    guncelle = []
    for s in kayitlar:
        if s.puan and s.puan != Decimal("0.00"):
            continue
        puan = deneme_puan_sonuctan(s)
        if puan > 0:
            s.puan = puan
            guncelle.append(s)
    if guncelle:
        DenemeSonucu.objects.bulk_update(guncelle, ["puan"])
    return kayitlar


def puan_sirasi_key(sonuc: DenemeSonucu) -> tuple:
    """Merkezi puan sıralaması tie-break: puan → net → ad soyad.

    Puan eşitliğinde net yüksek olan öne geçer; o da eşitse ad soyad
    alfabetik sıralanır (deterministik, tekrar üretilebilir sıralama).
    """
    return (
        -float(sonuc.puan or 0),
        -float(sonuc.toplam_net or 0),
        (sonuc.talebe.ad_soyad or "").upper(),
    )


def siralama_hesapla_ve_kaydet(deneme: DenemeSinavi) -> None:
    """Bir grup denemesinin sınıf/seviye/kurum sırasını hesaplayıp kaydeder.

    Bireysel denemeler sıralamaya girmez (fonksiyon sessizce çıkar).
    Sınıf seviyesi/kurum sırası, bu tek DenemeSinavi kaydının kapsadığı
    tüm sonuçlar üzerinden hesaplanır (bir DenemeSinavi tek bir sınıf
    seviyesine ait olduğundan bu ikisi aynı popülasyonu ifade eder;
    farklı seviyelerin aynı deneme serisinde kurum çapında birleştirilmesi
    bu sürümde desteklenmiyor).
    """
    if deneme.tur != DenemeSinavi.Tur.GRUP:
        return

    sonuclar = list(
        DenemeSonucu.objects.filter(deneme=deneme).select_related(
            "talebe", "talebe__sinif_sube"
        )
    )
    if not sonuclar:
        return

    sonuclar.sort(key=puan_sirasi_key)
    kurum_toplam = len(sonuclar)

    sinif_gruplari: dict[int | None, list[DenemeSonucu]] = {}
    for sonuc in sonuclar:
        sinif_gruplari.setdefault(sonuc.talebe.sinif_sube_id, []).append(sonuc)

    for genel_sira, sonuc in enumerate(sonuclar, start=1):
        sonuc.kurum_sirasi = genel_sira
        sonuc.kurum_toplam = kurum_toplam
        sonuc.seviye_sirasi = genel_sira
        sonuc.seviye_toplam = kurum_toplam

    for grup in sinif_gruplari.values():
        grup.sort(key=puan_sirasi_key)
        sinif_toplam = len(grup)
        for sira, sonuc in enumerate(grup, start=1):
            sonuc.sinif_sirasi = sira
            sonuc.sinif_toplam = sinif_toplam

    DenemeSonucu.objects.bulk_update(
        sonuclar,
        [
            "sinif_sirasi",
            "sinif_toplam",
            "seviye_sirasi",
            "seviye_toplam",
            "kurum_sirasi",
            "kurum_toplam",
        ],
    )


def sira_no_ata(
    egitim_yili,
    sinif_seviyesi: str,
    tercih: int | None = None,
    *,
    haric_deneme_id: int | None = None,
) -> int:
    """Eğitim yılı + sınıf seviyesi kapsamında bir sonraki sıra numarasını
    döner; ``tercih`` verilirse o numaranın boş olduğunu doğrular.

    Bu kontrol, DB kısıtındaki (UniqueConstraint) eğitim_yili NULL olduğunda
    SQL'in "NULL ≠ NULL" kuralı yüzünden oluşan boşluğu da kapatır — burada
    sıradan bir ``filter(egitim_yili=...)`` kullanıldığından NULL değerler
    de doğru şekilde eşleşir.
    """
    qs = DenemeSinavi.objects.filter(
        tur=DenemeSinavi.Tur.GRUP,
        sinif_seviyesi=sinif_seviyesi,
        egitim_yili=egitim_yili,
        sira_no__isnull=False,
    )
    if haric_deneme_id:
        qs = qs.exclude(pk=haric_deneme_id)

    if tercih is not None:
        if qs.filter(sira_no=tercih).exists():
            raise ValueError(
                f"{tercih}. sıra numarası bu eğitim yılı/seviye içinde zaten kullanılıyor."
            )
        return tercih

    mevcut = qs.order_by("-sira_no").values_list("sira_no", flat=True).first()
    return (mevcut or 0) + 1


def deneme_sira_haritasi_talebeler(talebe_ids) -> dict[int, int]:
    """Etüdün kendi deneme sırası.

    Kurum ``sira_no`` eğitim yılı + sınıf seviyesi içinde bütün şubeleri
    sayar. Burada yalnızca verilen talebelerin sonucu olan aktif grup
    denemeleri, aynı yıl ve seviye içinde sınav tarihine göre 1'den
    numaralanır. Sayfa filtresi bu kümeyi daraltmaz; erken bir deneme
    gizlenince sonrakinin numarası kaymaz. Kayıtlı ``sira_no`` değişmez.
    """
    ids = [pk for pk in (talebe_ids or []) if pk]
    if not ids:
        return {}
    denemeler = (
        DenemeSinavi.objects.filter(
            tur=DenemeSinavi.Tur.GRUP,
            durum=DenemeSinavi.Durum.AKTIF,
            sonuclar__talebe_id__in=ids,
        )
        .distinct()
        .order_by("sinav_tarihi", "id")
    )
    sayac: dict[tuple, int] = {}
    harita: dict[int, int] = {}
    for deneme in denemeler:
        anahtar = (deneme.egitim_yili_id, (deneme.sinif_seviyesi or "").strip())
        sira = sayac.get(anahtar, 0) + 1
        sayac[anahtar] = sira
        harita[deneme.pk] = sira
    return harita


def gorunen_deneme_sira_haritasi(user: User) -> dict[int, int] | None:
    """Tam kapsamda ``None``: kart kurum sırasını gösterir.

    Dar kapsamda etüdün (yetkili talebelerin) kendi sırası. İstek ömrünce
    kullanıcı nesnesinde tutulur.
    """
    if not getattr(user, "is_authenticated", False):
        return {}
    if user.is_superuser or tum_talebe_kapsami_var(user):
        return None
    from takip.permissions.service import _req_cache

    cache = _req_cache(user)
    key = "deneme_etut_sira"
    if key not in cache:
        cache[key] = deneme_sira_haritasi_talebeler(
            yetkili_talebeler(user).values_list("id", flat=True)
        )
    return cache[key]


def denemelere_goster_sira(user: User, denemeler) -> None:
    """Şablonun okuduğu ``goster_sira`` alanını yazar. Veritabanına kaydetmez."""
    harita = gorunen_deneme_sira_haritasi(user)
    for deneme in denemeler:
        if deneme is None:
            continue
        if harita is None:
            deneme.goster_sira = deneme.sira_no
        else:
            deneme.goster_sira = harita.get(deneme.pk, deneme.sira_no)


def deneme_arsiv_filtrele(qs: QuerySet[DenemeSinavi], get_params) -> tuple[QuerySet[DenemeSinavi], dict]:
    """Deneme arşivi filtreleri: eğitim yılı, sınıf seviyesi, sınıf, tür, yayın, tarih.

    ``get_params`` bir request.GET (QueryDict) benzeri nesne olmalı. Hem
    personel hem yönetim deneme listesi ekranlarında aynı mantığı kullanır.
    """
    egitim_yili_id = (get_params.get("egitim_yili") or "").strip()
    sinif_seviyesi = (get_params.get("sinif_seviyesi") or "").strip()
    sinif_sube_id = (get_params.get("sinif_sube") or "").strip()
    tur = (get_params.get("tur") or "").strip()
    yayin = (get_params.get("yayin") or "").strip()
    baslangic = (get_params.get("baslangic") or "").strip()
    bitis = (get_params.get("bitis") or "").strip()

    if egitim_yili_id:
        qs = qs.filter(egitim_yili_id=egitim_yili_id)
    if sinif_seviyesi:
        qs = qs.filter(sinif_seviyesi=sinif_seviyesi)
    if sinif_sube_id:
        qs = qs.filter(hedef_sinif_subeler__id=sinif_sube_id)
    if tur:
        qs = qs.filter(tur=tur)
    if yayin:
        qs = qs.filter(yayin__icontains=yayin)
    if baslangic:
        qs = qs.filter(sinav_tarihi__gte=baslangic)
    if bitis:
        qs = qs.filter(sinav_tarihi__lte=bitis)

    filtre = {
        "egitim_yili": egitim_yili_id,
        "sinif_seviyesi": sinif_seviyesi,
        "sinif_sube": sinif_sube_id,
        "tur": tur,
        "yayin": yayin,
        "baslangic": baslangic,
        "bitis": bitis,
    }
    return qs.distinct(), filtre


def deneme_arsiv_filtre_secenekleri() -> dict:
    from takip.models import EgitimYili, SinifSube

    return {
        "egitim_yillari": EgitimYili.objects.order_by("-baslangic"),
        "sinif_subeler": SinifSube.objects.filter(aktif=True).order_by("sinif", "sube"),
        "tur_secenekleri": DenemeSinavi.Tur.choices,
    }


def deneme_sinavini_sil(user: User, deneme: DenemeSinavi) -> None:
    """Sınavı arşive alır. Sonuç ve kazanım satırları durur, listelerden düşer."""
    del user
    if deneme.durum == DenemeSinavi.Durum.ARSIV:
        return
    deneme.durum = DenemeSinavi.Durum.ARSIV
    deneme.save(update_fields=["durum", "guncellenme"])


def deneme_detay_satirlari(sonuclar) -> list[dict]:
    """Sıralama tablosu + ders ders D/Y/B için şablon satırları."""
    rows: list[dict] = []
    for sira, sonuc in enumerate(sonuclar, start=1):
        brans_map = {b.brans: b for b in sonuc.brans_satirlari.all()}
        branslar = []
        for kod in DENEME_DETAY_BRANSLAR:
            b = brans_map.get(kod)
            branslar.append(
                {
                    "kod": kod,
                    "etiket": BRANS_ETIKETLERI[kod],
                    "dogru": int(b.dogru or 0) if b else 0,
                    "yanlis": int(b.yanlis or 0) if b else 0,
                    "bos": int(b.bos or 0) if b else 0,
                    "net": b.net if b else 0,
                }
            )
        rows.append({"sira": sira, "sonuc": sonuc, "branslar": branslar})
    return rows


def deneme_silebilir(user: User) -> bool:
    if user.is_superuser:
        return True
    return can(user, "deneme", "delete")


def deneme_yukleyebilir(user: User) -> bool:
    from takip.permissions.registry import LEGACY_IDARE_ROLLER
    from takip.permissions.service import kullanici_birincil_rol_slug

    if user.is_superuser:
        return True
    if kullanici_birincil_rol_slug(user) not in LEGACY_IDARE_ROLLER:
        return False
    return can(user, "deneme", "create")


def yetkili_denemeler(user: User) -> QuerySet[DenemeSinavi]:
    if not can(user, "deneme", "view"):
        return DenemeSinavi.objects.none()

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return DenemeSinavi.objects.annotate(
            sonuc_sayisi=Count("sonuclar", distinct=True)
        ).order_by("-sinav_tarihi", "-id")

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return (
        DenemeSinavi.objects.annotate(
            sonuc_sayisi=Count(
                "sonuclar",
                filter=Q(sonuclar__talebe_id__in=talebe_ids),
                distinct=True,
            )
        )
        .filter(
            durum=DenemeSinavi.Durum.AKTIF,
            sonuclar__talebe_id__in=talebe_ids,
        )
        .distinct()
        .order_by("-sinav_tarihi", "-id")
    )


def yetkili_deneme_sonuclari(user: User) -> QuerySet[DenemeSonucu]:
    if not can(user, "deneme", "view"):
        return DenemeSonucu.objects.none()

    qs = DenemeSonucu.objects.select_related(
        "deneme", "talebe", "talebe__sinif_sube"
    ).prefetch_related("brans_satirlari")

    if user.is_superuser or tum_talebe_kapsami_var(user):
        return qs

    talebe_ids = yetkili_talebeler(user).values_list("id", flat=True)
    return qs.filter(talebe_id__in=talebe_ids)


def deneme_sonuclari(user: User, deneme: DenemeSinavi) -> QuerySet[DenemeSonucu]:
    qs = yetkili_deneme_sonuclari(user).filter(deneme=deneme)
    return qs.order_by("-puan", "-toplam_net", "talebe__ad_soyad")


# Bireysel karne ders sırası — LGS karnesindeki yerleşim.
DENEME_KARNE_DERSLERI: tuple[tuple[str, str], ...] = (
    ("turkce", "TÜRKÇE"),
    ("sosyal", "SOSYAL BİLGİLER"),
    ("din", "DİN KÜLTÜRÜ"),
    ("ingilizce", "İNGİLİZCE"),
    ("matematik", "MATEMATİK"),
    ("fen", "FEN BİLGİSİ"),
)

_HARICI_AYIR = re.compile(r"\s*(?:·|\|)\s*")
_SIRA_CIFT = re.compile(r"(\d+)\s*/\s*(\d+)")
_SIRA_SAYI = re.compile(r"\d+")


def tr_buyuk(metin: str) -> str:
    """Türkçe büyük harf: i → İ, ı → I."""
    return (metin or "").replace("i", "İ").replace("ı", "I").upper()


def tr_ondalik(deger, basamak: int = 2) -> str:
    """Karnedeki net ve puan: Türkçe virgül, sabit basamak."""
    if deger is None or deger == "":
        return "—"
    try:
        sayi = Decimal(str(deger))
    except Exception:
        return "—"
    quant = Decimal("1").scaleb(-basamak)
    sayi = sayi.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{sayi:.{basamak}f}".replace(".", ",")


def _karne_adet(deger) -> str:
    if deger is None or deger == "":
        return "—"
    return str(int(deger))


def _ascii_kucuk(metin: str) -> str:
    metin = (metin or "").strip().replace("İ", "i").replace("I", "ı").lower()
    return (
        metin.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def _sira_cifti(deger: str) -> tuple[str, str]:
    """Excel sıralama hücresinden (giren, sıra). Tek sayı sıradır."""
    ham = (deger or "").strip()
    if not ham:
        return "—", "—"
    cift = _SIRA_CIFT.search(ham)
    if cift:
        a, b = int(cift.group(1)), int(cift.group(2))
        if a == b:
            return str(a), str(b)
        giren, sira = (a, b) if a > b else (b, a)
        return str(giren), str(sira)
    sayilar = _SIRA_SAYI.findall(ham)
    if len(sayilar) >= 2:
        a, b = int(sayilar[0]), int(sayilar[1])
        if a == b:
            return str(a), str(b)
        giren, sira = (a, b) if a > b else (b, a)
        return str(giren), str(sira)
    if len(sayilar) == 1:
        return "—", sayilar[0]
    return "—", "—"


def _sira_turu(etiket: str) -> str:
    anahtar = _ascii_kucuk(etiket)
    if not anahtar:
        return "genel"
    if "sube" in anahtar:
        return "sube"
    if "sinif" in anahtar:
        return "sinif"
    if "kurum" in anahtar or anahtar.startswith("okul"):
        return "kurum"
    if any(parca in anahtar for parca in ("genel", "turkiye", "ulke", "ulusal", "il ")):
        return "genel"
    if anahtar in {"il", "il sirasi", "il siralamasi"} or anahtar.startswith("il "):
        return "genel"
    if any(parca in anahtar for parca in ("sira", "dilim", "rank")):
        return "genel"
    return ""


def _harici_siralama_kovasi(metin: str) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Excel harici metnini genel/kurum/şube/sınıf kovalarına ayırır."""
    kovalar: dict[str, tuple[str, str]] = {}
    artik: list[str] = []
    ham = (metin or "").strip()
    if not ham:
        return kovalar, artik
    for parca in _HARICI_AYIR.split(ham):
        parca = parca.strip()
        if not parca:
            continue
        if ":" in parca:
            etiket, deger = parca.split(":", 1)
        else:
            etiket, deger = "", parca
        tur = _sira_turu(etiket)
        cift = _sira_cifti(deger)
        if not tur or tur in kovalar:
            artik.append(parca)
            continue
        kovalar[tur] = cift
    return kovalar, artik


def deneme_karne_ortalamalari(deneme: DenemeSinavi) -> dict:
    """Sınavdaki her dersin ve toplam netin genel ortalaması."""
    sonuclar = list(
        DenemeSonucu.objects.filter(deneme=deneme).prefetch_related("brans_satirlari")
    )
    kovalar: dict[str, list[Decimal]] = {kod: [] for kod, _ in DENEME_KARNE_DERSLERI}
    toplamlar: list[Decimal] = []
    for sonuc in sonuclar:
        toplamlar.append(Decimal(sonuc.toplam_net or 0))
        for brans in sonuc.brans_satirlari.all():
            if brans.brans in kovalar:
                kovalar[brans.brans].append(Decimal(brans.net or 0))

    def _ort(degerler: list[Decimal]):
        if not degerler:
            return None
        return (sum(degerler, Decimal("0")) / Decimal(len(degerler))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    ort = {kod: _ort(nets) for kod, nets in kovalar.items()}
    ort["toplam"] = _ort(toplamlar)
    return ort


def _sinif_etiket(talebe: Talebe) -> str:
    sube = getattr(talebe, "sinif_sube", None)
    if sube is not None:
        return sube.etiket
    sinif = (getattr(talebe, "sinif", "") or "").strip()
    harf = (getattr(talebe, "sube", "") or "").strip()
    if sinif and harf:
        return f"{sinif}-{harf}"
    return sinif or harf or "—"


def _sinif_rozet(seviye: str) -> str:
    s = (seviye or "").strip()
    if s.isdigit():
        return f"{s}.SINIF"
    return (s or "SINIF").upper()


def deneme_bireysel_karne(deneme: DenemeSinavi, sonuc: DenemeSonucu, ortalamalar: dict) -> dict:
    """Tek talebenin ders analizi karnesi. Netler kayıtlı değerdir, yeniden hesaplanmaz."""
    brans_map = {b.brans: b for b in sonuc.brans_satirlari.all()}
    dersler = []
    for kod, etiket in DENEME_KARNE_DERSLERI:
        brans = brans_map.get(kod)
        ort = ortalamalar.get(kod)
        if brans is None:
            dersler.append(
                {
                    "ad": etiket,
                    "soru": "—",
                    "dogru": "—",
                    "yanlis": "—",
                    "bos": "—",
                    "net": "—",
                    "ort": tr_ondalik(ort) if ort is not None else "—",
                }
            )
            continue
        dogru = int(brans.dogru or 0)
        yanlis = int(brans.yanlis or 0)
        bos = int(brans.bos or 0)
        dersler.append(
            {
                "ad": etiket,
                "soru": dogru + yanlis + bos,
                "dogru": dogru,
                "yanlis": yanlis,
                "bos": bos,
                "net": tr_ondalik(brans.net),
                "ort": tr_ondalik(ort) if ort is not None else "—",
            }
        )

    kovalar, artik = _harici_siralama_kovasi(sonuc.dis_siralama_metni or "")

    def _hucre(tur: str, yedek_giren, yedek_sira) -> tuple[str, str]:
        if tur in kovalar:
            return kovalar[tur]
        return _karne_adet(yedek_giren), _karne_adet(yedek_sira)

    genel_giren, genel_sira = _hucre("genel", None, None)
    kurum_giren, kurum_sira = _hucre("kurum", sonuc.kurum_toplam, sonuc.kurum_sirasi)
    sube_giren, sube_sira = _hucre("sube", None, None)
    sinif_giren, sinif_sira = _hucre("sinif", sonuc.sinif_toplam, sonuc.sinif_sirasi)
    deneme_sirasi = sube_sira if sube_sira and sube_sira != "—" else ""
    deneme_rozet = (
        int(deneme_sirasi)
        if deneme_sirasi.isdigit() and int(deneme_sirasi) in (1, 2, 3)
        else 0
    )

    return {
        "ad_soyad": tr_buyuk(sonuc.talebe.ad_soyad or ""),
        "okul_no": (sonuc.talebe.talebe_no or "").strip() or "—",
        "sinif_etiket": _sinif_etiket(sonuc.talebe),
        "sinif_rozet": _sinif_rozet(deneme.sinif_seviyesi),
        "sinav_tarihi": deneme.sinav_tarihi,
        "sinav_adi": deneme.ad,
        "dersler": dersler,
        "toplam": {
            "soru": int(sonuc.toplam_dogru or 0)
            + int(sonuc.toplam_yanlis or 0)
            + int(sonuc.toplam_bos or 0),
            "dogru": int(sonuc.toplam_dogru or 0),
            "yanlis": int(sonuc.toplam_yanlis or 0),
            "bos": int(sonuc.toplam_bos or 0),
            "net": tr_ondalik(sonuc.toplam_net),
            "ort": tr_ondalik(ortalamalar.get("toplam"))
            if ortalamalar.get("toplam") is not None
            else "—",
        },
        "siralama": [
            {"ad": "GENEL", "giren": genel_giren, "sira": genel_sira},
            {"ad": "KURUM", "giren": kurum_giren, "sira": kurum_sira},
            {"ad": "ŞUBE", "giren": sube_giren, "sira": sube_sira},
            {"ad": "SINIF", "giren": sinif_giren, "sira": sinif_sira},
        ],
        "harici_not": " · ".join(artik),
        "puan": tr_ondalik(sonuc.puan),
        "deneme_sirasi": deneme_sirasi,
        "deneme_rozet": deneme_rozet,
    }


def deneme_karne_pdf_adi(ad_soyad: str) -> str:
    ad = re.sub(r'[\\/:*?"<>|\r\n]+', " ", (ad_soyad or "").strip())
    ad = re.sub(r"\s+", " ", ad).strip() or "Talebe"
    return f"{ad}.pdf"


def deneme_karne_zip_adi(deneme: DenemeSinavi) -> str:
    from django.utils.text import slugify

    govde = slugify(deneme.ad) or f"deneme-{deneme.pk}"
    return f"deneme-karneleri_{govde}.zip"


def deneme_sonuc_ozeti(sonuclar) -> dict:
    kayitlar = list(sonuclar)
    if not kayitlar:
        return {
            "ogrenci_sayisi": 0,
            "ortalama_net": "—",
            "ortalama_puan": "—",
            "en_yuksek_puan": "—",
        }

    toplam_net = sum(float(s.toplam_net or 0) for s in kayitlar)
    toplam_puan = sum(float(s.puan or 0) for s in kayitlar)
    en_yuksek = max(float(s.puan or 0) for s in kayitlar)
    adet = len(kayitlar)
    return {
        "ogrenci_sayisi": adet,
        "ortalama_net": round(toplam_net / adet, 2),
        "ortalama_puan": round(toplam_puan / adet, 2),
        "en_yuksek_puan": round(en_yuksek, 2),
    }


def talebe_deneme_sonuclari(talebe: Talebe) -> QuerySet[DenemeSonucu]:
    return (
        DenemeSonucu.objects.filter(talebe=talebe, deneme__durum=DenemeSinavi.Durum.AKTIF)
        .select_related("deneme")
        .prefetch_related("brans_satirlari")
        .order_by("-deneme__sinav_tarihi", "-id")
    )


DENEME_SINAV_SABITLERI: dict[str, dict] = {
    "8": {"baslik": "LGS", "soru": 85, "taban": 100, "tavan": 500},
    "7": {"baslik": "Deneme", "soru": 90, "taban": 0, "tavan": 500},
    "6": {"baslik": "Deneme", "soru": 90, "taban": 0, "tavan": 500},
}


def _talebe_sinif_seviyesi(talebe: Talebe) -> str:
    if getattr(talebe, "sinif_sube_id", None):
        ss = talebe.sinif_sube
        if ss:
            return str(ss.sinif).strip()
    return str(talebe.sinif or "8").strip()


def deneme_puan_yuzdesi(puan: float, taban: float, tavan: float) -> int:
    if tavan <= taban:
        return 0
    yuzde = (float(puan) - taban) / (tavan - taban) * 100
    return max(0, min(100, round(yuzde)))


def talebe_deneme_performans_ozeti(
    talebe: Talebe,
    *,
    gecmis_limit: int | None = None,
) -> dict | None:
    """Öğrenci deneme özeti — LGS tarzı kart + sınav geçmişi."""
    sonuclar = list(talebe_deneme_sonuclari(talebe))
    if not sonuclar:
        return None

    sinif = _talebe_sinif_seviyesi(talebe)
    sabit = DENEME_SINAV_SABITLERI.get(sinif, DENEME_SINAV_SABITLERI["8"])
    taban = float(sabit["taban"])
    tavan = float(sabit["tavan"])

    puanlar = [float(s.puan or 0) for s in sonuclar]
    netler = [float(s.toplam_net or 0) for s in sonuclar]
    ort_puan = round(sum(puanlar) / len(puanlar), 2)
    ort_net = round(sum(netler) / len(netler), 2)

    gecmis = []
    for sonuc in sonuclar[: gecmis_limit or len(sonuclar)]:
        puan = float(sonuc.puan or 0)
        gecmis.append(
            {
                "deneme_id": sonuc.deneme_id,
                "ad": sonuc.deneme.ad,
                "tarih": sonuc.deneme.sinav_tarihi,
                "puan": puan,
                "net": float(sonuc.toplam_net or 0),
                "yuzde": deneme_puan_yuzdesi(puan, taban, tavan),
            }
        )

    grafik_kaynak = list(reversed(sonuclar[:10]))
    max_net = max(float(s.toplam_net or 0) for s in grafik_kaynak) or 1
    grafik = [
        {
            "etiket": s.deneme.sinav_tarihi.strftime("%d.%m"),
            "baslik": s.deneme.ad,
            "net": float(s.toplam_net or 0),
            "puan": float(s.puan or 0),
            "net_yuzde": round(float(s.toplam_net or 0) * 100 / max_net, 1),
        }
        for s in grafik_kaynak
    ]

    return {
        "baslik": sabit["baslik"],
        "soru": sabit["soru"],
        "taban": int(sabit["taban"]),
        "tavan": int(sabit["tavan"]),
        "ortalama_puan": ort_puan,
        "ortalama_net": ort_net,
        "en_yuksek_puan": round(max(puanlar), 2),
        "en_dusuk_puan": round(min(puanlar), 2),
        "genel_yuzde": deneme_puan_yuzdesi(ort_puan, taban, tavan),
        "toplam_sinav": len(sonuclar),
        "gecmis": gecmis,
        "grafik": grafik,
    }
