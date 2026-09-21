(function () {
    "use strict";

    initKttModal();
    initKttFilter();

    function initKttModal() {
        var modal = document.getElementById("ktt-form-modal");
        if (!modal) return;

        var openBtn = document.getElementById("ktt-open-form");
        var body = document.body;

        function openModal() {
            modal.hidden = false;
            body.classList.add("ktt-modal-open");
            if (openBtn) openBtn.setAttribute("aria-expanded", "true");
            var first = modal.querySelector("input, select, textarea");
            if (first) {
                setTimeout(function () {
                    first.focus();
                }, 80);
            }
        }

        function closeModal() {
            modal.hidden = true;
            body.classList.remove("ktt-modal-open");
            if (openBtn) {
                openBtn.setAttribute("aria-expanded", "false");
                openBtn.focus();
            }
        }

        if (openBtn) {
            openBtn.addEventListener("click", openModal);
        }

        document.querySelectorAll("[data-ktt-open-form]").forEach(function (el) {
            el.addEventListener("click", openModal);
        });

        modal.querySelectorAll("[data-ktt-close]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && !modal.hidden) {
                closeModal();
            }
        });

        if (document.documentElement.dataset.kttFormOpen === "1") {
            openModal();
        }

        var adInput = document.getElementById("id_ad");
        var dersSelect = document.getElementById("id_ders");
        var oneriBox = document.createElement("div");
        oneriBox.className = "ktt-konu-oneri";
        oneriBox.hidden = true;

        if (adInput && adInput.closest(".ktt-field")) {
            var konuField = adInput.closest(".ktt-field");
            konuField.classList.add("ktt-field-konu");
            konuField.appendChild(oneriBox);
        }

        var debounceTimer;
        function konuOneriYukle() {
            if (!adInput || adInput.value.trim().length < 2) {
                oneriBox.hidden = true;
                return;
            }
            var params = new URLSearchParams({
                q: adInput.value.trim(),
                sinif: "7",
            });
            if (dersSelect && dersSelect.value) {
                params.set("ders", dersSelect.value);
            }
            fetch("/ktt/konu-oneri/?" + params.toString(), {
                headers: { Accept: "application/json" },
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (data) {
                    oneriBox.innerHTML = "";
                    var list = data.oneriler || [];
                    if (!list.length) {
                        oneriBox.hidden = true;
                        return;
                    }
                    list.forEach(function (item) {
                        var btn = document.createElement("button");
                        btn.type = "button";
                        btn.textContent = item.ad;
                        btn.addEventListener("click", function () {
                            adInput.value = item.ad;
                            oneriBox.hidden = true;
                        });
                        oneriBox.appendChild(btn);
                    });
                    oneriBox.hidden = false;
                })
                .catch(function () {
                    oneriBox.hidden = true;
                });
        }

        if (adInput) {
            adInput.addEventListener("input", function () {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(konuOneriYukle, 220);
            });
            adInput.addEventListener("blur", function () {
                setTimeout(function () {
                    oneriBox.hidden = true;
                }, 180);
            });
        }
    }

    function initKttFilter() {
        var root = document.getElementById("ktt-list-filter");
        if (!root) return;

        var qInput = root.querySelector('[data-ktt-filter="q"]');
        var dersSelect = root.querySelector('[data-ktt-filter="ders"]');
        var sinifSelect = root.querySelector('[data-ktt-filter="sinif"]');
        var countEl = root.querySelector("[data-ktt-count]");
        var emptyEl = document.querySelector("[data-ktt-empty]");
        var rows = Array.prototype.slice.call(document.querySelectorAll("[data-ktt-row]"));
        if (!rows.length) return;

        function uniqueSorted(values) {
            var seen = {};
            var out = [];
            values.forEach(function (value) {
                var key = value.toLocaleLowerCase("tr");
                if (!key || seen[key]) return;
                seen[key] = true;
                out.push(value);
            });
            out.sort(function (a, b) {
                return a.localeCompare(b, "tr");
            });
            return out;
        }

        function fillSelect(select, values, placeholder) {
            if (!select) return;
            select.innerHTML = "";
            var all = document.createElement("option");
            all.value = "";
            all.textContent = placeholder;
            select.appendChild(all);
            values.forEach(function (value) {
                var opt = document.createElement("option");
                opt.value = value;
                opt.textContent = value;
                select.appendChild(opt);
            });
        }

        var dersler = uniqueSorted(
            rows.map(function (row) {
                return (row.getAttribute("data-ders") || "").trim();
            })
        );
        var siniflar = uniqueSorted(
            rows.reduce(function (acc, row) {
                (row.getAttribute("data-sinif") || "")
                    .split(",")
                    .map(function (part) {
                        return part.trim();
                    })
                    .filter(Boolean)
                    .forEach(function (part) {
                        acc.push(part);
                    });
                return acc;
            }, [])
        );

        fillSelect(dersSelect, dersler, "Tüm dersler");
        fillSelect(sinifSelect, siniflar, "Tüm sınıflar");

        var totalUnique = rows.filter(function (row) {
            return row.tagName === "TR";
        }).length;
        if (!totalUnique) {
            totalUnique = rows.filter(function (row) {
                return row.tagName === "DETAILS";
            }).length;
        }

        function applyFilter() {
            var q = qInput ? qInput.value.trim().toLocaleLowerCase("tr") : "";
            var ders = dersSelect ? dersSelect.value : "";
            var sinif = sinifSelect ? sinifSelect.value : "";
            var visible = 0;
            var seenKeys = {};

            rows.forEach(function (row) {
                var ad = (row.getAttribute("data-ad") || "").toLocaleLowerCase("tr");
                var rowDers = row.getAttribute("data-ders") || "";
                var rowSinif = row.getAttribute("data-sinif") || "";
                var match = true;
                if (q && ad.indexOf(q) === -1) match = false;
                if (ders && rowDers !== ders) match = false;
                if (sinif && rowSinif.indexOf(sinif) === -1) match = false;
                row.hidden = !match;
                if (match) {
                    var key = ad + "|" + rowDers + "|" + rowSinif;
                    if (!seenKeys[key]) {
                        seenKeys[key] = true;
                        visible += 1;
                    }
                }
            });

            if (countEl) {
                countEl.textContent =
                    visible === totalUnique ? String(totalUnique) : visible + " / " + totalUnique;
            }
            if (emptyEl) {
                emptyEl.hidden = visible !== 0;
            }
            var tableWrap = document.querySelector(".ktt-list-page .ktt-desktop-table");
            var accList = document.querySelector(".ktt-list-page .ktt-acc-list");
            if (tableWrap) tableWrap.hidden = visible === 0;
            if (accList) accList.hidden = visible === 0;
        }

        if (qInput) qInput.addEventListener("input", applyFilter);
        if (dersSelect) dersSelect.addEventListener("change", applyFilter);
        if (sinifSelect) sinifSelect.addEventListener("change", applyFilter);
        applyFilter();
    }
})();
