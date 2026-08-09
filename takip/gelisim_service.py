"""Gelişim dosyası — merkezi profil verisi ve timeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from takip.akademik_mudahale_service import talebe_akademik_ozet
from takip.deneme_service import BRANS_ETIKETLERI, talebe_deneme_sonuclari
from takip.dini_ders_takip_service import talebe_ilerleme_ozeti
from takip.models import (
    AkademikMudahale,
    DenemeSonucu,
    DiniDersKonuKaydi,
    GunlukSoruKaydi,
    GunlukTakipKaydi,
    KttSonucu,
    NamazYoklamaKaydi,
    OgrenciGorusmesi,
    Talebe,
    TalebeGenelDurum,
    TalebePersonelNotu,
)
from takip.namaz_yoklama_models import NamazDurumu
from takip.permissions.scope import tum_talebe_kapsami_var
from takip.permissions.service import can
from takip.rehberlik_models import GorusmeTuru
from takip.rehberlik_service import gorusme_timeline_dt
from takip.soru_takip_service import aylik_ozet
from takip.user_helpers import etut_hocasi_for_user


DURUM_STILLERI = {
    TalebeGenelDurum.DurumKodu.IYI: {"etiket": "Çok iyi", "renk": "#16a34a", "bg": "#f0fdf4"},
    TalebeGenelDurum.DurumKodu.TAKIP: {"etiket": "Takip ediliyor", "renk": "#ea580c", "bg": "#fff7ed"},
    TalebeGenelDurum.DurumKodu.RISK: {"etiket": "Riskli", "renk": "#dc2626", "bg": "#fef2f2"},
    TalebeGenelDurum.DurumKodu.PASIF: {"etiket": "Pasif", "renk": "#64748b", "bg": "#f1f5f9"},
}


@dataclass
class TimelineOge:
    tarih: datetime
    baslik: str
    ozet: str
    kaynak: str
    ikon: str = "note"


def gelisim_gorunum(user: User, talebe: Talebe | None = None) -> dict[str, bool]:
    idare = user.is_superuser or tum_talebe_kapsami_var(user)
    hoca = etut_hocasi_for_user(user)
    dini_sinirli = False
    if talebe and hoca and not idare:
        dini_sinirli = (
            talebe.dini_ders_hocasi_id == hoca.id
            and talebe.etut_hocasi_id != hoca.id
            and can(user, "dini_ders_takip", "view")
        )

    if dini_sinirli:
        return {
            "kimlik": True,
            "genel_durum": False,
            "akademik_ozet": False,
            "deneme_grafik": False,
            "deneme_tablo": False,
            "devam": False,
            "dini": True,
            "gorevler": False,
            "notlar": can(user, "gelisim_dosyasi", "view"),
            "not_ekle": can(user, "gelisim_dosyasi", "create"),
            "dosyalar": False,
            "dosya_yukle": False,
            "dosya_sil": False,
            "gorusmeler": False,
            "mudahaleler": False,
            "timeline": False,
        }

    return {
        "kimlik": True,
        "genel_durum": idare or can(user, "gelisim_dosyasi", "edit"),
        "akademik_ozet": idare
        or can(user, "deneme", "view")
        or can(user, "ktt", "view")
        or can(user, "soru_takip", "view")
        or can(user, "akademik_mudahale", "view"),
        "deneme_grafik": idare or can(user, "deneme", "view"),
        "deneme_tablo": idare or can(user, "deneme", "view"),
        "devam": idare
        or can(user, "namaz_yoklama", "view")
        or can(user, "gunluk_takip", "view"),
        "dini": idare or can(user, "dini_ders_takip", "view"),
        "gorevler": idare or can(user, "temizlik", "view") or can(user, "yemekcilik", "view"),
        "notlar": idare or can(user, "gelisim_dosyasi", "view"),
        "not_ekle": idare or can(user, "gelisim_dosyasi", "create"),
        "dosyalar": idare or can(user, "gelisim_dosyasi", "view"),
        "dosya_yukle": idare or can(user, "gelisim_dosyasi", "create"),
        "dosya_sil": idare or can(user, "gelisim_dosyasi", "delete"),
        "gorusmeler": idare
        or can(user, "rehberlik", "view")
        or can(user, "veli_iletisim", "view"),
        "mudahaleler": idare or can(user, "akademik_mudahale", "view"),
        "timeline": idare,
    }


def _ay_araligi(referans: date | None = None) -> tuple[date, date]:
    bugun = referans or timezone.localdate()
    baslangic = bugun.replace(day=1)
    if bugun.month == 12:
        bitis = bugun.replace(day=31)
    else:
        bitis = bugun.replace(month=bugun.month + 1, day=1) - timedelta(days=1)
    return baslangic, min(bitis, bugun)


def _kimlik_karti(talebe: Talebe, sinif_goster: str) -> dict:
    kayit = (
        talebe.zimmetler.order_by("zimmet_tarihi").values_list("zimmet_tarihi", flat=True).first()
    )
    return {
        "ad_soyad": talebe.ad_soyad,
        "talebe_no": talebe.talebe_no or "—",
        "sinif": sinif_goster,
        "dini_seviye": str(talebe.dini_ders_seviyesi) if talebe.dini_ders_seviyesi_id else "—",
        "etut_hocasi": talebe.etut_hocasi.ad_soyad,
        "dini_hocasi": talebe.dini_ders_hocasi.ad_soyad,
        "dogum_tarihi": talebe.dogum_tarihi,
        "durum": talebe.get_durum_display(),
        "durum_kod": talebe.durum,
        "kayit_tarihi": kayit,
    }


def _genel_durum_karti(genel: TalebeGenelDurum) -> dict:
    stil = DURUM_STILLERI.get(
        genel.durum_kodu,
        DURUM_STILLERI[TalebeGenelDurum.DurumKodu.TAKIP],
    )
    return {
        "kod": genel.durum_kodu,
        "etiket": stil["etiket"],
        "renk": stil["renk"],
        "bg": stil["bg"],
        "ozet": genel.ozet,
        "guncellenme": genel.guncellenme,
    }


def _akademik_ozet_kartlari(talebe: Talebe) -> list[dict]:
    bugun = timezone.localdate()
    ay = aylik_ozet(talebe, bugun)
    mudahale = talebe_akademik_ozet(talebe)

    son_deneme = talebe_deneme_sonuclari(talebe).first()
    son_ktt = (
        KttSonucu.objects.filter(talebe=talebe)
        .order_by("-ktt__sinav_tarihi", "-id")
        .first()
    )
    son_uc_deneme = list(talebe_deneme_sonuclari(talebe)[:3])
    ort_puan = None
    if son_uc_deneme:
        ort_puan = round(
            sum(float(s.puan or 0) for s in son_uc_deneme) / len(son_uc_deneme),
            1,
        )

    return [
        {
            "etiket": "Son deneme neti",
            "deger": str(son_deneme.toplam_net) if son_deneme else "—",
            "alt": son_deneme.deneme.ad if son_deneme else "Kayıt yok",
        },
        {
            "etiket": "Son KTT neti",
            "deger": str(son_ktt.net) if son_ktt else "—",
            "alt": son_ktt.ktt.ad if son_ktt else "Kayıt yok",
        },
        {
            "etiket": "Bu ay soru",
            "deger": str(ay["toplam_soru"]),
            "alt": f"Net {ay['toplam_net']} · %{ay['basari_orani']}",
        },
        {
            "etiket": "Bu ay müdahale",
            "deger": str(mudahale["bu_ay"]),
            "alt": f"Toplam {mudahale['toplam']}",
        },
        {
            "etiket": "Son 3 deneme puan",
            "deger": str(ort_puan) if ort_puan is not None else "—",
            "alt": "Ortalama",
        },
    ]


def _deneme_grafik_verisi(talebe: Talebe, *, limit: int = 6) -> list[dict]:
    sonuclar = list(talebe_deneme_sonuclari(talebe)[:limit])
    sonuclar.reverse()
    if not sonuclar:
        return []

    max_net = max(float(s.toplam_net or 0) for s in sonuclar) or 1
    grafik = []
    for sonuc in sonuclar:
        net = float(sonuc.toplam_net or 0)
        grafik.append(
            {
                "etiket": sonuc.deneme.sinav_tarihi.strftime("%d.%m"),
                "baslik": sonuc.deneme.ad,
                "net": net,
                "puan": float(sonuc.puan or 0),
                "net_yuzde": round(net * 100 / max_net, 1),
            }
        )
    return grafik


def _devam_ozeti(talebe: Talebe) -> dict:
    baslangic, bitis = _ay_araligi()
    gunluk = GunlukTakipKaydi.objects.filter(
        talebe=talebe,
        tarih__gte=baslangic,
        tarih__lte=bitis,
    )
    toplam_gun = gunluk.count()
    devamsiz = gunluk.filter(devam=GunlukTakipKaydi.DevamDurumu.GELMEDI).count()
    gec = gunluk.filter(devam=GunlukTakipKaydi.DevamDurumu.GEC).count()
    etut_katilan = gunluk.filter(etut_katilim=True).count()
    etut_katilmayan = gunluk.filter(etut_katilim=False).count()
    etut_oran = round((etut_katilan / toplam_gun) * 100, 1) if toplam_gun else 0

    namaz_qs = NamazYoklamaKaydi.objects.filter(
        talebe=talebe,
        oturum__tarih__gte=baslangic,
        oturum__tarih__lte=bitis,
    )
    namaz_toplam = namaz_qs.count()
    namaz_gelmedi = namaz_qs.filter(durum="gelmedi").count()
    namaz_oran = round(((namaz_toplam - namaz_gelmedi) / namaz_toplam) * 100, 1) if namaz_toplam else 0
    izinli = (
        namaz_qs.filter(durum=NamazDurumu.IZINLI)
        .values("oturum__tarih")
        .distinct()
        .count()
    )

    return {
        "ay_baslangic": baslangic,
        "devamsizlik": devamsiz,
        "gec_kalma": gec,
        "izinli": izinli,
        "etut_katilim_orani": etut_oran,
        "etut_kaçirma": etut_katilmayan,
        "namaz_katilim_orani": namaz_oran,
        "namaz_gelmedi": namaz_gelmedi,
    }


def _gorev_gecmisi(talebe: Talebe) -> dict:
    temizlik = [
        {
            "tarih": a.tarih,
            "baslik": str(a.alan) if a.alan_id else "Temizlik görevi",
            "durum": "Tamamlandı",
        }
        for a in talebe.temizlik_gorevleri.select_related("alan").order_by("-tarih")[:20]
    ]
    yemek = []
    for a in talebe.yemekci_gorevleri.select_related("ogun").order_by("-tarih")[:20]:
        yemek.append(
            {
                "tarih": a.tarih,
                "baslik": f"{a.ogun.ad} — Sorumlu",
                "durum": "Tamamlandı",
            }
        )
    for a in talebe.yemekci_yardimci_gorevleri.select_related("ogun").order_by("-tarih")[:10]:
        yemek.append(
            {
                "tarih": a.tarih,
                "baslik": f"{a.ogun.ad} — Yardımcı",
                "durum": "Tamamlandı",
            }
        )
    yemek.sort(key=lambda x: x["tarih"], reverse=True)
    return {"temizlik": temizlik, "yemek": yemek[:20]}


def _gorusme_listesi(talebe: Talebe, user: User) -> list[dict]:
    qs = OgrenciGorusmesi.objects.filter(talebe=talebe).select_related("tur", "kaydeden")
    if not (user.is_superuser or tum_talebe_kapsami_var(user)):
        alanlar = []
        if can(user, "rehberlik", "view"):
            alanlar.append(GorusmeTuru.Alan.REHBERLIK)
        if can(user, "veli_iletisim", "view"):
            alanlar.append(GorusmeTuru.Alan.ILETISIM)
        if alanlar:
            qs = qs.filter(tur__alan__in=alanlar)
        else:
            return []

    return [
        {
            "pk": g.pk,
            "tarih": g.tarih,
            "tur": g.tur.ad,
            "alan": g.tur.alan,
            "alan_etiket": g.tur.get_alan_display(),
            "ozet": g.ozet,
            "detay": g.detay[:200] if g.detay else "",
            "kaydeden": g.kaydeden.get_full_name() if g.kaydeden else "—",
        }
        for g in qs.order_by("-tarih", "-id")[:15]
    ]


def _deneme_tablo(talebe: Talebe, *, limit: int = 8) -> dict:
    sonuclar = list(talebe_deneme_sonuclari(talebe)[:limit])
    satirlar = []
    for sonuc in sonuclar:
        brans_map = {b.brans: b.net for b in sonuc.brans_satirlari.all()}
        satirlar.append(
            {
                "tarih": sonuc.deneme.sinav_tarihi,
                "ad": sonuc.deneme.ad,
                "deneme_id": sonuc.deneme_id,
                "brans_netleri": [
                    brans_map.get(kod) for kod in BRANS_ETIKETLERI
                ],
                "toplam_dogru": sonuc.toplam_dogru,
                "toplam_yanlis": sonuc.toplam_yanlis,
                "toplam_bos": sonuc.toplam_bos,
                "toplam_net": sonuc.toplam_net,
                "puan": sonuc.puan,
            }
        )
    return {"brans_etiketleri": BRANS_ETIKETLERI, "satirlar": satirlar}


def _mudahale_listesi(talebe: Talebe) -> list[dict]:
    return [
        {
            "tarih": m.tarih,
            "ders": m.ders.ad if m.ders_id else "—",
            "konu": m.konu or "—",
            "tur": m.mudahale_turu.ad,
            "sorumlu": m.olusturan.get_full_name() if m.olusturan else "—",
            "durum": m.degerlendirme_notu[:80] if m.degerlendirme_notu else "Kayıt",
            "pk": m.pk,
        }
        for m in AkademikMudahale.objects.filter(talebe=talebe)
        .select_related("mudahale_turu", "ders", "olusturan")
        .order_by("-tarih", "-id")[:12]
    ]


def talebe_gelisim_dosyasi(
    user: User,
    talebe: Talebe,
    *,
    sinif_goster: str,
    genel: TalebeGenelDurum,
) -> dict:
    gorunum = gelisim_gorunum(user, talebe)
    return {
        "gorunum": gorunum,
        "kimlik": _kimlik_karti(talebe, sinif_goster),
        "genel_durum": _genel_durum_karti(genel),
        "akademik_kartlar": _akademik_ozet_kartlari(talebe) if gorunum["akademik_ozet"] else [],
        "deneme_grafik": _deneme_grafik_verisi(talebe) if gorunum["deneme_grafik"] else [],
        "devam": _devam_ozeti(talebe) if gorunum["devam"] else None,
        "dini_ilerleme": talebe_ilerleme_ozeti(talebe) if gorunum["dini"] else [],
        "gorevler": _gorev_gecmisi(talebe) if gorunum["gorevler"] else {"temizlik": [], "yemek": []},
        "gorusmeler": _gorusme_listesi(talebe, user) if gorunum["gorusmeler"] else [],
        "deneme_tablo": _deneme_tablo(talebe) if gorunum["deneme_tablo"] else None,
        "mudahaleler": _mudahale_listesi(talebe) if gorunum["mudahaleler"] else [],
    }


def talebe_timeline(talebe: Talebe, user: User | None = None) -> list[TimelineOge]:
    ogeler: list[TimelineOge] = []

    notlar = TalebePersonelNotu.objects.filter(talebe=talebe).select_related("yazar")
    if user and not user.is_superuser:
        notlar = notlar.filter(staff_only=True)

    for not_kaydi in notlar[:50]:
        ogeler.append(
            TimelineOge(
                tarih=not_kaydi.olusturulma,
                baslik=not_kaydi.baslik,
                ozet=not_kaydi.icerik[:200],
                kaynak="Personel Notu",
                ikon="note",
            )
        )

    ktt_sonuclari = (
        KttSonucu.objects.filter(talebe=talebe)
        .select_related("ktt", "ktt__ders")
        .order_by("-ktt__sinav_tarihi")[:20]
    )
    for sonuc in ktt_sonuclari:
        tarih = datetime.combine(sonuc.ktt.sinav_tarihi, time.min)
        if timezone.is_naive(tarih):
            tarih = timezone.make_aware(tarih)
        ogeler.append(
            TimelineOge(
                tarih=tarih,
                baslik=f"{sonuc.ktt.ad} ({sonuc.ktt.ders.ad})",
                ozet=(
                    f"Net {sonuc.net} · Puan {sonuc.puan} · "
                    f"D{sonuc.dogru} Y{sonuc.yanlis} B{sonuc.bos}"
                ),
                kaynak="KTT",
                ikon="ktt",
            )
        )

    soru_kayitlari = (
        GunlukSoruKaydi.objects.filter(talebe=talebe)
        .prefetch_related("ders_satirlari")
        .order_by("-tarih")[:20]
    )
    for kayit in soru_kayitlari:
        tarih = datetime.combine(kayit.tarih, time.min)
        if timezone.is_naive(tarih):
            tarih = timezone.make_aware(tarih)
        ogeler.append(
            TimelineOge(
                tarih=tarih,
                baslik=f"Günlük Soru — {kayit.toplam_soru} soru",
                ozet=f"Net {kayit.toplam_net} · Başarı %{kayit.basari_orani}",
                kaynak="Soru Takip",
                ikon="soru",
            )
        )

    mudahaleler = (
        AkademikMudahale.objects.filter(talebe=talebe)
        .select_related("mudahale_turu", "ders")
        .order_by("-tarih")[:20]
    )
    for mudahale in mudahaleler:
        tarih = datetime.combine(mudahale.tarih, time.min)
        if timezone.is_naive(tarih):
            tarih = timezone.make_aware(tarih)
        ozet = mudahale.veli_ozet
        if mudahale.degerlendirme_notu:
            ozet = f"{ozet} · {mudahale.degerlendirme_notu[:120]}"
        ogeler.append(
            TimelineOge(
                tarih=tarih,
                baslik=f"{mudahale.mudahale_turu.ad}"
                + (f" — {mudahale.ders.ad}" if mudahale.ders_id else ""),
                ozet=ozet,
                kaynak="Akademik Müdahale",
                ikon="akademik",
            )
        )

    for gorusme in OgrenciGorusmesi.objects.filter(talebe=talebe).select_related("tur")[:25]:
        kaynak = (
            "Veli & Talebe İletişim"
            if gorusme.tur.alan == GorusmeTuru.Alan.ILETISIM
            else "Rehberlik"
        )
        ogeler.append(
            TimelineOge(
                tarih=gorusme_timeline_dt(gorusme),
                baslik=f"{kaynak} — {gorusme.tur.ad}",
                ozet=gorusme.ozet,
                kaynak=kaynak,
                ikon="rehberlik",
            )
        )

    deneme_sonuclari = (
        DenemeSonucu.objects.filter(talebe=talebe, deneme__durum="aktif")
        .select_related("deneme")
        .order_by("-deneme__sinav_tarihi")[:15]
    )
    for sonuc in deneme_sonuclari:
        tarih = datetime.combine(sonuc.deneme.sinav_tarihi, time.min)
        if timezone.is_naive(tarih):
            tarih = timezone.make_aware(tarih)
        ogeler.append(
            TimelineOge(
                tarih=tarih,
                baslik=sonuc.deneme.ad,
                ozet=f"Net {sonuc.toplam_net} · Puan {sonuc.puan}",
                kaynak="Deneme",
                ikon="deneme",
            )
        )

    dini_kayitlar = (
        DiniDersKonuKaydi.objects.filter(talebe=talebe, tamamlandi=True)
        .select_related("konu", "konu__alan", "isaretleyen")
        .order_by("-guncellenme")[:20]
    )
    for kayit in dini_kayitlar:
        ogeler.append(
            TimelineOge(
                tarih=kayit.guncellenme,
                baslik=f"{kayit.konu.alan.ad} — {kayit.konu.ad}",
                ozet="Konu tamamlandı",
                kaynak="Dini Ders Takip",
                ikon="dini",
            )
        )

    ogeler.sort(key=lambda o: o.tarih, reverse=True)
    return ogeler
