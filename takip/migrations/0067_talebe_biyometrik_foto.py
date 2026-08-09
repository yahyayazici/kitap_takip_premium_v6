from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0066_ktt_haric_talebeler"),
    ]

    operations = [
        migrations.AddField(
            model_name="talebe",
            name="biyometrik_foto",
            field=models.ImageField(
                blank=True,
                help_text="Vesikalık fotoğraf — profil ve not girişinde görünür.",
                null=True,
                upload_to="talebeler/biyometrik/",
                verbose_name="Biyometrik fotoğraf",
            ),
        ),
    ]
