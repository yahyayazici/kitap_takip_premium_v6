"""Tüm panelleri dolduran zengin demo verisi.

seed_demo komutundan çağrılır; boş/ince modülleri doldurur.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal
from itertools import cycle

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone


def _pazartesi(d=None):
    d = d or timezone.localdate()
    return d - timedelta(days=d.weekday())


def _sinif_al(sinif: str, sube: str = "A"):
    from takip.models import SinifSube

    ss, _ = SinifSube.objects.get_or_create(
        sinif=sinif, sube=sube, defaults={"aktif": True}
    )
    return ss


def _hoca_yahya():
    from takip.models import EtutHocasi

    return EtutHocasi.objects.filter(ad_soyad__icontains="Yahya").first() or EtutHocasi.objects.filter(aktif=True).first()


def _hoca_kemal():
    from takip.models import EtutHocasi

    return EtutHocasi.objects.filter(ad_soyad__icontains="Kemal").first()


def seed_genis_talebe_havuzu() -> list:
    """5–8. sınıflarda ekstra talebe; mevcutları silmez."""
    from takip.models import Talebe

    hoca = _hoca_yahya()
    kemal = _hoca_kemal()
    if not hoca:
        return []
    isimler = [
        ("5", "A", "Emir Can Yıldız", "2001"),
        ("5", "A", "Ömer Faruk Demir", "2002"),
        ("5", "B", "Ali Rıza Çelik", "2003"),
        ("5", "B", "Mustafa Efe Şahin", "2004"),
        ("6", "A", "Hüseyin Kerem Arslan", "2005"),
        ("6", "A", "İbrahim Halil Koç", "2006"),
        ("6", "B", "Furkan Yiğit Aydın", "2007"),
        ("6", "B", "Berat Enes Polat", "2008"),
        ("7", "A", "Talha Efe Bay", "2009"),
        ("7", "A", "Mert Ali Güneş", "2010"),
        ("7", "B", "Kerem Can Öztürk", "2011"),
        ("7", "B", "Enes Baran Doğan", "2012"),
        ("8", "A", "Yusuf Emir Kurt", "2013"),
        ("8", "A", "Burak Can Yalçın", "2014"),
        ("8", "B", "Umut Eren Acar", "2015"),
        ("8", "B", "Salih Efe Taş", "2016"),
    ]
    # Tüm sınıfları hocalara bağla (validation için)
    tum_siniflar = {_sinif_al(s, b) for s, b, _, _ in isimler}
    for hh in filter(None, [hoca, kemal]):
        hh.sorumlu_sinif_subeler.add(*tum_siniflar)

    sonuc = []
    for i, (sinif, sube, ad, no) in enumerate(isimler):
        ss = _sinif_al(sinif, sube)
        etut = hoca if i % 2 == 0 else (kemal or hoca)
        t = Talebe.objects.filter(ad_soyad=ad).first()
        if t is None:
            t = Talebe(
                ad_soyad=ad,
                sinif=sinif,
                sube=sube,
                sinif_sube=ss,
                talebe_no=no,
                etut_hocasi=etut,
                dini_ders_hocasi=etut,
                aktif=True,
            )
            t.save()
        else:
            dirty = False
            if not t.sinif_sube_id:
                t.sinif_sube = ss
                dirty = True
            if not t.talebe_no:
                t.talebe_no = no
                dirty = True
            if not t.etut_hocasi_id and etut:
                t.etut_hocasi = etut
                t.dini_ders_hocasi = etut
                dirty = True
            if not t.aktif:
                t.aktif = True
                dirty = True
            if dirty:
                t.save()
        sonuc.append(t)
    return sonuc


def seed_kitap_okuma() -> None:
    from takip.models import EtutHocasi, Kitap, OkumaKaydi, Talebe, Zimmet

    admin = User.objects.filter(username="admin").first()
    hoca = _hoca_yahya() or EtutHocasi.objects.filter(aktif=True).first()
    if not hoca:
        return

    kitaplar = [
        ("80 Günde Devriâlem", "Jules Verne", 240, "7. Sınıf"),
        ("Küçük Prens", "Antoine de Saint-Exupéry", 96, "5. Sınıf"),
        ("Simyacı", "Paulo Coelho", 184, "8. Sınıf"),
        ("Fareler ve İnsanlar", "John Steinbeck", 128, "8. Sınıf"),
        ("Şeker Portakalı", "José Mauro de Vasconcelos", 182, "6. Sınıf"),
        ("Çocuk Kalbi", "Edmondo De Amicis", 220, "5. Sınıf"),
    ]
    kitap_objs = []
    for ad, yazar, sayfa, seviye in kitaplar:
        k, _ = Kitap.objects.get_or_create(
            ad=ad,
            yazar=yazar,
            defaults={
                "toplam_sayfa": sayfa,
                "sinif_seviyesi": seviye,
                "olusturan": admin,
                "son_duzenleyen": admin,
            },
        )
        kitap_objs.append(k)

    bugun = timezone.localdate()
    talebeler = list(Talebe.objects.filter(aktif=True).order_by("ad_soyad")[:40])
    for i, talebe in enumerate(talebeler):
        etut = talebe.etut_hocasi or hoca
        if not etut:
            continue
        if talebe.etut_hocasi_id != etut.id:
            talebe.etut_hocasi = etut
            talebe.save(update_fields=["etut_hocasi"])
        kitap = kitap_objs[i % len(kitap_objs)]
        z = Zimmet.objects.filter(talebe=talebe, kitap=kitap, etut_hocasi=etut).first()
        if z is None:
            z = Zimmet(
                talebe=talebe,
                kitap=kitap,
                etut_hocasi=etut,
                olusturan=admin,
                son_duzenleyen=admin,
            )
            z.save()
        if not z.okuma_kayitlari.exists():
            for gun in range(5):
                OkumaKaydi.objects.get_or_create(
                    zimmet=z,
                    tarih=bugun - timedelta(days=gun * 2),
                    defaults={
                        "son_sayfa": min(kitap.toplam_sayfa, 20 + i * 3 + gun * 12),
                        "olusturan": admin,
                        "son_duzenleyen": admin,
                    },
                )


def seed_vazifeler() -> None:
    from takip.models import PersonelProfili
    from takip.vazife_models import PersonelVazife

    admin = User.objects.filter(username="admin").first()
    personeller = list(PersonelProfili.objects.filter(aktif=True).order_by("id")[:8])
    if not personeller:
        return
    bugun = timezone.localdate()
    ss = _sinif_al("7", "A")
    ornekler = [
        ("Haftalık okuma kontrolü", PersonelVazife.Durum.DEVAM, PersonelVazife.Oncelik.YUKSEK, 0, 5),
        ("7A veli bilgilendirme araması", PersonelVazife.Durum.ATANDI, PersonelVazife.Oncelik.NORMAL, 0, 3),
        ("Temizlik denetimi raporu", PersonelVazife.Durum.ONAYLANDI, PersonelVazife.Oncelik.NORMAL, -2, 2),
        ("Namaz yoklama özeti", PersonelVazife.Durum.TAMAMLANDI, PersonelVazife.Oncelik.DUSUK, -7, -1),
        ("KTT sonuç analizi", PersonelVazife.Durum.DEVAM, PersonelVazife.Oncelik.ACIL, 0, 1),
        ("Etüt planı haftalık güncelleme", PersonelVazife.Durum.ATANDI, PersonelVazife.Oncelik.YUKSEK, 0, 7),
        ("Disiplin kurul dosyası hazırlığı", PersonelVazife.Durum.DEVAM, PersonelVazife.Oncelik.YUKSEK, -1, 4),
        ("Yemekçilik haftalık kontrol", PersonelVazife.Durum.ATANDI, PersonelVazife.Oncelik.NORMAL, 0, 6),
        ("Dini ders konu işleme takibi", PersonelVazife.Durum.ONAYLANDI, PersonelVazife.Oncelik.NORMAL, 0, 10),
        ("Sohbet mevzuu veliye duyuru", PersonelVazife.Durum.TAMAMLANDI, PersonelVazife.Oncelik.DUSUK, -10, -3),
        ("Finans tahsilat hatırlatması", PersonelVazife.Durum.ATANDI, PersonelVazife.Oncelik.ACIL, 0, 2),
        ("Program PDF kontrolü", PersonelVazife.Durum.DEVAM, PersonelVazife.Oncelik.NORMAL, 0, 4),
    ]
    for i, (baslik, durum, oncelik, bas_offset, bit_offset) in enumerate(ornekler):
        atanan = personeller[i % len(personeller)]
        PersonelVazife.objects.update_or_create(
            baslik=baslik,
            atanan=atanan,
            defaults={
                "aciklama": f"Demo vazife: {baslik}. Panelde dolu görünmesi için örnek kayıt.",
                "atayan": admin,
                "sinif_sube": ss if i % 3 == 0 else None,
                "baslangic": bugun + timedelta(days=bas_offset),
                "bitis": bugun + timedelta(days=bit_offset),
                "durum": durum,
                "oncelik": oncelik,
                "personel_notu": "Demo personel notu." if durum == PersonelVazife.Durum.DEVAM else "",
            },
        )


def seed_yct() -> None:
    from takip.yct_models import YctOlay

    admin = User.objects.filter(username="admin").first()
    bugun = timezone.localdate()
    ay_basi = bugun.replace(day=1)
    olaylar = [
        ("1. Dönem yazılı kampı", YctOlay.Kategori.YAZILI, 3, 5, "Matematik–Türkçe yazılı hazırlık"),
        ("Kurum geneli KTT", YctOlay.Kategori.KTT, 8, 8, "Haftalık KTT uygulaması"),
        ("LGS deneme sınavı", YctOlay.Kategori.DENEME, 12, 12, "Kurum denemesi"),
        ("Veli toplantısı", YctOlay.Kategori.TOPLANTI, 15, 15, "Sınıf bazlı veli bilgilendirme"),
        ("Ara tatil", YctOlay.Kategori.TATIL, 18, 22, "Resmî ara tatil"),
        ("Kitap okuma etkinliği", YctOlay.Kategori.ETKINLIK, 10, 11, "Haftalık okuma günü"),
        ("Etüt program revizyonu", YctOlay.Kategori.PROGRAM, 6, 7, "Saat blokları güncellemesi"),
        ("İdareci nabız toplantısı", YctOlay.Kategori.TOPLANTI, 2, 2, "Haftalık idareci özeti"),
        ("Yazılı sonuç değerlendirme", YctOlay.Kategori.YAZILI, 25, 26, "Sonuç analizi"),
        ("Personel eğitim semineri", YctOlay.Kategori.GENEL, 14, 14, "Pedagojik seminer"),
        ("Temizlik denetim günü", YctOlay.Kategori.GENEL, 9, 9, ""),
        ("Rehberlik görüşme haftası", YctOlay.Kategori.ETKINLIK, 20, 24, "Yoğun görüşme dönemi"),
    ]
    for baslik, kat, d1, d2, aciklama in olaylar:
        try:
            bas = ay_basi.replace(day=min(d1, 28))
            bit = ay_basi.replace(day=min(d2, 28))
        except ValueError:
            bas = bugun
            bit = bugun
        YctOlay.objects.update_or_create(
            baslik=baslik,
            baslangic=bas,
            defaults={
                "bitis": bit if bit != bas else None,
                "kategori": kat,
                "aciklama": aciklama,
                "tum_personel": True,
                "olusturan": admin,
            },
        )


def seed_sohbet_mevzuu() -> None:
    from takip.sohbet_mevzuu_models import HaftalikSohbetMevzuu

    admin = User.objects.filter(username="admin").first()
    pazartesi = _pazartesi()
    ornekler = [
        (
            pazartesi,
            "Sorumluluk ve düzen",
            "Bu hafta talebelerimizle sorumluluk bilinci, oda düzeni ve zaman yönetimi üzerine sohbet edilecektir.",
        ),
        (
            pazartesi - timedelta(days=7),
            "Kardeşlik ve yardımlaşma",
            "Yardımlaşma, empati ve sınıf içi kardeşlik konularına değinilecektir.",
        ),
        (
            pazartesi - timedelta(days=14),
            "Namaz ve devam",
            "Namazda huşu, vakit bilinci ve devamın önemi konuşulacaktır.",
        ),
        (
            pazartesi - timedelta(days=21),
            "Çalışma disiplini",
            "Etüt verimi, soru çözümü ve hedef koyma üzerine sohbet.",
        ),
    ]
    for hafta, baslik, icerik in ornekler:
        HaftalikSohbetMevzuu.objects.update_or_create(
            baslik=baslik,
            hafta_baslangic=hafta,
            defaults={"icerik": icerik, "aktif": True, "olusturan": admin},
        )


def seed_bildirimler() -> None:
    from takip.bildirim_models import Bildirim

    admin = User.objects.filter(username="admin").first()
    alicilar = list(
        User.objects.filter(username__in=["admin", "yahya", "kemal", "veli"]).order_by("id")
    )
    if not alicilar:
        return
    bugun = timezone.localdate()
    ornekler = [
        ("Yeni vazife atandı", "Haftalık okuma kontrolü size atandı.", Bildirim.Tur.VAZIFE, False, 5),
        ("Duyuru: Program güncellendi", "Günlük kurum programında değişiklik var.", Bildirim.Tur.DUYURU, False, 7),
        ("Sistem: Panel yenilendi", "Yeni metrikler ve kısayollar eklendi.", Bildirim.Tur.SISTEM, True, None),
        ("Etüt planı hatırlatması", "Bu haftanın faaliyetlerini tamamlayın.", Bildirim.Tur.PROGRAM, False, 3),
        ("Veli toplantısı", "15'inde veli toplantısı planlandı.", Bildirim.Tur.GENEL, False, 10),
        ("KTT sonuçları hazır", "Son KTT sonuçları panellerde görünür.", Bildirim.Tur.GENEL, False, 4),
        ("Acil vazife", "Finans tahsilat hatırlatması süresi yaklaşıyor.", Bildirim.Tur.VAZIFE, False, 2),
        ("Okuma raporu", "Talebe okuma ilerlemeleri güncellendi.", Bildirim.Tur.GENEL, True, None),
    ]
    for i, (baslik, mesaj, tur, okundu, bit_gun) in enumerate(ornekler):
        for alici in alicilar:
            Bildirim.objects.update_or_create(
                alici=alici,
                baslik=baslik,
                defaults={
                    "mesaj": mesaj,
                    "tur": tur,
                    "okundu": okundu if alici.username != "yahya" else False,
                    "bitis": (bugun + timedelta(days=bit_gun)) if bit_gun else None,
                    "olusturan": admin,
                    "link": "/panel/" if i % 2 == 0 else "",
                },
            )


def seed_soru_takip() -> None:
    from takip.models import Ders, Talebe
    from takip.soru_takip_models import GunlukSoruDersSatiri, GunlukSoruKaydi
    from takip.soru_takip_service import seed_soru_takip_dersleri

    seed_soru_takip_dersleri()
    user = User.objects.filter(username="yahya").first() or User.objects.filter(is_staff=True).first()
    dersler = list(Ders.objects.filter(aktif=True).order_by("ad")[:5])
    if not dersler:
        return
    talebeler = list(Talebe.objects.filter(aktif=True).order_by("ad_soyad")[:20])
    bugun = timezone.localdate()
    for ti, talebe in enumerate(talebeler):
        for gun in range(7):
            tarih = bugun - timedelta(days=gun)
            kayit, _ = GunlukSoruKaydi.objects.get_or_create(
                talebe=talebe,
                tarih=tarih,
                defaults={
                    "kitap_okunan_sayfa": 8 + (ti + gun) % 15,
                    "gunluk_not": "Demo günlük not" if gun % 3 == 0 else "",
                    "kaydeden": user,
                },
            )
            for di, ders in enumerate(dersler[:3]):
                toplam = 20 + (ti + di) % 10
                dogru = 12 + (ti + gun + di) % 8
                yanlis = min(4, toplam - dogru)
                bos = max(0, toplam - dogru - yanlis)
                GunlukSoruDersSatiri.objects.update_or_create(
                    kayit=kayit,
                    ders=ders,
                    defaults={
                        "toplam_soru": toplam,
                        "dogru": dogru,
                        "yanlis": yanlis,
                        "bos": bos,
                    },
                )


def seed_akademik_mudahale_genis() -> None:
    from takip.akademik_mudahale_models import AkademikMudahale, MudahaleTuru
    from takip.akademik_mudahale_service import seed_mudahale_turleri
    from takip.models import Ders, Talebe

    seed_mudahale_turleri()
    turler = list(MudahaleTuru.objects.filter(aktif=True))
    dersler = list(Ders.objects.filter(aktif=True)[:6])
    if not turler or not dersler:
        return
    admin = User.objects.filter(username="yahya").first()
    bugun = timezone.localdate()
    konular = [
        "Paragraf",
        "Tam sayılar",
        "Fiilimsiler",
        "Denklemler",
        "Üslü sayılar",
        "Okuma stratejisi",
        "Problem çözme",
        "Geometri temelleri",
    ]
    for i, talebe in enumerate(Talebe.objects.filter(aktif=True).order_by("id")[:25]):
        for j in range(2):
            AkademikMudahale.objects.get_or_create(
                talebe=talebe,
                mudahale_turu=turler[(i + j) % len(turler)],
                tarih=bugun - timedelta(days=(i + j * 3) % 20),
                defaults={
                    "ders": dersler[(i + j) % len(dersler)],
                    "konu": konular[(i + j) % len(konular)],
                    "sure_dakika": 30 + (i % 4) * 10,
                    "olusturan": admin,
                    "degerlendirme_notu": "Demo müdahale kaydı — takip devam ediyor.",
                    "veliye_goster": True,
                },
            )


def seed_disiplin_kayitlari() -> None:
    from takip.disiplin_models import DisiplinKaydi, DisiplinOlayTuru
    from takip.disiplin_service import seed_disiplin_turleri
    from takip.models import Talebe

    seed_disiplin_turleri()
    turler = list(DisiplinOlayTuru.objects.filter(aktif=True))
    if not turler:
        return
    bugun = timezone.localdate()
    for i, talebe in enumerate(Talebe.objects.filter(aktif=True).order_by("id")[:12]):
        DisiplinKaydi.objects.get_or_create(
            talebe=talebe,
            tur=turler[i % len(turler)],
            tarih=bugun - timedelta(days=i * 2),
            defaults={
                "aciklama": f"Demo disiplin kaydı — {turler[i % len(turler)].ad}",
                "sonuc": "Uyarı verildi" if i % 2 == 0 else "Görüşme yapıldı",
            },
        )


def seed_finans_dosyalari() -> None:
    from takip.finans_models import FinansTahsilat, FinansTaksit, TalebeFinansDosyasi
    from takip.finans_service import aktif_egitim_yili, finans_seed_verisi
    from takip.models import Talebe

    finans_seed_verisi()
    yil = aktif_egitim_yili()
    if not yil:
        return
    admin = User.objects.filter(username="admin").first()
    bugun = timezone.localdate()
    for i, talebe in enumerate(Talebe.objects.filter(aktif=True).order_by("id")[:18]):
        toplam = Decimal("92000") if (talebe.sinif or "7") != "8" else Decimal("112000")
        indirim = Decimal("5000") if i % 3 == 0 else Decimal("0")
        net = toplam - indirim
        pesinat = Decimal("10000")
        odenen = pesinat + (Decimal("8000") if i % 2 == 0 else Decimal("0"))
        dosya, created = TalebeFinansDosyasi.objects.get_or_create(
            talebe=talebe,
            egitim_yili=yil,
            defaults={
                "toplam_ucret": toplam,
                "indirim_tutari": indirim,
                "net_ucret": net,
                "pesinat": pesinat,
                "odenen_tutar": odenen,
                "taksit_sayisi": 10,
                "durum": TalebeFinansDosyasi.Durum.DEVAM,
                "not_alani": "Demo finans dosyası",
                "olusturan": admin,
            },
        )
        if not created:
            continue
        kalan = net - pesinat
        taksit_tutar = (kalan / Decimal("10")).quantize(Decimal("0.01"))
        for sira in range(1, 11):
            durum = FinansTaksit.Durum.BEKLIYOR
            odenen_t = Decimal("0")
            if sira == 1 and i % 2 == 0:
                durum = FinansTaksit.Durum.ODENDI
                odenen_t = taksit_tutar
            FinansTaksit.objects.create(
                dosya=dosya,
                sira=sira,
                tutar=taksit_tutar,
                vade=bugun + timedelta(days=30 * sira),
                odenen_tutar=odenen_t,
                durum=durum,
            )
        FinansTahsilat.objects.create(
            dosya=dosya,
            tutar=pesinat,
            tarih=bugun - timedelta(days=20),
            yontem="nakit",
            tur="pesinat",
            aciklama="Demo peşinat",
            kaydeden=admin,
        )


def seed_dershane_program() -> None:
    from takip.dershane_program_models import (
        DershaneDersAtamasi,
        DershaneEtutGrubu,
        DershaneProgramGun,
        DershaneProgrami,
        DershaneSaatBloku,
    )
    from takip.models import Ders, EtutHocasi

    admin = User.objects.filter(username="admin").first()
    bugun = timezone.localdate()
    program, _ = DershaneProgrami.objects.update_or_create(
        ad="2025-2026 Dershane Haftalık Program",
        defaults={
            "aciklama": "Demo dolu dershane programı",
            "baslangic_tarihi": bugun - timedelta(days=30),
            "bitis_tarihi": bugun + timedelta(days=180),
            "aktif": True,
            "olusturan": admin,
        },
    )
    for gun in range(5):
        DershaneProgramGun.objects.update_or_create(
            program=program,
            gun=gun,
            defaults={"durum": DershaneProgramGun.Durum.TAMAMLANDI},
        )

    hocalar = list(EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad")[:4])
    gruplar = []
    for i, (etiket, seviye) in enumerate(
        [("5A Etüt", "5"), ("6A Etüt", "6"), ("7A Etüt", "7"), ("8A Etüt", "8")]
    ):
        g, _ = DershaneEtutGrubu.objects.update_or_create(
            program=program,
            etiket=etiket,
            defaults={
                "sinif_seviye": seviye,
                "etut_hocasi": hocalar[i % len(hocalar)] if hocalar else None,
                "sira": i,
            },
        )
        gruplar.append(g)

    blok_sablon = [
        (time(8, 0), time(8, 40), DershaneSaatBloku.Tur.DERS, "1. Ders"),
        (time(8, 50), time(9, 30), DershaneSaatBloku.Tur.DERS, "2. Ders"),
        (time(9, 40), time(10, 20), DershaneSaatBloku.Tur.DERS, "3. Ders"),
        (time(10, 30), time(11, 10), DershaneSaatBloku.Tur.ETUT, "Etüt"),
        (time(12, 0), time(12, 40), DershaneSaatBloku.Tur.YEMEK, "Öğle"),
        (time(13, 0), time(13, 40), DershaneSaatBloku.Tur.DERS, "4. Ders"),
        (time(13, 50), time(14, 30), DershaneSaatBloku.Tur.REHBERLIK, "Rehberlik"),
    ]
    dersler = list(Ders.objects.filter(aktif=True).order_by("ad")[:6]) or [None]
    ders_cycle = cycle(dersler)
    for gun in range(5):
        for sira, (bas, bit, tur, aciklama) in enumerate(blok_sablon):
            blok, _ = DershaneSaatBloku.objects.update_or_create(
                program=program,
                gun=gun,
                baslangic_saati=bas,
                defaults={
                    "bitis_saati": bit,
                    "tur": tur,
                    "aciklama": aciklama,
                    "sira": sira,
                },
            )
            if not blok.ders_atamasi_gerektirir:
                continue
            for grup in gruplar:
                ders = next(ders_cycle)
                DershaneDersAtamasi.objects.update_or_create(
                    program=program,
                    saat_bloku=blok,
                    etut_grubu=grup,
                    defaults={
                        "ders": ders,
                        "ders_adi": ders.ad if ders else aciklama,
                        "ogretmen_adi": (grup.etut_hocasi.ad_soyad if grup.etut_hocasi_id else "Öğretmen"),
                    },
                )


def seed_etut_plan() -> None:
    from takip.etut_plan_models import (
        EtutFaaliyetHavuzu,
        EtutGrupSaatBloku,
        EtutHaftaPlani,
        EtutPlanFaaliyet,
    )
    from takip.etut_plan_service import seed_havuz_kartlari
    from takip.models import EtutHocasi

    seed_havuz_kartlari()
    hoca = _hoca_yahya() or EtutHocasi.objects.filter(aktif=True).first()
    if not hoca:
        return
    user = hoca.user or User.objects.filter(username="yahya").first()
    saatler = [
        (time(14, 0), time(14, 40)),
        (time(14, 50), time(15, 30)),
        (time(15, 40), time(16, 20)),
        (time(16, 30), time(17, 10)),
    ]
    for gun in range(6):
        for sira, (bas, bit) in enumerate(saatler):
            EtutGrupSaatBloku.objects.update_or_create(
                etut_hocasi=hoca,
                gun=gun,
                baslangic_saati=bas,
                defaults={
                    "bitis_saati": bit,
                    "sira": sira,
                    "durum": EtutGrupSaatBloku.Durum.AKTIF,
                    "aktif": True,
                },
            )

    pazartesi = _pazartesi()
    plan, _ = EtutHaftaPlani.objects.update_or_create(
        etut_hocasi=hoca,
        hafta_baslangic=pazartesi,
        defaults={
            "hafta_bitis": pazartesi + timedelta(days=6),
            "durum": EtutHaftaPlani.Durum.AKTIF,
            "notlar": "Demo haftalık etüt planı — dolu görünüm",
            "olusturan": user,
        },
    )
    havuz = list(EtutFaaliyetHavuzu.objects.filter(aktif=True, ozel=False)[:8])
    turler = list(EtutPlanFaaliyet.FaaliyetTuru.values)
    durumlar = list(EtutPlanFaaliyet.UygulamaDurumu.values)
    bloklar = {
        (b.gun, b.baslangic_saati): b
        for b in EtutGrupSaatBloku.objects.filter(etut_hocasi=hoca, aktif=True)
    }
    idx = 0
    for gun in range(6):
        for sira, (bas, _bit) in enumerate(saatler):
            blok = bloklar.get((gun, bas))
            if not blok:
                continue
            kart = havuz[idx % len(havuz)] if havuz else None
            baslik = kart.baslik if kart else f"Çalışma {gun + 1}-{sira + 1}"
            EtutPlanFaaliyet.objects.update_or_create(
                plan=plan,
                saat_bloku=blok,
                defaults={
                    "gun": gun,
                    "baslik": baslik,
                    "havuz": kart,
                    "faaliyet_turu": turler[idx % len(turler)],
                    "hedef": (kart.varsayilan_hedef if kart else "") or "20 soru",
                    "uygulama_durumu": durumlar[idx % len(durumlar)],
                    "renk": (kart.renk if kart else "#eff6ff"),
                    "sira": sira,
                },
            )
            idx += 1


def seed_ogretmen_notlari() -> None:
    from takip.models import Ders, Talebe
    from takip.ogretmen_not_models import (
        OgretmenHaftalikKonu,
        OgretmenSinavNotu,
        OgretmenSinifYoklama,
    )

    hoca = _hoca_kemal() or _hoca_yahya()
    if not hoca:
        return
    ders = Ders.objects.filter(aktif=True).order_by("ad").first()
    if not ders:
        return
    pazartesi = _pazartesi()
    talebeler = list(
        Talebe.objects.filter(aktif=True, etut_hocasi=hoca).select_related("sinif_sube")[:20]
    )
    if not talebeler:
        talebeler = list(Talebe.objects.filter(aktif=True).select_related("sinif_sube")[:15])
    for i, talebe in enumerate(talebeler):
        OgretmenSinavNotu.objects.update_or_create(
            talebe=talebe,
            etut_hocasi=hoca,
            ders=ders,
            hafta_baslangic=pazartesi,
            defaults={
                "katilim": Decimal(70 + (i * 3) % 30),
                "takip": Decimal(65 + (i * 5) % 35),
                "disiplin": Decimal(75 + (i * 2) % 25),
                "aciklama": "Demo haftalık değerlendirme",
                "veliye_goster": True,
            },
        )
        if talebe.sinif_sube_id:
            OgretmenHaftalikKonu.objects.update_or_create(
                sinif_sube=talebe.sinif_sube,
                etut_hocasi=hoca,
                ders=ders,
                hafta_baslangic=pazartesi,
                defaults={"konu": "Rasyonel sayılar · problem çözme"},
            )
        # Her talebe için haftanın 1 günü yok işaretle (demo)
        OgretmenSinifYoklama.objects.update_or_create(
            talebe=talebe,
            etut_hocasi=hoca,
            tarih=pazartesi + timedelta(days=i % 5),
            defaults={"yok": True},
        )


def seed_deneme() -> None:
    from takip.deneme_models import DenemeSinavi, DenemeSonucu
    from takip.models import Talebe

    admin = User.objects.filter(username="admin").first()
    bugun = timezone.localdate()
    for seviye, ad_ek in [("7", "7. Sınıf Kurum Denemesi"), ("8", "8. Sınıf LGS Denemesi")]:
        deneme, _ = DenemeSinavi.objects.update_or_create(
            ad=ad_ek,
            sinav_tarihi=bugun - timedelta(days=10 if seviye == "7" else 5),
            defaults={
                "sinif_seviyesi": seviye,
                "aciklama": "Demo deneme sınavı sonuçları",
                "durum": DenemeSinavi.Durum.AKTIF,
                "olusturan": admin,
                "yukleyen": admin,
                "yuklenme_zamani": timezone.now(),
            },
        )
        talebeler = Talebe.objects.filter(aktif=True, sinif=seviye).order_by("ad_soyad")[:15]
        if not talebeler.exists():
            talebeler = Talebe.objects.filter(aktif=True).order_by("ad_soyad")[:12]
        for i, talebe in enumerate(talebeler):
            dogru = 60 + (i * 3) % 30
            yanlis = 10 + i % 8
            bos = max(0, 120 - dogru - yanlis)
            net = Decimal(dogru) - (Decimal(yanlis) / Decimal("4"))
            DenemeSonucu.objects.update_or_create(
                deneme=deneme,
                talebe=talebe,
                defaults={
                    "toplam_dogru": dogru,
                    "toplam_yanlis": yanlis,
                    "toplam_bos": bos,
                    "toplam_net": net.quantize(Decimal("0.01")),
                    "puan": (net * Decimal("5")).quantize(Decimal("0.01")),
                },
            )


def seed_yazili_genis() -> None:
    from takip.models import Talebe
    from takip.yazili_takip_models import YaziliKamp, YaziliSinav, YaziliSonuc
    from takip.yazili_takip_service import seed_yazili_takip_demo

    seed_yazili_takip_demo()
    kamp = YaziliKamp.objects.order_by("-id").first()
    if not kamp:
        return
    user = User.objects.filter(username="admin").first()
    sinav, _ = YaziliSinav.objects.update_or_create(
        kamp=kamp,
        ad="1. Yazılı — Matematik",
        defaults={
            "sinav_tarihi": timezone.localdate() - timedelta(days=3),
            "ders_ad": "Matematik",
            "brans": "Matematik",
            "yazili_no": 1,
            "tur": YaziliSinav.Tur.GERCEK,
            "soru_sayisi": 20,
            "durum": YaziliSinav.Durum.AKTIF,
            "olusturan": user,
        },
    )
    for i, talebe in enumerate(Talebe.objects.filter(aktif=True).order_by("id")[:30]):
        dogru = 10 + (i * 2) % 10
        yanlis = min(4, 20 - dogru)
        bos = 20 - dogru - yanlis
        YaziliSonuc.objects.update_or_create(
            sinav=sinav,
            talebe=talebe,
            defaults={
                "dogru": dogru,
                "yanlis": yanlis,
                "bos": bos,
                "kaydeden": user,
            },
        )


def seed_yemekci_sinif() -> None:
    from takip.yemekci_service import havuzlari_kur

    havuzlari_kur(seed_talebeler=True)


def seed_program_zenginlestir() -> None:
    from takip.models import ProgramPlan, ProgramSatir

    program = ProgramPlan.objects.filter(aktif=True).order_by("-id").first()
    if not program:
        return
    ekstra = [
        (8, time(16, 0), time(17, 0), ProgramSatir.FaaliyetTuru.ETUT, "Akşam etüt"),
        (9, time(17, 15), time(18, 0), ProgramSatir.FaaliyetTuru.NAMAZ, "İkindi / akşam arası"),
        (10, time(18, 0), time(19, 0), ProgramSatir.FaaliyetTuru.YEMEK, "Akşam yemeği"),
        (11, time(19, 30), time(20, 30), ProgramSatir.FaaliyetTuru.DERS, "Serbest çalışma"),
        (12, time(21, 0), time(22, 30), getattr(ProgramSatir.FaaliyetTuru, "UYKU", ProgramSatir.FaaliyetTuru.DINLENME), "Uyku"),
    ]
    mevcut = set(program.satirlar.values_list("faaliyet_adi", flat=True))
    for sira, bas, bit, tur, ad in ekstra:
        if ad in mevcut:
            continue
        ProgramSatir.objects.create(
            program=program,
            sira=sira,
            baslangic_saati=bas,
            bitis_saati=bit,
            faaliyet_turu=tur,
            faaliyet_adi=ad,
            faaliyet_durumu=ProgramSatir.FaaliyetDurumu.ETKIN,
        )


def seed_duyuru_zenginlestir() -> None:
    from takip.models import Duyuru

    admin = User.objects.filter(username="admin").first()
    ekstra = [
        ("Finans ödeme hatırlatması", "Aidat taksitlerini panellerden takip edebilirsiniz.", Duyuru.Kategori.GENEL, Duyuru.Ton.TEAL, Duyuru.HedefKitle.TUM_PERSONEL),
        ("Veli paneli aktif", "Sohbet mevzuu, notlar ve yoklama bilgileri velilerde görünür.", Duyuru.Kategori.KURUM, Duyuru.Ton.NAVY, Duyuru.HedefKitle.VELI),
        ("Disiplin kurulu süreci", "Kurul dosyaları idareci panelinden takip edilir.", Duyuru.Kategori.GENEL, Duyuru.Ton.VIOLET, Duyuru.HedefKitle.TUM_PERSONEL),
        ("Yemekçilik döngüsü", "Sınıf havuzları otomatik güncelleme ile çalışıyor.", Duyuru.Kategori.PROGRAM, Duyuru.Ton.TEAL, Duyuru.HedefKitle.TUM_PERSONEL),
    ]
    for sira, (baslik, ozet, kat, ton, hedef) in enumerate(ekstra, start=10):
        Duyuru.objects.update_or_create(
            baslik=baslik,
            defaults={
                "ozet": ozet,
                "kategori": kat,
                "ton": ton,
                "sira": sira,
                "hedef_kitle": hedef,
                "baslangic": timezone.localdate(),
                "aktif": True,
                "olusturan": admin,
            },
        )


def seed_dini_ders_genis() -> None:
    from takip.dini_ders_takip_models import DiniDersKonu, DiniDersKonuKaydi
    from takip.dini_ders_takip_service import seed_dini_ders_ornek_atamalar
    from takip.models import Talebe
    from takip.wave0_models import DiniDersSeviyesi

    seed_dini_ders_ornek_atamalar()
    admin = User.objects.filter(username="admin").first()
    seviyeler = list(DiniDersSeviyesi.objects.filter(aktif=True))
    if not seviyeler:
        return
    talebeler = list(Talebe.objects.filter(aktif=True).order_by("id")[:20])
    for i, talebe in enumerate(talebeler):
        seviye = seviyeler[i % len(seviyeler)]
        if talebe.dini_ders_seviyesi_id != seviye.id:
            talebe.dini_ders_seviyesi = seviye
            if not talebe.dini_ders_hocasi_id and talebe.etut_hocasi_id:
                talebe.dini_ders_hocasi = talebe.etut_hocasi
            try:
                talebe.save(update_fields=["dini_ders_seviyesi", "dini_ders_hocasi"])
            except Exception:
                pass
        konular = list(
            DiniDersKonu.objects.filter(seviye=seviye, aktif=True).order_by("sira")[:8]
        )
        for j, konu in enumerate(konular):
            DiniDersKonuKaydi.objects.update_or_create(
                talebe=talebe,
                konu=konu,
                defaults={
                    "tamamlandi": True,
                    "personel_notu": "Demo işlendi" if j % 2 == 0 else "",
                    "isaretleyen": admin,
                },
            )


def seed_namaz_genis() -> None:
    from takip.namaz_yoklama_models import NamazDurumu, NamazVakti
    from takip.namaz_yoklama_service import seed_namaz_demo, yoklama_kaydet
    from takip.models import EtutHocasi, Talebe

    seed_namaz_demo()
    hoca = EtutHocasi.objects.filter(ad_soyad__icontains="Yahya").first()
    if not hoca or not hoca.user_id:
        return
    talebeler = list(Talebe.objects.filter(aktif=True, etut_hocasi=hoca)[:25])
    if len(talebeler) < 3:
        talebeler = list(Talebe.objects.filter(aktif=True)[:25])
    if not talebeler:
        return
    bugun = timezone.localdate()
    for gun_offset, vakit in [
        (0, NamazVakti.SABAH),
        (0, NamazVakti.OGLE),
        (1, NamazVakti.SABAH),
        (1, NamazVakti.IKINDI),
        (2, NamazVakti.SABAH),
        (3, NamazVakti.AKSAM),
    ]:
        # Yalnızca sorunlu / izinli kayıtlar tutulur
        durumlar = {}
        for i, t in enumerate(talebeler):
            if i % 11 == 0:
                durumlar[t.id] = NamazDurumu.GELMEDI
            elif i % 9 == 0:
                durumlar[t.id] = NamazDurumu.IZINLI
            elif i % 7 == 0:
                durumlar[t.id] = NamazDurumu.TAKKE_TESBIH
        try:
            yoklama_kaydet(
                hoca.user,
                bugun - timedelta(days=gun_offset),
                vakit,
                durumlar,
                [t.id for t in talebeler],
            )
        except Exception:
            pass


def seed_rehberlik_guvence() -> None:
    from takip.rehberlik_service import seed_gorusme_turleri, seed_rehberlik_demo

    seed_gorusme_turleri()
    seed_rehberlik_demo()


def seed_disiplin_kurul_ve_lazy() -> None:
    from takip.disiplin_kurul_service import seed_demo_kurul, seed_kurul_sablonlari
    from takip.etut_plan_service import seed_havuz_kartlari

    seed_havuz_kartlari()
    seed_kurul_sablonlari()
    admin = User.objects.filter(username="admin").first()
    if admin:
        seed_demo_kurul(admin)


@transaction.atomic
def seed_tum_paneller() -> dict:
    """Tüm zengin demo adımlarını çalıştırır."""
    seed_genis_talebe_havuzu()
    seed_kitap_okuma()
    seed_program_zenginlestir()
    seed_duyuru_zenginlestir()
    seed_disiplin_kurul_ve_lazy()
    seed_rehberlik_guvence()
    seed_namaz_genis()
    seed_dini_ders_genis()
    seed_vazifeler()
    seed_yct()
    seed_sohbet_mevzuu()
    seed_bildirimler()
    seed_soru_takip()
    seed_akademik_mudahale_genis()
    seed_disiplin_kayitlari()
    seed_finans_dosyalari()
    seed_dershane_program()
    seed_etut_plan()
    seed_ogretmen_notlari()
    seed_deneme()
    seed_yazili_genis()
    seed_yemekci_sinif()
    return {"ok": True}
