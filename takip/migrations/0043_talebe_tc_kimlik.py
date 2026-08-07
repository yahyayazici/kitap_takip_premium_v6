from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0042_rehber_ogretmeni_rol"),
    ]

    operations = [
        migrations.AddField(
            model_name="talebe",
            name="tc_kimlik",
            field=models.CharField(
                blank=True,
                max_length=11,
                verbose_name="TC kimlik no",
            ),
        ),
    ]
