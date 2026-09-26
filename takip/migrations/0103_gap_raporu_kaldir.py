from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0102_karsilama_sozu"),
    ]

    operations = [
        migrations.DeleteModel(name="DenemeKonuSonucu"),
        migrations.DeleteModel(name="DenemeGapRaporu"),
    ]
