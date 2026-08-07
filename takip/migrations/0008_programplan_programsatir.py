from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0007_duyuru"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProgramPlan",
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
                    models.CharField(max_length=200, verbose_name="Program adı"),
                ),
                (
                    "aciklama",
                    models.TextField(blank=True, verbose_name="Açıklama"),
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
                        related_name="olusturdugu_programlar",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Oluşturan",
                    ),
                ),
            ],
            options={
                "verbose_name": "Program planı",
                "verbose_name_plural": "Program planları",
                "ordering": ["-baslangic_tarihi", "ad"],
            },
        ),
        migrations.CreateModel(
            name="ProgramSatir",
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
                ("baslangic_saati", models.TimeField(verbose_name="Başlangıç")),
                ("bitis_saati", models.TimeField(verbose_name="Bitiş")),
                (
                    "sure_dakika",
                    models.PositiveIntegerField(
                        default=0,
                        editable=False,
                        verbose_name="Süre (dk)",
                    ),
                ),
                (
                    "faaliyet_turu",
                    models.CharField(
                        choices=[
                            ("ders", "Ders"),
                            ("etut", "Etüt"),
                            ("namaz", "Namaz"),
                            ("yemek", "Yemek"),
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
                (
                    "faaliyet_adi",
                    models.CharField(max_length=200, verbose_name="Faaliyet adı"),
                ),
                (
                    "program_adi",
                    models.CharField(
                        blank=True,
                        help_text="Boş bırakılırsa üst program adı kullanılır.",
                        max_length=200,
                        verbose_name="Program adı",
                    ),
                ),
                (
                    "faaliyet_durumu",
                    models.CharField(
                        choices=[("etkin", "Etkin"), ("pasif", "Pasif")],
                        default="etkin",
                        max_length=10,
                        verbose_name="Durum",
                    ),
                ),
                (
                    "sira",
                    models.PositiveIntegerField(default=0, verbose_name="Sıra"),
                ),
                (
                    "program",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="satirlar",
                        to="takip.programplan",
                        verbose_name="Program",
                    ),
                ),
            ],
            options={
                "verbose_name": "Program satırı",
                "verbose_name_plural": "Program satırları",
                "ordering": ["sira", "baslangic_saati", "id"],
            },
        ),
    ]
