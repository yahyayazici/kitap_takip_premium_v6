# Generated manually for premium rehberlik module

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0023_mezun_aidat_rehberlik"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="gorusmeturu",
            name="grup",
            field=models.CharField(
                choices=[
                    ("veli", "Veli"),
                    ("ogrenci", "Öğrenci"),
                    ("telefon", "Telefon"),
                    ("whatsapp", "WhatsApp"),
                    ("akademik", "Akademik"),
                    ("disiplin", "Disiplin"),
                    ("din", "Din Eğitimi"),
                    ("genel", "Genel Not"),
                ],
                default="genel",
                max_length=20,
                verbose_name="Grup",
            ),
        ),
        migrations.AddField(
            model_name="gorusmeturu",
            name="ikon",
            field=models.CharField(default="💬", max_length=8, verbose_name="İkon"),
        ),
        migrations.AddField(
            model_name="gorusmeturu",
            name="kod",
            field=models.SlugField(blank=True, max_length=40, verbose_name="Kod"),
        ),
        migrations.AddField(
            model_name="gorusmeturu",
            name="renk",
            field=models.CharField(default="#3b82f6", max_length=20, verbose_name="Renk"),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="etiketler",
            field=models.JSONField(blank=True, default=list, verbose_name="Etiketler"),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="genel_durum",
            field=models.CharField(
                choices=[
                    ("iyi", "İyi Durumda"),
                    ("takip", "Takip Gerekiyor"),
                    ("risk", "Riskli"),
                    ("pasif", "Pasif"),
                ],
                default="iyi",
                max_length=12,
                verbose_name="Genel durum",
            ),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="kaydeden",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rehberlik_gorusmeleri",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Kaydeden",
            ),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="saat",
            field=models.TimeField(blank=True, null=True, verbose_name="Saat"),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="sonraki_gorusme",
            field=models.DateField(blank=True, null=True, verbose_name="Sonraki görüşme"),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="sonraki_gorusme_saat",
            field=models.TimeField(blank=True, null=True, verbose_name="Sonraki görüşme saati"),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="takip_gerekiyor",
            field=models.BooleanField(default=False, verbose_name="Takip gerekiyor"),
        ),
        migrations.AddField(
            model_name="ogrencigorusmesi",
            name="yapilacaklar",
            field=models.JSONField(blank=True, default=list, verbose_name="Yapılacaklar"),
        ),
        migrations.AlterField(
            model_name="ogrencigorusmesi",
            name="kararlar",
            field=models.TextField(blank=True, verbose_name="Alınan kararlar"),
        ),
        migrations.CreateModel(
            name="GorusmeGorevi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("baslik", models.CharField(max_length=200, verbose_name="Görev")),
                ("sorumlu", models.CharField(blank=True, max_length=120, verbose_name="Sorumlu")),
                (
                    "durum",
                    models.CharField(
                        choices=[
                            ("bekliyor", "Bekliyor"),
                            ("devam", "Devam Ediyor"),
                            ("tamam", "Tamamlandı"),
                        ],
                        default="bekliyor",
                        max_length=12,
                        verbose_name="Durum",
                    ),
                ),
                ("tamamlandi", models.BooleanField(default=False, verbose_name="Tamamlandı")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                (
                    "gorusme",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gorevler",
                        to="takip.ogrencigorusmesi",
                        verbose_name="Görüşme",
                    ),
                ),
                (
                    "talebe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rehberlik_gorevleri",
                        to="takip.talebe",
                        verbose_name="Talebe",
                    ),
                ),
            ],
            options={
                "verbose_name": "Görüşme görevi",
                "verbose_name_plural": "Görüşme görevleri",
                "ordering": ["tamamlandi", "-olusturulma"],
            },
        ),
        migrations.CreateModel(
            name="GorusmeDosyasi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ad", models.CharField(blank=True, max_length=160, verbose_name="Dosya adı")),
                ("dosya", models.FileField(upload_to="rehberlik/%Y/%m/", verbose_name="Dosya")),
                (
                    "tur",
                    models.CharField(
                        choices=[
                            ("pdf", "PDF"),
                            ("foto", "Fotoğraf"),
                            ("ses", "Ses Kaydı"),
                            ("diger", "Diğer"),
                        ],
                        default="diger",
                        max_length=12,
                        verbose_name="Tür",
                    ),
                ),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                (
                    "gorusme",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dosyalar",
                        to="takip.ogrencigorusmesi",
                        verbose_name="Görüşme",
                    ),
                ),
                (
                    "yukleyen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rehberlik_dosyalari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Yükleyen",
                    ),
                ),
            ],
            options={
                "verbose_name": "Görüşme dosyası",
                "verbose_name_plural": "Görüşme dosyaları",
                "ordering": ["-olusturulma"],
            },
        ),
    ]
