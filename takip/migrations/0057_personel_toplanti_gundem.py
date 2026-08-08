from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0056_personel_toplanti"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonelToplantiGundemMadde",
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
                ("sira", models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")),
                (
                    "madde",
                    models.CharField(max_length=300, verbose_name="Gündem maddesi"),
                ),
                (
                    "gorusulen",
                    models.TextField(
                        blank=True,
                        help_text="Toplantıda bu madde hakkında konuşulanlar.",
                        verbose_name="Görüşülen / konuşulanlar",
                    ),
                ),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "toplanti",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gundem_maddeleri",
                        to="takip.personeltoplantisi",
                        verbose_name="Toplantı",
                    ),
                ),
            ],
            options={
                "verbose_name": "Gündem maddesi",
                "verbose_name_plural": "Gündem maddeleri",
                "ordering": ["sira", "id"],
            },
        ),
    ]
