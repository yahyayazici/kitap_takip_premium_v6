"""LGS "taban + net başına katsayı" tabloları.

MEB'in puan formülü netlerin doğrusal fonksiyonu olduğu için
MSP ≈ Taban + Σ katsayı_i × net_i yazılabilir. Değerler üçüncü taraf
kaynaktan (hemenhesap.com, MEB ÖDSGM raporlarına dayandığını belirtiyor);
birincil MEB belgesiyle doğrulanamadı. Her yıl için tam net ≈ 500 verir.
2025 ve 2026 değerleri yayımlanmadı; bu yüzden puan "tahmini"dir.
"""

LGS_KATSAYILARI = {
    2020: {"taban": 200.264, "turkce": 3.797, "matematik": 5.623, "fen": 3.341, "inkilap": 1.411, "din": 1.532, "yabanci_dil": 1.505},
    2021: {"taban": 200.004, "turkce": 3.446, "matematik": 5.787, "fen": 3.562, "inkilap": 1.475, "din": 1.592, "yabanci_dil": 1.339},
    2022: {"taban": 200.013, "turkce": 3.920, "matematik": 4.929, "fen": 3.703, "inkilap": 1.752, "din": 1.660, "yabanci_dil": 1.478},
    2023: {"taban": 194.752, "turkce": 4.348, "matematik": 4.253, "fen": 4.123, "inkilap": 1.666, "din": 1.899, "yabanci_dil": 1.507},
    2024: {"taban": 196.620, "turkce": 4.107, "matematik": 4.632, "fen": 3.889, "inkilap": 1.729, "din": 1.818, "yabanci_dil": 1.531},
}

LGS_YILLARI = sorted(LGS_KATSAYILARI)

# LGS'de derslerin soru sayısı; farklı soru sayılı denemelerde net bu sayıya oranlanır.
LGS_SORU_SAYISI = {"turkce": 20, "matematik": 20, "fen": 20, "inkilap": 10, "din": 10, "yabanci_dil": 10}
