from django.core.management.base import BaseCommand

from takip.models import SinavBasvuruMesajSablon


DEFAULTS = [
    {
        "an_kodu": SinavBasvuruMesajSablon.AnKodu.BASVURU_ALINDI,
        "baslik": "Başvuru alındı",
        "metin": (
            "Sayın veli, {ad_soyad} için {sinav_adi} başvurunuz alınmıştır. "
            "Kesin kayıt hakkı sınav sonucuna göre belirlenecektir. "
            "İlçe: {ilce}."
        ),
        "aktif": False,
        "alici": SinavBasvuruMesajSablon.Alici.IKISI,
        "sira": 1,
    },
    {
        "an_kodu": SinavBasvuruMesajSablon.AnKodu.SINAV_DAVETI,
        "baslik": "Sınav daveti",
        "metin": (
            "Sayın veli, {ad_soyad} için {sinav_adi} sınav daveti: "
            "Detaylar en kısa sürede tarafınıza iletilecektir. İlçe: {ilce}."
        ),
        "aktif": False,
        "alici": SinavBasvuruMesajSablon.Alici.IKISI,
        "sira": 2,
    },
    {
        "an_kodu": SinavBasvuruMesajSablon.AnKodu.SONUC_BILDIRIMI,
        "baslik": "Sonuç bildirimi",
        "metin": (
            "Sayın veli, {ad_soyad} için {sinav_adi} sonucu hakkında "
            "bilgilendirme: Lütfen kurum ile iletişime geçiniz."
        ),
        "aktif": False,
        "alici": SinavBasvuruMesajSablon.Alici.IKISI,
        "sira": 3,
    },
    {
        "an_kodu": SinavBasvuruMesajSablon.AnKodu.KABUL,
        "baslik": "Kabul",
        "metin": (
            "Sayın veli, {ad_soyad} için {sinav_adi} değerlendirmesi sonucu "
            "kabul edilmiştir. Kayıt süreci için sizinle iletişime geçilecektir."
        ),
        "aktif": False,
        "alici": SinavBasvuruMesajSablon.Alici.IKISI,
        "sira": 4,
    },
    {
        "an_kodu": SinavBasvuruMesajSablon.AnKodu.RED,
        "baslik": "Red",
        "metin": (
            "Sayın veli, {ad_soyad} için {sinav_adi} değerlendirmesi sonucu "
            "bu dönem kontenjana yerleştirme yapılamamıştır."
        ),
        "aktif": False,
        "alici": SinavBasvuruMesajSablon.Alici.IKISI,
        "sira": 5,
    },
]


class Command(BaseCommand):
    help = "Sınav başvurusu varsayılan WhatsApp mesaj anlarını oluşturur/günceller."

    def handle(self, *args, **options):
        for item in DEFAULTS:
            obj, created = SinavBasvuruMesajSablon.objects.update_or_create(
                an_kodu=item["an_kodu"],
                defaults=item,
            )
            self.stdout.write(
                f"{'+' if created else '~'} {obj.get_an_kodu_display()}"
            )
        self.stdout.write(self.style.SUCCESS("Mesaj anları hazır."))
