(function () {
    var gate = document.getElementById("gate");
    if (!gate) {
        return;
    }

    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!reduced) {
        gate.addEventListener("pointermove", function (e) {
            gate.style.setProperty("--mx", e.clientX + "px");
            gate.style.setProperty("--my", e.clientY + "px");
        });
    }
})();
