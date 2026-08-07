from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0035_gelisim_durum_kodu"),
    ]

    operations = [
        migrations.CreateModel(
            name="TemizlikMahalSorumlusu",
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
                    "alan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mahal_sorumlulari",
                        to="takip.temizlikalani",
                        verbose_name="Mahal",
                    ),
                ),
                (
                    "personel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="temizlik_mahal_sorumluluklari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Sorumlu personel",
                    ),
                ),
            ],
            options={
                "verbose_name": "Mahal sorumlusu",
                "verbose_name_plural": "Mahal sorumluları",
            },
        ),
        migrations.AddConstraint(
            model_name="temizlikmahalsorumlusu",
            constraint=models.UniqueConstraint(
                fields=("alan", "personel"),
                name="benzersiz_temizlik_mahal_sorumlu",
            ),
        ),
    ]
