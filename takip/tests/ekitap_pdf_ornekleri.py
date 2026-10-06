"""Soru tespiti testleri için gerçekçi deneme kitapçığı PDF'leri üretir (reportlab).

Gerçek kitapçıklarda karşılaşılan durumlar:
- iki sütunlu sayfa, kalın soru numaraları,
- kapakta "7. Sınıf" gibi satır başında numara,
- soru içinde girintili "1. 2. 3." maddeleri, "2.5 kg" gibi ondalık satırlar,
- şekil (dikdörtgen + çizgiler), her sayfada tekrar eden üst bant ve sayfa numarası,
- sayfanın son sorusunun bir sonraki sayfada devam etmesi,
- aynı bölümde ikinci testte numaraların 1'den yeniden başlaması,
- atlanmış numara (8 yok),
- yalnızca görselden oluşan (taranmış) sayfa ve tamamen taranmış PDF.
"""

from __future__ import annotations

import io

A4_G, A4_Y = 595.2756, 841.8898
SOL_X = (50, 50 + A4_G / 2)


def _ust_bant(c, baslik: str) -> None:
    c.setFillColorRGB(0.07, 0.24, 0.55)
    c.rect(0, A4_Y - 46, A4_G, 46, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, A4_Y - 30, "7. SINIF KURUMSAL DENEME")
    c.drawRightString(A4_G - 40, A4_Y - 30, baslik)
    c.setFillColorRGB(0, 0, 0)
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.line(A4_G / 2, 60, A4_G / 2, A4_Y - 70)


def _sayfa_no(c, no: int) -> None:
    c.setFont("Helvetica", 9)
    c.drawCentredString(A4_G / 2, 28, str(no))


def _soru(c, sutun: int, y: float, no: int, *, satir: int = 5, sekil: bool = False,
          maddeler: bool = False, ondalik: bool = False, sik: bool = True) -> float:
    """Soruyu çizer, alt sınırının y değerini döner."""
    x = SOL_X[sutun]
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, f"{no}.")
    c.setFont("Helvetica", 10)
    yy = y
    for i in range(satir):
        c.drawString(x + 22, yy, "Asagidaki ifadelerden hangisi dogrudur? Ornek metin"[: 40 + i])
        yy -= 14
    if maddeler:
        for m in range(1, 4):
            c.drawString(x + 34, yy, f"{m}. madde: kisa bir ifade")
            yy -= 14
    if ondalik:
        c.drawString(x + 22, yy, "2.5 kg un fiyati 30 TL ise")
        yy -= 14
    if sekil:
        c.rect(x + 30, yy - 70, 170, 64)
        c.line(x + 30, yy - 70, x + 200, yy - 6)
        c.circle(x + 115, yy - 38, 18)
        yy -= 80
    if sik:
        for harf in "ABCD":
            c.drawString(x + 22, yy, f"{harf}) secenek {harf.lower()}")
            yy -= 14
    return yy


