/**
 * Sprint 4 visual capture. Usage:
 *   node sprint4-shots.js before
 *   node sprint4-shots.js after
 */
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");
const { authStatePath, loadDotenv } = require("./helpers/layout");

loadDotenv();

const label = process.argv[2] || "shot";
const OUT = path.join(__dirname, "screenshots", "sprint4", label);
fs.mkdirSync(OUT, { recursive: true });

const VPS = [
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1440", width: 1440, height: 900 },
];

const ROUTES = [
  { id: "personel", path: "/panel/", role: "personel" },
  { id: "ogretmen", path: "/ogretmen-panel/", role: "ogretmen" },
  { id: "veli", path: "/veli/", role: "veli" },
  { id: "yonetim-talebe", path: "/yonetim/talebeler/", role: "yonetim" },
  { id: "talebe-listesi", path: "/talebeler/", role: "personel" },
  { id: "etut-plan", path: "/etut-plani/", role: "personel" },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  for (const vp of VPS) {
    for (const route of ROUTES) {
      const context = await browser.newContext({
        baseURL: process.env.BASE_URL || "http://127.0.0.1:8000",
        storageState: authStatePath(route.role),
        viewport: { width: vp.width, height: vp.height },
      });
      const page = await context.newPage();
      await page.goto(route.path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(500);
      const dest = path.join(OUT, `${route.id}-${vp.name}.png`);
      await page.screenshot({ path: dest, fullPage: true });
      await context.close();
      console.log("wrote", dest);
    }
  }
  await browser.close();
})();
