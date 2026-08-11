"""Otomatik doldurulmuş dershane demo atamalarını temizle."""

from django.db import migrations


def temizle(apps, schema_editor):
    DershaneDersAtamasi = apps.get_model("takip", "DershaneDersAtamasi")
    DershaneProgramGun = apps.get_model("takip", "DershaneProgramGun")
    DershaneProgrami = apps.get_model("takip", "DershaneProgrami")

    DershaneDersAtamasi.objects.all().delete()
    for program in DershaneProgrami.objects.filter(aktif=True):
        for gun in range(7):
            DershaneProgramGun.objects.update_or_create(
                program=program,
                gun=gun,
                defaults={"durum": "bos"},
            )


def geri_al(apps, schema_editor):
    # Demo veri geri yüklenmez.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("takip", "0076_konu_sorusu_turu"),
    ]

    operations = [
        migrations.RunPython(temizle, geri_al),
    ]
