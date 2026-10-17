from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0117_sinav_bildirim"),
    ]

    operations = [
        migrations.AddField(
            model_name="sinavbasvuru",
            name="veli_eposta",
            field=models.EmailField(blank=True, max_length=254, verbose_name="Veli e-posta"),
        ),
        migrations.AddField(
            model_name="sinavbasvuru",
            name="hatirlatma_turu",
            field=models.CharField(
                blank=True,
                choices=[("push", "Uygulama bildirimi"), ("takvim", "Takvim")],
                max_length=10,
                verbose_name="Hatırlatma türü",
            ),
        ),
        migrations.AddField(
            model_name="sinavbildirimlog",
            name="eposta_gonderildi",
            field=models.BooleanField(default=False, verbose_name="E-posta gönderildi"),
        ),
    ]
