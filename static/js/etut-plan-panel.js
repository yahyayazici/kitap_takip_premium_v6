(function () {
    const panel = document.querySelector("[data-ep-panel]");
    if (!panel) return;

    const planId = panel.dataset.plan;
    const hocaId = panel.dataset.hoca;
    const canEdit = panel.dataset.duzenle === "1";
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

    function postJson(url, payload) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({ ...payload, plan_id: planId, hoca_id: hocaId }),
        })
            .then(async (r) => {
                let data = {};
                try {
                    data = await r.json();
                } catch (_) {
                    data = { ok: false, hata: "Sunucu yanıtı okunamadı (" + r.status + ")." };
                }
                if (typeof data.ok === "undefined") data.ok = r.ok;
                return data;
            })
            .catch(() => ({ ok: false, hata: "Bağlantı hatası." }));
    }

    function syncSwatches(root, color) {
        if (!root) return;
        const value = (color || "").toLowerCase();
        let matched = false;
        root.querySelectorAll(".ep-swatch[data-color]").forEach((btn) => {
            const on = (btn.dataset.color || "").toLowerCase() === value;
            btn.classList.toggle("is-on", on);
            if (on) matched = true;
        });
        const picker = root.querySelector(".ep-swatch-picker");
        const pickerInput = root.querySelector("[data-ep-color-picker]");
        if (picker) picker.classList.toggle("is-on", !matched && !!value);
        if (picker && pickerInput && value) {
            try {
                pickerInput.value = value;
            } catch (_) {
                /* ignore invalid hex */
            }
            if (!matched) {
                picker.style.setProperty("--ep-picker-bg", value);
            } else {
                picker.style.removeProperty("--ep-picker-bg");
            }
        }
    }

    function colorInputOf(form) {
        return form?.querySelector('input[name="renk"]');
    }

    function applyColor(form, wrap, color) {
        const colorInput = colorInputOf(form);
        if (!colorInput || !color) return;
        colorInput.value = color;
        syncSwatches(wrap || form?.querySelector("[data-ep-swatches]"), color);
        updatePreview(form);
    }

    function updatePreview(form) {
        if (!form) return;
        const preview = form.querySelector("[data-ep-preview]");
        if (!preview) return;
        const title =
            form.querySelector('[data-ep-live="title"]')?.value?.trim() || "Etkinlik başlığı";
        const hedef =
            form.querySelector('[data-ep-live="hedef"]')?.value?.trim() || "Hedef yok";
        const renk = colorInputOf(form)?.value || "#dbeafe";
        const titleEl = preview.querySelector("[data-ep-preview-title]");
        const hedefEl = preview.querySelector("[data-ep-preview-hedef]");
        if (titleEl) titleEl.textContent = title;
        if (hedefEl) hedefEl.textContent = hedef;
        preview.style.setProperty("--ep-kart-renk", renk);
    }

    function openModal(name) {
        document.querySelectorAll("[data-ep-modal]").forEach((modal) => {
            const open = modal.dataset.epModal === name;
            modal.hidden = !open;
            if (open) {
                const focusEl = modal.querySelector(
                    "input:not([type=hidden]):not([type=color]), textarea"
                );
                if (focusEl) requestAnimationFrame(() => focusEl.focus());
            }
        });
        document.documentElement.classList.add("ep-modal-open");
    }

    function closeModals() {
        document.querySelectorAll("[data-ep-modal]").forEach((modal) => {
            modal.hidden = true;
        });
        document.documentElement.classList.remove("ep-modal-open");
    }

    document.querySelectorAll("[data-ep-open]").forEach((btn) => {
        btn.addEventListener("click", () => openModal(btn.dataset.epOpen));
    });
    document.querySelectorAll("[data-ep-close]").forEach((btn) => {
        btn.addEventListener("click", closeModals);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeModals();
    });

    document.querySelectorAll("[data-ep-swatches]").forEach((wrap) => {
        const form = wrap.closest("form");
        function pickSwatch(btn) {
            if (!btn || !btn.dataset.color) return;
            applyColor(form, wrap, btn.dataset.color);
        }
        wrap.addEventListener("click", (event) => {
            if (event.target.closest(".ep-swatch-picker")) return;
            pickSwatch(event.target.closest(".ep-swatch[data-color]"));
        });
        wrap.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            const btn = event.target.closest(".ep-swatch[data-color]");
            if (!btn) return;
            event.preventDefault();
            pickSwatch(btn);
        });
        const picker = wrap.querySelector("[data-ep-color-picker]");
        if (picker) {
            const openPicker = () => {
                const current = colorInputOf(form)?.value || "#dbeafe";
                try {
                    picker.value = current;
                } catch (_) {
                    picker.value = "#dbeafe";
                }
            };
            picker.addEventListener("click", openPicker);
            picker.addEventListener("input", () => {
                applyColor(form, wrap, picker.value);
            });
            picker.addEventListener("change", () => {
                applyColor(form, wrap, picker.value);
            });
        }
        const colorInput = colorInputOf(form);
        if (colorInput) syncSwatches(wrap, colorInput.value);
    });

    const hucreForm = document.querySelector("[data-ep-hucre-form]");
    if (hucreForm) {
        hucreForm.querySelectorAll("[data-ep-live]").forEach((el) => {
            el.addEventListener("input", () => updatePreview(hucreForm));
        });

        hucreForm.querySelectorAll("[data-ep-quick] .ep-quick-chip").forEach((chip) => {
            chip.addEventListener("click", () => {
                hucreForm.querySelectorAll(".ep-quick-chip").forEach((c) => {
                    c.classList.toggle("is-on", c === chip);
                });
                const baslik = hucreForm.querySelector("#ep-baslik");
                const hedef = hucreForm.querySelector("#ep-hedef");
                const renk = colorInputOf(hucreForm);
                if (baslik) baslik.value = chip.dataset.title || "";
                if (hedef) hedef.value = chip.dataset.hedef || "";
                if (renk) renk.value = chip.dataset.renk || "#dbeafe";
                syncSwatches(hucreForm.querySelector("[data-ep-swatches]"), renk?.value);
                updatePreview(hucreForm);
                baslik?.focus();
            });
        });
    }

    let dragged = null;
    let draggedCardEl = null;
    let poolOrderDirty = false;
    const pool = document.querySelector("[data-ep-pool]");

    function poolCardIds() {
        if (!pool) return [];
        return Array.from(pool.querySelectorAll(".ep-pool-card"))
            .map((el) => el.dataset.havuzId)
            .filter(Boolean);
    }

    function savePoolOrder() {
        if (!canEdit || !pool) return Promise.resolve({ ok: true });
        return postJson("/etut-plani/api/havuz-sirala/", {
            havuz_ids: poolCardIds(),
        }).then((res) => {
            if (!res.ok) alert(res.hata || "Sıra kaydedilemedi.");
            return res;
        });
    }

    function movePoolCard(card, direction) {
        if (!pool || !card) return false;
        if (direction < 0) {
            const prev = card.previousElementSibling;
            if (!prev || !prev.classList.contains("ep-pool-card")) return false;
            pool.insertBefore(card, prev);
            savePoolOrder();
            return true;
        }
        const next = card.nextElementSibling;
        if (!next || !next.classList.contains("ep-pool-card")) return false;
        pool.insertBefore(next, card);
        savePoolOrder();
        return true;
    }

    function unlockPoolDrag() {
        if (!pool) return;
        pool.querySelectorAll(".ep-pool-card[data-ep-drag-locked]").forEach((card) => {
            card.removeAttribute("data-ep-drag-locked");
            if (canEdit) card.setAttribute("draggable", "true");
        });
    }

    if (pool && canEdit) {
        pool.addEventListener(
            "pointerdown",
            (event) => {
                const actions = event.target.closest(".ep-pool-card-actions");
                if (!actions) return;
                event.stopPropagation();
                const card = actions.closest(".ep-pool-card");
                if (!card) return;
                card.dataset.epDragLocked = "1";
                card.setAttribute("draggable", "false");
            },
            true
        );
        document.addEventListener("pointerup", unlockPoolDrag);
        document.addEventListener("pointercancel", unlockPoolDrag);

        pool.addEventListener("click", (event) => {
            const up = event.target.closest("[data-ep-havuz-up]");
            const down = event.target.closest("[data-ep-havuz-down]");
            const del = event.target.closest("[data-ep-havuz-sil]");
            if (!up && !down && !del) return;
            event.preventDefault();
            event.stopPropagation();
            const card = event.target.closest(".ep-pool-card");
            if (!card) return;
            if (up) {
                movePoolCard(card, -1);
                return;
            }
            if (down) {
                movePoolCard(card, 1);
                return;
            }
            if (!confirm("Bu havuz kartı silinsin mi?")) return;
            const havuzId = del.dataset.epHavuzSil || card.dataset.havuzId;
            postJson("/etut-plani/api/havuz-sil/", { havuz_id: havuzId }).then((res) => {
                if (res.ok) card.remove();
                else alert(res.hata || "Silinemedi.");
            });
        });

        pool.addEventListener("dragstart", (event) => {
            const card = event.target.closest(".ep-pool-card");
            if (!card || card.dataset.epDragLocked === "1") {
                event.preventDefault();
                return;
            }
            if (event.target.closest(".ep-pool-card-actions")) {
                event.preventDefault();
                return;
            }
            draggedCardEl = card;
            poolOrderDirty = false;
            dragged = {
                havuzId: card.dataset.havuzId,
                baslik: card.dataset.baslik,
                hedef: card.dataset.hedef,
                renk: card.dataset.renk,
            };
            card.classList.add("dragging");
            try {
                event.dataTransfer.effectAllowed = "copyMove";
                event.dataTransfer.setData("text/plain", card.dataset.havuzId || "");
            } catch (_) {
                /* ignore */
            }
        });

        pool.addEventListener("dragover", (event) => {
            if (!draggedCardEl) return;
            const over = event.target.closest(".ep-pool-card");
            if (!over || over === draggedCardEl) return;
            event.preventDefault();
            const rect = over.getBoundingClientRect();
            const before = event.clientY < rect.top + rect.height / 2;
            const ref = before ? over : over.nextElementSibling;
            if (ref !== draggedCardEl) {
                pool.insertBefore(draggedCardEl, ref);
                poolOrderDirty = true;
            }
        });

        pool.addEventListener("dragend", () => {
            if (draggedCardEl) draggedCardEl.classList.remove("dragging");
            dragged = null;
            draggedCardEl = null;
            unlockPoolDrag();
            if (poolOrderDirty) {
                poolOrderDirty = false;
                savePoolOrder();
            }
        });
    }

    function assignActivity(blokId, data) {
        return postJson("/etut-plani/api/faaliyet-ata/", {
            saat_bloku_id: blokId,
            havuz_id: data.havuzId || null,
            baslik: data.baslik || "",
            aciklama: data.aciklama || "",
            hedef: data.hedef || "",
            renk: data.renk || "",
        }).then((res) => {
            if (res.ok) window.location.reload();
            else alert(res.hata || "Kaydedilemedi.");
        });
    }

    document.querySelectorAll("[data-drop='1']").forEach((cell) => {
        cell.addEventListener("dragover", (event) => {
            if (!canEdit || !dragged) return;
            event.preventDefault();
            cell.classList.add("drag-over");
        });
        cell.addEventListener("dragleave", () => cell.classList.remove("drag-over"));
        cell.addEventListener("drop", (event) => {
            event.preventDefault();
            cell.classList.remove("drag-over");
            if (!canEdit || !dragged) return;
            const blokId = cell.dataset.blokId;
            if (!blokId) return;
            const data = dragged;
            const dirty = poolOrderDirty;
            poolOrderDirty = false;
            const run = () => assignActivity(blokId, data);
            if (dirty) savePoolOrder().finally(run);
            else run();
        });
    });

    function slotMetaFromCell(cell) {
        if (!cell) return "Hücre seçilmedi";
        const gun = (cell.dataset.gun || "").trim();
        const saat = (cell.dataset.saat || "").trim();
        if (gun && saat) return gun + " · " + saat;
        return saat || gun || "Hücre seçilmedi";
    }

    function prepareHucreModal(cell) {
        const form = document.querySelector("[data-ep-hucre-form]");
        const meta = document.querySelector("[data-ep-slot-meta]");
        const blokId = cell?.dataset.blokId || "";
        if (meta) meta.textContent = slotMetaFromCell(cell);
        if (form) {
            form.reset();
            document.getElementById("ep-blok-id").value = blokId;
            const renk = colorInputOf(form);
            if (renk) renk.value = "#dbeafe";
            form.querySelectorAll(".ep-quick-chip").forEach((c) => c.classList.remove("is-on"));
            syncSwatches(form.querySelector("[data-ep-swatches]"), "#dbeafe");
            updatePreview(form);
        } else {
            document.getElementById("ep-blok-id").value = blokId;
        }
        openModal("hucre");
    }

    document.querySelectorAll("[data-ep-cell-add]").forEach((btn) => {
        btn.addEventListener("click", () => {
            prepareHucreModal(btn.closest("[data-blok-id]"));
        });
    });

    document.querySelectorAll("[data-drop='1'].ep-cell-empty").forEach((cell) => {
        cell.addEventListener("dblclick", () => {
            if (!canEdit) return;
            prepareHucreModal(cell);
        });
    });

    if (hucreForm) {
        hucreForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const fd = new FormData(hucreForm);
            assignActivity(fd.get("blok_id"), {
                baslik: fd.get("baslik"),
                aciklama: fd.get("aciklama"),
                hedef: fd.get("hedef"),
                renk: fd.get("renk"),
            });
        });
    }

    document.querySelectorAll("[data-ep-remove]").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (!confirm("Etkinlik kaldırılsın mı?")) return;
            postJson("/etut-plani/api/faaliyet-sil/", {
                faaliyet_id: btn.dataset.epRemove,
            }).then((res) => {
                if (res.ok) window.location.reload();
            });
        });
    });

    document.querySelectorAll("[data-ep-durum]").forEach((select) => {
        select.addEventListener("change", () => {
            postJson("/etut-plani/api/durum/", {
                faaliyet_id: select.dataset.epDurum,
                durum: select.value,
            });
        });
    });

    const ozelForm = document.querySelector("[data-ep-ozel-form]");
    if (ozelForm) {
        ozelForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const fd = new FormData(ozelForm);
            postJson("/etut-plani/api/havuz/", {
                baslik: fd.get("baslik"),
                hedef: fd.get("hedef"),
                renk: fd.get("renk"),
            }).then((res) => {
                if (res.ok) window.location.reload();
                else alert(res.hata || "Oluşturulamadı.");
            });
        });
    }

    const kopyalaBtn = document.querySelector("[data-ep-kopyala]");
    if (kopyalaBtn) {
        kopyalaBtn.addEventListener("click", () => {
            postJson("/etut-plani/api/kopyala/", {}).then((res) => {
                if (res.ok) {
                    alert(`${res.kopya} etkinlik kopyalandı.`);
                    window.location.reload();
                } else {
                    alert(res.hata || "Kopyalanamadı.");
                }
            });
        });
    }
})();
