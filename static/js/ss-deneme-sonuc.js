(function () {
    var table = document.getElementById("ssSonucTable");
    if (!table) return;

    function sayi(input) {
        var n = parseInt(String(input && input.value ? input.value : "0"), 10);
        return Number.isFinite(n) && n > 0 ? n : 0;
    }

    function hucreyiHesapla(dogruEl, yanlisEl, bosEl) {
        var hedef = parseInt(dogruEl.getAttribute("data-hedef") || "0", 10) || 0;
        var dogru = sayi(dogruEl);
        var yanlis = sayi(yanlisEl);
        if (dogru > hedef) {
            dogru = hedef;
            dogruEl.value = String(dogru);
        }
        if (yanlis > hedef - dogru) {
            yanlis = Math.max(0, hedef - dogru);
            yanlisEl.value = String(yanlis);
        }
        bosEl.value = String(Math.max(0, hedef - dogru - yanlis));
    }

    table.querySelectorAll("tbody tr").forEach(function (row) {
        var dogrular = row.querySelectorAll(".ss-dogru");
        var yanlislar = row.querySelectorAll(".ss-yanlis");
        var boslar = row.querySelectorAll(".ss-bos");
        dogrular.forEach(function (el, i) {
            function run() {
                hucreyiHesapla(dogrular[i], yanlislar[i], boslar[i]);
            }
            el.addEventListener("input", run);
            el.addEventListener("change", run);
            yanlislar[i].addEventListener("input", run);
            yanlislar[i].addEventListener("change", run);
        });
    });
})();