def deneme_pdf() -> bytes:
    """7 sayfalık metinli kitapçık. Beklenen sorular:

    Test 1 (Matematik): 1–15 — 11. soru 3. sayfanın sonunda başlar, 4. sayfada devam eder.
    Test 2 (Fen): 1–7, 9 (8 atlanmış) — 6. sayfada.
    7. sayfa yalnızca görselden oluşur (taranmış).
    """
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=(A4_G, A4_Y))

    # 1 — kapak
    c.setFillColorRGB(0.07, 0.24, 0.55)
    c.rect(0, 0, A4_G, A4_Y, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(A4_G / 2, A4_Y / 2 + 40, "7. Sinif Deneme 1")
    c.setFont("Helvetica", 18)
    c.drawString(80, A4_Y / 2 - 20, "1. Oturum: Sayisal")
    c.drawString(80, A4_Y / 2 - 50, "2. Oturum: Sozel")
    c.showPage()

    # 2 — Matematik 1–6 (2: iç maddeler, 3: şekil, 5: ondalık)
    _ust_bant(c, "MATEMATIK")
    c.setFont("Helvetica-Bold", 15)
    c.drawString(50, A4_Y - 80, "MATEMATIK TESTI")
    c.setFont("Helvetica", 9)
    c.drawString(50, A4_Y - 94, "Bu testte 15 soru vardir.")
    y = A4_Y - 125
    y = _soru(c, 0, y, 1) - 26
    y = _soru(c, 0, y, 2, maddeler=True) - 26
    _soru(c, 0, y, 3, satir=3, sekil=True)
    y = A4_Y - 90
    y = _soru(c, 1, y, 4) - 26
    y = _soru(c, 1, y, 5, ondalik=True) - 26
    _soru(c, 1, y, 6)
    _sayfa_no(c, 2)
    c.showPage()

    # 3 — 7–11; 11. sorunun şıkları 4. sayfada
    _ust_bant(c, "MATEMATIK")
    y = A4_Y - 90
    y = _soru(c, 0, y, 7, satir=6) - 30
    y = _soru(c, 0, y, 8, sekil=True) - 30
    y = A4_Y - 90
    y = _soru(c, 1, y, 9) - 30
    y = _soru(c, 1, y, 10, satir=6) - 30
    _soru(c, 1, y, 11, satir=6, sekil=True, sik=False)
    _sayfa_no(c, 3)
    c.showPage()

    # 4 — 11'in devamı (şıklar) + 12–15
    _ust_bant(c, "MATEMATIK")
    c.setFont("Helvetica", 10)
    yy = A4_Y - 90
    for harf in "ABCD":
        c.drawString(SOL_X[0] + 22, yy, f"{harf}) devam eden secenek {harf.lower()}")
        yy -= 14
    y = yy - 40
    y = _soru(c, 0, y, 12) - 30
    _soru(c, 0, y, 13)
    y = A4_Y - 90
    y = _soru(c, 1, y, 14, sekil=True) - 30
    _soru(c, 1, y, 15)
    _sayfa_no(c, 4)
    c.showPage()

    # 5 — Fen 1–6 (numaralar yeniden başlar)
    _ust_bant(c, "FEN BILIMLERI")
    c.setFont("Helvetica-Bold", 15)
    c.drawString(50, A4_Y - 80, "FEN BILIMLERI TESTI")
    y = A4_Y - 115
    y = _soru(c, 0, y, 1) - 30
    y = _soru(c, 0, y, 2, sekil=True) - 30
    _soru(c, 0, y, 3)
    y = A4_Y - 90
    y = _soru(c, 1, y, 4) - 30
    y = _soru(c, 1, y, 5, maddeler=True) - 30
    _soru(c, 1, y, 6)
    _sayfa_no(c, 5)
    c.showPage()

    # 6 — 7 ve 9 (8 atlanmış)
    _ust_bant(c, "FEN BILIMLERI")
    _soru(c, 0, A4_Y - 90, 7, satir=8)
    _soru(c, 1, A4_Y - 90, 9, satir=8)
    _sayfa_no(c, 6)
    c.showPage()

    # 7 — taranmış sayfa (yalnızca görsel)
    c.drawImage(ImageReader(_taranmis_gorsel(3)), 0, 0, width=A4_G, height=A4_Y)
    c.showPage()

    c.save()
    return tampon.getvalue()


def _taranmis_gorsel(sayfa_no: int):
    """Taranmış kitapçık sayfası: yazı katmanı yok, yalnızca piksel (2 px/pt).

    OCR'ın okuyabileceği gerçek yazı (reportlab ile gelen Vera yazı tipi) ve
    her soruda bir şekil içerir.
    """
    import os

    import reportlab
    from PIL import Image, ImageDraw, ImageFont

    yazi_yolu = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    kalin = ImageFont.truetype(os.path.join(yazi_yolu, "VeraBd.ttf"), 26)
    duz = ImageFont.truetype(os.path.join(yazi_yolu, "Vera.ttf"), 21)
    olcek = 2
    g = Image.new("L", (int(A4_G * olcek), int(A4_Y * olcek)), 250)
    d = ImageDraw.Draw(g)
    for sutun in range(2):
        for k in range(3):
            x = int(SOL_X[sutun] * olcek)
            y = int((90 + k * 240) * olcek)
            no = (sayfa_no - 1) * 6 + sutun * 3 + k + 1
            d.text((x, y), f"{no}.", font=kalin, fill=10)
            for satir in range(3):
                d.text((x + 44, y + 2 + satir * 30), "Which statement below is correct here"[: 30 + satir],
                       font=duz, fill=20)
            d.rectangle((x + 60, y + 100, x + 380, y + 200), outline=40, width=3)
            d.line((x + 60, y + 200, x + 380, y + 100), fill=40, width=3)
            for i, harf in enumerate("ABCD"):
                d.text((x + 44, y + 220 + i * 30), f"{harf}) option {harf.lower()}", font=duz, fill=20)
    tampon = io.BytesIO()
    g.save(tampon, format="PNG")
    tampon.seek(0)
    return tampon


def taranmis_pdf(sayfa: int = 2) -> bytes:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=(A4_G, A4_Y))
    for i in range(sayfa):
        c.drawImage(ImageReader(_taranmis_gorsel(i + 1)), 0, 0, width=A4_G, height=A4_Y)
        c.showPage()
    c.save()
    return tampon.getvalue()


