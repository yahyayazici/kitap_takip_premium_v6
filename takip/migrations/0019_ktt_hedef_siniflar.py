from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0018_dini_ders_takip"),
    ]

    operations = [
        migrations.AddField(
            model_name="kttsinav",
            name="hedef_siniflar",
            field=models.CharField(
                blank=True,
                help_text="Örn. 7-A, 7-B",
                max_length=200,
                verbose_name="Hedef sınıflar",
            ),
        ),
    ]
