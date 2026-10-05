# E-Kitap alt alan adı modelleri (ana kullanıcı sistemiyle ilişkisiz).

import django.db.models.deletion
import takip.ekitap_storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0107_ai_ktt_analiz_turu"),
    ]

    operations = [
        migrations.CreateModel(
            name="EKitap",
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
                ("ad", models.CharField(max_length=160, verbose_name="Kitap adı")),
                (
                    "gorunur",
                    models.BooleanField(
                        default=True,
                        help_text="Kapalıysa kitap tahtadaki listede görünmez.",
                        verbose_name="Görüntüleme sayfasında göster",
                    ),
                ),
                ("sira", models.PositiveIntegerField(default=0, verbose_name="Sıra")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "E-kitap",
                "verbose_name_plural": "E-kitaplar",
                "ordering": ["sira", "-olusturulma"],
            },
        ),
        migrations.CreateModel(
            name="EKitapAyar",
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
                ("pin_hash", models.CharField(blank=True, max_length=255)),
                (
                    "pin_surumu",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="PIN değişince artar; eski PIN ile açılmış tahtalar yeniden PIN ister.",
                    ),
                ),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "E-kitap ayarı",
            },
        ),
        migrations.CreateModel(
            name="EKitapBolum",
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
                ("ad", models.CharField(max_length=80, verbose_name="Bölüm adı")),
                ("sira", models.PositiveIntegerField(default=0, verbose_name="Sıra")),
                (
                    "pdf",
                    models.FileField(
                        max_length=255,
                        storage=takip.ekitap_storage.ekitap_depolama,
                        upload_to="pdf/",
                        verbose_name="PDF",
                    ),
                ),
                ("sayfa_sayisi", models.PositiveIntegerField(default=0)),
                (
                    "islem_durumu",
                    models.CharField(
                        choices=[
                            ("bekliyor", "İşleniyor"),
                            ("hazir", "Hazır"),
                            ("hata", "Hata"),
                        ],
                        default="bekliyor",
                        max_length=12,
                    ),
                ),
                ("islem_notu", models.CharField(blank=True, max_length=255)),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "kitap",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bolumler",
                        to="takip.ekitap",
                    ),
                ),
            ],
            options={
                "verbose_name": "E-kitap bölümü",
                "verbose_name_plural": "E-kitap bölümleri",
                "ordering": ["sira", "id"],
            },
        ),
        migrations.CreateModel(
            name="EKitapSayfa",
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
                ("sira", models.PositiveIntegerField()),
                (
                    "gorsel",
                    models.ImageField(
                        max_length=255,
                        storage=takip.ekitap_storage.ekitap_depolama,
                        upload_to="sayfa/",
                    ),
                ),
                (
                    "kucuk",
                    models.ImageField(
                        blank=True,
                        max_length=255,
                        storage=takip.ekitap_storage.ekitap_depolama,
                        upload_to="kucuk/",
                    ),
                ),
                ("genislik", models.PositiveIntegerField(default=0)),
                ("yukseklik", models.PositiveIntegerField(default=0)),
                (
                    "bolum",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sayfalar",
                        to="takip.ekitapbolum",
                    ),
                ),
            ],
            options={
                "ordering": ["sira"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("bolum", "sira"), name="benzersiz_ekitap_sayfa"
                    )
                ],
            },
        ),
    ]
