(function () {
    "use strict";

    var cfg = window.OLCME_FOTO || {};
    var soruSayisi = cfg.soruSayisi || 20;
    var secenekler = cfg.secenekler || ["A", "B", "C", "D"];
    var sinavId = Number(cfg.sinavId);
    var baseUrl = cfg.baseUrl || "";
    var hasTalebe = !!cfg.hasTalebe;

    var fileInput = document.getElementById("olcme-foto-input");
    var canvas = document.getElementById("olcme-foto-canvas");
    var scanBtn = document.getElementById("olcme-foto-scan");
    var statusEl = document.getElementById("olcme-foto-status");
    var canvasWrap = document.getElementById("olcme-foto-canvas-wrap");
    if (!fileInput || !canvas) return;

    var ctx = canvas.getContext("2d");
    var imageLoaded = false;
    var cal = {
        top: document.getElementById("olcme-cal-top"),
        left: document.getElementById("olcme-cal-left"),
        width: document.getElementById("olcme-cal-width"),
        height: document.getElementById("olcme-cal-height"),
        threshold: document.getElementById("olcme-cal-threshold"),
    };

    function setStatus(msg, isError) {
        if (!statusEl) return;
        statusEl.textContent = msg || "";
        statusEl.classList.toggle("olcme-foto-status--error", !!isError);
    }

    function parseKarekod(text) {
        var raw = (text || "").trim();
        var m = raw.match(/^OLCME;S(\d+);T(\d+);N([^;]+);K([A-E])$/);
        if (m) {
            return {
                sinav_id: parseInt(m[1], 10),
                talebe_id: parseInt(m[2], 10),
                kitapcik: m[4],
            };
        }

        try {
            var url = new URL(raw, window.location.origin);
            var talebe = url.searchParams.get("talebe");
            var kitapcik = (url.searchParams.get("kitapcik") || "A").toUpperCase().charAt(0);
            var pathM = url.pathname.match(/\/olcme\/sinav\/(\d+)\/optik-foto\/?$/);
            if (talebe && pathM) {
                return {
                    sinav_id: parseInt(pathM[1], 10),
                    talebe_id: parseInt(talebe, 10),
                    kitapcik: kitapcik || "A",
                };
            }
        } catch (e) {
            return null;
        }
        return null;
    }

    function cropRegion(imageData, width, height, xRatio, yRatio, wRatio, hRatio) {
        var x = Math.floor(width * xRatio);
        var y = Math.floor(height * yRatio);
        var w = Math.floor(width * wRatio);
        var h = Math.floor(height * hRatio);
        if (w < 40 || h < 40) return null;
        var tmp = document.createElement("canvas");
        tmp.width = w;
        tmp.height = h;
        tmp.getContext("2d").putImageData(imageData, -x, -y);
        return tmp.getContext("2d").getImageData(0, 0, w, h);
    }

    function upscaleImageData(imageData, factor) {
        var srcCanvas = document.createElement("canvas");
        srcCanvas.width = imageData.width;
        srcCanvas.height = imageData.height;
        srcCanvas.getContext("2d").putImageData(imageData, 0, 0);

        var dst = document.createElement("canvas");
        dst.width = Math.floor(imageData.width * factor);
        dst.height = Math.floor(imageData.height * factor);
        var dctx = dst.getContext("2d");
        dctx.imageSmoothingEnabled = false;
        dctx.drawImage(srcCanvas, 0, 0, dst.width, dst.height);
        return dctx.getImageData(0, 0, dst.width, dst.height);
    }

    function decodeBlock(block) {
        if (!block || typeof jsQR !== "function") return null;
        var found = jsQR(block.data, block.width, block.height, { inversionAttempts: "attemptBoth" });
        return found && found.data ? found.data : null;
    }

    function readQrFromImageData(imageData, width, height) {
        if (typeof jsQR !== "function") {
            setStatus("Karekod kütüphanesi yüklenemedi. Sayfayı yenileyin.", true);
            return null;
        }

        var regions = [
            [0, 0, 1, 1],
            [0.52, 0, 0.48, 0.4],
            [0.5, 0, 0.5, 0.45],
            [0.55, 0, 0.45, 0.35],
            [0.45, 0, 0.55, 0.5],
        ];
        var i;
        for (i = 0; i < regions.length; i += 1) {
            var r = regions[i];
            var block = cropRegion(imageData, width, height, r[0], r[1], r[2], r[3]);
            var metin = decodeBlock(block);
            if (metin) return metin;
            if (block) {
                metin = decodeBlock(upscaleImageData(block, 2));
                if (metin) return metin;
            }
        }
        return null;
    }

    function redirectForParsed(parsed) {
        var sep = baseUrl.indexOf("?") >= 0 ? "&" : "?";
        window.location.href =
            baseUrl + sep + "talebe=" + parsed.talebe_id + "&kitapcik=" + parsed.kitapcik;
    }

    function applyParsedKarekod(parsed, metin) {
        if (!parsed) {
            setStatus("Karekod okundu ama format tanınmadı: " + metin, true);
            return false;
        }
        if (parsed.sinav_id !== sinavId) {
            setStatus("Bu karekod başka bir sınava ait.", true);
            return false;
        }
        if (!hasTalebe) {
            setStatus("Talebe seçiliyor…", false);
            redirectForParsed(parsed);
            return true;
        }
        setStatus("Karekod: talebe #" + parsed.talebe_id + " · kitapçık " + parsed.kitapcik, false);
        var kitSel = document.getElementById("olcme-kitapcik-select");
        if (kitSel) kitSel.value = parsed.kitapcik;
        return true;
    }

    function tryKarekodOku() {
        if (!imageLoaded) {
            setStatus("Önce fotoğraf yükleyin.", true);
            return;
        }
        redrawBase();
        var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        var metin = readQrFromImageData(imageData, canvas.width, canvas.height);
        if (!metin) {
            setStatus(
                "Karekod bulunamadı. Sağ üst net görünsün, tekrar deneyin veya metni yapıştırın.",
                true
            );
            return;
        }
        applyParsedKarekod(parseKarekod(metin), metin);
    }

    function calib() {
        return {
            top: (cal.top ? parseInt(cal.top.value, 10) : 22) / 100,
            left: (cal.left ? parseInt(cal.left.value, 10) : 8) / 100,
            width: (cal.width ? parseInt(cal.width.value, 10) : 84) / 100,
            height: (cal.height ? parseInt(cal.height.value, 10) : 72) / 100,
            threshold: (cal.threshold ? parseInt(cal.threshold.value, 10) : 28) / 100,
        };
    }

    function sampleDarkness(cx, cy, radius) {
        var r = Math.max(4, Math.floor(radius));
        var x0 = Math.max(0, Math.floor(cx - r));
        var y0 = Math.max(0, Math.floor(cy - r));
        var w = Math.min(canvas.width - x0, r * 2);
        var h = Math.min(canvas.height - y0, r * 2);
        if (w <= 0 || h <= 0) return 0;
        var data = ctx.getImageData(x0, y0, w, h).data;
        var dark = 0;
        var total = 0;
        for (var i = 0; i < data.length; i += 4) {
            var lum = (data[i] + data[i + 1] + data[i + 2]) / 3;
            if (lum < 140) dark += 1;
            total += 1;
        }
        return total ? dark / total : 0;
    }

    function redrawBase() {
        if (!canvas._sourceImg) return;
        ctx.drawImage(canvas._sourceImg, 0, 0, canvas.width, canvas.height);
    }

    function drawGrid() {
        if (!imageLoaded || !hasTalebe) return;
        redrawBase();
        var c = calib();
        var w = canvas.width;
        var h = canvas.height;
        var tableLeft = w * c.left;
        var tableTop = h * c.top;
        var tableWidth = w * c.width;
        var tableHeight = h * c.height;
        var colCount = secenekler.length + 1;
        var colWidth = tableWidth / colCount;
        var rowHeight = tableHeight / soruSayisi;

        ctx.strokeStyle = "rgba(37, 99, 235, 0.7)";
        ctx.lineWidth = 2;
        ctx.strokeRect(tableLeft, tableTop, tableWidth, tableHeight);

        for (var row = 0; row < soruSayisi; row += 1) {
            for (var ci = 0; ci < secenekler.length; ci += 1) {
                var col = ci + 1;
                var cx = tableLeft + col * colWidth + colWidth / 2;
                var cy = tableTop + row * rowHeight + rowHeight / 2;
                ctx.beginPath();
                ctx.arc(cx, cy, Math.min(colWidth, rowHeight) * 0.18, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
    }

    function scanBubbles() {
        if (!imageLoaded) {
            setStatus("Önce fotoğraf yükleyin.", true);
            return null;
        }
        redrawBase();
        var c = calib();
        var w = canvas.width;
        var h = canvas.height;
        var tableLeft = w * c.left;
        var tableTop = h * c.top;
        var tableWidth = w * c.width;
        var tableHeight = h * c.height;
        var colCount = secenekler.length + 1;
        var colWidth = tableWidth / colCount;
        var rowHeight = tableHeight / soruSayisi;
        var answers = {};

        for (var row = 0; row < soruSayisi; row += 1) {
            var bestOpt = "BOS";
            var bestDark = 0;
            for (var ci = 0; ci < secenekler.length; ci += 1) {
                var col = ci + 1;
                var cx = tableLeft + col * colWidth + colWidth / 2;
                var cy = tableTop + row * rowHeight + rowHeight / 2;
                var dark = sampleDarkness(cx, cy, Math.min(colWidth, rowHeight) * 0.32);
                if (dark > bestDark) {
                    bestDark = dark;
                    bestOpt = secenekler[ci];
                }
            }
            answers[row + 1] = bestDark >= c.threshold ? bestOpt : "BOS";
        }
        return answers;
    }

    function applyAnswers(answers) {
        Object.keys(answers).forEach(function (no) {
            var sel = document.querySelector('select[name="s_' + no + '"]');
            if (sel) sel.value = answers[no];
        });
    }

    fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) return;
        var img = new Image();
        img.onload = function () {
            var maxW = 1600;
            var scale = img.width > maxW ? maxW / img.width : 1;
            canvas.width = Math.floor(img.width * scale);
            canvas.height = Math.floor(img.height * scale);
            canvas._sourceImg = img;
            imageLoaded = true;
            if (canvasWrap) canvasWrap.hidden = false;
            redrawBase();
            tryKarekodOku();
            if (hasTalebe) {
                drawGrid();
            }
        };
        img.onerror = function () {
            setStatus("Fotoğraf yüklenemedi.", true);
        };
        img.src = URL.createObjectURL(file);
    });

    Object.keys(cal).forEach(function (key) {
        if (cal[key]) cal[key].addEventListener("input", drawGrid);
    });

    if (scanBtn) {
        scanBtn.addEventListener("click", function () {
            var answers = scanBubbles();
            if (!answers) return;
            drawGrid();
            applyAnswers(answers);
            var filled = Object.values(answers).filter(function (v) { return v !== "BOS"; }).length;
            setStatus(filled + " / " + soruSayisi + " soru işaretlendi. Kontrol edip kaydedin.", false);
        });
    }
})();
