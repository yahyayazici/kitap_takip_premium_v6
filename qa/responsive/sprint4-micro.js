/**
 * Personel /panel/ bottom micro-pass capture + metrics.
 * Usage: node sprint4-micro.js before|after
 */
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");
const { authStatePath, loadDotenv } = require("./helpers/layout");

loadDotenv();

const label = process.argv[2] || "shot";
const OUT = path.join(__dirname, "screenshots", "sprint4", `micro-${label}`);
fs.mkdirSync(OUT, { recursive: true });

const VPS = [
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1440", width: 1440, height: 900 },
  { name: "1536", width: 1536, height: 864 },
];

async function measure(page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    const overflowX = Math.max(doc.scrollWidth, body.scrollWidth) - window.innerWidth;
    const pageH = Math.max(doc.scrollHeight, body.scrollHeight);
    const fold = window.innerHeight;

    const box = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        h: Math.round(r.height),
        w: Math.round(r.width),
        top: Math.round(r.top + window.scrollY),
        bg: cs.backgroundColor,
        border: cs.borderColor,
        color: cs.color,
      };
    };

    const items = [...document.querySelectorAll(".mudahale-ai-item")].map((el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        h: Math.round(r.height),
        bg: cs.backgroundColor,
        border: cs.borderTopColor,
      };
    });

    const yenile = document.querySelector(".ai-zekasi-yenile");
    let yenileBox = null;
    if (yenile) {
      const r = yenile.getBoundingClientRect();
      yenileBox = { w: Math.round(r.width), h: Math.round(r.height) };
    }

    const panel = document.querySelector(".ai-zekasi-panel");
    const loading = document.querySelector(".ai-zekasi-loading, .ai-zekasi-error");
    const analiz = document.querySelector(".ai-zekasi-panel .ktt-analiz-card");

    return {
      pageH,
      overflowX,
      fold,
      notice: box(".ai-setup-notice"),
      erken: box(".ai-erken-uyari"),
      erkenHead: box(".ai-erken-uyari-head h2"),
      hero: box(".dash-ai-hero, .dash-ai-bottom"),
      widget: box(".ai-zekasi-widget"),
      panel: box(".ai-zekasi-panel"),
      loading: loading
        ? {
            text: loading.textContent.trim(),
            h: Math.round(loading.getBoundingClientRect().height),
          }
        : null,
      hasAnaliz: Boolean(analiz),
      yenile: yenileBox,
      items,
      itemCount: items.length,
    };
  });
}

(async () => {
  const launchOpts = { headless: true };
  try {
    launchOpts.channel = "chrome";
  } catch (_) {}
  let browser;
  try {
    browser = await chromium.launch(launchOpts);
  } catch (e) {
    delete launchOpts.channel;
    browser = await chromium.launch(launchOpts);
  }

  const metrics = {};
  for (const vp of VPS) {
    const context = await browser.newContext({
      baseURL: process.env.BASE_URL || "http://127.0.0.1:8000",
      storageState: authStatePath("personel"),
      viewport: { width: vp.width, height: vp.height },
    });
    const page = await context.newPage();
    await page.goto("/panel/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1800);
    const m = await measure(page);
    metrics[vp.name] = m;

    const dest = path.join(OUT, `panel-${vp.name}.png`);
    await page.screenshot({ path: dest, fullPage: true });

    const erken = page.locator(".ai-erken-uyari");
    if (await erken.count()) {
      await erken.screenshot({ path: path.join(OUT, `erken-${vp.name}.png`) });
    }
    const widget = page.locator(".ai-zekasi-widget");
    if (await widget.count()) {
      await widget.screenshot({ path: path.join(OUT, `ai-${vp.name}.png`) });
    }
    const hero = page.locator(".dash-ai-hero, .dash-ai-bottom");
    if (await hero.count()) {
      await hero.first().screenshot({ path: path.join(OUT, `bottom-${vp.name}.png`) });
    }

    if (label === "after") {
      await page.evaluate(() => {
        const panel = document.querySelector(".ai-zekasi-panel");
        if (!panel) return;
        panel.innerHTML = `
          <section class="ktt-analiz-card ai-zekasi-card">
            <header class="ktt-analiz-head">
              <div class="ktt-analiz-head-text">
                <p class="ktt-analiz-kicker">Gelişim Zekası</p>
                <h2 class="ktt-analiz-title">Kurum özeti</h2>
              </div>
              <span class="ktt-analiz-badge is-data">Kural tabanlı</span>
            </header>
            <div class="ktt-analiz-stack">
              <article class="ktt-analiz-section">
                <h3 class="ktt-analiz-section-title">Öncelikler</h3>
                <div class="ktt-analiz-section-body">Etüt katılımı düşük olan talebeler için erken müdahale önerilir. Bu blok, gerçek analiz geldiğinde doğal yükseklikte açılmayı doğrular.</div>
              </article>
            </div>
          </section>`;
      });
      const filled = await measure(page);
      metrics[vp.name].filledWidget = filled.widget;
      metrics[vp.name].hasAnalizFilled = filled.hasAnaliz;
      metrics[vp.name].overflowXFilled = filled.overflowX;
      if (await hero.count()) {
        await hero.first().screenshot({
          path: path.join(OUT, `bottom-filled-${vp.name}.png`),
        });
      }
    }

    await context.close();
    console.log("wrote", dest);
  }

  const jsonPath = path.join(OUT, "metrics.json");
  fs.writeFileSync(jsonPath, JSON.stringify(metrics, null, 2));
  console.log("metrics", JSON.stringify(metrics, null, 2));
  await browser.close();
})();
