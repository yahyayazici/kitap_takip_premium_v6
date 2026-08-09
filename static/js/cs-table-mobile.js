/**
 * Çinili Saray — mobil tablo kart görünümü
 * thead başlıklarını td data-label olarak kopyalar (yalnızca sunum).
 */
(function () {
    "use strict";

    var MOBILE_MAX = 640;

    function enhanceTable(table) {
        if (!table || table.dataset.csMobileReady === "1") return;

        var thead = table.querySelector("thead");
        var tbody = table.querySelector("tbody");
        if (!thead || !tbody) return;

        var headers = Array.from(thead.querySelectorAll("th")).map(function (th) {
            return (th.textContent || "").trim();
        });

        if (!headers.length) return;

        Array.from(tbody.querySelectorAll("tr")).forEach(function (row) {
            Array.from(row.children).forEach(function (cell, index) {
                if (cell.tagName === "TD" && headers[index]) {
                    cell.setAttribute("data-label", headers[index]);
                }
            });
        });

        table.classList.add("cs-mobile-ready");
        table.dataset.csMobileReady = "1";
    }

    function enhanceAll() {
        var tables = document.querySelectorAll(
            ".responsive-table .report-data-table, " +
            ".responsive-table .yonetim-data-table, " +
            ".responsive-table .profile-data-table"
        );
        tables.forEach(enhanceTable);

        document.querySelectorAll(".responsive-table").forEach(function (wrap) {
            if (wrap.querySelector(".cs-mobile-ready")) {
                wrap.classList.add("cs-mobile-cards");
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", enhanceAll);
    } else {
        enhanceAll();
    }

    window.addEventListener("resize", function () {
        if (window.innerWidth <= MOBILE_MAX) {
            enhanceAll();
        }
    });
})();
