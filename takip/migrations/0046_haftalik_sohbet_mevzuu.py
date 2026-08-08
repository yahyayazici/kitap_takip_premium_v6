# Generated manually for HaftalikSohbetMevzuu

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0045_ogretmen_haftalik_not_yoklama"),
    ]

    operations = [
        migrations.CreateModel(
            name="HaftalikSohbetMevzuu",
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
                ("baslik", models.CharField(max_length=200, verbose_name="Sohbet başlığı")),
                ("icerik", models.TextField(verbose_name="İçerik")),
                (
                    "hafta_baslangic",
                    models.DateField(
                        default=django.utils.timezone.localdate,
                        help_text="Haftanın pazartesi tarihi.",
                        verbose_name="Hafta başlangıcı",
                    ),
                ),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "olusturan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="olusturdugu_sohbet_mevzulari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Oluşturan",
                    ),
                ),
            ],
            options={
                "verbose_name": "Haftalık sohbet mevzuu",
                "verbose_name_plural": "Haftalık sohbet mevzuları",
                "ordering": ["-hafta_baslangic", "-id"],
            },
        ),
    ]
