from django.db import migrations

KEEP = {"talebeler", "ktt", "deneme", "kitap", "gunluk_takip"}


def sadece_bes_forward(apps, schema_editor):
    PanelKisayol = apps.get_model("takip", "PanelKisayol")
    PanelKisayol.objects.filter(goster_personel=True).exclude(
        anahtar__in=KEEP
    ).update(goster_personel=False)


def sadece_bes_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0098_panel_kisayol_sira_reorder"),
    ]

    operations = [
        migrations.RunPython(sadece_bes_forward, sadece_bes_backward),
    ]
