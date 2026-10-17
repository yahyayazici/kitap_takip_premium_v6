import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0119_sinavbildirimlog_push_hata"),
    ]

    operations = [
        migrations.CreateModel(
            name="SinavSalon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sinav_adi", models.CharField(max_length=200, verbose_name="Sınav adı")),
                ("ad", models.CharField(max_length=60, verbose_name="Salon adı")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
                ("masa_sayisi", models.PositiveSmallIntegerField(default=0, verbose_name="Masa sayısı")),
                ("masa_kisi", models.PositiveSmallIntegerField(default=1, verbose_name="Masa başına öğrenci")),
            ],
            options={
                "verbose_name": "Sınav salonu",
                "verbose_name_plural": "Sınav salonları",
                "ordering": ["sinav_adi", "sira", "id"],
            },
        ),
        migrations.CreateModel(
            name="SinavYerlesim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("masa_no", models.PositiveSmallIntegerField(verbose_name="Masa")),
                ("koltuk", models.PositiveSmallIntegerField(default=1, verbose_name="Koltuk")),
                (
                    "basvuru",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="yerlesim",
                        to="takip.sinavbasvuru",
                        verbose_name="Başvuru",
                    ),
                ),
                (
                    "salon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="yerlesimler",
                        to="takip.sinavsalon",
                        verbose_name="Salon",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sınav yerleşimi",
                "verbose_name_plural": "Sınav yerleşimleri",
                "ordering": ["salon__sira", "masa_no", "koltuk"],
            },
        ),
        migrations.AddConstraint(
            model_name="sinavyerlesim",
            constraint=models.UniqueConstraint(
                fields=("salon", "masa_no", "koltuk"), name="uniq_sinav_yerlesim_koltuk"
            ),
        ),
    ]
