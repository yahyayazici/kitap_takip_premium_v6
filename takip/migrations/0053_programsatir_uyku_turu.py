from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0052_yemekci_sinif_dongu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="programsatir",
            name="faaliyet_turu",
            field=models.CharField(
                choices=[
                    ("ders", "Ders"),
                    ("etut", "Etüt"),
                    ("namaz", "Namaz"),
                    ("yemek", "Yemek"),
                    ("uyku", "Uyku"),
                    ("dinlenme", "Dinlenme"),
                    ("spor", "Spor"),
                    ("gorev", "Görev"),
                    ("toplanti", "Toplantı"),
                    ("diger", "Diğer"),
                ],
                default="ders",
                max_length=20,
                verbose_name="Faaliyet türü",
            ),
        ),
    ]
