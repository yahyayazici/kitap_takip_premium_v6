(function () {
    var panel = document.querySelector("[data-ny-panel]");
    if (!panel) return;

    var odakInput = document.getElementById("ny-odak-vakit");
    var labels = document.querySelectorAll("[data-ny-odak-label]");
    var live = document.querySelector("[data-ny-live]");
    var liveBar = document.querySelector("[data-ny-live-bar]");

    function currentVakit() {
        return odakInput ? odakInput.value : panel.dataset.odak;
    }

    function setOdak(vakit, label) {
        if (odakInput) odakInput.value = vakit;
        panel.dataset.odak = vakit;
        document.querySelectorAll(".ny-vakit-tab").forEach(function (tab) {
            tab.classList.toggle("is-on", tab.dataset.nyVakit === vakit);
        });
        document.querySelectorAll(".ny-mark-set").forEach(function (set) {
            set.classList.toggle("is-active", set.dataset.vakit === vakit);
        });
        document.querySelectorAll(".ny-table [data-col-vakit], .ny-table [data-cell-vakit]").forEach(function (el) {
            var key = el.getAttribute("data-col-vakit") || el.getAttribute("data-cell-vakit");
            el.classList.toggle("is-odak", key === vakit);
        });
        if (label) {
            labels.forEach(function (node) {
                node.textContent = label;
            });
        }
        refreshCounts();
        syncTableFromRadios();
        try {
            var url = new URL(window.location.href);
            url.searchParams.set("vakit", vakit);
            window.history.replaceState({}, "", url.toString());
        } catch (e) {
            /* ignore */
        }
    }

    function refreshCounts() {
        var vakit = currentVakit();
        var marked = 0;
        document.querySelectorAll('.ny-mark-set[data-vakit="' + vakit + '"] input:checked').forEach(function () {
            marked += 1;
        });
        if (live) live.textContent = marked + " işaret";
        if (liveBar) liveBar.textContent = marked + " işaretli";

        document.querySelectorAll("[data-ny-count-for]").forEach(function (badge) {
            var v = badge.getAttribute("data-ny-count-for");
            var n = document.querySelectorAll(
                '.ny-mark-set[data-vakit="' + v + '"] input[value="G"]:checked'
            ).length;
            badge.textContent = String(n);
        });

        document.querySelectorAll("[data-ny-row][data-talebe]").forEach(function (row) {
            var id = row.getAttribute("data-talebe");
            var checked = document.querySelector(
                'input[name="k_' + id + "_" + vakit + '"]:checked'
            );
            row.classList.toggle("is-marked", !!checked);
        });
    }

    function syncTableFromRadios() {
        document.querySelectorAll("[data-ny-table-pills]").forEach(function (wrap) {
            var id = wrap.getAttribute("data-talebe");
            var v = wrap.getAttribute("data-vakit");
            var checked = document.querySelector(
                'input[name="k_' + id + "_" + v + '"]:checked'
            );
            var val = checked ? checked.value : "";
            wrap.querySelectorAll(".ny-pill").forEach(function (btn) {
                var on = btn.getAttribute("data-val") === val;
                btn.classList.toggle("is-on", on);
                btn.setAttribute("aria-pressed", on ? "true" : "false");
            });
        });
    }

    function setRadio(talebeId, vakit, value) {
        var name = "k_" + talebeId + "_" + vakit;
        var inputs = document.querySelectorAll('input[name="' + name + '"]');
        if (!inputs.length) return;
        if (!value) {
            inputs.forEach(function (input) {
                input.checked = false;
            });
        } else {
            inputs.forEach(function (input) {
                input.checked = input.value === value;
            });
        }
        refreshCounts();
        syncTableFromRadios();
    }

    // Vakit tabs
    document.querySelectorAll("[data-ny-vakit]").forEach(function (tab) {
        tab.addEventListener("click", function () {
            setOdak(tab.dataset.nyVakit, tab.dataset.label);
        });
    });

    // View toggle
    document.querySelectorAll("[data-ny-view]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var mode = btn.dataset.nyView;
            document.querySelectorAll("[data-ny-view]").forEach(function (b) {
                b.classList.toggle("is-on", b === btn);
            });
            document.querySelectorAll("[data-ny-mode]").forEach(function (pane) {
                pane.hidden = pane.getAttribute("data-ny-mode") !== mode;
            });
            if (mode === "table") syncTableFromRadios();
        });
    });

    // Search
    var search = document.querySelector("[data-ny-search]");
    if (search) {
        search.addEventListener("input", function () {
            var q = (search.value || "").trim().toLowerCase();
            document.querySelectorAll("[data-ny-row][data-name]").forEach(function (row) {
                var hit = !q || (row.getAttribute("data-name") || "").indexOf(q) !== -1;
                row.classList.toggle("is-hidden", !hit);
                if (row.tagName === "TR") row.style.display = hit ? "" : "none";
            });
            document.querySelectorAll("[data-ny-group]").forEach(function (group) {
                var any = group.querySelector("[data-ny-row]:not(.is-hidden)");
                group.style.display = any ? "" : "none";
            });
        });
    }

    // Toggle-off: ikinci basışta kaldır (checked durumu pointerdown ile alınır —
    // click anında tarayıcı zaten işaretlediği için eski mantık her tıkta silıyordu)
    document.querySelectorAll(".ny-mark").forEach(function (label) {
        var input = label.querySelector("input");
        if (!input) return;

        label.addEventListener("pointerdown", function () {
            label.dataset.wasChecked = input.checked ? "1" : "0";
        });

        label.addEventListener("click", function (event) {
            if (label.dataset.wasChecked === "1") {
                event.preventDefault();
                input.checked = false;
            }
            setTimeout(function () {
                refreshCounts();
                syncTableFromRadios();
            }, 0);
        });
    });

    document.querySelectorAll(".ny-mark input").forEach(function (input) {
        input.addEventListener("change", function () {
            refreshCounts();
            syncTableFromRadios();
        });
    });

    // Table pills drive the real radios
    document.querySelectorAll("[data-ny-table-pills]").forEach(function (wrap) {
        wrap.addEventListener("click", function (event) {
            var btn = event.target.closest(".ny-pill");
            if (!btn) return;
            event.preventDefault();
            var id = wrap.getAttribute("data-talebe");
            var v = wrap.getAttribute("data-vakit");
            var val = btn.getAttribute("data-val");
            var current = document.querySelector(
                'input[name="k_' + id + "_" + v + '"]:checked'
            );
            if (current && current.value === val) {
                setRadio(id, v, "");
            } else {
                setRadio(id, v, val);
            }
        });
    });

    setOdak(currentVakit());
})();
