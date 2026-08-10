from django.db import migrations, models


def seed_turler(apps, schema_editor):
    ProgramFaaliyetTuru = apps.get_model("takip", "ProgramFaaliyetTuru")
    varsayilanlar = [
        ("ders", "Ders", "blue", 10),
        ("etut", "Etüt", "blue", 20),
        ("namaz", "Namaz", "green", 30),
        ("yemek", "Yemek", "amber", 40),
        ("mola", "Mola", "slate", 50),
        ("serbest_zaman", "Serbest Zaman", "sky", 60),
        ("uyku", "Uyku", "slate", 70),
        ("dinlenme", "Dinlenme", "slate", 80),
        ("spor", "Spor", "blue", 90),
        ("gorev", "Görev", "slate", 100),
        ("toplanti", "Toplantı", "slate", 110),
        ("diger", "Diğer", "sky", 120),
    ]
    for kod, ad, renk, sira in varsayilanlar:
        ProgramFaaliyetTuru.objects.update_or_create(
            kod=kod,
            defaults={"ad": ad, "renk": renk, "sira": sira, "aktif": True},
        )


def unseed_turler(apps, schema_editor):
    ProgramFaaliyetTuru = apps.get_model("takip", "ProgramFaaliyetTuru")
    ProgramFaaliyetTuru.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("takip", "0073_talebe_memleket_ilce_ev_adresi"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProgramFaaliyetTuru",
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
                    "kod",
                    models.SlugField(
                        help_text="Küçük harf, örn. ders, namaz, mola",
                        max_length=40,
                        unique=True,
                        verbose_name="Kod",
                    ),
                ),
                ("ad", models.CharField(max_length=80, verbose_name="Ad")),
                (
                    "renk",
                    models.CharField(
                        default="slate",
                        help_text="green, blue, amber, sky, slate",
                        max_length=20,
                        verbose_name="Renk",
                    ),
                ),
                ("sira", models.PositiveIntegerField(default=0, verbose_name="Sıra")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
            ],
            options={
                "verbose_name": "Program faaliyet türü",
                "verbose_name_plural": "Program faaliyet türleri",
                "ordering": ["sira", "ad"],
            },
        ),
        migrations.AlterField(
            model_name="programsatir",
            name="faaliyet_turu",
            field=models.CharField(
                default="ders",
                help_text="Tür listesi Program faaliyet türlerinden yönetilir.",
                max_length=40,
                verbose_name="Faaliyet türü",
            ),
        ),
        migrations.RunPython(seed_turler, unseed_turler),
    ]
