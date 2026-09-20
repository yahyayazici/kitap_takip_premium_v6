(function () {
    document.querySelectorAll("[data-dg-root]").forEach(function (root) {
        var toggle = root.querySelector("[data-dg-bireysel-toggle]");
        var panel = root.querySelector("[data-dg-bireysel-panel]");
        if (!toggle || !panel) return;
        toggle.addEventListener("click", function () {
            var open = panel.classList.toggle("is-open");
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        });
    });
})();
