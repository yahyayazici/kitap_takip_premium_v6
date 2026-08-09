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
            ".responsive-table .profile-data-table, " +
            ".ktt-table-wrap .ktt-table, " +
            ".at-table-wrap .at-table, " +
            ".st-table-wrap .st-table, " +
            ".fn-table-wrap .fn-table, " +
            ".ep-table-wrap .ep-admin-table, " +
            ".dk-table-wrap .dk-table, " +
            ".im-table-wrap .im-table, " +
            ".tz-table-wrap .tz-table, " +
            ".rh-table-wrap .rh-table, " +
            ".mz-table-wrap .mz-table, " +
            ".program-table-wrap .program-table, " +
            ".gt-etut-table-wrap .gt-etut-table, " +
            "table.ep-admin-table, " +
            "table.dk-table, " +
            "table.im-table, " +
            "table.tz-table, " +
            "table.rh-table, " +
            "table.mz-table, " +
            "table.program-table, " +
            "table.gt-etut-table"
        );
        tables.forEach(enhanceTable);

        document.querySelectorAll(
            ".responsive-table, .ktt-table-wrap, .at-table-wrap, .st-table-wrap, " +
            ".fn-table-wrap, .ep-table-wrap, .dk-table-wrap, .im-table-wrap, " +
            ".tz-table-wrap, .rh-table-wrap, .mz-table-wrap, .program-table-wrap, " +
            ".gt-etut-table-wrap"
        ).forEach(function (wrap) {
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
