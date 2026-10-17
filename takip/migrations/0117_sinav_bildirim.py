import datetime
from zoneinfo import ZoneInfo

import django.db.models.deletion
from django.db import migrations, models

SINAV_ADI = "Yazılı Öncesi Seviye Tespit Sınavı"


def takvim_ekle(apps, schema_editor):
    SinavTakvim = apps.get_model("takip", "SinavTakvim")
    tz = ZoneInfo("Europe/Istanbul")
    SinavTakvim.objects.get_or_create(
        sinav_adi=SINAV_ADI,
        defaults={
            "baslangic": datetime.datetime(2026, 10, 24, 11, 0, tzinfo=tz),
            "bitis": datetime.datetime(2026, 10, 24, 13, 10, tzinfo=tz),
            "yer": "Çinili Saray Öğrenci Yurdu, Başakşehir",
            "bildirim_aktif": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0116_sinavbasvuru_sinif_okul"),
    ]

    operations = [
        migrations.CreateModel(
            name="SinavTakvim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sinav_adi", models.CharField(help_text="Başvurulardaki sınav adıyla birebir aynı olmalı.", max_length=200, unique=True, verbose_name="Sınav adı")),
                ("baslangic", models.DateTimeField(verbose_name="Sınav başlangıcı")),
                ("bitis", models.DateTimeField(verbose_name="Sınav bitişi")),
                ("yer", models.CharField(blank=True, max_length=200, verbose_name="Yer")),
                ("bildirim_aktif", models.BooleanField(default=True, verbose_name="Hatırlatmalar açık")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sınav takvimi",
                "verbose_name_plural": "Sınav takvimleri",
                "ordering": ["-baslangic"],
            },
        ),
        migrations.CreateModel(
            name="SinavBasvuruPushAbonelik",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.URLField(max_length=500, verbose_name="Endpoint")),
                ("p256dh", models.CharField(max_length=255, verbose_name="p256dh anahtarı")),
                ("auth", models.CharField(max_length=255, verbose_name="Auth anahtarı")),
                ("user_agent", models.CharField(blank=True, max_length=255, verbose_name="Cihaz/Tarayıcı")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("basvuru", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_abonelikleri", to="takip.sinavbasvuru", verbose_name="Başvuru")),
            ],
            options={
                "verbose_name": "Başvuru bildirim aboneliği",
                "verbose_name_plural": "Başvuru bildirim abonelikleri",
                "ordering": ["-olusturulma"],
                "constraints": [
                    models.UniqueConstraint(fields=("basvuru", "endpoint"), name="uniq_sinav_basvuru_push_endpoint"),
                ],
            },
        ),
        migrations.CreateModel(
            name="SinavBildirimLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("an_kodu", models.CharField(max_length=40, verbose_name="Bildirim anı")),
                ("baslik", models.CharField(blank=True, max_length=120, verbose_name="Başlık")),
                ("mesaj", models.TextField(blank=True, verbose_name="Mesaj")),
                ("gonderilen", models.PositiveSmallIntegerField(default=0, verbose_name="Ulaşan cihaz")),
                ("olusturulma", models.DateTimeField(auto_now_add=True, verbose_name="Zaman")),
                ("basvuru", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bildirim_loglari", to="takip.sinavbasvuru", verbose_name="Başvuru")),
            ],
            options={
                "verbose_name": "Sınav bildirim kaydı",
                "verbose_name_plural": "Sınav bildirim kayıtları",
                "ordering": ["-olusturulma"],
                "constraints": [
                    models.UniqueConstraint(fields=("basvuru", "an_kodu"), name="uniq_sinav_bildirim_basvuru_an"),
                ],
            },
        ),
        migrations.RunPython(takvim_ekle, migrations.RunPython.noop),
    ]
