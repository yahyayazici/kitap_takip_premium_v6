# Generated manually for Pazar izin dönüşü yoklaması

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0063_ai_platform"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PazarIzinDonusGunAyar",
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
                    "tarih",
                    models.DateField(
                        help_text="Pazar izin dönüşü yoklama günü.",
                        unique=True,
                        verbose_name="Yoklama tarihi",
                    ),
                ),
                (
                    "beklenen_giris_tarihi",
                    models.DateField(verbose_name="Beklenen giriş tarihi"),
                ),
                (
                    "beklenen_giris_saati",
                    models.TimeField(verbose_name="Beklenen giriş saati"),
                ),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "guncelleyen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="guncelledigi_pazar_izin_gun_ayarlari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Güncelleyen",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pazar izin dönüş gün ayarı",
                "verbose_name_plural": "Pazar izin dönüş gün ayarları",
                "ordering": ["-tarih"],
            },
        ),
        migrations.CreateModel(
            name="PazarIzinDonusOturum",
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
                ("tarih", models.DateField(verbose_name="Yoklama tarihi")),
                (
                    "beklenen_giris_tarihi",
                    models.DateField(verbose_name="Beklenen giriş tarihi"),
                ),
                (
                    "beklenen_giris_saati",
                    models.TimeField(verbose_name="Beklenen giriş saati"),
                ),
                ("kaydedilme", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "kaydeden",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kaydettigi_pazar_izin_oturumlari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Kaydeden",
                    ),
                ),
                (
                    "sinif_sube",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pazar_izin_donus_oturumlari",
                        to="takip.sinifsube",
                        verbose_name="Sınıf",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pazar izin dönüş oturumu",
                "verbose_name_plural": "Pazar izin dönüş oturumları",
                "ordering": ["-tarih", "sinif_sube__sinif", "sinif_sube__sube"],
            },
        ),
        migrations.CreateModel(
            name="PazarIzinDonusKaydi",
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
                    "durum",
                    models.CharField(
                        choices=[
                            ("geldi", "GELDİ"),
                            ("izinli", "İZİNLİ"),
                            ("gec_geldi", "GEÇ GELDİ"),
                            ("gelmedi", "GELMEDİ"),
                        ],
                        default="geldi",
                        max_length=12,
                        verbose_name="Durum",
                    ),
                ),
                (
                    "giris_tarihi",
                    models.DateField(blank=True, null=True, verbose_name="Giriş tarihi"),
                ),
                (
                    "giris_saati",
                    models.TimeField(blank=True, null=True, verbose_name="Giriş saati"),
                ),
                (
                    "gecikme_dk",
                    models.PositiveIntegerField(default=0, verbose_name="Gecikme (dk)"),
                ),
                (
                    "aciklama",
                    models.CharField(blank=True, max_length=300, verbose_name="Açıklama"),
                ),
                (
                    "oturum",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="kayitlar",
                        to="takip.pazarizindonusoturum",
                        verbose_name="Oturum",
                    ),
                ),
                (
                    "talebe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pazar_izin_donus_kayitlari",
                        to="takip.talebe",
                        verbose_name="Talebe",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pazar izin dönüş kaydı",
                "verbose_name_plural": "Pazar izin dönüş kayıtları",
            },
        ),
        migrations.AddConstraint(
            model_name="pazarizindonusoturum",
            constraint=models.UniqueConstraint(
                fields=("sinif_sube", "tarih"),
                name="benzersiz_pazar_izin_oturum",
            ),
        ),
        migrations.AddConstraint(
            model_name="pazarizindonuskaydi",
            constraint=models.UniqueConstraint(
                fields=("oturum", "talebe"),
                name="benzersiz_pazar_izin_talebe",
            ),
        ),
    ]
