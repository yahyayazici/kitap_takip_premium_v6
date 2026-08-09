# Generated manually for AI platform

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0062_yazili_donem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AiUretimKaydi",
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
                    "tur",
                    models.CharField(
                        choices=[
                            ("gelisim_zekasi", "Gelişim Zekası"),
                            ("mudahale_oneri", "Müdahale Önerisi"),
                            ("veli_haftalik", "Veli Haftalık Özet"),
                            ("deneme_analiz", "Deneme Analizi"),
                            ("rehberlik_ozet", "Rehberlik Özeti"),
                            ("kurum_zekasi", "Kurum Zekası"),
                            ("soru_takip", "Soru Takip İçgörüsü"),
                        ],
                        max_length=32,
                        verbose_name="Tür",
                    ),
                ),
                (
                    "anahtar",
                    models.CharField(db_index=True, max_length=160, verbose_name="Anahtar"),
                ),
                ("icerik", models.JSONField(default=dict, verbose_name="İçerik")),
                (
                    "yapay_zeka",
                    models.BooleanField(
                        default=False, verbose_name="Yapay zeka ile üretildi"
                    ),
                ),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "olusturan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ai_uretimleri",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Oluşturan",
                    ),
                ),
            ],
            options={
                "verbose_name": "AI üretim kaydı",
                "verbose_name_plural": "AI üretim kayıtları",
                "ordering": ["-guncellenme"],
            },
        ),
        migrations.AddConstraint(
            model_name="aiuretimkaydi",
            constraint=models.UniqueConstraint(
                fields=("tur", "anahtar"),
                name="benzersiz_ai_uretim",
            ),
        ),
    ]
