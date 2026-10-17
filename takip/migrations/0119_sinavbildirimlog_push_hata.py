from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0118_sinav_hatirlatma_eposta"),
    ]

    operations = [
        migrations.AddField(
            model_name="sinavbildirimlog",
            name="push_hata",
            field=models.TextField(blank=True, verbose_name="Bildirim hatası"),
        ),
    ]
