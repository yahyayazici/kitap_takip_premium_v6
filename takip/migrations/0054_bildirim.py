from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("takip", "0053_programsatir_uyku_turu"),
    ]

    operations = [
        migrations.CreateModel(
            name="Bildirim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("baslik", models.CharField(max_length=200, verbose_name="Başlık")),
                ("mesaj", models.TextField(blank=True, verbose_name="Mesaj")),
                (
                    "tur",
                    models.CharField(
                        choices=[
                            ("genel", "Genel"),
                            ("vazife", "Vazife"),
                            ("duyuru", "Duyuru"),
                            ("program", "Program"),
                            ("sistem", "Sistem"),
                        ],
                        default="genel",
                        max_length=20,
                        verbose_name="Tür",
                    ),
                ),
                ("link", models.CharField(blank=True, max_length=500, verbose_name="Bağlantı")),
                (
                    "bitis",
                    models.DateField(
                        blank=True,
                        help_text="Doluysa bu tarihe kadar aktif bildirim sayılır.",
                        null=True,
                        verbose_name="Geçerlilik (şu güne kadar)",
                    ),
                ),
                ("okundu", models.BooleanField(default=False, verbose_name="Okundu")),
                ("okunma_zamani", models.DateTimeField(blank=True, null=True)),
                ("email_gonderildi", models.BooleanField(default=False)),
                ("kaynak_model", models.CharField(blank=True, max_length=80)),
                ("kaynak_id", models.PositiveIntegerField(blank=True, null=True)),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                (
                    "alici",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bildirimler",
                        to="auth.user",
                        verbose_name="Alıcı",
                    ),
                ),
                (
                    "olusturan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gonderdigi_bildirimler",
                        to="auth.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Bildirim",
                "verbose_name_plural": "Bildirimler",
                "ordering": ["-olusturulma", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="bildirim",
            index=models.Index(fields=["alici", "okundu", "-olusturulma"], name="takip_bildi_alici_i_7c8a1d_idx"),
        ),
        migrations.AddIndex(
            model_name="bildirim",
            index=models.Index(fields=["alici", "bitis"], name="takip_bildi_alici_i_2f9b0e_idx"),
        ),
    ]
