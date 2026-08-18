(function () {
    "use strict";

    function normalizePath(path) {
        if (!path) {
            return "/";
        }
        return path.endsWith("/") ? path : path + "/";
    }

    function updateActiveNav() {
        var current = normalizePath(window.location.pathname);
        var links = document.querySelectorAll(
            ".v3-nav-link[href], .v3-nav-dropdown-link[href], #ogretmen-nav a[href], #talebe-nav a[href], #veli-nav a[href]"
        );
        var bestLink = null;
        var bestLen = -1;

        links.forEach(function (link) {
            link.classList.remove("active");
            try {
                var linkPath = normalizePath(new URL(link.href, window.location.origin).pathname);
                if (current === linkPath || current.indexOf(linkPath) === 0) {
                    if (linkPath.length > bestLen) {
                        bestLink = link;
                        bestLen = linkPath.length;
                    }
                }
            } catch (err) {
                /* ignore invalid href */
            }
        });

        if (bestLink) {
            bestLink.classList.add("active");
        }
    }

    function maybeUpdateTitle(target) {
        if (!target) {
            return;
        }
        var customTitle = target.querySelector("[data-page-title]");
        if (customTitle) {
            document.title = customTitle.getAttribute("data-page-title") || document.title;
        }
    }

    function ensureScript(src, onReady) {
        var existing = document.querySelector('script[src="' + src + '"]');
        if (existing) {
            if (typeof onReady === "function") {
                onReady();
            }
            return;
        }
        var script = document.createElement("script");
        script.src = src;
        script.defer = true;
        script.onload = function () {
            if (typeof onReady === "function") {
                onReady();
            }
        };
        document.body.appendChild(script);
    }

    function hydratePanelDate(target) {
        if (!target || !target.querySelector(".dashboard-page")) {
            return;
        }
        var now = new Date();
        var day = new Intl.DateTimeFormat("tr-TR", { day: "2-digit" }).format(now);
        var month = new Intl.DateTimeFormat("tr-TR", { month: "long", year: "numeric" }).format(now);
        var week = new Intl.DateTimeFormat("tr-TR", { weekday: "long" }).format(now);
        var full = new Intl.DateTimeFormat("tr-TR", {
            day: "numeric",
            month: "long",
            year: "numeric",
            weekday: "long",
        }).format(now);
        target.querySelectorAll("[data-panel-date-day]").forEach(function (el) {
            el.textContent = day;
        });
        target.querySelectorAll("[data-panel-date-month]").forEach(function (el) {
            el.textContent = month.charAt(0).toUpperCase() + month.slice(1);
        });
        target.querySelectorAll("[data-panel-date-week]").forEach(function (el) {
            el.textContent = week.charAt(0).toUpperCase() + week.slice(1);
        });
        target.querySelectorAll("#current-date, [data-panel-date]").forEach(function (el) {
            el.textContent = full;
        });
    }

    function reinitDashboardWidgets(target) {
        if (!target || !target.querySelector(".dashboard-page")) {
            return;
        }
        ensureScript("/static/js/duyuru-carousel.js?v=half5", function () {
            if (typeof window.initDuyuruCarousel === "function") {
                window.initDuyuruCarousel(target);
            }
        });
        hydratePanelDate(target);
    }

    function renderHtmxError(target, statusCode) {
        if (!target || target.id !== "main-content") {
            return;
        }
        var label = statusCode === 404 ? "Sayfa bulunamadı (404)." : "Sayfa yüklenirken bir hata oluştu.";
        target.innerHTML = (
            '<section class="dash-panel">' +
            '<h2>Sayfa açılamadı</h2>' +
            "<p>" + label + " Lütfen tekrar deneyin.</p>" +
            '<a href="' + window.location.pathname + '" class="ghost-btn">Tam sayfa yenile</a>' +
            "</section>"
        );
    }

    document.addEventListener("htmx:beforeRequest", function () {
        if (typeof window.csCloseMobileNav === "function") {
            window.csCloseMobileNav();
        }
    });

    document.addEventListener("htmx:afterSwap", function (event) {
        if (event.target && event.target.id === "main-content") {
            maybeUpdateTitle(event.target);
            updateActiveNav();
            reinitDashboardWidgets(event.target);
            document.querySelectorAll(".v3-nav-trigger[aria-expanded='true']").forEach(function (trigger) {
                trigger.setAttribute("aria-expanded", "false");
            });
            document.querySelectorAll(".v3-nav-dropdown.open").forEach(function (el) {
                el.classList.remove("open");
            });
            document.querySelectorAll(".v3-nav.open").forEach(function (el) {
                el.classList.remove("open");
            });
            document.body.classList.remove("v3-nav-menu-open", "v3-mobile-nav-open");
        }
    });

    document.addEventListener("htmx:responseError", function (event) {
        var target = event.detail && event.detail.target ? event.detail.target : null;
        var xhr = event.detail && event.detail.xhr ? event.detail.xhr : null;
        var statusCode = xhr ? xhr.status : 0;
        if (statusCode === 404 || statusCode >= 500) {
            renderHtmxError(target, statusCode);
        }
    });

    document.addEventListener("htmx:sendError", function (event) {
        var target = event.detail && event.detail.target ? event.detail.target : null;
        renderHtmxError(target, 0);
    });

    if (window.htmx && window.htmx.config) {
        window.htmx.config.timeout = 8000;
    }

    window.addEventListener("popstate", updateActiveNav);
    document.addEventListener("DOMContentLoaded", updateActiveNav);
})();
