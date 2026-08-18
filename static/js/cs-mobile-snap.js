(function () {
    "use strict";

    var TOGGLE_SEL =
        "#v3-menu-toggle, #yonetim-menu-toggle, #talebe-menu-toggle, #ogretmen-menu-toggle, #veli-menu-toggle";

    document.addEventListener(
        "pointerdown",
        function (event) {
            if (event.button != null && event.button !== 0) {
                return;
            }
            if (event.pointerType === "mouse") {
                return;
            }
            var control = event.target.closest(TOGGLE_SEL + ", .v3-nav-trigger");
            if (!control) {
                return;
            }
            event.preventDefault();
            control.click();
        },
        { capture: true, passive: false }
    );
})();
