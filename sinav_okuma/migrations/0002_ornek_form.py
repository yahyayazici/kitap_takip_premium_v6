from django.db import migrations


def ornek_formu_ekle(apps, schema_editor):
    Form = apps.get_model("sinav_okuma", "OptikForm")
    Alan = apps.get_model("sinav_okuma", "OptikFormAlani")
    from sinav_okuma.okuma import (
        ORNEK_ALANLAR,
        ORNEK_FORM_ACIKLAMA,
        ORNEK_FORM_AD,
        ORNEK_KODLAMA,
        ORNEK_SATIR,
    )

    if Form.objects.filter(ad=ORNEK_FORM_AD).exists():
        return
    form = Form.objects.create(
        ad=ORNEK_FORM_AD,
        aciklama=ORNEK_FORM_ACIKLAMA,
        satir_uzunluk=ORNEK_SATIR,
        kodlama=ORNEK_KODLAMA,
    )
    Alan.objects.bulk_create(
        [
            Alan(form=form, tur=tur, baslangic=bas, bitis=bit, sira=sira)
            for sira, (tur, bas, bit) in enumerate(ORNEK_ALANLAR)
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("sinav_okuma", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ornek_formu_ekle, migrations.RunPython.noop),
    ]
