from django.db import migrations

ORDER = [
    "talebeler",
    "ktt",
    "deneme",
    "kitap",
    "gunluk_takip",
    "etut",
    "rehberlik",
    "veli_iletisim",
    "gorevler",
    "dosyalar",
    "takvim",
    "raporlar",
    "ayarlar",
]


def reorder_forward(apps, schema_editor):
    PanelKisayol = apps.get_model("takip", "PanelKisayol")
    for index, anahtar in enumerate(ORDER):
        PanelKisayol.objects.filter(anahtar=anahtar).update(sira=index * 10)


def reorder_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0097_akilli_tahta_dosya_merkezi"),
    ]

    operations = [
        migrations.RunPython(reorder_forward, reorder_backward),
    ]
