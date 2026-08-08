(function () {
    var panel = document.querySelector("[data-yc-panel]");
    if (!panel) return;

    var csrf =
        document.querySelector("[name=csrfmiddlewaretoken]") &&
        document.querySelector("[name=csrfmiddlewaretoken]").value;

    function postJson(url, payload) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf || "",
            },
            body: JSON.stringify(payload || {}),
        }).then(function (r) {
            return r.json();
        });
    }

    var dateInput = panel.querySelector("[data-yc-date]");
    if (dateInput) {
        dateInput.addEventListener("change", function () {
            window.location = "?sekme=bugun&tarih=" + dateInput.value;
        });
    }

    panel.querySelectorAll("[data-yc-gorevli]").forEach(function (sel) {
        sel.addEventListener("change", function () {
            var talebeId = sel.value;
            if (!talebeId) return;
            postJson("/yemekcilik/api/gorevli/", {
                tarih: panel.getAttribute("data-tarih"),
                sinif: sel.getAttribute("data-sinif"),
                talebe_id: Number(talebeId),
            }).then(function (res) {
                if (res.ok) window.location.reload();
                else alert(res.hata || "Kaydedilemedi.");
            });
        });
    });

    panel.querySelectorAll("[data-yc-add]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var pool = form.closest("[data-sinif]");
            var sinif = pool && pool.getAttribute("data-sinif");
            var sel = form.querySelector("select[name=talebe_id]");
            if (!sinif || !sel || !sel.value) return;
            postJson("/yemekcilik/api/kayit-ekle/", {
                sinif: sinif,
                talebe_id: Number(sel.value),
            }).then(function (res) {
                if (res.ok) window.location.reload();
                else alert(res.hata || "Eklenemedi.");
            });
        });
    });

    panel.querySelectorAll("[data-yc-sil]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            if (!confirm("Kayıt silinsin mi?")) return;
            postJson("/yemekcilik/api/kayit-sil/", {
                kayit_id: Number(btn.getAttribute("data-yc-sil")),
            }).then(function (res) {
                if (res.ok) window.location.reload();
                else alert(res.hata || "Silinemedi.");
            });
        });
    });

    // Drag reorder within pool lists
    panel.querySelectorAll("[data-yc-list]").forEach(function (list) {
        var dragged = null;
        list.querySelectorAll(".yc-pool-item[draggable='true']").forEach(function (item) {
            item.addEventListener("dragstart", function () {
                dragged = item;
                item.classList.add("dragging");
            });
            item.addEventListener("dragend", function () {
                item.classList.remove("dragging");
                dragged = null;
                var pool = list.closest("[data-sinif]");
                var ids = Array.from(list.querySelectorAll(".yc-pool-item"))
                    .map(function (el) {
                        return Number(el.getAttribute("data-kayit-id"));
                    })
                    .filter(Boolean);
                if (!pool || !ids.length) return;
                postJson("/yemekcilik/api/sirala/", {
                    sinif: pool.getAttribute("data-sinif"),
                    kayit_ids: ids,
                });
            });
            item.addEventListener("dragover", function (event) {
                event.preventDefault();
                if (!dragged || dragged === item) return;
                var rect = item.getBoundingClientRect();
                var before = event.clientY < rect.top + rect.height / 2;
                list.insertBefore(dragged, before ? item : item.nextSibling);
            });
        });
    });
})();
