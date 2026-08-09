(function () {
    var metaEl = document.getElementById("yk-talebe-meta");
    if (!metaEl) return;

    var meta;
    try {
        meta = JSON.parse(metaEl.textContent);
    } catch (e) {
        return;
    }

    var sinifSelect = document.querySelector("[data-yk-sinif-sec]");
    var etutSelect = document.querySelector("[data-yk-etut-sec]");
    var seviyeSelect = document.querySelector("[data-yk-dini-seviye-sec]");
    var diniHocaSelect = document.querySelector("[data-yk-dini-hoca-sec]");

    if (!sinifSelect || !etutSelect || !seviyeSelect || !diniHocaSelect) return;

    var allEtutOptions = Array.from(etutSelect.options).map(function (opt) {
        return { value: opt.value, text: opt.text, selected: opt.selected };
    });

    var allDiniOptions = Array.from(diniHocaSelect.options).map(function (opt) {
        return { value: opt.value, text: opt.text, selected: opt.selected };
    });

    function rebuildSelect(select, options, keepValue) {
        var current = keepValue || select.value;
        select.innerHTML = "";
        options.forEach(function (item) {
            var opt = document.createElement("option");
            opt.value = item.value;
            opt.textContent = item.text;
            if (item.value === current) {
                opt.selected = true;
            }
            select.appendChild(opt);
        });
        if (current && !select.value) {
            select.value = current;
        }
    }

    function filterEtutForSinif() {
        var sinifId = sinifSelect.value;
        var hocaIds = meta.sinif_etut[sinifId] || [];
        var filtered = allEtutOptions.filter(function (opt) {
            return !opt.value || hocaIds.indexOf(parseInt(opt.value, 10)) !== -1;
        });

        if (filtered.length <= 1 && hocaIds.length === 1) {
            filtered = allEtutOptions.filter(function (opt) {
                return !opt.value || parseInt(opt.value, 10) === hocaIds[0];
            });
        }

        rebuildSelect(etutSelect, filtered.length > 1 ? filtered : allEtutOptions.filter(function (opt) {
            return !opt.value || hocaIds.indexOf(parseInt(opt.value, 10)) !== -1;
        }));

        if (hocaIds.length === 1) {
            etutSelect.value = String(hocaIds[0]);
        } else if (hocaIds.length > 1 && !hocaIds.some(function (id) {
            return String(id) === etutSelect.value;
        })) {
            etutSelect.value = "";
        }
    }

    function filterDiniHocaForSeviye() {
        var seviyeId = seviyeSelect.value;
        if (!seviyeId) {
            rebuildSelect(diniHocaSelect, allDiniOptions);
            return;
        }

        var hocaIds = meta.seviye_hocalar[seviyeId] || [];
        var filtered = allDiniOptions.filter(function (opt) {
            return !opt.value || hocaIds.indexOf(parseInt(opt.value, 10)) !== -1;
        });

        rebuildSelect(diniHocaSelect, filtered.length > 0 ? filtered : allDiniOptions);

        if (hocaIds.length === 1) {
            diniHocaSelect.value = String(hocaIds[0]);
        } else if (!hocaIds.some(function (id) {
            return String(id) === diniHocaSelect.value;
        })) {
            diniHocaSelect.value = "";
        }
    }

    sinifSelect.addEventListener("change", filterEtutForSinif);
    seviyeSelect.addEventListener("change", filterDiniHocaForSeviye);

    filterEtutForSinif();
    filterDiniHocaForSeviye();
})();
