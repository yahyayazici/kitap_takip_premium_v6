(function () {
    var kapsayici = document.getElementById("yonetim-toplu-liste");
    if (!kapsayici) return;

    var selectAll = document.getElementById("yonetim-select-all");
    var rowChecks = kapsayici.querySelectorAll(".yonetim-row-check");
    var bulkBar = document.getElementById("yonetim-toplu-bar");
    var seciliSayEl = document.getElementById("yonetim-secili-say");
    var bulkForm = document.getElementById("yonetim-toplu-sil-form");

    function guncelleSecim() {
        var secili = kapsayici.querySelectorAll(".yonetim-row-check:checked").length;
        if (seciliSayEl) {
            seciliSayEl.textContent = String(secili);
        }
        if (bulkBar) {
            bulkBar.hidden = secili === 0;
        }
        if (selectAll && rowChecks.length) {
            selectAll.indeterminate = secili > 0 && secili < rowChecks.length;
            selectAll.checked = secili === rowChecks.length;
        }
    }

    rowChecks.forEach(function (cb) {
        cb.addEventListener("change", guncelleSecim);
    });

    if (selectAll) {
        selectAll.addEventListener("change", function () {
            rowChecks.forEach(function (cb) {
                cb.checked = selectAll.checked;
            });
            guncelleSecim();
        });
    }

    if (bulkForm) {
        bulkForm.addEventListener("submit", function (event) {
            var secili = kapsayici.querySelectorAll(".yonetim-row-check:checked").length;
            if (!secili) {
                event.preventDefault();
                return;
            }
                if (
                    !window.confirm(
                        secili + " kayıt silinsin mi? Aktif olanlar pasif edilir, pasif olanlar kalıcı silinir."
                    )
                ) {
                event.preventDefault();
            }
        });
    }

    guncelleSecim();
})();
