from django.db import migrations, models


def bayraklari_ayir(apps, schema_editor):
    Ayar = apps.get_model("takip", "YemekciAyar")
    for ayar in Ayar.objects.all():
        ayar.cumartesi_cikar = ayar.hafta_sonu_cikar
        ayar.pazar_cikar = ayar.hafta_sonu_cikar
        ayar.save(update_fields=["cumartesi_cikar", "pazar_cikar"])


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0114_nehari_gunluk_odev"),
    ]

    operations = [
        migrations.AddField(
            model_name="yemekciayar",
            name="cumartesi_cikar",
            field=models.BooleanField(
                default=True,
                help_text="İşaretliyse cumartesi gününe görev yazılmaz.",
                verbose_name="Cumartesiyi çıkar",
            ),
        ),
        migrations.AddField(
            model_name="yemekciayar",
            name="pazar_cikar",
            field=models.BooleanField(
                default=True,
                help_text="İşaretliyse pazar gününe görev yazılmaz.",
                verbose_name="Pazarı çıkar",
            ),
        ),
        migrations.RunPython(bayraklari_ayir, migrations.RunPython.noop),
    ]
