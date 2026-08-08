# Generated manually for class-based yemekçilik

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0051_panel_goster_ogretmen"),
    ]

    operations = [
        migrations.CreateModel(
            name="YemekciAyar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hafta_sonu_cikar", models.BooleanField(default=True, help_text="Cumartesi/Pazar görev yazılmaz.", verbose_name="Hafta sonlarını çıkar")),
                ("dongu_baslangic", models.DateField(help_text="Gün indeksi bu tarihten itibaren sayılır.", verbose_name="Döngü başlangıç tarihi")),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Yemekçilik ayarı",
                "verbose_name_plural": "Yemekçilik ayarları",
            },
        ),
        migrations.CreateModel(
            name="YemekciSinifHavuzu",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sinif", models.CharField(max_length=4, unique=True, verbose_name="Sınıf")),
                ("renk", models.CharField(blank=True, max_length=20, verbose_name="Renk")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Yemekçi sınıf havuzu",
                "verbose_name_plural": "Yemekçi sınıf havuzları",
                "ordering": ["sinif"],
            },
        ),
        migrations.CreateModel(
            name="YemekciHavuzKaydi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sira", models.PositiveIntegerField(default=0, verbose_name="Sıra")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("havuz", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kayitlar", to="takip.yemekcisinifhavuzu", verbose_name="Havuz")),
                ("talebe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="yemekci_havuz_kayitlari", to="takip.talebe", verbose_name="Talebe")),
            ],
            options={
                "verbose_name": "Yemekçi havuz kaydı",
                "verbose_name_plural": "Yemekçi havuz kayıtları",
                "ordering": ["havuz__sinif", "sira", "id"],
            },
        ),
        migrations.CreateModel(
            name="YemekciGunAtama",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tarih", models.DateField(db_index=True, verbose_name="Tarih")),
                ("sinif", models.CharField(max_length=4, verbose_name="Sınıf")),
                ("manuel", models.BooleanField(default=False, help_text="True ise döngü hesabını ezer.", verbose_name="Manuel")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                ("olusturan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="olusturdugu_yemekci_gun_atamalari", to=settings.AUTH_USER_MODEL)),
                ("talebe", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="yemekci_gun_gorevleri", to="takip.talebe", verbose_name="Talebe")),
            ],
            options={
                "verbose_name": "Yemekçi gün ataması",
                "verbose_name_plural": "Yemekçi gün atamaları",
                "ordering": ["tarih", "sinif"],
            },
        ),
        migrations.AddConstraint(
            model_name="yemekcihavuzkaydi",
            constraint=models.UniqueConstraint(fields=("havuz", "talebe"), name="yemekci_havuz_talebe_tek"),
        ),
        migrations.AddConstraint(
            model_name="yemekcigunatama",
            constraint=models.UniqueConstraint(fields=("tarih", "sinif"), name="yemekci_gun_sinif_tek"),
        ),
    ]
