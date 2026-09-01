/**
 * Sprint 5 — real role QA (login, redirect, portals, network, overflow).
 * Run: npm run qa:sprint5  (from qa/responsive)
 */
const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");
const { analyzePage } = require("./helpers/overflow");
const {
  authStatePath,
  credentialsForRole,
  roleHasCredentials,
  SCREENSHOT_DIR,
} = require("./helpers/layout");

const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1024", width: 1024, height: 768 },
  { name: "1440", width: 1440, height: 900 },
  { name: "1536", width: 1536, height: 864 },
];

const PORTALS = [
  {
    role: "personel",
    home: "/panel/",
    loginPrefix: "/panel",
    extra: ["/talebeler/", "/etut-plani/"],
  },
  {
    role: "yonetim",
    home: "/yonetim/",
    loginPrefix: "/panel",
    extra: ["/yonetim/duyurular/", "/yonetim/talebeler/"],
  },
  {
    role: "ogretmen",
    home: "/ogretmen-panel/",
    loginPrefix: "/ogretmen-panel",
    extra: ["/ogretmen-panel/ders-programi/"],
  },
  {
    role: "veli",
    home: "/veli/",
    loginPrefix: "/veli",
    extra: ["/veli/duyurular/"],
  },
  {
    role: "talebe",
    home: "/talebe/",
    loginPrefix: "/talebe",
    extra: ["/talebe/profil/"],
  },
];

const CROSS = [
  { role: "ogretmen", forbidden: "/yonetim/", mustNotStay: "/yonetim" },
  { role: "veli", forbidden: "/ogretmen-panel/", mustNotStay: "/ogretmen-panel" },
  { role: "talebe", forbidden: "/panel/", mustNotStay: "/panel" },
];

const REPORT_PATH = path.join(__dirname, "reports", "sprint5-roles.json");
const OUT_SHOTS = path.join(SCREENSHOT_DIR, "sprint5");
const results = [];

function authExists(role) {
  try {
    return fs.existsSync(authStatePath(role));
  } catch {
    return false;
  }
}

function classifyStatus(url, status) {
  const u = String(url || "");
  if (status >= 500) {
    if (/\/panel\/ai\//.test(u)) return "C";
    return "A";
  }
  if (status === 404) {
    if (/\/media\//.test(u)) return "B";
    return "A";
  }
  if (status === 403) return "C";
  return "";
}

test.describe.configure({ mode: "serial" });

test("sprint5 login redirects for five roles", async ({ browser, baseURL }) => {
  const report = { logins: {}, generatedAt: new Date().toISOString() };
  for (const portal of PORTALS) {
    test.skip(!roleHasCredentials(portal.role), `No credentials for ${portal.role}`);
    const { username, password } = credentialsForRole(portal.role);
    const context = await browser.newContext({
      baseURL: baseURL || "http://127.0.0.1:8000",
      viewport: { width: 1440, height: 900 },
      storageState: { cookies: [], origins: [] },
    });
    const page = await context.newPage();
    await page.goto("/giris/", { waitUntil: "domcontentloaded" });
    await page.locator('input[name="username"]').fill(username);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
      page.waitForURL((url) => !String(url.pathname || "").includes("/giris"), {
        timeout: 60000,
      }),
      page.locator('button[type="submit"], .gate-submit').first().click(),
    ]);
    const pathname = new URL(page.url()).pathname;
    report.logins[portal.role] = { username, pathname };
    expect(
      pathname.startsWith(portal.loginPrefix),
      `${portal.role} landed on ${pathname}, expected prefix ${portal.loginPrefix}`
    ).toBeTruthy();
    await context.close();
  }
  results.push({ kind: "login", ...report });
});

test("sprint5 cross-role RBAC is not bypassed", async ({ browser, baseURL }) => {
  for (const row of CROSS) {
    test.skip(!authExists(row.role), `Missing storageState ${row.role}`);
    const context = await browser.newContext({
      baseURL: baseURL || "http://127.0.0.1:8000",
      storageState: authStatePath(row.role),
      viewport: { width: 1440, height: 900 },
    });
    const page = await context.newPage();
    await page.goto(row.forbidden, { waitUntil: "domcontentloaded" });
    const pathname = new URL(page.url()).pathname;
    expect(
      pathname.startsWith(row.mustNotStay),
      `${row.role} must not remain on ${row.forbidden} (now ${pathname})`
    ).toBeFalsy();
    await context.close();
  }
});

