from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0115_yemekci_hafta_ayri"),
    ]

    operations = [
        migrations.AddField(
            model_name="sinavbasvuru",
            name="sinif",
            field=models.CharField(
                blank=True,
                choices=[
                    ("4", "4. sınıf"),
                    ("5", "5. sınıf"),
                    ("6", "6. sınıf"),
                    ("7", "7. sınıf"),
                    ("8", "8. sınıf"),
                ],
                max_length=2,
                verbose_name="Sınıf",
            ),
        ),
        migrations.AddField(
            model_name="sinavbasvuru",
            name="okul_adi",
            field=models.CharField(blank=True, max_length=150, verbose_name="Okul adı"),
        ),
        migrations.AlterField(
            model_name="sinavbasvuru",
            name="ad_soyad",
            field=models.CharField(max_length=150, verbose_name="Öğrenci ad soyad"),
        ),
    ]
