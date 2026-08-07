from django.core.management.base import BaseCommand, CommandError

from takip.kurum_ogrenci_pdf_import import kurum_ogrenci_pdf_ice_aktar, pdf_ogrencileri_coz


class Command(BaseCommand):
    help = "Kurum geneli öğrenci listesi PDF dosyasından talebeleri içe aktarır."

    def add_arguments(self, parser):
        parser.add_argument(
            "pdf_yolu",
            help="Öğrenci listesi PDF dosyasının yolu",
        )
        parser.add_argument(
            "--koru",
            action="store_true",
            help="PDF'de olmayan mevcut öğrencileri silme",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Sadece PDF'den okunan öğrenci sayısını göster",
        )

    def handle(self, *args, **options):
        pdf_yolu = options["pdf_yolu"]

        try:
            ogrenciler = pdf_ogrencileri_coz(pdf_yolu)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(f"PDF okunamadı: {exc}") from exc

        if options["dry_run"]:
            sinif_ozet: dict[str, int] = {}
            for ogrenci in ogrenciler:
                anahtar = f"{ogrenci.sinif}/{ogrenci.sube}"
                sinif_ozet[anahtar] = sinif_ozet.get(anahtar, 0) + 1

            self.stdout.write(f"Toplam öğrenci: {len(ogrenciler)}")
            for anahtar in sorted(sinif_ozet):
                self.stdout.write(f"  {anahtar}: {sinif_ozet[anahtar]}")
            return

        sonuc = kurum_ogrenci_pdf_ice_aktar(
            pdf_yolu,
            listede_olmayanlari_sil=not options["koru"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Eklenen: {sonuc.eklenen}, güncellenen: {sonuc.guncellenen}, "
                f"silinen: {sonuc.silinen}, numaralandırılan: {sonuc.numaralandirilan}"
            )
        )

        for hata in sonuc.hatalar:
            self.stdout.write(self.style.WARNING(hata))