for (const portal of PORTALS) {
  for (const vp of VIEWPORTS) {
    test(`sprint5 ${portal.role} ${vp.name} ${portal.home}`, async ({
      browser,
      baseURL,
    }, testInfo) => {
      test.skip(!authExists(portal.role), `Missing storageState ${portal.role}`);
      fs.mkdirSync(path.join(OUT_SHOTS, vp.name), { recursive: true });
      const context = await browser.newContext({
        baseURL: baseURL || "http://127.0.0.1:8000",
        storageState: authStatePath(portal.role),
        viewport: { width: vp.width, height: vp.height },
      });
      const page = await context.newPage();
      const consoleErrors = [];
      const net = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });
      page.on("pageerror", (err) => {
        consoleErrors.push(String(err && err.message ? err.message : err));
      });
      page.on("response", (res) => {
        const status = res.status();
        if (status >= 400) {
          net.push({
            url: res.url(),
            status,
            bucket: classifyStatus(res.url(), status),
          });
        }
      });

      const response = await page.goto(portal.home, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(700);
      const status = response ? response.status() : 0;
      const pathname = new URL(page.url()).pathname;
      expect(
        pathname.startsWith(portal.home.replace(/\/$/, "")),
        `stayed in portal (${pathname})`
      ).toBeTruthy();
      expect(status, "home HTTP").toBeLessThan(500);

      const analysis = await analyzePage(page, { isPhone: vp.width <= 430 });
      expect(analysis.meta.pageOverflow, "horizontal overflow").toBeLessThanOrEqual(2);

      const toggle = page.locator(
        "#v3-menu-toggle, #yonetim-menu-toggle, #talebe-menu-toggle, #ogretmen-menu-toggle, #veli-menu-toggle, .v3-menu-toggle, .yonetim-menu-toggle"
      );
      if (vp.width <= 768 && (await toggle.count())) {
        const box = await toggle.first().boundingBox();
        if (box) {
          expect(Math.min(box.width, box.height), "hamburger touch").toBeGreaterThanOrEqual(44);
        }
      }

      const brokenImgs = await page.evaluate(() =>
        [...document.images].filter((img) => img.complete && img.naturalWidth === 0 && img.src).length
      );
      expect(brokenImgs, "broken images").toBe(0);

      const app500 = net.filter((n) => n.bucket === "A" && n.status >= 500);
      expect(app500, `unexpected app 5xx: ${JSON.stringify(app500)}`).toHaveLength(0);

      const logout = page.locator('a[href*="cikis"], a[href*="logout"], .v3-logout, .gate-logout').first();
      if (await logout.count()) {
        const lbox = await logout.boundingBox();
        if (lbox && vp.width <= 430) {
          expect(Math.min(lbox.width, lbox.height) || lbox.height).toBeGreaterThanOrEqual(32);
        }
      }

      await page.screenshot({
        path: path.join(OUT_SHOTS, vp.name, `${portal.role}-home.png`),
        fullPage: true,
      });

      for (const extra of portal.extra) {
        const extraRes = await page.goto(extra, { waitUntil: "domcontentloaded" });
        await page.waitForTimeout(350);
        const extraStatus = extraRes ? extraRes.status() : 0;
        expect(extraStatus, `${extra} HTTP`).toBeLessThan(500);
      }

      results.push({
        role: portal.role,
        viewport: vp.name,
        home: portal.home,
        pathname,
        status,
        overflow: analysis.meta.pageOverflow,
        consoleErrors: consoleErrors.filter(
          (t) => !/favicon|Failed to load resource/.test(t)
        ),
        network: net,
        findings: analysis.errors,
      });

      await context.close();
    });
  }
}

test.afterAll(async () => {
  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(results, null, 2));
});
