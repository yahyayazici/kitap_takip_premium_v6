"""Optik sonuçlarını ana sitenin (cinilisarayproje.com) deneme modülüne aktarır.

Ana site deneme sonuçlarını `takip` uygulamasında tutar (DenemeSinavi,
DenemeSonucu, DenemeBransSonucu, DenemeKazanimSonucu, DenemeSoruSonucu) ve
veli/talebe panelleri, ÇİSA, gelişim, etüt gibi ekranlar oradan okur. Buradaki
aktarım, XYS Excel içe aktarımının ürettiği kayıtların aynısını üretir; böylece
o ekranların hiçbiri değişmez. Aktarılan deneme **taslak** başlar; ana sitede
"Yayınla" denince velilere görünür.

`takip` uygulaması yalnızca ana sitenin içinde çalışırken vardır; bu yüzden
içe aktarımlar fonksiyon içindedir ve özellik `OKUMA_ANA_SITE` ayarıyla açılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from okuma.models import Deneme, Ogrenci
from okuma.services.optik import numara_normalize

# Optik ders anahtarı → ana sitenin branş kodu
BRANS = {
    "turkce": "turkce",
    "matematik": "matematik",
    "fen": "fen",
    "inkilap": "sosyal",
    "din": "din",
    "yabanci_dil": "ingilizce",
}
SEVIYELER = {"5", "6", "7", "8"}
IKI = Decimal("0.01")


def ana_site_acik() -> bool:
    return bool(getattr(settings, "OKUMA_ANA_SITE", False))


def ana_site_deneme_adresi(ana_deneme_id: int | None) -> str:
    if not ana_deneme_id:
        return ""
    taban = (getattr(settings, "PANEL_PUBLIC_URL", "") or "").rstrip("/")
    return f"{taban}/yonetim/denemeler/{ana_deneme_id}/"


def _seviye(sinif: str) -> str:
    m = re.search(r"\d+", sinif or "")
    return m.group(0) if m else ""


# ── Öğrenci eşitleme ───────────────────────────────────────────────────────


@dataclass
class EsitlemeSonucu:
    eklenen: int = 0
    guncellenen: int = 0
    numarasiz: int = 0


@transaction.atomic
def talebeleri_esitle() -> EsitlemeSonucu:
    """Ana sitedeki aktif 5–8. sınıf talebelerini optik öğrenci listesine işler.

    Optik numarası = talebe numarası. Ana site esastır: aynı numaradaki kaydın
    adı, sınıfı ve şubesi talebeden alınır.
    """
    from takip.models import Talebe

    sonuc = EsitlemeSonucu()
    talebeler = Talebe.objects.filter(aktif=True, durum=Talebe.Durum.AKTIF).select_related("sinif_sube")
    for t in talebeler:
        seviye = _seviye(t.sinif)
        if seviye not in SEVIYELER:
            continue
        numara = numara_normalize(t.talebe_no or "")
        if not numara.isdigit():
            sonuc.numarasiz += 1
            continue
        ogr = Ogrenci.objects.filter(dis_kimlik=str(t.pk)).first() or Ogrenci.objects.filter(numara=numara).first()
        veri = {
            "numara": numara,
            "ad_soyad": t.ad_soyad,
            "sinif_seviyesi": seviye,
            "sube": (t.sube or "").strip().upper()[:10],
            "dis_kimlik": str(t.pk),
            "aktif": True,
        }
        if ogr is None:
            Ogrenci.objects.create(**veri)
            sonuc.eklenen += 1
            continue
        if ogr.numara != numara:
            # Talebe numarası değişmiş; eski numarayı kullanan başka kayıt varsa ondan ayır.
            Ogrenci.objects.filter(numara=numara).exclude(pk=ogr.pk).update(numara=f"x{ogr.pk}-{numara}"[:20], aktif=False)
        degisti = [k for k, v in veri.items() if getattr(ogr, k) != v]
        if degisti:
            for k in degisti:
                setattr(ogr, k, veri[k])
            ogr.save(update_fields=degisti)
            sonuc.guncellenen += 1
    return sonuc


def talebe_bul(ogrenci: Ogrenci):
    """Optik öğrencisinin ana sitedeki talebesi: bağlantı → talebe no → ad soyad (kesin eşleşme)."""
    from takip.deneme_excel import talebe_eslestir
    from takip.models import Talebe

    if ogrenci.dis_kimlik.isdigit():
        t = Talebe.objects.filter(pk=int(ogrenci.dis_kimlik)).first()
        if t:
            return t
    for t in Talebe.objects.filter(talebe_no__isnull=False).exclude(talebe_no="").filter(talebe_no__endswith=ogrenci.numara):
        if numara_normalize(t.talebe_no) == ogrenci.numara:
            return t
    if ogrenci.ad_soyad:
        t, tip, _ = talebe_eslestir(ogrenci.ad_soyad, f"{ogrenci.sinif_seviyesi}{ogrenci.sube}")
        if t is not None and tip in ("otomatik", "alias"):
            return t
    return None


# ── Aktarım ────────────────────────────────────────────────────────────────


@dataclass
class AktarimSonucu:
    ana_deneme_id: int
    aktarilan: int = 0
    eslesmeyen: list[str] = field(default_factory=list)
    yeni: bool = False
    durum: str = "taslak"


def _kazanim_adi(k) -> str:
    return f"{k.kod} {k.metin}".strip() if k.kod else k.metin


@transaction.atomic
def ana_siteye_aktar(deneme: Deneme, kullanici=None) -> AktarimSonucu:
    from takip.deneme_excel import normalize_ad
    from takip.deneme_kazanim_excel import name_key
    from takip.deneme_models import (
        DenemeBransSonucu,
        DenemeKazanimSonucu,
        DenemeSinavi,
        DenemeSonucu,
        DenemeSoruSonucu,
    )
    from takip.deneme_service import eksik_deneme_puanlarini_doldur, sira_no_ata, siralama_hesapla_ve_kaydet
    from takip.dini_ilerleme_service import aktif_egitim_yili
    from takip.soru_takip_service import deneme_sonucu_soru_takibe_yansit

    from okuma.services.puanlama import harita_kur
    from okuma.services.raporlar import kazanim_sayimlari

    sonuclar = list(
        deneme.sonuclar.select_related("ogrenci").prefetch_related("test_sonuclari__test").order_by("sira_kurum")
    )
    if not sonuclar:
        raise ValueError("Aktarılacak sonuç yok. Önce optik dosyasını okutun.")

    # 1) Ana sitedeki deneme kaydı (varsa güncellenir; yayın durumu korunur)
    ana = DenemeSinavi.objects.filter(pk=deneme.ana_site_deneme_id).first() if deneme.ana_site_deneme_id else None
    yeni = ana is None
    if yeni:
        yil = aktif_egitim_yili()
        ana = DenemeSinavi(
            tur=DenemeSinavi.Tur.GRUP,
            durum=DenemeSinavi.Durum.TASLAK,
            egitim_yili=yil,
            sira_no=sira_no_ata(yil, deneme.sinif_seviyesi),
            olusturan=kullanici,
        )
    ana.ad = deneme.ad
    ana.sinav_tarihi = deneme.tarih
    ana.sinif_seviyesi = deneme.sinif_seviyesi
    ana.yayin = ana.yayin or "Kurum denemesi (optik)"
    ana.toplam_soru = deneme.toplam_soru
    ana.yukleyen = kullanici
    ana.yuklenme_zamani = timezone.now()
    if not ana.aciklama:
        ana.aciklama = "Optik panelinden aktarıldı."
    ana.save()
    deneme.ana_site_deneme_id = ana.pk
    deneme.ana_site_aktarim = timezone.now()
    deneme.save(update_fields=["ana_site_deneme_id", "ana_site_aktarim"])

    # 2) Öğrenci → talebe eşleşmesi
    talebeler = {}
    eslesmeyen = []
    for s in sonuclar:
        t = talebe_bul(s.ogrenci)
        if t is None:
            eslesmeyen.append(f"{s.ogrenci.numara} {s.ogrenci.ad_soyad}".strip())
            continue
        if s.ogrenci.dis_kimlik != str(t.pk):
            s.ogrenci.dis_kimlik = str(t.pk)
            s.ogrenci.save(update_fields=["dis_kimlik"])
        talebeler[s.pk] = t

    # 3) Eski sonuçları kaldır (soru takibinden de düş), yenilerini yaz
    for eski in DenemeSonucu.objects.filter(deneme=ana).prefetch_related("brans_satirlari", "talebe"):
        deneme_sonucu_soru_takibe_yansit(user=kullanici, deneme=ana, sonuc=eski, silindi=True)
    DenemeSonucu.objects.filter(deneme=ana).delete()
    DenemeKazanimSonucu.objects.filter(deneme=ana).delete()
    DenemeSoruSonucu.objects.filter(deneme=ana).delete()

    yazilan = []
    for s in sonuclar:
        t = talebeler.get(s.pk)
        if t is None:
            continue
        ana_sonuc = DenemeSonucu.objects.create(
            deneme=ana,
            talebe=t,
            toplam_dogru=s.dogru,
            toplam_yanlis=s.yanlis,
            toplam_bos=s.bos,
            toplam_net=Decimal(s.net).quantize(IKI, rounding=ROUND_HALF_UP),
            puan=Decimal(s.puan).quantize(IKI, rounding=ROUND_HALF_UP) if s.puan is not None else Decimal("0.00"),
        )
        branslar: dict[str, list] = {}
        for ts in s.test_sonuclari.all():
            kod = BRANS.get(ts.test.lgs_ders)
            if not kod:
                continue
            b = branslar.setdefault(kod, [0, 0, 0, Decimal(0)])
            b[0] += ts.dogru
            b[1] += ts.yanlis
            b[2] += ts.bos
            b[3] += ts.net
        DenemeBransSonucu.objects.bulk_create(
            DenemeBransSonucu(sonuc=ana_sonuc, brans=kod, dogru=d, yanlis=y, bos=b, net=Decimal(n).quantize(IKI))
            for kod, (d, y, b, n) in branslar.items()
        )
        deneme_sonucu_soru_takibe_yansit(user=kullanici, deneme=ana, sonuc=ana_sonuc)
        yazilan.append(ana_sonuc)

    eksik_deneme_puanlarini_doldur(DenemeSonucu.objects.filter(deneme=ana).prefetch_related("brans_satirlari"))
    siralama_hesapla_ve_kaydet(ana)

    # 4) Kazanım yüzdeleri (doğru ÷ toplam soru × 100; net doğru = D − Y/k)
    ogr_talebe = {s.ogrenci_id: talebeler[s.pk] for s in sonuclar if s.pk in talebeler}
    k = deneme.yanlis_katsayi
    sayimlar, _ = kazanim_sayimlari([deneme])
    kazanim_kayitlari = {}
    for kayit in sayimlar.values():
        konu = _kazanim_adi(kayit.kazanim)[:300]
        for oid, (d, y, b) in kayit.ogrenciler.items():
            t = ogr_talebe.get(oid)
            toplam = d + y + b
            if t is None or not toplam:
                continue
            anahtar = (t.pk, name_key(kayit.ders_adi)[:120], name_key(konu)[:300])
            kazanim_kayitlari[anahtar] = DenemeKazanimSonucu(
                deneme=ana,
                talebe=t,
                ders_ad=kayit.ders_adi[:120],
                konu_ad=konu,
                ders_key=anahtar[1],
                konu_key=anahtar[2],
                yuzde=(Decimal(100 * d) / Decimal(toplam)).quantize(IKI, rounding=ROUND_HALF_UP),
                net_dogru=(Decimal(d) - (Decimal(y) / Decimal(k) if k else 0)).quantize(IKI, rounding=ROUND_HALF_UP),
                net_toplam=Decimal(toplam),
            )
    DenemeKazanimSonucu.objects.bulk_create(kazanim_kayitlari.values(), batch_size=500)

    # 5) Soru soru sonuçlar — öğrencinin kendi kitapçığındaki soru numarasıyla (karne 2. sayfa)
    harita = harita_kur(deneme)
    testler = {t.pk: t for t in harita.testler}
    soru_bilgi = {}
    for t in harita.testler:
        for soru in t.sorular.all():
            siralar = {ks.kitapcik: ks.no for ks in soru.kitapcik_siralari.all()}
            konu = next(iter(soru.kazanimlar.all()), None)
            soru_bilgi[soru.pk] = (soru.no, siralar, _kazanim_adi(konu)[:300] if konu else "")
    soru_kayitlari = {}
    for s in sonuclar:
        t = talebeler.get(s.pk)
        if t is None:
            continue
        if not s.a_sirali:
            # Eşleşmesiz kitapçık: kendi sırası ve kendi anahtarıyla (konu bilinmez).
            i = 0
            for test in harita.testler:
                ders_key = normalize_ad(test.ders)[:120]
                for no, dogru in enumerate(harita.bagimsiz.get(s.kitapcik, {}).get(test.pk, ""), start=1):
                    c = s.cevaplar_a[i] if i < len(s.cevaplar_a) else " "
                    i += 1
                    if dogru == "X":
                        continue
                    soru_kayitlari[(t.pk, ders_key, no)] = DenemeSoruSonucu(
                        deneme=ana, talebe=t, ders_ad=test.ders[:120], ders_key=ders_key, soru_no=no, konu_ad="",
                        sonuc="bos" if c == " " else ("dogru" if c == dogru else "yanlis"), sira=test.sira * 1000 + no,
                    )
            continue
        for sb in harita.sorular:
            if sb.iptal:
                continue
            test = testler[sb.test_id]
            a_no, siralar, konu = soru_bilgi[sb.soru_id]
            no = a_no if s.kitapcik == "A" else siralar.get(s.kitapcik, a_no)
            c = s.cevaplar_a[sb.a_index]
            durum = "bos" if c == " " else ("dogru" if c in sb.dogrular else "yanlis")
            ders_key = normalize_ad(test.ders)[:120]
            soru_kayitlari[(t.pk, ders_key, no)] = DenemeSoruSonucu(
                deneme=ana,
                talebe=t,
                ders_ad=test.ders[:120],
                ders_key=ders_key,
                soru_no=no,
                konu_ad=konu,
                sonuc=durum,
                sira=test.sira * 1000 + no,
            )
    DenemeSoruSonucu.objects.bulk_create(soru_kayitlari.values(), batch_size=500)

    return AktarimSonucu(ana_deneme_id=ana.pk, aktarilan=len(yazilan), eslesmeyen=eslesmeyen, yeni=yeni, durum=ana.durum)
