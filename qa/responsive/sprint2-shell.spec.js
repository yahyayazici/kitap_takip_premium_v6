/**
 * Sprint 2 shell / typography / overflow measurements.
 * Run: npm run qa:sprint2  (from qa/responsive)
 * Not part of default QA_SMOKE (testMatch stays on responsive.spec.js).
 */
const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");
const { analyzePage } = require("./helpers/overflow");
const { authStatePath, roleHasCredentials } = require("./helpers/layout");

const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1024", width: 1024, height: 768 },
  { name: "1366", width: 1366, height: 768 },
  { name: "1440", width: 1440, height: 900 },
];

const SHELLS = [
  { id: "personel", path: "/panel/", role: "personel" },
  { id: "yonetim", path: "/yonetim/", role: "yonetim" },
  { id: "ogretmen", path: "/ogretmen-panel/", role: "ogretmen" },
  { id: "veli", path: "/veli/", role: "veli" },
  { id: "talebe", path: "/talebe/", role: "talebe" },
];

const EXTRA = [
  { id: "talebe-listesi", path: "/talebeler/", role: "personel", kind: "list-pagehead" },
  { id: "kitap-ekle", path: "/kitap-ekle/", role: "personel", kind: "form" },
  { id: "dini-ders", path: "/dini-ders/", role: "personel", kind: "dini" },
  { id: "raporlar", path: "/raporlar/", role: "personel", kind: "page-head" },
  { id: "etut-plan", path: "/etut-plani/", role: "personel", kind: "etut" },
  { id: "yonetim-personel", path: "/yonetim/personeller/", role: "yonetim", kind: "dense-table" },
];

const REPORT_PATH = path.join(__dirname, "reports", "sprint2-metrics.json");
const results = [];

function authExists(role) {
  try {
    return fs.existsSync(authStatePath(role));
  } catch {
    return false;
  }
}

async function openAs(browser, testInfo, role, viewport) {
  const context = await browser.newContext({
    baseURL: testInfo.project.use.baseURL || process.env.BASE_URL || "http://127.0.0.1:8000",
    storageState: authStatePath(role),
    viewport: { width: viewport.width, height: viewport.height },
  });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err && err.message ? err.message : err));
  });
  return { context, page, consoleErrors };
}

async function measure(page, meta) {
  return page.evaluate((metaIn) => {
    const docEl = document.documentElement;
    const overflow = docEl.scrollWidth - docEl.clientWidth;
    const vw = window.innerWidth;
    const h1 = document.querySelector("h1");
    const h2 = document.querySelector("h2");
    const h1cs = h1 ? getComputedStyle(h1) : null;
    const h2cs = h2 ? getComputedStyle(h2) : null;
    const toggle = document.querySelector(
      "#v3-menu-toggle, #yonetim-menu-toggle, #talebe-menu-toggle, #ogretmen-menu-toggle, #veli-menu-toggle, .v3-menu-toggle"
    );
    const nav = document.querySelector("#v3-nav, #yonetim-nav, #talebe-nav, #ogretmen-nav, #veli-nav, .cs-v6-nav, .v3-nav");
    let toggleBox = null;
    let toggleVisible = false;
    if (toggle) {
      const r = toggle.getBoundingClientRect();
      const st = getComputedStyle(toggle);
      toggleVisible =
        st.display !== "none" &&
        st.visibility !== "hidden" &&
        r.width > 1 &&
        r.height > 1;
      toggleBox = {
        w: Math.round(r.width),
        h: Math.round(r.height),
        display: st.display,
      };
    }
    let navBox = null;
    if (nav) {
      const r = nav.getBoundingClientRect();
      navBox = {
        left: Math.round(r.left),
        right: Math.round(r.right),
        width: Math.round(r.width),
        open: nav.classList.contains("open"),
      };
    }
    const pageHead = document.querySelector(
      ".page-head, .patterned-page-head, .yonetim-page-head, .ogretmen-page-head"
    );
    let pageHeadFlex = null;
    if (pageHead) {
      const st = getComputedStyle(pageHead);
      pageHeadFlex = {
        direction: st.flexDirection,
        wrap: st.flexWrap,
        align: st.alignItems,
      };
    }
    const topic = document.querySelector(".dd-topic-col");
    let topicBox = null;
    if (topic) {
      const r = topic.getBoundingClientRect();
      topicBox = { w: Math.round(r.width), h: Math.round(r.height) };
    }
    const header = document.querySelector("header, .cs-v6-header, .v3-header");
    const headerH = header ? Math.round(header.getBoundingClientRect().height) : 0;
    const main = document.querySelector("main, .cs-v6-main, .v3-main");
    const mainTop = main ? Math.round(main.getBoundingClientRect().top) : null;
    return {
      ...metaIn,
      overflow,
      h1: h1cs
        ? { text: (h1.textContent || "").trim().slice(0, 48), size: h1cs.fontSize, weight: h1cs.fontWeight }
        : null,
      h2: h2cs
        ? { text: (h2.textContent || "").trim().slice(0, 48), size: h2cs.fontSize, weight: h2cs.fontWeight }
        : null,
      toggleVisible,
      toggleBox,
      navBox,
      pageHeadFlex,
      topicBox,
      headerH,
      mainTop,
    };
  }, meta);
}

