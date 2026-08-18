(function () {
    "use strict";

    var TOGGLE_SEL =
        "#v3-menu-toggle, #yonetim-menu-toggle, #talebe-menu-toggle, #ogretmen-menu-toggle, #veli-menu-toggle";
    var going = false;
    var press = null;

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

    function isInternalNav(anchor) {
        if (!anchor || !anchor.getAttribute) {
            return false;
        }
        var raw = (anchor.getAttribute("href") || "").trim();
        if (!raw || raw.charAt(0) === "#" || raw.indexOf("javascript:") === 0) {
            return false;
        }
        if (anchor.target && anchor.target !== "_self") {
            return false;
        }
        if (anchor.hasAttribute("download")) {
            return false;
        }
        try {
            return new URL(anchor.href, location.href).origin === location.origin;
        } catch (err) {
            return false;
        }
    }

    function go(href) {
        if (going || !href) {
            return;
        }
        going = true;
        window.location.assign(href);
    }

    function prefetchNav() {
        var seen = {};
        var count = 0;
        document
            .querySelectorAll(".v3-nav a[href], .cs-v6-nav a[href], #yonetim-nav a[href]")
            .forEach(function (anchor) {
                if (count >= 16 || !isInternalNav(anchor) || seen[anchor.href]) {
                    return;
                }
                seen[anchor.href] = 1;
                prefetch(anchor.href);
                count += 1;
            });
    }

    document.addEventListener(
        "pointerdown",
        function (event) {
            if (event.button != null && event.button !== 0) {
                return;
            }
            if (event.target.closest(TOGGLE_SEL + ", .v3-nav-trigger")) {
                press = null;
                if (event.pointerType !== "mouse") {
                    var control = event.target.closest(TOGGLE_SEL + ", .v3-nav-trigger");
                    event.preventDefault();
                    control.click();
                }
                return;
            }
            var anchor = event.target.closest("a[href]");
            if (!isInternalNav(anchor)) {
                press = null;
                return;
            }
            if (event.pointerType === "mouse") {
                press = null;
                return;
            }
            press = {
                anchor: anchor,
                x: event.clientX,
                y: event.clientY,
            };
            prefetch(anchor.href);
        },
        { capture: true, passive: false }
    );

    document.addEventListener(
        "pointerup",
        function (event) {
            if (!press || !press.anchor) {
                return;
            }
            if (event.pointerType === "mouse") {
                press = null;
                return;
            }
            var dx = event.clientX - press.x;
            var dy = event.clientY - press.y;
            var anchor = press.anchor;
            press = null;
            if (dx * dx + dy * dy > 64) {
                return;
            }
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            go(anchor.href);
        },
        { capture: true, passive: false }
    );

    document.addEventListener(
        "click",
        function (event) {
            if (!going) {
                return;
            }
            var anchor = event.target.closest("a[href]");
            if (isInternalNav(anchor)) {
                event.preventDefault();
                event.stopPropagation();
            }
        },
        true
    );

    if ("requestIdleCallback" in window) {
        window.requestIdleCallback(prefetchNav, { timeout: 1500 });
    } else {
        window.setTimeout(prefetchNav, 600);
    }
})();
