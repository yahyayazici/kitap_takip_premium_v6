from django.db import migrations


def sil_forward(apps, schema_editor):
    """Öğrenci aidat / finans kayıtlarını sil. Öğretmen ödeme tablolarına dokunma."""
    modeller = [
        "FinansTahsilat",
        "FinansIslemLog",
        "FinansTaksit",
        "TalebeFinansDosyasi",
        "FinansKampanya",
        "FinansIndirim",
        "FinansUcretPolitikasi",
        "AidatTahsilat",
        "TalebeAidatKaydi",
        "AidatTanim",
    ]
    for ad in modeller:
        try:
            Model = apps.get_model("takip", ad)
        except LookupError:
            continue
        Model.objects.all().delete()

    try:
        VeliIcerikGoruntuleme = apps.get_model("takip", "VeliIcerikGoruntuleme")
    except LookupError:
        return
    VeliIcerikGoruntuleme.objects.filter(tur="aidat").delete()
    VeliIcerikGoruntuleme.objects.filter(sayfa="veli_talebe_aidat").delete()


def sil_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0099_panel_kisayol_sadece_5"),
    ]

    operations = [
        migrations.RunPython(sil_forward, sil_backward),
    ]
