import django.db.models.deletion
from decimal import Decimal

from django.db import migrations, models

import takip.sinav_sonuc_models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0120_sinav_salon_yerlesim"),
    ]

    operations = [
        migrations.AddField(
            model_name="sinavbasvuru",
            name="sonuc_karar",
            field=models.CharField(
                blank=True,
                choices=[("kazandi", "Kazandı"), ("kazanamadi", "Kazanamadı")],
                max_length=12,
                verbose_name="Sonuç kararı",
            ),
        ),
        migrations.AddField(
            model_name="sinavtakvim",
            name="sonuc_mesaji",
            field=models.TextField(blank=True, verbose_name="Sonuç e-posta mesajı"),
        ),
        migrations.CreateModel(
            name="SinavSonuc",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("veri_var", models.BooleanField(default=False, verbose_name="Excel sonucu var")),
                ("excel_ad", models.CharField(blank=True, max_length=150, verbose_name="Excel'deki ad")),
                ("toplam_dogru", models.PositiveSmallIntegerField(default=0)),
                ("toplam_yanlis", models.PositiveSmallIntegerField(default=0)),
                ("toplam_bos", models.PositiveSmallIntegerField(default=0)),
                ("toplam_net", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=7)),
                ("puan", models.DecimalField(blank=True, decimal_places=3, max_digits=8, null=True)),
                ("branslar", models.JSONField(blank=True, default=dict, verbose_name="Ders sonuçları")),
                ("genel_sira", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Genel sıra")),
                ("sinif_sira", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Sınıf sırası")),
                (
                    "karne",
                    models.FileField(
                        blank=True,
                        storage=takip.sinav_sonuc_models.sinav_sonuc_depolama,
                        upload_to=takip.sinav_sonuc_models.karne_yolu,
                        verbose_name="Karne dosyası",
                    ),
                ),
                ("karne_adi", models.CharField(blank=True, max_length=200, verbose_name="Yüklenen dosya adı")),
                ("karne_surum", models.PositiveSmallIntegerField(default=0)),
                ("karne_yuklenme", models.DateTimeField(blank=True, null=True)),
                ("gonderilen_surum", models.PositiveSmallIntegerField(default=0)),
                ("gonderim_zamani", models.DateTimeField(blank=True, null=True, verbose_name="Veliye gönderildi")),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "basvuru",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sonuc",
                        to="takip.sinavbasvuru",
                        verbose_name="Başvuru",
                    ),
                ),
            ],
            options={
                "verbose_name": "Seviye tespit sonucu",
                "verbose_name_plural": "Seviye tespit sonuçları",
                "ordering": ["genel_sira", "basvuru__ad_soyad"],
            },
        ),
    ]
