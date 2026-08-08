# Generated manually

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0055_yazili_puan_ders_hedef"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonelToplantisi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("toplanti_no", models.CharField(max_length=32, unique=True, verbose_name="Toplantı no")),
                ("baslik", models.CharField(max_length=200, verbose_name="Toplantı başlığı")),
                ("tarih", models.DateField(verbose_name="Tarih")),
                ("saat", models.TimeField(blank=True, null=True, verbose_name="Saat")),
                ("yer", models.CharField(blank=True, max_length=200, verbose_name="Yer")),
                ("katilimcilar_metin", models.TextField(blank=True, help_text="Her satır: Ad Soyad · görev", verbose_name="Katılımcılar")),
                ("gundem_ozet", models.TextField(blank=True, verbose_name="Gündem özeti")),
                ("gizli_notlar", models.TextField(blank=True, help_text="Yalnızca yönetim ekranında görünür; PDF'e dahil edilmez.", verbose_name="Sekreter / gizli notlar")),
                ("genel_degerlendirme", models.TextField(blank=True, verbose_name="Genel değerlendirme")),
                ("durum", models.CharField(choices=[("taslak", "Taslak"), ("tamamlandi", "Tamamlandı")], default="taslak", max_length=16, verbose_name="Durum")),
                ("tutanak_pdf", models.FileField(blank=True, null=True, upload_to="personel_toplanti/tutanaklar/", verbose_name="Tutanak PDF")),
                ("arsivlandi", models.BooleanField(default=False, verbose_name="Arşivlendi")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                ("baskan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="baskanlik_ettigi_toplantilar", to="takip.personelprofili", verbose_name="Toplantı başkanı")),
                ("olusturan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="olusturdugu_personel_toplantilari", to=settings.AUTH_USER_MODEL, verbose_name="Oluşturan")),
                ("sekreter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sekreterlik_ettigi_toplantilar", to="takip.personelprofili", verbose_name="Sekreter")),
            ],
            options={
                "verbose_name": "Personel toplantısı",
                "verbose_name_plural": "Personel toplantıları",
                "ordering": ["-tarih", "-id"],
            },
        ),
        migrations.CreateModel(
            name="PersonelToplantiKarar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sira", models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")),
                ("tur", models.CharField(choices=[("karar", "Karar"), ("yapilacak", "Yapılacak"), ("takip", "Takip edilecek")], default="karar", max_length=12, verbose_name="Tür")),
                ("metin", models.TextField(verbose_name="Metin")),
                ("kontrol_tarihi", models.DateField(blank=True, null=True, verbose_name="Takip / son tarih")),
                ("durum", models.CharField(choices=[("bekliyor", "Bekliyor"), ("devam", "Devam ediyor"), ("tamam", "Tamamlandı"), ("iptal", "İptal")], default="bekliyor", max_length=12, verbose_name="Durum")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                ("sorumlu", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="toplanti_kararlari", to="takip.personelprofili", verbose_name="Sorumlu personel")),
                ("toplanti", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kararlar", to="takip.personeltoplantisi", verbose_name="Toplantı")),
                ("vazife", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="toplanti_kaynaklari", to="takip.personelvazife", verbose_name="Oluşan vazife")),
            ],
            options={
                "verbose_name": "Toplantı kararı",
                "verbose_name_plural": "Toplantı kararları",
                "ordering": ["sira", "id"],
            },
        ),
        migrations.AddField(
            model_name="personelvazife",
            name="toplanti_karar",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bagli_vazifeler", to="takip.personeltoplantikarar", verbose_name="Toplantı kararı"),
        ),
    ]