def karisik_duzen_pdf() -> bytes:
    """Gerçek kitapçıktaki düzen: numaralar sütunun en kenarında, dar oluk.

    1. sayfa sütun sütun okunur (1, 2 solda; 3 sağda, uzun).
    2. sayfa satır satır okunur (4 | 5 üstte, yatay çizgi, 6 | 7 altta).
    Üstte numaralı yönergeler ("1. Bu testte 20 soru vardır."), altta
    "1. Deneme · Sayısal Bölüm" alt bilgisi vardır; ikisi de soru değildir.
    Şıklar daire içinde harf olarak çizilir ("A)" yazısı yoktur).
    """
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=(A4_G, A4_Y))
    NX = (22, 22 + A4_G / 2)  # numara x
    TX = (44, 44 + A4_G / 2)  # metin x

    def bant(sayfa_no):
        c.setFillColorRGB(0.95, 0.96, 0.98)
        c.rect(0, A4_Y - 40, A4_G, 40, fill=1, stroke=0)
        c.setFillColorRGB(0.1, 0.15, 0.35)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(22, A4_Y - 22, "Cinili Saray Ogrenci Yurdu")
        c.setFont("Helvetica", 8)
        c.drawString(22, A4_Y - 32, "7. Sinif Kurumsal Deneme - 1. Deneme")
        c.drawRightString(A4_G - 22, A4_Y - 24, "Matematik")
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 7)
        c.drawString(22, 24, "1. Deneme - Sayisal Bolum")
        c.drawCentredString(A4_G / 2, 24, str(sayfa_no))
        c.drawRightString(A4_G - 22, 24, "A Kitapcigi")
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(A4_G / 2, 50, A4_G / 2, A4_Y - 60)

    def soru(sutun, y, no, satir=4, sekil=False):
        c.setFillColorRGB(0.1, 0.3, 0.7)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(NX[sutun], y, f"{no}.")
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 9)
        yy = y
        for i in range(satir):
            c.drawString(TX[sutun], yy, "Ece sinifta oynanan oyunda kartlari sececektir. Kartlar"[: 46 + i % 3])
            yy -= 13
        if sekil:
            c.rect(TX[sutun] + 10, yy - 70, 200, 62)
            yy -= 80
        c.setFont("Helvetica-Bold", 9)
        c.drawString(TX[sutun], yy, "Buna gore hangisi dogrudur?")
        yy -= 18
        c.setFont("Helvetica", 9)
        for i, harf in enumerate("ABCD"):
            x = TX[sutun] + (i % 2) * 120
            if i == 2:
                yy -= 18
            c.circle(x + 5, yy + 3, 6)
            c.drawCentredString(x + 5, yy, harf)
            c.drawString(x + 16, yy, f"secenek {harf.lower()}")
        return yy

    # 1. sayfa: sütun sütun
    bant(2)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(22, A4_Y - 78, "MATEMATIK")
    c.setFont("Helvetica", 7)
    c.drawRightString(A4_G / 2 - 12, A4_Y - 70, "1. Bu testte 20 soru vardir.")
    c.drawRightString(A4_G / 2 - 12, A4_Y - 80, "2. Cevaplarinizi cevap kagidina isaretleyiniz.")
    soru(0, A4_Y - 120, 1, satir=3)
    c.line(14, A4_Y / 2 + 20, A4_G / 2 - 10, A4_Y / 2 + 20)
    soru(0, A4_Y / 2, 2, satir=4, sekil=True)
    soru(1, A4_Y - 120, 3, satir=4, sekil=True)
    c.showPage()

    # 2. sayfa: satır satır
    bant(3)
    soru(0, A4_Y - 80, 4, satir=7, sekil=True)
    soru(1, A4_Y - 80, 5, satir=2, sekil=True)
    c.line(14, A4_Y / 2 + 30, A4_G - 14, A4_Y / 2 + 30)
    soru(0, A4_Y / 2, 6, satir=3, sekil=True)
    soru(1, A4_Y / 2, 7, satir=2)
    c.showPage()
    c.save()
    return tampon.getvalue()


