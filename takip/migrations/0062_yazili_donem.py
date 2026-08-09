from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0061_cuma_durum"),
    ]

    operations = [
        migrations.AddField(
            model_name="yazilisinav",
            name="donem",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Gerçek okul yazılıları için 1 veya 2. dönem",
                verbose_name="Dönem",
            ),
        ),
        migrations.AlterModelOptions(
            name="yazilisinav",
            options={
                "ordering": ["sinav_tarihi", "donem", "yazili_no", "id"],
                "verbose_name": "Yazılı sınav",
                "verbose_name_plural": "Yazılı sınavlar",
            },
        ),
    ]
