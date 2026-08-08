# Generated manually for haftalık not + yoklama

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0044_duyuru_ogretmen_hedef_ozet_uzunluk"),
    ]

    operations = [
        migrations.AddField(
            model_name="ogretmensinavnotu",
            name="hafta_baslangic",
            field=models.DateField(
                default="2026-08-03",
                help_text="Haftanın pazartesi tarihi.",
                verbose_name="Hafta başlangıcı",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ogretmensinavnotu",
            name="katilim",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="Katılım (%30)",
            ),
        ),
        migrations.AddField(
            model_name="ogretmensinavnotu",
            name="takip",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="Takip (%30)",
            ),
        ),
        migrations.AddField(
            model_name="ogretmensinavnotu",
            name="disiplin",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="Disiplin (%40)",
            ),
        ),
        migrations.AlterField(
            model_name="ogretmensinavnotu",
            name="puan",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="Ağırlıklı puan",
            ),
        ),
        migrations.AlterField(
            model_name="ogretmensinavnotu",
            name="tarih",
            field=models.DateField(blank=True, null=True, verbose_name="Tarih (eski)"),
        ),
        migrations.AlterField(
            model_name="ogretmensinavnotu",
            name="tur",
            field=models.CharField(
                blank=True, default="", max_length=10, verbose_name="Tür (eski)"
            ),
        ),
        migrations.AlterField(
            model_name="ogretmensinavnotu",
            name="aciklama",
            field=models.TextField(blank=True, verbose_name="Değerlendirme notu"),
        ),
        migrations.AlterModelOptions(
            name="ogretmensinavnotu",
            options={
                "ordering": ["-hafta_baslangic", "-id"],
                "verbose_name": "Öğretmen haftalık notu",
                "verbose_name_plural": "Öğretmen haftalık notları",
            },
        ),
        migrations.AddConstraint(
            model_name="ogretmensinavnotu",
            constraint=models.UniqueConstraint(
                fields=("talebe", "etut_hocasi", "ders", "hafta_baslangic"),
                name="benzersiz_ogretmen_haftalik_not",
            ),
        ),
        migrations.CreateModel(
            name="OgretmenHaftalikKonu",
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
                ("hafta_baslangic", models.DateField(verbose_name="Hafta başlangıcı")),
                (
                    "konu",
                    models.CharField(
                        blank=True, max_length=300, verbose_name="İşlenen konu"
                    ),
                ),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "ders",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ogretmen_haftalik_konular",
                        to="takip.ders",
                        verbose_name="Ders",
                    ),
                ),
                (
                    "etut_hocasi",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="haftalik_konulari",
                        to="takip.etuthocasi",
                        verbose_name="Öğretmen",
                    ),
                ),
                (
                    "sinif_sube",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ogretmen_haftalik_konular",
                        to="takip.sinifsube",
                        verbose_name="Sınıf",
                    ),
                ),
            ],
            options={
                "verbose_name": "Öğretmen haftalık konu",
                "verbose_name_plural": "Öğretmen haftalık konular",
            },
        ),
        migrations.AddConstraint(
            model_name="ogretmenhaftalikkonu",
            constraint=models.UniqueConstraint(
                fields=("sinif_sube", "etut_hocasi", "ders", "hafta_baslangic"),
                name="benzersiz_ogretmen_haftalik_konu",
            ),
        ),
        migrations.CreateModel(
            name="OgretmenSinifYoklama",
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
                ("yok", models.BooleanField(default=True, verbose_name="Yok")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "etut_hocasi",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="girdigi_sinif_yoklamalari",
                        to="takip.etuthocasi",
                        verbose_name="Öğretmen",
                    ),
                ),
                (
                    "talebe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ogretmen_sinif_yoklamalari",
                        to="takip.talebe",
                        verbose_name="Talebe",
                    ),
                ),
            ],
            options={
                "verbose_name": "Öğretmen sınıf yoklaması",
                "verbose_name_plural": "Öğretmen sınıf yoklamaları",
                "ordering": ["-tarih", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="ogretmensinifyoklama",
            constraint=models.UniqueConstraint(
                fields=("talebe", "etut_hocasi", "tarih"),
                name="benzersiz_ogretmen_sinif_yoklama",
            ),
        ),
    ]
