# İmam müezzin ayrı havuz kayıtları

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0025_temizlik_kat_panel"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImamMuezzinHavuzKaydi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "rol",
                    models.CharField(
                        choices=[("imam", "İmam"), ("muezzin", "Müezzin")],
                        max_length=10,
                        verbose_name="Rol",
                    ),
                ),
                ("sira", models.PositiveIntegerField(default=0, verbose_name="Sıra")),
                (
                    "liste",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="havuz_kayitlari",
                        to="takip.imammuezzinlistesi",
                        verbose_name="Liste",
                    ),
                ),
                (
                    "talebe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="imam_muezzin_havuz_kayitlari",
                        to="takip.talebe",
                        verbose_name="Talebe",
                    ),
                ),
            ],
            options={
                "verbose_name": "İmam müezzin havuz kaydı",
                "verbose_name_plural": "İmam müezzin havuz kayıtları",
                "ordering": ["rol", "sira", "talebe__ad_soyad"],
            },
        ),
        migrations.AddConstraint(
            model_name="imammuezzinhavuzkaydi",
            constraint=models.UniqueConstraint(
                fields=("liste", "rol", "talebe"),
                name="benzersiz_imam_muezzin_havuz",
            ),
        ),
    ]
