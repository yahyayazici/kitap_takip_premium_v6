import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0104_kaldirilan_sayfa_tablolari"),
    ]

    operations = [
        migrations.CreateModel(
            name="DenemeSoruSonucu",
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
                ("ders_ad", models.CharField(max_length=120, verbose_name="Ders")),
                ("ders_key", models.CharField(db_index=True, max_length=120)),
                ("soru_no", models.PositiveSmallIntegerField(verbose_name="Soru no")),
                ("konu_ad", models.CharField(blank=True, max_length=300, verbose_name="Konu")),
                (
                    "sonuc",
                    models.CharField(
                        choices=[("dogru", "Doğru"), ("yanlis", "Yanlış"), ("bos", "Boş")],
                        max_length=10,
                        verbose_name="Sonuç",
                    ),
                ),
                ("sira", models.PositiveIntegerField(default=0)),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                (
                    "deneme",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="soru_sonuclari",
                        to="takip.denemesinavi",
                        verbose_name="Deneme",
                    ),
                ),
                (
                    "talebe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deneme_soru_sonuclari",
                        to="takip.talebe",
                        verbose_name="Talebe",
                    ),
                ),
            ],
            options={
                "verbose_name": "Deneme soru sonucu",
                "verbose_name_plural": "Deneme soru sonuçları",
                "ordering": ["sira", "ders_ad", "soru_no", "id"],
                "indexes": [
                    models.Index(fields=["deneme", "talebe"], name="takip_denem_deneme__soru_t_idx"),
                    models.Index(
                        fields=["deneme", "ders_key", "soru_no"],
                        name="takip_denem_deneme__soru_d_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("deneme", "talebe", "ders_key", "soru_no"),
                        name="deneme_soru_benzersiz",
                    )
                ],
            },
        ),
    ]
