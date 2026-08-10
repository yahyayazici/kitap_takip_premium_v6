from django.db import migrations, models
import django.db.models.deletion


def seed_mesaj_anlari(apps, schema_editor):
    Sablon = apps.get_model("takip", "SinavBasvuruMesajSablon")
    defaults = [
        {
            "an_kodu": "basvuru_alindi",
            "baslik": "Başvuru alındı",
            "metin": (
                "Sayın veli, {ad_soyad} için {sinav_adi} başvurunuz alınmıştır. "
                "Kesin kayıt hakkı sınav sonucuna göre belirlenecektir. "
                "İlçe: {ilce}."
            ),
            "aktif": False,
            "alici": "ikisi",
            "sira": 1,
        },
        {
            "an_kodu": "sinav_daveti",
            "baslik": "Sınav daveti",
            "metin": (
                "Sayın veli, {ad_soyad} için {sinav_adi} sınav daveti: "
                "Detaylar en kısa sürede tarafınıza iletilecektir. İlçe: {ilce}."
            ),
            "aktif": False,
            "alici": "ikisi",
            "sira": 2,
        },
        {
            "an_kodu": "sonuc_bildirimi",
            "baslik": "Sonuç bildirimi",
            "metin": (
                "Sayın veli, {ad_soyad} için {sinav_adi} sonucu hakkında "
                "bilgilendirme: Lütfen kurum ile iletişime geçiniz."
            ),
            "aktif": False,
            "alici": "ikisi",
            "sira": 3,
        },
        {
            "an_kodu": "kabul",
            "baslik": "Kabul",
            "metin": (
                "Sayın veli, {ad_soyad} için {sinav_adi} değerlendirmesi sonucu "
                "kabul edilmiştir. Kayıt süreci için sizinle iletişime geçilecektir."
            ),
            "aktif": False,
            "alici": "ikisi",
            "sira": 4,
        },
        {
            "an_kodu": "red",
            "baslik": "Red",
            "metin": (
                "Sayın veli, {ad_soyad} için {sinav_adi} değerlendirmesi sonucu "
                "bu dönem kontenjana yerleştirme yapılamamıştır."
            ),
            "aktif": False,
            "alici": "ikisi",
            "sira": 5,
        },
    ]
    for item in defaults:
        Sablon.objects.update_or_create(
            an_kodu=item["an_kodu"],
            defaults=item,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0069_sinav_basvuru"),
    ]

    operations = [
        migrations.CreateModel(
            name="SinavBasvuruMesajSablon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "an_kodu",
                    models.CharField(
                        choices=[
                            ("basvuru_alindi", "Başvuru alındı"),
                            ("sinav_daveti", "Sınav daveti"),
                            ("sonuc_bildirimi", "Sonuç bildirimi"),
                            ("kabul", "Kabul"),
                            ("red", "Red"),
                        ],
                        max_length=40,
                        unique=True,
                        verbose_name="Mesaj anı",
                    ),
                ),
                ("baslik", models.CharField(max_length=120, verbose_name="Başlık")),
                (
                    "metin",
                    models.TextField(
                        help_text=(
                            "Değişkenler: {ad_soyad}, {sinav_adi}, {il}, {ilce}, "
                            "{baba_adi}, {anne_adi}"
                        ),
                        verbose_name="Mesaj metni",
                    ),
                ),
                ("aktif", models.BooleanField(default=False, verbose_name="Aktif")),
                (
                    "alici",
                    models.CharField(
                        choices=[
                            ("baba", "Sadece baba"),
                            ("anne", "Sadece anne"),
                            ("ikisi", "Baba ve anne"),
                        ],
                        default="ikisi",
                        max_length=10,
                        verbose_name="Alıcı",
                    ),
                ),
                (
                    "wa_template_name",
                    models.CharField(
                        blank=True,
                        help_text="Meta’da onaylı template adı. Boşsa metin mesajı denenir.",
                        max_length=120,
                        verbose_name="WhatsApp template adı",
                    ),
                ),
                (
                    "wa_template_lang",
                    models.CharField(
                        default="tr",
                        max_length=20,
                        verbose_name="Template dili",
                    ),
                ),
                (
                    "sira",
                    models.PositiveSmallIntegerField(default=0, verbose_name="Sıra"),
                ),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sınav başvuru mesaj anı",
                "verbose_name_plural": "Sınav başvuru mesaj anları",
                "ordering": ["sira", "an_kodu"],
            },
        ),
        migrations.CreateModel(
            name="SinavBasvuruMesajLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("an_kodu", models.CharField(max_length=40, verbose_name="Mesaj anı")),
                ("telefon", models.CharField(max_length=20, verbose_name="Telefon")),
                (
                    "alici_etiket",
                    models.CharField(blank=True, max_length=20, verbose_name="Alıcı"),
                ),
                (
                    "metin",
                    models.TextField(blank=True, verbose_name="Gönderilen metin"),
                ),
                (
                    "durum",
                    models.CharField(
                        choices=[
                            ("beklemede", "Beklemede"),
                            ("gonderildi", "Gönderildi"),
                            ("hata", "Hata"),
                            ("atlandi", "Atlandı"),
                        ],
                        default="beklemede",
                        max_length=20,
                        verbose_name="Durum",
                    ),
                ),
                (
                    "provider_yanit",
                    models.TextField(blank=True, verbose_name="Sağlayıcı yanıtı"),
                ),
                (
                    "olusturulma",
                    models.DateTimeField(auto_now_add=True, verbose_name="Zaman"),
                ),
                (
                    "basvuru",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mesaj_loglari",
                        to="takip.sinavbasvuru",
                        verbose_name="Başvuru",
                    ),
                ),
                (
                    "sablon",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="loglar",
                        to="takip.sinavbasvurumesajsablon",
                        verbose_name="Şablon",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sınav başvuru mesaj logu",
                "verbose_name_plural": "Sınav başvuru mesaj logları",
                "ordering": ["-olusturulma"],
            },
        ),
        migrations.RunPython(seed_mesaj_anlari, migrations.RunPython.noop),
    ]
