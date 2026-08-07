from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0006_talebe_dini_ders_hocasi"),
    ]

    operations = [
        migrations.CreateModel(
            name="Duyuru",
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
                    "baslik",
                    models.CharField(max_length=200, verbose_name="Başlık"),
                ),
                (
                    "ozet",
                    models.TextField(max_length=500, verbose_name="Kısa açıklama"),
                ),
                (
                    "kategori",
                    models.CharField(
                        choices=[
                            ("genel", "Genel"),
                            ("egitim", "Eğitim"),
                            ("program", "Program"),
                            ("kurum", "Kurum"),
                        ],
                        default="genel",
                        max_length=20,
                        verbose_name="Kategori",
                    ),
                ),
                (
                    "hedef_kitle",
                    models.CharField(
                        choices=[
                            ("tum_personel", "Tüm personel"),
                            ("personel", "Personel paneli"),
                            ("veli", "Veli paneli"),
                        ],
                        default="tum_personel",
                        max_length=20,
                        verbose_name="Hedef kitle",
                    ),
                ),
                (
                    "dis_link",
                    models.URLField(
                        blank=True,
                        help_text="İsteğe bağlı. Duyuruya tıklanınca açılacak adres.",
                        verbose_name="Bağlantı",
                    ),
                ),
                (
                    "ton",
                    models.CharField(
                        choices=[
                            ("navy", "Lacivert"),
                            ("violet", "Mor"),
                            ("teal", "Turkuaz"),
                            ("amber", "Kehribar"),
                        ],
                        default="navy",
                        max_length=20,
                        verbose_name="Görsel ton",
                    ),
                ),
                (
                    "baslangic",
                    models.DateField(
                        default=django.utils.timezone.localdate,
                        verbose_name="Yayın başlangıcı",
                    ),
                ),
                (
                    "bitis",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Yayın bitişi",
                    ),
                ),
                (
                    "sira",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Küçük numara önce gösterilir.",
                        verbose_name="Sıra",
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
                        related_name="olusturdugu_duyurular",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Oluşturan",
                    ),
                ),
            ],
            options={
                "verbose_name": "Duyuru",
                "verbose_name_plural": "Duyurular",
                "ordering": ["sira", "-baslangic", "-id"],
            },
        ),
    ]
