(function () {
    var table = document.querySelector(".st-page .st-table");
    if (!table) return;

    function sayi(input) {
        var n = parseInt(String(input && input.value ? input.value : "0"), 10);
        return Number.isFinite(n) && n > 0 ? n : 0;
    }

    function formatNet(n) {
        return (Math.round(n * 100) / 100).toFixed(2).replace(".", ",");
    }

    function satiriHesapla(row) {
        var toplamEl = row.querySelector(".st-toplam");
        var dogruEl = row.querySelector(".st-dogru");
        var yanlisEl = row.querySelector(".st-yanlis");
        var bosEl = row.querySelector(".st-bos");
        if (!toplamEl || !dogruEl || !yanlisEl || !bosEl) return;

        var toplam = sayi(toplamEl);
        var dogru = sayi(dogruEl);
        var yanlis = sayi(yanlisEl);

        if (dogru > toplam) {
            dogru = toplam;
            dogruEl.value = String(dogru);
        }
        if (yanlis > toplam - dogru) {
            yanlis = Math.max(0, toplam - dogru);
            yanlisEl.value = String(yanlis);
        }

        bosEl.value = String(Math.max(0, toplam - dogru - yanlis));

        var net = dogru - yanlis / 4;
        if (net < 0) net = 0;
        var netEl = row.querySelector(".st-net");
        if (netEl) netEl.textContent = formatNet(net);
    }

    table.querySelectorAll("tbody tr").forEach(function (row) {
        row.querySelectorAll(".st-toplam, .st-dogru, .st-yanlis").forEach(function (input) {
            input.addEventListener("input", function () {
                satiriHesapla(row);
            });
            input.addEventListener("change", function () {
                satiriHesapla(row);
            });
        });
    });
})();
