from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0008_programplan_programsatir"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImamMuezzinListesi",
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
                    "ad",
                    models.CharField(max_length=200, verbose_name="Liste adı"),
                ),
                (
                    "baslangic_tarihi",
                    models.DateField(verbose_name="Başlangıç tarihi"),
                ),
                (
                    "bitis_tarihi",
                    models.DateField(verbose_name="Bitiş tarihi"),
                ),
                (
                    "cumartesi_dahil",
                    models.BooleanField(default=True, verbose_name="Cumartesi dahil"),
                ),
                (
                    "pazar_dahil",
                    models.BooleanField(default=False, verbose_name="Pazar dahil"),
                ),
                (
                    "haric_tarihler",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="ISO formatında tarih listesi (YYYY-MM-DD).",
                        verbose_name="Hariç tutulan günler",
                    ),
                ),
                (
                    "aktif",
                    models.BooleanField(default=True, verbose_name="Aktif"),
                ),
                (
                    "olusturulma",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Oluşturulma",
                    ),
                ),
                (
                    "guncellenme",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Güncellenme",
                    ),
                ),
                (
                    "olusturan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="olusturdugu_imam_listeleri",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Oluşturan",
                    ),
                ),
                (
                    "talebe_havuzu",
                    models.ManyToManyField(
                        blank=True,
                        related_name="imam_muezzin_listeleri",
                        to="takip.talebe",
                        verbose_name="Talebe havuzu",
                    ),
                ),
            ],
            options={
                "verbose_name": "İmam müezzin listesi",
                "verbose_name_plural": "İmam müezzin listeleri",
                "ordering": ["-baslangic_tarihi", "ad"],
            },
        ),
        migrations.CreateModel(
            name="ImamMuezzinAtama",
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
                ("tarih", models.DateField(verbose_name="Tarih")),
                (
                    "manuel_duzenlendi",
                    models.BooleanField(
                        default=False,
                        verbose_name="Manuel düzenlendi",
                    ),
                ),
                (
                    "imam",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="imam_gorevleri",
                        to="takip.talebe",
                        verbose_name="İmam",
                    ),
                ),
                (
                    "liste",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="atamalar",
                        to="takip.imammuezzinlistesi",
                        verbose_name="Liste",
                    ),
                ),
                (
                    "muezzin",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="muezzin_gorevleri",
                        to="takip.talebe",
                        verbose_name="Müezzin",
                    ),
                ),
            ],
            options={
                "verbose_name": "İmam müezzin ataması",
                "verbose_name_plural": "İmam müezzin atamaları",
                "ordering": ["tarih"],
            },
        ),
        migrations.AddConstraint(
            model_name="imammuezzinatama",
            constraint=models.UniqueConstraint(
                fields=("liste", "tarih"),
                name="benzersiz_liste_gun_atama",
            ),
        ),
    ]
