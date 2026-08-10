(function () {
    var gate = document.getElementById("gate");
    if (!gate || !gate.querySelector(".gate-sketch-img")) {
        return;
    }

    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    if (reduced || !fine) {
        return;
    }

    var targetX = 0;
    var targetY = 0;
    var currentX = 0;
    var currentY = 0;
    var raf = 0;

    function tick() {
        currentX += (targetX - currentX) * 0.05;
        currentY += (targetY - currentY) * 0.05;
        gate.style.setProperty("--rx", currentX.toFixed(3) + "deg");
        gate.style.setProperty("--ry", currentY.toFixed(3) + "deg");
        raf = window.requestAnimationFrame(tick);
    }

    gate.addEventListener("pointermove", function (e) {
        var nx = (e.clientX / window.innerWidth) * 2 - 1;
        var ny = (e.clientY / window.innerHeight) * 2 - 1;
        /* Hafif eğim — sola kaydırma yok */
        targetY = nx * 2.8;
        targetX = ny * -2;
    });

    gate.addEventListener("pointerleave", function () {
        targetX = 0;
        targetY = 0;
    });

    raf = window.requestAnimationFrame(tick);

    window.addEventListener("beforeunload", function () {
        window.cancelAnimationFrame(raf);
    });
})();
