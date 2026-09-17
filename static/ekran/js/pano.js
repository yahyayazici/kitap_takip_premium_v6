/* ============================================================
   Pano — tahtanın etrafındaki basit davranışlar
   (tahtanın kendisi studyo.js içinde)
     · Dosyayı tahtaya sürükleyip bırakma
     · Taslak seçici
     · "Ekranlara gönder" penceresi
   ============================================================ */
(function () {
    'use strict';

    var kok = document.getElementById('ek-studyo');
    if (!kok) { return; }

    // ——— Taslak seçici ————————————————————————————————————————

    var baslangicKatmani = document.getElementById('ek-baslangic-katmani');
    if (baslangicKatmani) {
        baslangicKatmani.querySelectorAll('[data-baslangic-kapat]').forEach(function (d) {
            d.addEventListener('click', function () { baslangicKatmani.remove(); });
        });
        // Boş alana tıklayınca da kapansın.
        baslangicKatmani.addEventListener('click', function (olay) {
            if (olay.target === baslangicKatmani) { baslangicKatmani.remove(); }
        });
    }

    // ——— Ekranlara gönder ————————————————————————————————————

    var gonderKatmani = document.getElementById('ek-gonder-katmani');
    var gonderAc = document.getElementById('ek-gonder-ac');

    if (gonderKatmani && gonderAc) {
        gonderAc.addEventListener('click', function () {
            // Gönderilen şey KAYDEDİLMİŞ hâldir; önce kaydet, sonra aç.
            var kaydet = document.getElementById('ek-kaydet');
            if (kaydet) { kaydet.click(); }
            gonderKatmani.hidden = false;
        });

        gonderKatmani.querySelectorAll('[data-gonder-kapat]').forEach(function (d) {
            d.addEventListener('click', function () { gonderKatmani.hidden = true; });
        });
        gonderKatmani.addEventListener('click', function (olay) {
            if (olay.target === gonderKatmani) { gonderKatmani.hidden = true; }
        });
        document.addEventListener('keydown', function (olay) {
            if (olay.key === 'Escape' && !gonderKatmani.hidden) { gonderKatmani.hidden = true; }
        });

        // Tek tek ekran işaretlenince "seçtiğim ekranlar"a geç.
        gonderKatmani.querySelectorAll('input[name="cihaz"], input[name="konum"]').forEach(function (kutu) {
            kutu.addEventListener('change', function () {
                if (kutu.checked) {
                    var secili = gonderKatmani.querySelector('input[name="hedef"][value="secili"]');
                    if (secili) { secili.checked = true; }
                }
            });
        });

        var form = document.getElementById('ek-gonder-form');
        if (form) {
            form.addEventListener('submit', function (olay) {
                var hedef = form.querySelector('input[name="hedef"]:checked');
                if (hedef && hedef.value === 'secili') {
                    var sayi = form.querySelectorAll(
                        'input[name="cihaz"]:checked, input[name="konum"]:checked'
                    ).length;
                    if (!sayi) {
                        olay.preventDefault();
                        window.alert('En az bir ekran ya da kat seçin.');
                    }
                }
            });
        }
    }
}());
