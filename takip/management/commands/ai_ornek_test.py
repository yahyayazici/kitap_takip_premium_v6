"""Temsilî analiz ve sohbet örneklerini gerçek veritabanı verisiyle çalıştırır.

Kullanım (ANTHROPIC_API_KEY tanımlıyken gerçek Claude çağrısı yapar, ücretlidir):
    python manage.py ai_ornek_test --kullanici admin
    python manage.py ai_ornek_test --kullanici admin --sadece sohbet

Anahtar yoksa aynı örnekler kural tabanlı modda çalışır; böylece iki modun çıktısı
aynı veri üzerinde karşılaştırılabilir. Analizler önbelleği atlar (yenile=True).
"""

from __future__ import annotations

import time

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from takip.claude_client import claude_yapilandirildi_mi, gorev_modeli

SOHBET_ORNEKLERI = [
    ("Selamlaşma", ["Merhaba, kolay gelsin"]),
    ("Sayısal veri", ["Kaç aktif talebemiz var, sınıflara göre dağılım nasıl?"]),
    ("Bağlamlı rapor isteği", ["Okuma raporu lazım", "sadece {sinif} sınıfının"]),
    ("Talebe değerlendirmesi", ["{talebe} son durumu nasıl, ne önerirsin?"]),
    ("Yapılamayan işlem", ["{talebe} velisine devamsızlık için SMS gönder"]),
    ("Panelde olmayan veri", ["Geçen yılın mezun sayısı kaçtı?"]),
]


class Command(BaseCommand):
    help = "Yapay zeka analiz ve asistan örneklerini çalıştırır (karşılaştırma/duman testi)."

    def add_arguments(self, parser):
        parser.add_argument("--kullanici", default="admin", help="Yetkileri kullanılacak kullanıcı adı")
        parser.add_argument("--sadece", choices=["analiz", "sohbet"], default=None)

    def handle(self, *args, **opts):
        user = User.objects.filter(username=opts["kullanici"]).first()
        if not user:
            raise CommandError(f"Kullanıcı bulunamadı: {opts['kullanici']}")
        mod = (
            f"CLAUDE (analiz: {gorev_modeli('analiz')}, sohbet: {gorev_modeli('sohbet')})"
            if claude_yapilandirildi_mi()
            else "KURAL TABANLI (ANTHROPIC_API_KEY tanımlı değil)"
        )
        self.stdout.write(self.style.MIGRATE_HEADING(f"Mod: {mod}"))
        if opts["sadece"] != "sohbet":
            self._analizler(user)
        if opts["sadece"] != "analiz":
            self._sohbetler(user)

    def _yaz_analiz(self, baslik, fonksiyon):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== ANALİZ: {baslik} ==="))
        bas = time.monotonic()
        try:
            sonuc = fonksiyon()
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"Hata: {type(exc).__name__}: {exc}"))
            return
        sure = time.monotonic() - bas
        self.stdout.write(f"yapay_zeka={sonuc.yapay_zeka} süre={sure:.1f}s")
        if sonuc.uyari:
            self.stdout.write(self.style.WARNING(f"UYARI: {sonuc.uyari}"))
        for bolum in sonuc.bolumler:
            self.stdout.write(f"\n[{bolum.baslik}]\n{bolum.icerik}")

    def _analizler(self, user):
        from takip.ai_service import gelisim_zekasi_analizi, kurum_zekasi_ozet, soru_takip_insight
        from takip.ktt_analiz_service import ktt_rapor_analizi
        from takip.ktt_service import ktt_rapor_istatistik, yetkili_ktt_sonuclari
        from takip.permissions.scope import yetkili_talebeler

        self._yaz_analiz("Kurum Zekası", lambda: kurum_zekasi_ozet(user, yenile=True))
        talebe = yetkili_talebeler(user).order_by("id").first()
        if talebe:
            self._yaz_analiz(
                f"Gelişim Zekası — {talebe.ad_soyad}",
                lambda: gelisim_zekasi_analizi(user, talebe, yenile=True),
            )
            self._yaz_analiz(
                f"Soru Takip — {talebe.ad_soyad}",
                lambda: soru_takip_insight(user, talebe, yenile=True),
            )
        self._yaz_analiz("Soru Takip — kurum", lambda: soru_takip_insight(user, None, yenile=True))
        ktt = list(yetkili_ktt_sonuclari(user).order_by("-ktt__sinav_tarihi")[:200])
        if ktt:
            self._yaz_analiz(
                "KTT kohort raporu (son 200 kayıt)",
                lambda: ktt_rapor_analizi(ktt, ktt_rapor_istatistik(ktt), {}, {}),
            )
        else:
            self.stdout.write("\n(KTT sonucu yok — KTT analizi atlandı)")

    def _sohbetler(self, user):
        from takip.asistan_service import mesaj_isle
        from takip.permissions.scope import yetkili_talebeler
        from takip.talebe_liste_raporu_service import erisilebilir_siniflar, sinif_etiketi_goster

        talebeler = yetkili_talebeler(user)
        talebe = talebeler.order_by("id").first()
        siniflar = list(erisilebilir_siniflar(talebeler))
        degerler = {
            "talebe": talebe.ad_soyad if talebe else "Ahmet",
            "sinif": sinif_etiketi_goster(siniflar[0]) if siniflar else "5-A",
        }
        for baslik, mesajlar in SOHBET_ORNEKLERI:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== SOHBET: {baslik} ==="))
            history: list[dict] = []
            for sablon in mesajlar:
                mesaj = sablon.format(**degerler)
                bas = time.monotonic()
                yanit = mesaj_isle(user, mesaj, history)
                sure = time.monotonic() - bas
                self.stdout.write(f"\n> {mesaj}\n({'Claude' if yanit.get('ai') else 'kural'} · {sure:.1f}s)")
                self.stdout.write(yanit.get("reply", ""))
                if yanit.get("uyari"):
                    self.stdout.write(self.style.WARNING(f"UYARI: {yanit['uyari']}"))
                for eylem in yanit.get("actions") or []:
                    self.stdout.write(f"  [buton] {eylem['label']}")
                history += [
                    {"role": "user", "content": mesaj},
                    {"role": "assistant", "content": yanit.get("reply", "")},
                ]
