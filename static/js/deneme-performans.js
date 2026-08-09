(function () {
    document.querySelectorAll("[data-dp-root]").forEach(function (root) {
        const search = root.querySelector("[data-dp-search]");
        const items = root.querySelectorAll("[data-dp-item]");
        const graphBtn = root.querySelector("[data-dp-graph-toggle]");
        const chartPanel = root.querySelector("[data-dp-chart]");

        if (search && items.length) {
            search.addEventListener("input", function () {
                const q = search.value.trim().toLocaleLowerCase("tr-TR");
                items.forEach(function (item) {
                    const text = (item.getAttribute("data-dp-search-text") || item.textContent || "")
                        .toLocaleLowerCase("tr-TR");
                    item.hidden = q && !text.includes(q);
                });
            });
        }

        if (graphBtn && chartPanel) {
            graphBtn.addEventListener("click", function () {
                const open = chartPanel.classList.toggle("is-open");
                graphBtn.setAttribute("aria-expanded", open ? "true" : "false");
            });
        }
    });
})();
