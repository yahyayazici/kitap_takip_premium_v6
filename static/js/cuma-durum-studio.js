(function () {
    "use strict";

    var dataEl = document.getElementById("cd-stuyo-data");
    if (!dataEl) return;

    var stuyo;
    try {
        stuyo = JSON.parse(dataEl.textContent);
    } catch (e) {
        return;
    }

    var story = document.getElementById("cd-story-export");
    var previewMetin = document.getElementById("cd-preview-metin");
    var previewKaynak = document.getElementById("cd-preview-kaynak");
    var previewAd = document.getElementById("cd-preview-ad");
    var previewRol = document.getElementById("cd-preview-rol");
    var previewTarih = document.getElementById("cd-preview-tarih");
    var quoteList = document.getElementById("cd-quote-list");
    var themeGrid = document.getElementById("cd-theme-grid");
    var inputAd = document.getElementById("cd-person-ad");
    var inputRol = document.getElementById("cd-person-rol");
    var ozelMetin = document.getElementById("cd-ozel-metin");
    var ozelKaynak = document.getElementById("cd-ozel-kaynak");
    var downloadBtn = document.getElementById("cd-download-btn");

    var state = {
        metin: "",
        kaynak: "",
        sablon: "gece",
        seciliId: null,
    };

    function truncate(str, len) {
        if (!str) return "";
        return str.length > len ? str.slice(0, len) + "…" : str;
    }

    function uygulaMetin(metin, kaynak, sablon, id) {
        state.metin = metin || "";
        state.kaynak = kaynak || "";
        state.sablon = sablon || "gece";
        state.seciliId = id != null ? id : null;

        previewMetin.textContent = state.metin;
        previewKaynak.textContent = state.kaynak ? "— " + state.kaynak : "";

        story.className = "cd-story cd-theme-" + state.sablon;
        story.setAttribute("data-theme", state.sablon);

        document.querySelectorAll(".cd-quote-card").forEach(function (card) {
            card.classList.toggle(
                "is-selected",
                state.seciliId != null && card.dataset.id === String(state.seciliId)
            );
        });

        document.querySelectorAll(".cd-theme-chip").forEach(function (chip) {
            chip.classList.toggle("is-active", chip.dataset.theme === state.sablon);
        });
    }

    function baslangicMetni() {
        if (stuyo.oneri) {
            uygulaMetin(stuyo.oneri.metin, stuyo.oneri.kaynak, stuyo.oneri.sablon, stuyo.oneri.id);
        } else if (stuyo.havuz.length) {
            var ilk = stuyo.havuz[0];
            uygulaMetin(ilk.metin, ilk.kaynak, ilk.sablon, ilk.id);
        }
    }

    function renderHavuz() {
        quoteList.innerHTML = "";
        if (!stuyo.havuz.length) {
            quoteList.innerHTML =
                '<p class="cd-panel-lead">Henüz hazır metin yok. Yönetimden eklenmesini isteyin veya kendin yaz sekmesini kullanın.</p>';
            return;
        }

        stuyo.havuz.forEach(function (item) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "cd-quote-card";
            btn.dataset.id = item.id;

            var oneri =
                stuyo.oneri && stuyo.oneri.id === item.id
                    ? '<span class="cd-badge-oneri">Bu haftanın önerisi</span>'
                    : "";

            btn.innerHTML =
                "<strong>" +
                truncate(item.metin, 140) +
                "</strong>" +
                (item.kaynak ? "<small>" + item.kaynak + "</small>" : "") +
                oneri;

            btn.addEventListener("click", function () {
                uygulaMetin(item.metin, item.kaynak, item.sablon, item.id);
            });
            quoteList.appendChild(btn);
        });
    }

    function renderTemalar() {
        themeGrid.innerHTML = "";
        (stuyo.sablonlar || []).forEach(function (s) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "cd-theme-chip";
            chip.dataset.theme = s.kod;
            chip.textContent = s.etiket;
            chip.addEventListener("click", function () {
                state.sablon = s.kod;
                story.className = "cd-story cd-theme-" + s.kod;
                story.setAttribute("data-theme", s.kod);
                document.querySelectorAll(".cd-theme-chip").forEach(function (c) {
                    c.classList.toggle("is-active", c.dataset.theme === s.kod);
                });
            });
            themeGrid.appendChild(chip);
        });
    }

    /* Sekmeler */
    document.querySelectorAll(".cd-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            var key = tab.dataset.tab;
            document.querySelectorAll(".cd-tab").forEach(function (t) {
                t.classList.toggle("is-active", t === tab);
                t.setAttribute("aria-selected", t === tab ? "true" : "false");
            });
            document.querySelectorAll(".cd-tab-panel").forEach(function (panel) {
                panel.classList.toggle("is-active", panel.dataset.panel === key);
            });
        });
    });

    document.getElementById("cd-ozel-uygula").addEventListener("click", function () {
        var metin = (ozelMetin.value || "").trim();
        if (!metin) return;
        uygulaMetin(metin, (ozelKaynak.value || "").trim(), state.sablon, null);
    });

    inputAd.addEventListener("input", function () {
        previewAd.textContent = inputAd.value.trim() || stuyo.personel_ad;
    });

    inputRol.addEventListener("input", function () {
        previewRol.textContent = inputRol.value.trim();
    });

    if (inputRol && stuyo.personel_rol) {
        inputRol.value = stuyo.personel_rol;
        previewRol.textContent = stuyo.personel_rol;
    }

    if (previewTarih && stuyo.cuma_tarihi) {
        previewTarih.textContent = stuyo.cuma_tarihi;
    }

    function exportStory() {
        if (typeof html2canvas !== "function") {
            alert("Görsel oluşturucu yüklenemedi. Sayfayı yenileyip tekrar deneyin.");
            return;
        }

        if (!state.metin.trim()) {
            alert("Lütfen bir hadis veya söz seçin / yazın.");
            return;
        }

        downloadBtn.disabled = true;
        var originalText = downloadBtn.innerHTML;
        downloadBtn.textContent = "Hazırlanıyor…";

        var clone = story.cloneNode(true);
        clone.className = "cd-story cd-theme-" + state.sablon;
        clone.style.transform = "none";
        clone.style.marginBottom = "0";
        clone.style.width = "1080px";
        clone.style.height = "1920px";

        var wrap = document.createElement("div");
        wrap.className = "cd-export-clone";
        wrap.appendChild(clone);
        document.body.appendChild(wrap);

        html2canvas(clone, {
            scale: 1,
            useCORS: true,
            allowTaint: false,
            backgroundColor: null,
            width: 1080,
            height: 1920,
            logging: false,
        })
            .then(function (canvas) {
                canvas.toBlob(function (blob) {
                    if (!blob) {
                        alert("Görsel oluşturulamadı.");
                        return;
                    }
                    var ad = (inputAd.value || stuyo.personel_ad || "cuma").replace(/\s+/g, "-");
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement("a");
                    a.href = url;
                    a.download = "cuma-durum-" + ad + ".png";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                }, "image/png");
            })
            .catch(function () {
                alert("Görsel indirilemedi. Logo yüklenmemiş olabilir; yine de metin kaydedildi.");
            })
            .finally(function () {
                wrap.remove();
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = originalText;
            });
    }

    downloadBtn.addEventListener("click", exportStory);

    renderHavuz();
    renderTemalar();
    baslangicMetni();
})();
