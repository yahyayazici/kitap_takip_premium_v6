/* Seviye Tespit — filtreler kendiliğinden uygulanır, seçim yapılınca toplu işlem çubuğu çıkar,
 * satırdaki durum değişince kaydedilir. */
(function () {
    "use strict";

    var filtre = document.getElementById("st-filtre");
    if (filtre) {
        filtre.querySelectorAll("[data-otomatik]").forEach(function (el) {
            el.addEventListener("change", function () {
                filtre.submit();
            });
        });
    }

    var form = document.getElementById("st-liste-form");
    if (!form) {
        return;
    }

    var eylem = document.getElementById("st-eylem");
    var hepsi = document.getElementById("st-hepsi");
    var satirlar = Array.prototype.slice.call(form.querySelectorAll(".st-satir-sec"));
    var toplu = document.getElementById("st-toplu");
    var seciliSayi = document.getElementById("st-secili");
    var topluDurum = document.getElementById("st-toplu-durum");

    function guncelle() {
        var secili = satirlar.filter(function (el) { return el.checked; }).length;
        toplu.hidden = secili === 0;
        seciliSayi.textContent = String(secili);
        if (hepsi) {
            hepsi.checked = secili > 0 && secili === satirlar.length;
            hepsi.indeterminate = secili > 0 && secili < satirlar.length;
        }
    }

    if (hepsi) {
        hepsi.addEventListener("change", function () {
            satirlar.forEach(function (el) { el.checked = hepsi.checked; });
            guncelle();
        });
    }
    satirlar.forEach(function (el) { el.addEventListener("change", guncelle); });

    document.getElementById("st-toplu-vazgec").addEventListener("click", function () {
        satirlar.forEach(function (el) { el.checked = false; });
        guncelle();
    });

    document.getElementById("st-toplu-uygula").addEventListener("click", function () {
        if (!topluDurum.value) {
            topluDurum.focus();
            return;
        }
        var ad = topluDurum.options[topluDurum.selectedIndex].text;
        var secili = seciliSayi.textContent;
        if (!window.confirm(secili + " başvurunun durumu “" + ad + "” olarak değiştirilsin mi?")) {
            return;
        }
        eylem.value = "toplu_durum";
        form.submit();
    });

    form.querySelectorAll("[data-satir-durum]").forEach(function (el) {
        el.addEventListener("change", function () {
            eylem.value = "satir_durumlar";
            form.submit();
        });
    });

    guncelle();
})();
