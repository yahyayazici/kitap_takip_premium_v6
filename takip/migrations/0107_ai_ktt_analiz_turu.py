# AI üretim önbelleğine KTT analizi türü eklendi (yalnızca seçenek değişikliği).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0106_sinif_seviye_mesulu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiuretimkaydi",
            name="tur",
            field=models.CharField(
                choices=[
                    ("gelisim_zekasi", "Gelişim Zekası"),
                    ("mudahale_oneri", "Müdahale Önerisi"),
                    ("veli_haftalik", "Veli Haftalık Özet"),
                    ("deneme_analiz", "Deneme Analizi"),
                    ("rehberlik_ozet", "Rehberlik Özeti"),
                    ("kurum_zekasi", "Kurum Zekası"),
                    ("soru_takip", "Soru Takip İçgörüsü"),
                    ("veli_takip", "Veli Takip Raporu"),
                    ("ktt_analiz", "KTT Analizi"),
                ],
                max_length=32,
                verbose_name="Tür",
            ),
        ),
    ]
