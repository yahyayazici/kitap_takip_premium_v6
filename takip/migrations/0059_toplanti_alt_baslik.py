from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0058_toplanti_katilimci_m2m"),
    ]

    operations = [
        migrations.AlterField(
            model_name="personeltoplantisi",
            name="baslik",
            field=models.CharField(
                blank=True,
                help_text="İsteğe bağlı; raporda Personel Toplantısı altında görünür.",
                max_length=200,
                verbose_name="Alt başlık",
            ),
        ),
    ]
