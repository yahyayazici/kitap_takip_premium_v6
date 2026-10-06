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
    from PIL import Image, ImageDraw

    olcek = 2
    g = Image.new("L", (int(A4_G * olcek), int(A4_Y * olcek)), 250)
    d = ImageDraw.Draw(g)
    for sutun in range(2):
        for k in range(3):
            x = int(SOL_X[sutun] * olcek)
            y = int((90 + k * 240) * olcek)
            d.text((x, y), f"{(sayfa_no - 1) * 6 + sutun * 3 + k + 1}.", fill=10)
            for satir in range(6):
                d.line((x + 40, y + 30 + satir * 28, x + 480, y + 30 + satir * 28), fill=60, width=3)
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
