/**
 * Sprint 4 visual QA measurements.
 * node sprint4-qa.js
 */
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");
const { authStatePath, loadDotenv } = require("./helpers/layout");

loadDotenv();

const OUT = path.join(__dirname, "reports", "sprint4-metrics.json");
const VPS = [
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1024", width: 1024, height: 768 },
  { name: "1366", width: 1366, height: 768 },
  { name: "1440", width: 1440, height: 900 },
];

const ROUTES = [
  { id: "personel", path: "/panel/", role: "personel" },
  { id: "yonetim", path: "/yonetim/", role: "yonetim" },
  { id: "ogretmen", path: "/ogretmen-panel/", role: "ogretmen" },
  { id: "veli", path: "/veli/", role: "veli" },
  { id: "talebe", path: "/talebe/", role: "talebe" },
  { id: "talebe-listesi", path: "/talebeler/", role: "personel" },
  { id: "yonetim-talebe", path: "/yonetim/talebeler/", role: "yonetim" },
  { id: "etut-plan", path: "/etut-plani/", role: "personel" },
  { id: "dini-ders", path: "/dini-ders/", role: "personel" },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const vp of VPS) {
    for (const route of ROUTES) {
      const context = await browser.newContext({
        baseURL: process.env.BASE_URL || "http://127.0.0.1:8000",
        storageState: authStatePath(route.role),
        viewport: { width: vp.width, height: vp.height },
      });
      const page = await context.newPage();
      const consoleErrors = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });
      page.on("pageerror", (err) => consoleErrors.push(String(err.message || err)));
      await page.goto(route.path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(250);
      const metrics = await page.evaluate(() => {
        const overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
        const header = document.querySelector(".v3-header, .cs-v6-header");
        const headerH = header ? header.getBoundingClientRect().height : 0;
        const touchSel =
          "a.primary-btn, a.ghost-btn, button.primary-btn, .yonetim-search-btn, .og-wow-cta, .dash-shortcut-card, .tl-btn, .ep-btn, .ep-btn-sm";
        const undersized = [];
        document.querySelectorAll(touchSel).forEach((el) => {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.height > 0 && (r.height < 43 || r.width < 43)) {
            undersized.push({
              tag: el.tagName,
              cls: (el.className || "").toString().slice(0, 80),
              w: Math.round(r.width),
              h: Math.round(r.height),
            });
          }
        });
        const hero = document.querySelector(".dash-hero");
        const pageHead = document.querySelector("header.page-head, header.yonetim-page-head");
        return {
          url: location.pathname,
          overflow,
          headerH: Math.round(headerH),
          undersized: undersized.slice(0, 8),
          undersizedCount: undersized.length,
          heroBg: hero ? getComputedStyle(hero).backgroundColor : null,
          heroAnim: hero ? getComputedStyle(hero).animationName : null,
          pageHeadBg: pageHead ? getComputedStyle(pageHead).backgroundColor : null,
          pageHeadColor: pageHead ? getComputedStyle(pageHead).color : null,
        };
      });
      results.push({
        route: route.id,
        viewport: vp.name,
        ...metrics,
        consoleErrors: consoleErrors.slice(0, 12),
      });
      await context.close();
      const flag = metrics.overflow !== 0 || metrics.undersizedCount ? "!" : "ok";
      console.log(flag, vp.name, route.id, "overflow", metrics.overflow, "touch<", metrics.undersizedCount, "url", metrics.url);
    }
  }
  await browser.close();
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
  const overflows = results.filter((r) => r.overflow !== 0);
  const touches = results.filter((r) => r.undersizedCount > 0);
  console.log("\nsummary overflow", overflows.length, "touch-fail-rows", touches.length);
})();
