(function () {
    var form = document.getElementById("oo-donem-form");
    if (!form) return;

    function parseSaat(value) {
        var raw = (value || "").replace(",", ".").trim();
        var num = parseFloat(raw);
        return isNaN(num) ? 0 : num;
    }

    function formatSaat(num) {
        return num.toFixed(2).replace(".", ",");
    }

    function gunIdFromInput(input) {
        var name = input.getAttribute("name") || "";
        var parts = name.split("_");
        if (parts.length !== 3 || parts[0] !== "cell") return null;
        return parts[1];
    }

    function hesaplaMatris() {
        var gunToplam = {};
        form.querySelectorAll(".oo-cell-input").forEach(function (input) {
            var gunId = gunIdFromInput(input);
            if (!gunId) return;
            if (!gunToplam[gunId]) gunToplam[gunId] = 0;
            gunToplam[gunId] += parseSaat(input.value);
        });

        var genelToplam = 0;
        form.querySelectorAll(".oo-col-total").forEach(function (cell) {
            var gunId = cell.getAttribute("data-gun-id");
            var total = gunToplam[gunId] || 0;
            cell.textContent = formatSaat(total);
            genelToplam += total;
        });

        var saatEl = document.getElementById("oo-toplam-saat");
        if (saatEl) saatEl.textContent = formatSaat(genelToplam);

        var rateInput = document.querySelector(".oo-rate-input");
        var tutarEl = document.getElementById("oo-toplam-tutar");
        if (rateInput && tutarEl) {
            var tutar = genelToplam * parseSaat(rateInput.value);
            tutarEl.textContent = formatSaat(tutar) + " ₺";
        }
    }

    form.querySelectorAll(".oo-cell-input").forEach(function (input) {
        input.addEventListener("input", hesaplaMatris);
    });

    var rateInput = document.querySelector(".oo-rate-input");
    if (rateInput) rateInput.addEventListener("input", hesaplaMatris);

    hesaplaMatris();
})();
