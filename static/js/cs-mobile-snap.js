(function () {
    "use strict";

    var TOGGLE_SEL =
        "#v3-menu-toggle, #yonetim-menu-toggle, #talebe-menu-toggle, #ogretmen-menu-toggle, #veli-menu-toggle";

    function prefetch(href) {
        if (!href || href.indexOf("javascript:") === 0) {
            return;
        }
        try {
            var url = new URL(href, location.href);
            if (url.origin !== location.origin) {
                return;
            }
            if (url.pathname === location.pathname && url.search === location.search) {
                return;
            }
            if (document.querySelector('link[data-cs-prefetch][href="' + url.href + '"]')) {
                return;
            }
            var link = document.createElement("link");
            link.rel = "prefetch";
            link.href = url.href;
            link.setAttribute("data-cs-prefetch", "1");
            document.head.appendChild(link);
        } catch (err) {
            /* yoksay */
        }
    }

    document.addEventListener(
        "pointerdown",
        function (event) {
            if (event.pointerType === "mouse") {
                var link = event.target.closest("a[href]");
                if (link && !link.target && !link.hasAttribute("download")) {
                    prefetch(link.href);
                }
                return;
            }

            var toggle = event.target.closest(TOGGLE_SEL);
            if (toggle) {
                event.preventDefault();
                toggle.click();
                return;
            }

            var trigger = event.target.closest(".v3-nav-trigger");
            if (trigger) {
                event.preventDefault();
                trigger.click();
                return;
            }

            var navLink = event.target.closest("a[href]");
            if (navLink && !navLink.target && !navLink.hasAttribute("download")) {
                prefetch(navLink.href);
            }
        },
        { capture: true, passive: false }
    );
})();
