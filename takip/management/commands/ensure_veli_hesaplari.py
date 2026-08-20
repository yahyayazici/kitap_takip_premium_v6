"""TC kimliği kayıtlı tüm öğrenciler için veli hesabı/bağlantısını tamamlar.

Öğrenciler normalde Excel içe aktarma sırasında `veli_panel_ensure()` ile
otomatik veli hesabına kavuşuyor. Ama bir öğrenci Excel dışı bir yoldan
(örn. tekil ekleme formu) sisteme girdiyse bu adım hiç çalışmamış olabilir
— sonuç: öğrencinin TC'si sistemde var ama veliye bağlı bir hesap yok,
veli panelinde hiçbir veri görünmüyor.

İdempotent: `veli_panel_ensure()` var olan hesaplara asla dokunmaz (şifre
sıfırlamaz), sadece eksik hesap/bağlantıyı tamamlar. Bu yüzden build.sh'te
her deploy'da güvenle tekrar çalıştırılabilir.

Anne/baba adı hiç girilmemişse veli hesabının görünen adı olarak
öğrencinin kendi adı kullanılır (giriş TC ile çalışır, sadece görünen
isim geçicidir) — idareci gerçek veli adını öğrenince panelden
düzeltebilir.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from takip.models import Talebe
from takip.veli_hesap_util import veli_panel_ensure


class Command(BaseCommand):
    help = "TC kimliği olan aktif öğrenciler için eksik veli hesabı/bağlantısını tamamlar."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Hiçbir şey yazmadan yalnızca ne yapılacağını listeler.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        talebeler = Talebe.objects.filter(aktif=True).exclude(tc_kimlik="")

        olusturulan = 0
        zaten_tamam = 0
        isimsiz_yer_tutucu = 0
        atlanan_cakisma = 0

        for talebe in talebeler:
            veli_ad = talebe.anne_adi or talebe.baba_adi or ""
            if not veli_ad:
                isimsiz_yer_tutucu += 1
                veli_ad = talebe.ad_soyad

            if dry_run:
                self.stdout.write(f"[dry-run] {talebe.ad_soyad} -> veli: {veli_ad}")
                continue

            sonuc = veli_panel_ensure(talebe, talebe.tc_kimlik, veli_ad, talebe.telefon)
            if not sonuc.basarili:
                atlanan_cakisma += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"ÇAKIŞMA (TC başka bir hesaba ait): {talebe.ad_soyad} "
                        f"(id={talebe.pk}, tc={talebe.tc_kimlik})"
                    )
                )
                continue

            if sonuc.olusturuldu:
                olusturulan += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"YENİ VELİ HESABI: {talebe.ad_soyad} → kullanıcı adı: "
                        f"{talebe.tc_kimlik}, geçici şifre: {sonuc.gecici_sifre}"
                    )
                )
            else:
                zaten_tamam += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Bitti: {olusturulan} yeni hesap ({isimsiz_yer_tutucu} yer tutucu adla), "
                f"{zaten_tamam} zaten tamamdı, {atlanan_cakisma} çakışma atlandı."
            )
        )
