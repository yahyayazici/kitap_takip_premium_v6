(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function buildUrl(widget, yenile) {
    var tur = widget.getAttribute("data-ai-tur");
    var params = new URLSearchParams({ tur: tur });
    if (yenile) params.set("yenile", "1");
    var talebe = widget.getAttribute("data-ai-talebe");
    var deneme = widget.getAttribute("data-ai-deneme");
    var gorusme = widget.getAttribute("data-ai-gorusme");
    if (talebe) params.set("talebe_id", talebe);
    if (deneme) params.set("deneme_id", deneme);
    if (gorusme) params.set("gorusme_id", gorusme);
    return "/panel/ai/analiz/html/?" + params.toString();
  }

  function loadWidget(widget, yenile) {
    var panel = qs(".ai-zekasi-panel", widget);
    if (!panel) return;
    panel.hidden = false;
    panel.innerHTML = '<p class="ai-zekasi-loading">Analiz hazırlanıyor…</p>';
    fetch(buildUrl(widget, yenile), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function (html) {
        if (html.trim()) {
          panel.innerHTML = html;
        } else {
          panel.innerHTML = '<p class="ai-zekasi-loading">Analiz üretilemedi.</p>';
        }
      })
      .catch(function () {
        panel.innerHTML = '<p class="ai-zekasi-loading">Bağlantı hatası.</p>';
      });
  }

  function expandWidget(widget) {
    widget.classList.remove("is-collapsed");
    widget.removeAttribute("data-ai-collapsed");
    var actions = qs(".ai-zekasi-actions", widget);
    if (actions) {
      actions.innerHTML =
        '<button type="button" class="ai-zekasi-yenile ghost-btn" title="Yenile">↻</button>';
      var refreshBtn = qs(".ai-zekasi-yenile", widget);
      if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
          loadWidget(widget, true);
        });
      }
    }
    loadWidget(widget, false);
  }

  function initWidget(widget) {
    var collapsed = widget.getAttribute("data-ai-collapsed") === "1";
    var expandBtn = qs(".ai-zekasi-expand", widget);
    if (expandBtn) {
      expandBtn.addEventListener("click", function () {
        expandWidget(widget);
      });
      return;
    }
    if (!collapsed) {
      loadWidget(widget, false);
    }
    var refreshBtn = qs(".ai-zekasi-yenile", widget);
    if (refreshBtn) {
      refreshBtn.addEventListener("click", function () {
        loadWidget(widget, true);
      });
    }
  }

  function init() {
    document.querySelectorAll(".ai-zekasi-widget").forEach(initWidget);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
