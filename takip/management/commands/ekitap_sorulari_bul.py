"""E-Kitap: hazır bölümlerde soru tespitini (yeniden) çalıştırır.

Tekrar çalıştırılması güvenlidir: onaylı/elle düzeltilmiş sorular korunur,
otomatik sorular yeniden oluşturulur, eksik soru görselleri üretilir.

    python manage.py ekitap_sorulari_bul              # tüm hazır bölümler
    python manage.py ekitap_sorulari_bul --kitap 3    # yalnızca bir kitap
    python manage.py ekitap_sorulari_bul --bolum 7 --bolum 8
    python manage.py ekitap_sorulari_bul --eksik      # yalnızca hiç tespit yapılmamışlar
    python manage.py ekitap_sorulari_bul --eksik --rozetsiz  # + rozet konumu hesaplanmamış eski tespitler
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from takip import ekitap_service as servis
from takip.ekitap_models import EKitapBolum, EKitapSoru


class Command(BaseCommand):
    help = "E-Kitap bölümlerinde soruları bulur (güvenle tekrar çalıştırılabilir)."

    def add_arguments(self, parser):
        parser.add_argument("--kitap", type=int, action="append", default=[])
        parser.add_argument("--bolum", type=int, action="append", default=[])
        parser.add_argument(
            "--eksik", action="store_true", help="Yalnızca tespiti hiç yapılmamış bölümler."
        )
        parser.add_argument(
            "--rozetsiz",
            action="store_true",
            help="Rozet konumu olmayan otomatik soruları bulunan bölümler (eski sürümle yapılmış tespit).",
        )

    def handle(self, *args, **opts):
        bolumler = EKitapBolum.objects.filter(islem_durumu=EKitapBolum.IslemDurumu.HAZIR)
        if opts["kitap"]:
            bolumler = bolumler.filter(kitap_id__in=opts["kitap"])
        if opts["bolum"]:
            bolumler = bolumler.filter(pk__in=opts["bolum"])
        if opts["eksik"] or opts["rozetsiz"]:
            kosul = Q()
            if opts["eksik"]:
                kosul |= Q(tespit_durumu=EKitapBolum.TespitDurumu.YOK)
            if opts["rozetsiz"]:
                kosul |= Q(pk__in=EKitapSoru.objects.filter(
                    kaynak=EKitapSoru.Kaynak.OTOMATIK, gizli=False, rozet_x__isnull=True
                ).values("bolum_id"))
            bolumler = bolumler.filter(kosul)
        bolumler = list(bolumler.select_related("kitap").order_by("kitap_id", "sira", "pk"))
        if not bolumler:
            self.stdout.write("İşlenecek bölüm yok.")
            return
        for bolum in bolumler:
            sonuc = servis.sorulari_bul(bolum.pk)
            bolum.refresh_from_db()
            kontrol = bolum.sayfalar.filter(kontrol_gerekli=True).count()
            self.stdout.write(
                f"{bolum.kitap.ad} · {bolum.ad}: {bolum.get_tespit_durumu_display()}"
                f" — {bolum.sorular.filter(gizli=False).count()} soru"
                + (f", {kontrol} sayfa kontrol bekliyor" if kontrol else "")
                + (f" ({bolum.tespit_notu})" if bolum.tespit_notu else "")
                + ("" if sonuc is not None else " [hata]")
            )
