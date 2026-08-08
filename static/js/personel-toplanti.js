(function () {
    "use strict";

    function addFormsetRow(prefix, container, templateEl) {
        var totalInput = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
        if (!totalInput || !container || !templateEl) return;

        var index = parseInt(totalInput.value, 10);
        var html = templateEl.innerHTML.replace(/__prefix__/g, String(index));
        var wrap = document.createElement("div");
        wrap.innerHTML = html.trim();
        var row = wrap.firstElementChild;
        if (!row) return;

        container.appendChild(row);
        totalInput.value = String(index + 1);
        renumberRows(container, ".pt-row-no");
    }

    function renumberRows(container, selector) {
        container.querySelectorAll(selector).forEach(function (el, i) {
            el.textContent = "#" + (i + 1);
        });
    }

    function bindAddButton(btnId, prefix, containerId, templateId) {
        var btn = document.getElementById(btnId);
        var container = document.getElementById(containerId);
        var templateEl = document.getElementById(templateId);
        if (!btn || !container || !templateEl) return;

        btn.addEventListener("click", function () {
            addFormsetRow(prefix, container, templateEl);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        bindAddButton("pt-gundem-add", "gundem", "pt-gundem-rows", "pt-gundem-empty");
        bindAddButton("pt-yapilacak-add", "yapilacak", "pt-yapilacak-rows", "pt-yapilacak-empty");
    });
})();
