from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0101_deneme_kazanim_sonucu"),
    ]

    operations = [
        migrations.CreateModel(
            name="KarsilamaSozu",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("metin", models.TextField(blank=True, verbose_name="Söz")),
                ("kaynak", models.CharField(blank=True, help_text="İsteğe bağlı. Hadis, kişi veya kitap adı.", max_length=160, verbose_name="Kaynak")),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Karşılama sözü",
                "verbose_name_plural": "Karşılama sözü",
            },
        ),
    ]
