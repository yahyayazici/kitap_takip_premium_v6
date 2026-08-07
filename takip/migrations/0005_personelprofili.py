from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def personel_profillerini_olustur(apps, schema_editor):
    User = apps.get_model("auth", "User")
    EtutHocasi = apps.get_model("takip", "EtutHocasi")
    PersonelProfili = apps.get_model("takip", "PersonelProfili")

    for hoca in EtutHocasi.objects.select_related("user").iterator():
        PersonelProfili.objects.update_or_create(
            user_id=hoca.user_id,
            defaults={
                "ad_soyad": hoca.ad_soyad,
                "ana_rol": "etut_mesul",
                "etut_hocasi_id": hoca.pk,
                "aktif": hoca.aktif,
            },
        )

    for user in User.objects.filter(is_superuser=True).iterator():
        ad = user.first_name or user.username
        PersonelProfili.objects.update_or_create(
            user_id=user.pk,
            defaults={
                "ad_soyad": ad,
                "ana_rol": "idareci",
                "etut_hocasi_id": None,
                "aktif": user.is_active,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0004_alter_sinifsube_sinif_alter_sinifsube_sube"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonelProfili",
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
                    "ad_soyad",
                    models.CharField(max_length=120, verbose_name="Ad soyad"),
                ),
                (
                    "ana_rol",
                    models.CharField(
                        choices=[
                            ("idareci", "İdareci"),
                            ("ic_mesul", "İç Mesul"),
                            ("egitim_mesul", "Eğitim Mesulü"),
                            ("etut_mesul", "Etüt Mesulü"),
                            ("sinif_mesul", "Sınıf Mesulü"),
                            ("muhasebeci", "Muhasebeci"),
                            ("nehari_mesul", "Nehari Mesulü"),
                            ("mahal_sorumlusu", "Mahal Sorumlusu"),
                        ],
                        default="etut_mesul",
                        max_length=30,
                        verbose_name="Ana rol",
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
                    "etut_hocasi",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="personel_kaydi",
                        to="takip.etuthocasi",
                        verbose_name="Etüt hocası kaydı",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="personel_profili",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Kullanıcı hesabı",
                    ),
                ),
            ],
            options={
                "verbose_name": "Personel profili",
                "verbose_name_plural": "Personel profilleri",
                "ordering": ["ad_soyad"],
            },
        ),
        migrations.RunPython(
            personel_profillerini_olustur,
            migrations.RunPython.noop,
        ),
    ]
