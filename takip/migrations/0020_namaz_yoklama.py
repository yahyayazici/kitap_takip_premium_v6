from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0019_ktt_hedef_siniflar"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NamazYoklamaOturum",
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
                    "vakit",
                    models.CharField(
                        choices=[
                            ("sabah", "Sabah"),
                            ("ogle", "Öğle"),
                            ("ikindi", "İkindi"),
                            ("aksam", "Akşam"),
                            ("yatsi", "Yatsı"),
                        ],
                        max_length=10,
                        verbose_name="Namaz vakti",
                    ),
                ),
                ("kaydedilme", models.DateTimeField(auto_now_add=True)),
                (
                    "kaydeden",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="kaydettigi_namaz_yoklamalari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Kaydeden",
                    ),
                ),
            ],
            options={
                "verbose_name": "Namaz yoklama oturumu",
                "verbose_name_plural": "Namaz yoklama oturumları",
                "ordering": ["-tarih", "vakit"],
            },
        ),
        migrations.CreateModel(
            name="NamazYoklamaKaydi",
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
                    "durum",
                    models.CharField(
                        choices=[
                            ("G", "Gelmedi"),
                            ("TT", "Takke & Tesbih Eksik"),
                            ("I", "İzinli"),
                        ],
                        max_length=2,
                        verbose_name="Durum",
                    ),
                ),
                (
                    "oturum",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="kayitlar",
                        to="takip.namazyoklamaoturum",
                        verbose_name="Oturum",
                    ),
                ),
                (
                    "talebe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="namaz_yoklama_kayitlari",
                        to="takip.talebe",
                        verbose_name="Talebe",
                    ),
                ),
            ],
            options={
                "verbose_name": "Namaz yoklama kaydı",
                "verbose_name_plural": "Namaz yoklama kayıtları",
            },
        ),
        migrations.AddConstraint(
            model_name="namazyoklamaoturum",
            constraint=models.UniqueConstraint(
                fields=("tarih", "vakit"), name="benzersiz_namaz_oturum"
            ),
        ),
        migrations.AddConstraint(
            model_name="namazyoklamakaydi",
            constraint=models.UniqueConstraint(
                fields=("oturum", "talebe"), name="benzersiz_namaz_talebe_kaydi"
            ),
        ),
    ]
