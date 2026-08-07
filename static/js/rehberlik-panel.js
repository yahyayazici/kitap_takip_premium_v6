(function () {
    "use strict";

    var root = document.querySelector("[data-rehberlik-panel]");
    if (!root) return;

    var search = root.querySelector("[data-rh-search]");
    var grid = root.querySelector("[data-rh-picker-grid]");
    if (search && grid) {
        search.addEventListener("input", function () {
            var q = search.value.trim().toLowerCase();
            grid.querySelectorAll("[data-rh-name]").forEach(function (item) {
                var name = item.getAttribute("data-rh-name") || "";
                item.style.display = !q || name.indexOf(q) !== -1 ? "" : "none";
            });
        });
    }

    var chipWrap = root.querySelector("[data-rh-chips]");
    if (chipWrap) {
        var input = root.querySelector("#id_etiketler_metin");
        chipWrap.addEventListener("click", function (event) {
            var btn = event.target.closest("[data-rh-chip]");
            if (!btn || !input) return;
            var tag = btn.getAttribute("data-rh-chip");
            var parts = input.value
                .split(",")
                .map(function (s) { return s.trim(); })
                .filter(Boolean);
            var idx = parts.indexOf(tag);
            if (idx === -1) {
                parts.push(tag);
                btn.classList.add("is-on");
            } else {
                parts.splice(idx, 1);
                btn.classList.remove("is-on");
            }
            input.value = parts.join(", ");
        });

        if (input && input.value) {
            var existing = input.value.split(",").map(function (s) { return s.trim(); });
            chipWrap.querySelectorAll("[data-rh-chip]").forEach(function (btn) {
                if (existing.indexOf(btn.getAttribute("data-rh-chip")) !== -1) {
                    btn.classList.add("is-on");
                }
            });
        }
    }

    var typeGrid = root.querySelector("[data-rh-type-grid]");
    if (typeGrid) {
        typeGrid.addEventListener("change", function (event) {
            if (event.target.name !== "tur") return;
            typeGrid.querySelectorAll(".rh-type-card").forEach(function (card) {
                card.style.opacity = card.querySelector("input:checked") ? "1" : "0.72";
            });
        });
        typeGrid.dispatchEvent(new Event("change"));
    }
})();
