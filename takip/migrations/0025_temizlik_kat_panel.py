# Kat bazlı temizlik görev yönetimi

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0024_rehberlik_premium"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TemizlikKati",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ad", models.CharField(max_length=120, verbose_name="Kat adı")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                (
                    "liste",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="katlar",
                        to="takip.temizliklistesi",
                        verbose_name="Liste",
                    ),
                ),
            ],
            options={
                "verbose_name": "Temizlik katı",
                "verbose_name_plural": "Temizlik katları",
                "ordering": ["sira", "ad"],
            },
        ),
        migrations.AddField(
            model_name="temizlikalani",
            name="kat",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alanlar",
                to="takip.temizlikkati",
                verbose_name="Kat",
            ),
        ),
        migrations.CreateModel(
            name="TemizlikKatSorumlusu",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sorumlular",
                        to="takip.temizlikkati",
                        verbose_name="Kat",
                    ),
                ),
                (
                    "personel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="temizlik_kat_sorumluluklari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Sorumlu personel",
                    ),
                ),
            ],
            options={
                "verbose_name": "Kat sorumlusu",
                "verbose_name_plural": "Kat sorumluları",
            },
        ),
        migrations.CreateModel(
            name="TemizlikGorevlisi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                (
                    "alan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gorevliler",
                        to="takip.temizlikalani",
                        verbose_name="Mahal",
                    ),
                ),
                (
                    "liste",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gorevliler",
                        to="takip.temizliklistesi",
                        verbose_name="Liste",
                    ),
                ),
                (
                    "talebe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="temizlik_mahal_gorevleri",
                        to="takip.talebe",
                        verbose_name="Görevli talebe",
                    ),
                ),
            ],
            options={
                "verbose_name": "Temizlik görevlisi",
                "verbose_name_plural": "Temizlik görevlileri",
                "ordering": ["alan__sira", "alan__ad", "talebe__ad_soyad"],
            },
        ),
        migrations.AddConstraint(
            model_name="temizlikkati",
            constraint=models.UniqueConstraint(
                fields=("liste", "ad"),
                name="benzersiz_temizlik_liste_kat",
            ),
        ),
        migrations.AddConstraint(
            model_name="temizlikkatsorumlusu",
            constraint=models.UniqueConstraint(
                fields=("kat", "personel"),
                name="benzersiz_temizlik_kat_sorumlu",
            ),
        ),
        migrations.AddConstraint(
            model_name="temizlikgorevlisi",
            constraint=models.UniqueConstraint(
                fields=("liste", "alan", "talebe"),
                name="benzersiz_temizlik_liste_alan_gorevli",
            ),
        ),
    ]
