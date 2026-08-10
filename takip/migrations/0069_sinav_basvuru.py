from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0068_konu_destek_merkezi"),
    ]

    operations = [
        migrations.CreateModel(
            name="SinavBasvuru",
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
                ("ad_soyad", models.CharField(max_length=150, verbose_name="Ad soyad")),
                ("baba_adi", models.CharField(max_length=100, verbose_name="Baba adı")),
                (
                    "baba_telefon",
                    models.CharField(max_length=20, verbose_name="Baba telefon"),
                ),
                ("anne_adi", models.CharField(max_length=100, verbose_name="Anne adı")),
                (
                    "anne_telefon",
                    models.CharField(max_length=20, verbose_name="Anne telefon"),
                ),
                (
                    "il",
                    models.CharField(
                        default="İstanbul",
                        max_length=80,
                        verbose_name="İl",
                    ),
                ),
                ("ilce", models.CharField(max_length=80, verbose_name="İlçe")),
                ("dogum_tarihi", models.DateField(verbose_name="Doğum tarihi")),
                (
                    "sinav_adi",
                    models.CharField(
                        help_text="Başvuru anındaki sınav başlığı",
                        max_length=200,
                        verbose_name="Sınav adı",
                    ),
                ),
                (
                    "durum",
                    models.CharField(
                        choices=[
                            ("yeni", "Yeni"),
                            ("inceleniyor", "İnceleniyor"),
                            ("kabul", "Kabul"),
                            ("red", "Red"),
                        ],
                        default="yeni",
                        max_length=20,
                        verbose_name="Durum",
                    ),
                ),
                (
                    "notlar",
                    models.TextField(blank=True, verbose_name="Yönetim notu"),
                ),
                (
                    "olusturulma",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Başvuru zamanı",
                    ),
                ),
                (
                    "guncellenme",
                    models.DateTimeField(auto_now=True, verbose_name="Güncellenme"),
                ),
            ],
            options={
                "verbose_name": "Sınav başvurusu",
                "verbose_name_plural": "Sınav başvuruları",
                "ordering": ["-olusturulma"],
            },
        ),
    ]
