from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0115_optik_form"),
    ]

    operations = [
        migrations.DeleteModel(name="DenemeOptik"),
        migrations.DeleteModel(name="OptikFormAlani"),
        migrations.DeleteModel(name="OptikForm"),
    ]