def ortak_bilgili_pdf() -> bytes:
    """Beceri temelli test düzeni.

    1. sayfa: 1. soru tam genişlik (şekilli); altında iki sütun: 2 solda, 3 sağda.
       2 ve 3 aynı yükseklikte başlar ve iki sütunun satırları TEK yazı bloğunda
       yazılır (PDF'te tek satır gibi görünür).
    2. sayfa: "4, 5 ve 6. soruları aşağıda verilen bilgi ile cevaplayınız."
       başlığı, bilgi metni, görsel ve tablo; ardından 4, 5, 6 ve 7. sorular.
    """
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=(A4_G, A4_Y))
    SOL, ORTA = 40, A4_G / 2 + 10

    def ust(no):
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(A4_G / 2, A4_Y - 40, "Tam Sayilarla Islemler")
        c.setFont("Helvetica", 8)
        c.drawRightString(A4_G - 40, 30, str(no))

    def numara(x, y, no):
        c.setFillColorRGB(0.1, 0.3, 0.7)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y, f"{no}.")
        c.setFillColorRGB(0, 0, 0)

    def siklar(x, y, adim=110):
        c.setFont("Helvetica", 9)
        for i, h in enumerate("ABCD"):
            c.drawString(x + i * adim, y, f"{h}) {(i + 1) * 12}")

    # —— 1. sayfa
    ust(53)
    numara(SOL, A4_Y - 80, 1)
    c.setFont("Helvetica", 9)
    for i in range(2):
        c.drawString(SOL + 16, A4_Y - 80 - i * 12, "Iki cubuk, ardisik tam sayilar arasi uzakligin 1 cm oldugu bir sayi dogrusuna")
    c.line(SOL + 30, A4_Y - 130, A4_G - 60, A4_Y - 130)
    c.rect(SOL + 80, A4_Y - 150, 200, 10)
    c.drawString(SOL + 16, A4_Y - 180, "Buna gore K ve L noktalarina karsilik gelen tam sayilarin carpimi kactir?")
    siklar(SOL + 16, A4_Y - 198)
    # 2 ve 3: iki sütunun satırları tek yazı bloğunda
    y0 = A4_Y / 2 + 40
    numara(SOL, y0, 2)
    numara(ORTA, y0, 3)
    t = c.beginText()
    t.setFont("Helvetica", 9)
    sol_satirlar = ["Asagida ayri renklerdeki kartlarin", "uzerinde ayni tam sayilarin yazili", "oldugu kirmizi, mavi ve sari kartlar"]
    sag_satirlar = ["Asagidaki termometrenin uzerine", "bir zincir yerlestirilmistir. Bu", "zincirin sag ucu -2 sayisinin"]
    for i in range(3):
        t.setTextOrigin(SOL + 16, y0 - i * 12)
        t.textOut(sol_satirlar[i])
        t.moveCursor(ORTA + 16 - (SOL + 16), 0)
        t.textOut(sag_satirlar[i])
    c.drawText(t)
    c.rect(SOL + 20, y0 - 120, 180, 80)
    c.rect(ORTA + 30, y0 - 150, 60, 110)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(SOL + 16, y0 - 140, "Buna gore toplam kactir?")
    c.drawString(ORTA + 16, y0 - 170, "Zincirin sol ucu hangi sayidadir?")
    siklar(SOL + 16, y0 - 158, 55)
    siklar(ORTA + 16, y0 - 188, 55)
    c.showPage()

    # —— 2. sayfa: ortak bilgili grup
    ust(54)
    c.rect(SOL, A4_Y - 82, A4_G - 2 * SOL, 18)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(A4_G / 2, A4_Y - 77, "4, 5 ve 6. sorulari asagida verilen bilgi ile cevaplayiniz.")
    c.setFont("Helvetica", 9)
    for i in range(3):
        c.drawString(SOL, A4_Y - 105 - i * 12, "Fatih ile Mehmet, asagidaki labutlara top atacaklari bir oyun oynayacaklardir. Bu oyuna gore"[: 88 - i])
    for i in range(8):
        c.circle(SOL + 60 + i * 50, A4_Y - 175, 14)
    c.rect(SOL + 120, A4_Y - 260, 220, 50)
    c.line(SOL + 120, A4_Y - 235, SOL + 340, A4_Y - 235)
    yy = A4_Y - 300
    for no in (4, 5, 6, 7):
        numara(SOL, yy, no)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(SOL + 16, yy, "Oyun sonunda Fatih ile Mehmet'in puanlarinin toplami kac olur?")
        siklar(SOL + 16, yy - 20)
        yy -= 90
    c.showPage()
    c.save()
    return tampon.getvalue()


def taranmis_kopya(pdf: bytes, olcek: float = 2.0) -> bytes:
    """Metinli PDF'in sayfalarını görsele çevirip yazı katmanı olmayan PDF üretir."""
    import pypdfium2 as pdfium
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    belge = pdfium.PdfDocument(pdf)
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=(A4_G, A4_Y))
    for i in range(len(belge)):
        gorsel = belge[i].render(scale=olcek).to_pil().convert("L")
        b = io.BytesIO()
        gorsel.save(b, format="PNG")
        b.seek(0)
        c.drawImage(ImageReader(b), 0, 0, width=A4_G, height=A4_Y)
        c.showPage()
    c.save()
    return tampon.getvalue()
