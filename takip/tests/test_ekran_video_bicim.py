"""Video biçimi denetimi.

Mac ve iPhone videoları .mov olarak gelir. İçindeki kodek H.264 ise
tarayıcılar sorunsuz oynatır; HEVC (H.265) ise televizyon tarayıcılarında
siyah kare olarak kalır. Bu yüzden HEVC yükleme anında reddedilir.
"""

from __future__ import annotations

import shutil
import struct
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from takip.ekran_media_service import (
    MedyaHatasi,
    dosya_turunu_belirle,
    medya_yukle,
    video_kodegi,
)
from takip.ekran_models import EkranMedya

GECICI = tempfile.mkdtemp(prefix="ekran-video-")


def sahte_video(kodek: bytes, uzanti_markasi: bytes = b"qt  ") -> bytes:
    """ISO taban biçiminde küçük bir dosya: ftyp imzası + kodek etiketi."""
    ftyp = struct.pack(">I", 24) + b"ftyp" + uzanti_markasi + b"\x00\x00\x02\x00" + b"mp42isom"
    # moov/stsd kutusunu taklit eden, kodek etiketini içeren dolgu
    govde = b"\x00" * 3000 + b"stsd" + b"\x00" * 8 + kodek + b"\x00" * 3000
    return ftyp + govde


@override_settings(MEDIA_ROOT=GECICI, EKRAN_MEDIA_ROOT=Path(GECICI))
class VideoBicimTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(GECICI, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("ekran_video", password="test-12345")

    # —— .mov kabulü ——

    def test_mov_uzantisi_video_olarak_taninir(self):
        dosya = SimpleUploadedFile("kayit.mov", sahte_video(b"avc1"))
        tur, uzanti, mime = dosya_turunu_belirle(dosya)
        self.assertEqual(tur, EkranMedya.Tur.VIDEO)
        self.assertEqual(uzanti, "mov")
        # Tarayıcıların oynatabilmesi için video/mp4 olarak servis edilir.
        self.assertEqual(mime, "video/mp4")

    def test_h264_mov_yuklenebilir(self):
        sonuc = medya_yukle(
            SimpleUploadedFile("tanitim.mov", sahte_video(b"avc1")),
            kullanici=self.user,
            video_sure_sn=12.5,
        )
        self.assertTrue(sonuc.yeni_mi)
        self.assertEqual(sonuc.medya.tur, EkranMedya.Tur.VIDEO)
        self.assertEqual(sonuc.medya.mime, "video/mp4")
        self.assertAlmostEqual(sonuc.medya.sure_sn, 12.5)

    # —— HEVC reddi ——

    def test_hevc_video_reddedilir(self):
        with self.assertRaises(MedyaHatasi) as kapsam:
            medya_yukle(
                SimpleUploadedFile("iphone.mov", sahte_video(b"hvc1")),
                kullanici=self.user,
            )
        mesaj = str(kapsam.exception)
        self.assertIn("HEVC", mesaj)
        # Kullanıcıya ne yapacağı söylenmeli, sadece "olmaz" denmemeli.
        self.assertIn("QuickTime", mesaj)
        self.assertIn("En Uyumlu", mesaj)

    def test_hevc_reddedilince_kayit_olusmaz(self):
        try:
            medya_yukle(
                SimpleUploadedFile("iphone2.mov", sahte_video(b"hev1")),
                kullanici=self.user,
            )
        except MedyaHatasi:
            pass
        self.assertEqual(EkranMedya.objects.count(), 0)

    # —— Kodek okuma ——

    def test_kodek_okuma(self):
        for etiket, beklenen in ((b"avc1", "h264"), (b"hvc1", "hevc"), (b"hev1", "hevc")):
            with self.subTest(etiket=etiket):
                dosya = SimpleUploadedFile("v.mov", sahte_video(etiket))
                self.assertEqual(video_kodegi(dosya), beklenen)

    def test_kodek_parca_sinirinda_kacmaz(self):
        """Etiket 1 MB'lik okuma sınırına denk gelirse de bulunmalı."""
        dolgu = b"\x00" * (1024 * 1024 - 2)
        ham = struct.pack(">I", 24) + b"ftyp" + b"qt  " + b"\x00" * 12 + dolgu + b"hvc1" + b"\x00" * 100
        self.assertEqual(video_kodegi(SimpleUploadedFile("s.mov", ham)), "hevc")

    def test_kodek_bilinmiyorsa_yukleme_engellenmez(self):
        """Etiket okunamıyorsa kullanıcıyı boş yere durdurmayalım."""
        ham = struct.pack(">I", 24) + b"ftyp" + b"qt  " + b"\x00" * 3000
        self.assertEqual(video_kodegi(SimpleUploadedFile("b.mov", ham)), "bilinmiyor")
        sonuc = medya_yukle(SimpleUploadedFile("bilinmeyen.mov", ham), kullanici=self.user)
        self.assertTrue(sonuc.yeni_mi)
