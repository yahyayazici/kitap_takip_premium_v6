/**
 * In-page responsive checks (read-only). Returns { errors, warnings }.
 */
async function analyzePage(page, { isPhone = false } = {}) {
  return page.evaluate(({ isPhone }) => {
    const TOL = 2;
    const errors = [];
    const warnings = [];

    const push = (level, type, payload) => {
      const item = { level, type, ...payload };
      if (level === "ERROR") errors.push(item);
      else warnings.push(item);
    };

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const docEl = document.documentElement;
    const pageOverflow = docEl.scrollWidth - docEl.clientWidth;
    if (pageOverflow > TOL) {
      // Help identify offender (widest right-edge element)
      let worst = null;
      document.querySelectorAll("body *").forEach((el) => {
        if (!(el instanceof Element)) return;
        const st = getComputedStyle(el);
        if (st.display === "none" || st.visibility === "hidden") return;
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return;
        if (r.right <= vw + TOL) return;
        const over = r.right - vw;
        if (!worst || over > worst.over) {
          const tag = el.tagName.toLowerCase();
          const id = el.id ? `#${el.id}` : "";
          const cls = (el.className && String(el.className).split(/\s+/).filter(Boolean)[0]) || "";
          worst = {
            over,
            selector: `${tag}${id}${cls ? "." + cls : ""}`,
            rect: {
              x: Math.round(r.x),
              y: Math.round(r.y),
              width: Math.round(r.width),
              height: Math.round(r.height),
              right: Math.round(r.right),
            },
          };
        }
      });
      push("ERROR", "page_horizontal_overflow", {
        selector: worst ? worst.selector : "html",
        detail: `scrollWidth-clientWidth=${pageOverflow}` +
          (worst ? `; widestRight=${worst.selector}(+${Math.round(worst.over)}px)` : ""),
        rect: worst
          ? { scrollWidth: docEl.scrollWidth, clientWidth: docEl.clientWidth, ...worst.rect }
          : { scrollWidth: docEl.scrollWidth, clientWidth: docEl.clientWidth },
      });
    }

    const isVisible = (el) => {
      if (!el || !(el instanceof Element)) return false;
      const style = window.getComputedStyle(el);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity) === 0
      ) {
        return false;
      }
      const r = el.getBoundingClientRect();
      if (r.width < 1 && r.height < 1) return false;
      // intentionally off-screen nav / drawers
      if (
        el.closest(
          ".offcanvas, .drawer, [aria-hidden='true'], [hidden], .sr-only, .visually-hidden"
        )
      ) {
        return false;
      }
      if (style.position === "fixed" || style.position === "absolute") {
        // skip far-off overlays kept for animation
        if (r.right < -40 || r.left > vw + 40) return false;
      }
      return true;
    };

    const cssPath = (el) => {
      if (!el || !el.tagName) return "unknown";
      if (el.id) return `${el.tagName.toLowerCase()}#${el.id}`;
      const cls = (el.className && String(el.className).split(/\s+/).filter(Boolean)[0]) || "";
      const tag = el.tagName.toLowerCase();
      return cls ? `${tag}.${cls}` : tag;
    };

    const SELECTOR =
      "main, section, article, table, form, nav, header, dialog, [role='dialog'], .modal, [class*='modal'], [class*='card'], button, input, select, textarea, .page-content, .cs-v6-main, .page-head";

    const SCROLLPORT_SEL =
      ".responsive-table, .cs-table-wrap, .yonetim-table-wrap, .st-table-wrap, .ktt-table-wrap, .report-data-table-wrap, .dd-matrix-wrap, .dp-matrix-scroll, .ep-table-wrap, .ep-week-grid-wrap, .ep-grid-wrap, .fn-table-wrap, .pid-table-wrap, [class*='-wrap']";

    const inIntentionalScrollport = (el) => {
      const wrap = el.closest(SCROLLPORT_SEL);
      if (!wrap || wrap === el) return false;
      const ws = getComputedStyle(wrap);
      const scrolls =
        ws.overflowX === "auto" ||
        ws.overflowX === "scroll" ||
        ws.overflow === "auto" ||
        ws.overflow === "scroll";
      if (!scrolls) return false;
      const wr = wrap.getBoundingClientRect();
      // Wrap itself must fit viewport (page not expanded)
      return wr.left >= -TOL && wr.right <= vw + TOL + 1;
    };

    document.querySelectorAll(SELECTOR).forEach((el) => {
      if (!isVisible(el)) return;
      if (inIntentionalScrollport(el)) return;
      const r = el.getBoundingClientRect();
      const overflowLeft = r.left < -TOL;
      const overflowRight = r.right > vw + TOL;
      if (!overflowLeft && !overflowRight) return;

      // ignore tiny decorative / icon-only chips slightly over
      if (r.width < 8 || r.height < 8) return;

      // Real dialogs only — ignore decorative .fn-modal panels
      const isModal =
        el.matches("dialog, [role='dialog'], .modal, [data-ep-modal], [data-dp-modal], [data-tz-modal]") ||
        !!el.closest("dialog, [role='dialog'], [data-ep-modal], [data-dp-modal], [data-tz-modal]");
      const isMain =
        el.matches("main, .page-content, .cs-v6-main, header, nav") ||
        el.tagName === "MAIN";

      const level = isModal || isMain ? "ERROR" : "WARNING";
      push(level, isModal ? "modal_viewport_overflow" : "element_viewport_overflow", {
        selector: cssPath(el),
        detail: overflowLeft ? "left" : "right",
        rect: {
          x: Math.round(r.x),
          y: Math.round(r.y),
          width: Math.round(r.width),
          height: Math.round(r.height),
        },
      });
    });

    // Parent/child overflow for layout containers
    const containers = document.querySelectorAll(
      ".page-content, .cs-v6-main, [class*='grid'], [class*='split'], [class*='card'], .responsive-table, .cs-table-wrap, [class*='-wrap']"
    );
    containers.forEach((parent) => {
      if (!isVisible(parent)) return;
      const pr = parent.getBoundingClientRect();
      if (pr.width < 40) return;
      const pStyle = getComputedStyle(parent);
      const allowsX =
        pStyle.overflowX === "auto" ||
        pStyle.overflowX === "scroll" ||
        parent.classList.contains("responsive-table") ||
        parent.classList.contains("cs-table-wrap") ||
        /wrap$/i.test(parent.className || "");

      Array.from(parent.children || []).slice(0, 40).forEach((child) => {
        if (!isVisible(child)) return;
        const cr = child.getBoundingClientRect();
        const over = cr.width - pr.width;
        if (over <= TOL + 4) return;
        if (allowsX) return; // intentional scrollport
        push("WARNING", "container_child_overflow", {
          selector: `${cssPath(parent)} > ${cssPath(child)}`,
          detail: `child wider by ${Math.round(over)}px`,
          rect: {
            parentWidth: Math.round(pr.width),
            childWidth: Math.round(cr.width),
          },
        });
      });
    });

    // Text clipping (hidden/clip overflow + scroll overflow)
    document
      .querySelectorAll("h1, h2, h3, p, label, th, td, .page-head, [class*='title']")
      .forEach((el) => {
        if (!isVisible(el)) return;
        const style = getComputedStyle(el);
        const ox = style.overflowX;
        const oy = style.overflowY;
        const clipped =
          ox === "hidden" ||
          ox === "clip" ||
          oy === "hidden" ||
          oy === "clip" ||
          style.textOverflow === "ellipsis";
        if (!clipped) return;
        const xCut = el.scrollWidth - el.clientWidth > TOL + 4;
        const yCut = el.scrollHeight - el.clientHeight > TOL + 8;
        if (!xCut && !yCut) return;
        // skip expected ellipsis single-line titles
        if (style.textOverflow === "ellipsis" && !yCut && el.scrollWidth - el.clientWidth < 80) {
          return;
        }
        push("WARNING", "text_clipping", {
          selector: cssPath(el),
          detail: xCut ? "horizontal" : "vertical",
          rect: {
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth,
            scrollHeight: el.scrollHeight,
            clientHeight: el.clientHeight,
          },
        });
      });

    // Touch targets on phone viewports
    if (isPhone) {
      const controls = document.querySelectorAll(
        "button, a.primary-btn, a.ghost-btn, a.btn, a.btn-primary, input, select, [role='button']"
      );
      let smallCount = 0;
      controls.forEach((el) => {
        if (!isVisible(el)) return;
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return;
        // skip pure text nav links without button classes (inline text links: leave alone)
        if (el.tagName === "A") {
          const cls = String(el.className || "");
          const isAction =
            /(^|\s)(primary-btn|ghost-btn|btn|btn-primary|btn-ghost|small-button|yonetim-action-btn|yonetim-head-ghost)(\s|$)/.test(
              cls
            );
          if (!isAction) return;
        }
        // skip non-button-like inputs (checkbox/radio/hidden — not text controls)
        if (el.tagName === "INPUT") {
          const t = String(el.getAttribute("type") || "text").toLowerCase();
          if (["checkbox", "radio", "hidden", "file", "color", "range", "image"].includes(t)) {
            return;
          }
        }
        const min = Math.min(r.width, r.height);
        if (min + 0.5 < 44) {
          smallCount += 1;
          if (smallCount <= 12) {
            push("WARNING", "touch_target_small", {
              selector: cssPath(el),
              detail: `${Math.round(r.width)}x${Math.round(r.height)}`,
              rect: {
                width: Math.round(r.width),
                height: Math.round(r.height),
              },
            });
          }
        }
      });
    }

    // Critical: primary nav/header missing or zero size
    const header = document.querySelector("header, .topbar, .v6-top, nav");
    if (header && isVisible(header)) {
      const hr = header.getBoundingClientRect();
      if (hr.height < 8) {
        push("ERROR", "header_collapsed", {
          selector: cssPath(header),
          detail: "header height < 8",
          rect: { height: Math.round(hr.height) },
        });
      }
    }

    return {
      errors: errors.slice(0, 80),
      warnings: warnings.slice(0, 80),
      meta: { vw, vh, pageOverflow },
    };
  }, { isPhone });
}

module.exports = { analyzePage };
