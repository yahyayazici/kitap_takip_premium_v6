(function () {
    function updateLabel(wrap, select, placeholder) {
        const selected = Array.from(select.selectedOptions).filter((o) => o.value);
        const label = wrap.querySelector(".ms-filter-label");
        if (!label) return;
        if (!selected.length) {
            label.textContent = placeholder;
        } else if (selected.length === 1) {
            label.textContent = selected[0].textContent.trim();
        } else {
            label.textContent = selected.length + " seçili";
        }
    }

    function initMultiSelect(select) {
        if (!select || select.dataset.msInit === "1") return;
        select.dataset.msInit = "1";
        select.multiple = true;

        const placeholder = select.dataset.placeholder || "Seçin";
        const wrap = document.createElement("div");
        wrap.className = "ms-filter-wrap";
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);
        select.classList.add("ms-filter-native");
        select.hidden = true;

        const trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "ms-filter-trigger";
        trigger.innerHTML =
            '<span class="ms-filter-label">' +
            placeholder +
            '</span><span class="ms-filter-chevron">▾</span>';
        wrap.appendChild(trigger);

        const panel = document.createElement("div");
        panel.className = "ms-filter-panel";
        panel.hidden = true;

        const actions = document.createElement("div");
        actions.className = "ms-filter-actions";
        actions.innerHTML =
            '<button type="button" class="ms-filter-all">Tümünü seç</button>' +
            '<button type="button" class="ms-filter-clear">Temizle</button>';
        panel.appendChild(actions);

        const list = document.createElement("div");
        list.className = "ms-filter-list";

        Array.from(select.options).forEach(function (opt) {
            if (!opt.value) return;
            const label = document.createElement("label");
            label.className = "ms-filter-option";
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = opt.value;
            cb.checked = opt.selected;
            cb.addEventListener("change", function () {
                opt.selected = cb.checked;
                updateLabel(wrap, select, placeholder);
            });
            label.appendChild(cb);
            label.appendChild(document.createTextNode(" " + opt.textContent.trim()));
            list.appendChild(label);
        });

        panel.appendChild(list);
        wrap.appendChild(panel);

        trigger.addEventListener("click", function (event) {
            event.stopPropagation();
            panel.hidden = !panel.hidden;
        });

        actions.querySelector(".ms-filter-all").addEventListener("click", function () {
            list.querySelectorAll("input[type='checkbox']").forEach(function (cb) {
                cb.checked = true;
            });
            Array.from(select.options).forEach(function (opt) {
                if (opt.value) opt.selected = true;
            });
            updateLabel(wrap, select, placeholder);
        });

        actions.querySelector(".ms-filter-clear").addEventListener("click", function () {
            list.querySelectorAll("input[type='checkbox']").forEach(function (cb) {
                cb.checked = false;
            });
            Array.from(select.options).forEach(function (opt) {
                opt.selected = false;
            });
            updateLabel(wrap, select, placeholder);
        });

        document.addEventListener("click", function (event) {
            if (!wrap.contains(event.target)) panel.hidden = true;
        });

        updateLabel(wrap, select, placeholder);
    }

    function initAll(root) {
        (root || document).querySelectorAll("select.ms-filter").forEach(initMultiSelect);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll(document);
        });
    } else {
        initAll(document);
    }

    window.initMultiSelectFilters = initAll;
})();