test.describe("sprint2 shell", () => {
  test.skip(process.env.QA_SPRINT2 !== "1", "opt-in: QA_SPRINT2=1");
  test.describe.configure({ mode: "serial" });

  test.afterAll(() => {
    fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify({ generatedAt: new Date().toISOString(), results }, null, 2));
  });

  for (const vp of VIEWPORTS) {
    test.describe(`${vp.name}x${vp.height}`, () => {
      for (const route of [...SHELLS, ...EXTRA]) {
        test(`${route.id}`, async ({ browser }, testInfo) => {
          if (testInfo.project.name === "setup") test.skip();
          const role = route.role || "personel";
          test.skip(!roleHasCredentials(role) && !authExists(role), `No auth for ${role}`);
          test.skip(!authExists(role), `Missing storageState ${role}`);

          const { context, page, consoleErrors } = await openAs(browser, testInfo, role, vp);
          try {
            let response = await page.goto(route.path, { waitUntil: "domcontentloaded" });
            if (response && response.status() >= 500) {
              await page.waitForTimeout(750);
              response = await page.goto(route.path, { waitUntil: "domcontentloaded" });
            }
            expect(page.url(), "auth").not.toContain("/giris");
            await page.waitForTimeout(350);
            await page.waitForLoadState("load").catch(() => {});

            const findings = await analyzePage(page, { isPhone: vp.width <= 430 });
            const metrics = await measure(page, {
              route: route.id,
              path: route.path,
              viewport: `${vp.width}x${vp.height}`,
              http: response ? response.status() : 0,
            });

            if (vp.width <= 1400 && SHELLS.some((s) => s.id === route.id)) {
              const toggle = page.locator(
                "#v3-menu-toggle, #yonetim-menu-toggle, #talebe-menu-toggle, #ogretmen-menu-toggle, #veli-menu-toggle"
              );
              if (await toggle.count()) {
                await expect(toggle.first()).toBeVisible();
                const box = await toggle.first().boundingBox();
                expect.soft(box, "hamburger box").toBeTruthy();
                if (box) {
                  expect.soft(box.width, "hamburger width").toBeGreaterThanOrEqual(44);
                  expect.soft(box.height, "hamburger height").toBeGreaterThanOrEqual(44);
                }
                await toggle.first().click();
                await page.waitForTimeout(200);
                const navOpen = await page.evaluate(() => {
                  const nav = document.querySelector(
                    "#v3-nav.open, #yonetim-nav.open, #talebe-nav.open, #ogretmen-nav.open, #veli-nav.open, .cs-v6-nav.open, .v3-nav.open"
                  );
                  if (!nav) return { open: false };
                  const r = nav.getBoundingClientRect();
                  return {
                    open: true,
                    left: r.left,
                    right: r.right,
                    overflowRight: r.right - window.innerWidth,
                  };
                });
                expect.soft(navOpen.open, "nav opens").toBeTruthy();
                if (navOpen.open) {
                  expect.soft(navOpen.overflowRight, "nav stays in viewport").toBeLessThanOrEqual(2);
                  expect.soft(navOpen.left, "nav left").toBeGreaterThanOrEqual(-2);
                }
                await page.keyboard.press("Escape");
              }
            }

            if (route.kind === "dense-table") {
              const dense = await page.locator(".cs-table-dense, .yonetim-table-wrap, .responsive-table").first();
              if (await dense.count()) {
                const overflow = await page.evaluate(() => {
                  const el = document.querySelector(".cs-table-dense, .yonetim-table-wrap, .responsive-table");
                  if (!el) return 0;
                  const r = el.getBoundingClientRect();
                  return Math.max(0, r.right - window.innerWidth);
                });
                expect.soft(overflow, "dense table wrap stays in viewport").toBeLessThanOrEqual(2);
              }
            }

            if (route.kind === "dini") {
              const topic = page.locator(".dd-topic-col").first();
              if (await topic.count()) {
                const box = await topic.boundingBox();
                if (box) {
                  expect.soft(box.width, "dd-topic-col width").toBeGreaterThanOrEqual(44);
                }
              }
            }

            const h1px = metrics.h1 ? parseFloat(metrics.h1.size) : 0;
            if (h1px) {
              expect.soft(h1px, "page H1 not body-sized").toBeGreaterThanOrEqual(18);
            }
            const h2px = metrics.h2 ? parseFloat(metrics.h2.size) : 0;
            if (h2px && metrics.h2 && /card|özel|panel|yct/i.test(metrics.h2.text || "")) {
              expect.soft(h2px, "card H2 not 14px body").toBeGreaterThanOrEqual(15);
            }

            expect.soft(metrics.overflow, "root horizontal overflow").toBeLessThanOrEqual(2);
            expect.soft(findings.errors.length, findings.errors.map((e) => e.type).join(",")).toBe(0);

            results.push({
              ...metrics,
              consoleErrors: consoleErrors.slice(0, 12),
              analyzeErrors: findings.errors.slice(0, 8),
              analyzeWarnings: findings.warnings.slice(0, 12),
            });
          } finally {
            await context.close();
          }
        });
      }
    });
  }
});
