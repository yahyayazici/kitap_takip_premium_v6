(function () {
  var bar = document.createElement("div");
  bar.className = "pv4-progress";
  document.body.appendChild(bar);

  function startBar() {
    bar.classList.remove("pv4-progress--done");
    bar.classList.add("pv4-progress--active");
  }

  function isPlainLeftClick(e) {
    return !e.defaultPrevented && e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
  }

  document.addEventListener("click", function (e) {
    var link = e.target.closest("a[href]");
    if (!link || !isPlainLeftClick(e)) return;
    if (link.target && link.target !== "" && link.target !== "_self") return;
    if (link.hasAttribute("download")) return;
    var href = link.getAttribute("href");
    if (!href || href.charAt(0) === "#" || href.indexOf("javascript:") === 0) return;
    try {
      var url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
    } catch (err) {
      return;
    }
    startBar();
  }, true);

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form && form.method && form.method.toLowerCase() !== "get" && !form.hasAttribute("data-no-progress")) {
      startBar();
    } else if (form && !form.hasAttribute("data-no-progress")) {
      startBar();
    }
  }, true);

  window.addEventListener("pageshow", function () {
    bar.classList.remove("pv4-progress--active");
    bar.classList.remove("pv4-progress--done");
  });
})();
