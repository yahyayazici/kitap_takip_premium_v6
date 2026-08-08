(function () {
    var wrap = document.querySelector("[data-ep-week-scroll]");
    var PAGE_KEY = "epAdminPageScroll";
    var WEEK_KEY = "epAdminWeekScroll";
    var odak = wrap ? wrap.getAttribute("data-odak-gun") : null;

    function restorePageScroll() {
        var saved = sessionStorage.getItem(PAGE_KEY);
        if (!saved) return;
        try {
            var y = parseInt(saved, 10);
            if (!isNaN(y)) {
                window.scrollTo(0, y);
            }
        } catch (e) {
            /* ignore */
        }
        sessionStorage.removeItem(PAGE_KEY);
    }

    function restoreWeekScroll() {
        if (!wrap) return;
        var saved = sessionStorage.getItem(WEEK_KEY);
        if (saved) {
            try {
                var pos = JSON.parse(saved);
                wrap.scrollLeft = pos.l || 0;
                wrap.scrollTop = pos.t || 0;
            } catch (e) {
                /* ignore */
            }
            sessionStorage.removeItem(WEEK_KEY);
        }
        if (odak === null || odak === "") return;
        var target =
            wrap.querySelector('.ep-week-col[data-gun="' + odak + '"]') ||
            wrap.querySelector('th[data-gun="' + odak + '"]');
        if (target && typeof target.scrollIntoView === "function") {
            target.scrollIntoView({
                inline: "center",
                block: "nearest",
                behavior: "instant",
            });
        }
    }

    function saveScroll() {
        sessionStorage.setItem(PAGE_KEY, String(window.scrollY || window.pageYOffset || 0));
        if (wrap) {
            sessionStorage.setItem(
                WEEK_KEY,
                JSON.stringify({ l: wrap.scrollLeft, t: wrap.scrollTop })
            );
        }
    }

    document.querySelectorAll(".ep-admin-page form[method='post']").forEach(function (form) {
        form.addEventListener("submit", saveScroll);
    });

    function restore() {
        restorePageScroll();
        restoreWeekScroll();
        // Hash ile gelindiyse (saat ekle) ilgili alana odaklan; sayfa tepesine zıplamasın
        if (location.hash === "#ep-saat-ekle") {
            var el = document.getElementById("ep-saat-ekle");
            if (el) {
                el.scrollIntoView({ block: "nearest", behavior: "instant" });
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            requestAnimationFrame(restore);
        });
    } else {
        requestAnimationFrame(restore);
    }
})();
