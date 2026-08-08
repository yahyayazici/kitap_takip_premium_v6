from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0057_personel_toplanti_gundem"),
    ]

    operations = [
        migrations.AddField(
            model_name="personeltoplantisi",
            name="katilimci_personeller",
            field=models.ManyToManyField(
                blank=True,
                related_name="katildigi_personel_toplantilari",
                to="takip.personelprofili",
                verbose_name="Katılımcılar",
            ),
        ),
        migrations.AlterField(
            model_name="personeltoplantisi",
            name="katilimcilar_metin",
            field=models.TextField(
                blank=True,
                help_text="Kullanımdan kalktı; katılımcı seçimi kullanın.",
                verbose_name="Katılımcılar (eski)",
            ),
        ),
    ]
