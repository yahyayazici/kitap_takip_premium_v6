# Generated manually for PanelKisayolGorsel

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0047_idareci_vazife_yct_yazili_tur"),
    ]

    operations = [
        migrations.CreateModel(
            name="PanelKisayolGorsel",
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
                    "anahtar",
                    models.SlugField(
                        help_text="Örn. kitap, talebeler, etut",
                        max_length=40,
                        unique=True,
                        verbose_name="Kısayol anahtarı",
                    ),
                ),
                (
                    "baslik",
                    models.CharField(
                        blank=True,
                        max_length=80,
                        verbose_name="Görünen ad",
                    ),
                ),
                (
                    "gorsel",
                    models.ImageField(
                        help_text="Önerilen: 640×400 veya 16:10 yatay görsel.",
                        upload_to="panel_kisayol/",
                        verbose_name="Banner görseli",
                    ),
                ),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Panel kısayol görseli",
                "verbose_name_plural": "Panel kısayol görselleri",
                "ordering": ["anahtar"],
            },
        ),
    ]
