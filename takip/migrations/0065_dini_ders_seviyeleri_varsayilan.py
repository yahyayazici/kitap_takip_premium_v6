from django.db import migrations


def dini_ders_seviyeleri_olustur(apps, schema_editor):
    DiniDersSeviyesi = apps.get_model("takip", "DiniDersSeviyesi")
    for ad, sira in [
        ("Seviye 1", 1),
        ("Seviye 2", 2),
        ("Seviye 3", 3),
        ("Seviye 4", 4),
    ]:
        obj, _ = DiniDersSeviyesi.objects.get_or_create(
            ad=ad,
            defaults={"sira": sira, "aktif": True},
        )
        if not obj.aktif or obj.sira != sira:
            obj.sira = sira
            obj.aktif = True
            obj.save(update_fields=["sira", "aktif"])


class Migration(migrations.Migration):
    dependencies = [
        ("takip", "0064_pazar_izin_donus"),
    ]

    operations = [
        migrations.RunPython(dini_ders_seviyeleri_olustur, migrations.RunPython.noop),
    ]
