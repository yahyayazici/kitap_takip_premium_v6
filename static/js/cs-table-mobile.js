/**
 * Çinili Saray — tablo sunumu
 * Az sütunlu/az satırlı tablolarda kart; yoğun CRUD listelerinde wrap içi yatay kaydırma.
 * Yalnızca sunum — form name / POST / data-* API değişmez.
 */
(function () {
    "use strict";

    var MOBILE_MAX = 640;
    var DENSE_MIN_COLS = 6;
    var DENSE_MIN_ROWS = 8;

    var TABLE_SEL =
        ".responsive-table .report-data-table, " +
        ".responsive-table .yonetim-data-table, " +
        ".responsive-table .profile-data-table, " +
        ".yonetim-table-wrap .yonetim-data-table, " +
        ".cs-table-wrap table, " +
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
        "table.gt-etut-table, " +
        ".pid-table-wrap .pid-table, " +
        "table.pid-table, " +
        ".vz-table-wrap .vz-table, " +
        "table.vz-table, " +
        ".pt-table-wrap .pt-table, " +
        "table.pt-table, " +
        ".yc-table-wrap .yc-table, " +
        "table.yc-table";

    var WRAP_SEL =
        ".responsive-table, .cs-table-wrap, .yonetim-table-wrap, .ktt-table-wrap, .at-table-wrap, .st-table-wrap, " +
        ".fn-table-wrap, .ep-table-wrap, .dk-table-wrap, .im-table-wrap, " +
        ".tz-table-wrap, .rh-table-wrap, .mz-table-wrap, .program-table-wrap, " +
        ".gt-etut-table-wrap, .pid-table-wrap, .vz-table-wrap, .pt-table-wrap, " +
        ".yc-table-wrap";

    var SCROLL_SEL =
        ".responsive-table, .cs-table-wrap, .yonetim-table-wrap, " +
        ".st-table-wrap, .ktt-table-wrap, .report-data-table-wrap, " +
        ".cs-table-dense";

    function closestWrap(table) {
        return table.closest(WRAP_SEL);
    }

    function isDenseTable(table) {
        if (table.classList.contains("cs-stack-on-mobile")) {
            return false;
        }
        var cols = table.querySelectorAll("thead th").length;
        var rows = table.querySelectorAll("tbody tr").length;
        return cols >= DENSE_MIN_COLS || rows >= DENSE_MIN_ROWS;
    }

    function markDense(table) {
        var wrap = closestWrap(table);
        table.classList.remove("cs-mobile-ready");
        table.dataset.csMobileReady = "dense";
        if (wrap) {
            wrap.classList.add("cs-table-dense");
            wrap.classList.remove("cs-mobile-cards");
        }
    }

    function enhanceTable(table) {
        if (!table || table.dataset.csMobileReady === "1" || table.dataset.csMobileReady === "dense") {
            return;
        }

        var thead = table.querySelector("thead");
        var tbody = table.querySelector("tbody");
        if (!thead || !tbody) return;

        if (isDenseTable(table)) {
            markDense(table);
            return;
        }

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
        document.querySelectorAll(TABLE_SEL).forEach(enhanceTable);

        document.querySelectorAll(WRAP_SEL).forEach(function (wrap) {
            if (wrap.classList.contains("cs-table-dense")) {
                wrap.classList.remove("cs-mobile-cards");
                return;
            }
            if (wrap.querySelector(".cs-mobile-ready")) {
                wrap.classList.add("cs-mobile-cards");
            }
        });

        syncHorizontalScrollports();
    }

    /**
     * Yatay taşma yoksa overflow kapat — dikey tekerlek native sayfa scroll'una kalsın.
     * Yoğun listelerde wrap her zaman kaydırılabilir yüzeydir.
     */
    function syncHorizontalScrollports() {
        document.querySelectorAll(SCROLL_SEL).forEach(function (wrap) {
            if (wrap.classList.contains("cs-table-dense")) {
                wrap.classList.add("cs-h-scroll");
                return;
            }
            wrap.classList.remove("cs-h-scroll");
            void wrap.offsetWidth;
            var needs = wrap.scrollWidth > wrap.clientWidth + 2;
            wrap.classList.toggle("cs-h-scroll", needs);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", enhanceAll);
    } else {
        enhanceAll();
    }

    var lastWidth = window.innerWidth;
    var resizeTimer;
    window.addEventListener("resize", function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            var width = window.innerWidth;
            if (width === lastWidth) {
                return;
            }
            lastWidth = width;
            if (width <= MOBILE_MAX) {
                enhanceAll();
            } else {
                syncHorizontalScrollports();
            }
        }, 180);
    });
})();
