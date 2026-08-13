# Generated manually for KTT akıllı takip

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0078_dini_ilerleme_motoru"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="KttEslestirmeEsik",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("yuksek_guven", models.PositiveSmallIntegerField(default=88, verbose_name="Yüksek güven (otomatik eşleştir)")),
                ("orta_guven", models.PositiveSmallIntegerField(default=72, verbose_name="Orta güven (inceleme öner)")),
                ("kapanma_gelisim_puan", models.PositiveSmallIntegerField(default=15, verbose_name="Eksik kapanma — min. gelişim puanı")),
                ("zayif_ktt_puan", models.PositiveSmallIntegerField(default=70, verbose_name="Zayıf KTT eşiği (puan altı)")),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "KTT eşleştirme eşiği",
                "verbose_name_plural": "KTT eşleştirme eşikleri",
            },
        ),
        migrations.CreateModel(
            name="KonuAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sinif_seviyesi", models.CharField(max_length=30, verbose_name="Sınıf seviyesi")),
                ("brans", models.CharField(max_length=20, verbose_name="Branş")),
                ("ham_normalize", models.CharField(help_text="Küçük harf, noktalama temizlenmiş eşleştirme anahtarı.", max_length=220, verbose_name="Normalize ham ifade")),
                ("onaylandi", models.BooleanField(default=True, verbose_name="Onaylı")),
                ("kullanim_sayisi", models.PositiveIntegerField(default=0, verbose_name="Kullanım sayısı")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("konu", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="konu_aliaslari", to="takip.konukatalogu", verbose_name="Standart konu")),
                ("olusturan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="olusturdugu_konu_aliaslari", to=settings.AUTH_USER_MODEL, verbose_name="Oluşturan")),
            ],
            options={
                "verbose_name": "Konu alias",
                "verbose_name_plural": "Konu aliasları",
                "ordering": ["sinif_seviyesi", "brans", "ham_normalize"],
            },
        ),
        migrations.AddConstraint(
            model_name="konualias",
            constraint=models.UniqueConstraint(fields=("sinif_seviyesi", "brans", "ham_normalize"), name="konu_alias_benzersiz"),
        ),
        migrations.CreateModel(
            name="KonuEslestirmeInceleme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sinif_seviyesi", models.CharField(max_length=30, verbose_name="Sınıf seviyesi")),
                ("brans", models.CharField(max_length=20, verbose_name="Branş")),
                ("ham_metin", models.CharField(max_length=200, verbose_name="Girilen konu")),
                ("ham_normalize", models.CharField(max_length=220, verbose_name="Normalize ham")),
                ("guven_yuzde", models.PositiveSmallIntegerField(default=0, verbose_name="Güven %")),
                ("durum", models.CharField(choices=[("bekliyor", "İnceleme bekliyor"), ("onaylandi", "Onaylandı"), ("reddedildi", "Reddedildi")], default="bekliyor", max_length=20, verbose_name="Durum")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                ("ktt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="konu_eslestirme_incelemeleri", to="takip.kttsinav", verbose_name="İlgili KTT")),
                ("onerilen_konu", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="eslestirme_incelemeleri", to="takip.konukatalogu", verbose_name="Önerilen standart konu")),
            ],
            options={
                "verbose_name": "Konu eşleştirme incelemesi",
                "verbose_name_plural": "Konu eşleştirme incelemeleri",
                "ordering": ["-olusturulma"],
            },
        ),
        migrations.CreateModel(
            name="KttEtutMudahale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mudahale_tarihi", models.DateField(verbose_name="Müdahale tarihi")),
                ("notlar", models.CharField(blank=True, max_length=300, verbose_name="Not")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("eksik", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ktt_mudahaleleri", to="takip.talebekonueksigi", verbose_name="Konu eksiği")),
                ("etut_hocasi", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ktt_mudahaleleri", to="takip.etuthocasi", verbose_name="Etüt hocası")),
                ("konu", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ktt_mudahaleleri", to="takip.konukatalogu", verbose_name="Standart konu")),
                ("olusturan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="kaydettigi_ktt_mudahaleleri", to=settings.AUTH_USER_MODEL, verbose_name="Kaydeden")),
                ("talebe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ktt_etut_mudahaleleri", to="takip.talebe", verbose_name="Talebe")),
                ("tetikleyen_sonuc", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tetikledigi_mudahaleler", to="takip.kttsonucu", verbose_name="Tetikleyen KTT sonucu")),
            ],
            options={
                "verbose_name": "KTT etüt müdahalesi",
                "verbose_name_plural": "KTT etüt müdahaleleri",
                "ordering": ["-mudahale_tarihi", "-id"],
            },
        ),
        migrations.AddField(
            model_name="kttsinav",
            name="eslestirme_guven",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Konu eşleştirme güveni (%)"),
        ),
        migrations.AddField(
            model_name="kttsinav",
            name="konu_ham_ad",
            field=models.CharField(blank=True, help_text="Etüt hocasının yazdığı orijinal ifade.", max_length=200, verbose_name="Ham konu adı"),
        ),
        migrations.AddField(
            model_name="kttsinav",
            name="konu_katalog",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ktt_sinavlari", to="takip.konukatalogu", verbose_name="Standart konu"),
        ),
        migrations.AddField(
            model_name="talebekonueksigi",
            name="gelisim_puan",
            field=models.SmallIntegerField(blank=True, null=True, verbose_name="Gelişim puanı"),
        ),
        migrations.AddField(
            model_name="talebekonueksigi",
            name="kapanma_skor",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name="Kapanma skoru"),
        ),
        migrations.AddField(
            model_name="talebekonueksigi",
            name="mudahale_durumu",
            field=models.CharField(
                choices=[
                    ("bekliyor", "Müdahale bekliyor"),
                    ("calisildi", "Etüt çalışması yapıldı"),
                    ("kapandi", "Eksik kapandı"),
                    ("takip", "Takip ediliyor"),
                ],
                default="bekliyor",
                max_length=20,
                verbose_name="Müdahale durumu",
            ),
        ),
        migrations.AddField(
            model_name="talebekonueksigi",
            name="son_ktt_sonuc",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tespit_ettigi_eksikler", to="takip.kttsonucu", verbose_name="Son tetikleyen KTT sonucu"),
        ),
    ]
