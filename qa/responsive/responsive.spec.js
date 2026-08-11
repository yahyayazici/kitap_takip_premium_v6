const fs = require("fs");
const { test, expect } = require("@playwright/test");
const { getRoutes } = require("./routes");
const { analyzePage } = require("./helpers/overflow");
const {
  screenshotPath,
  authStatePath,
  roleHasCredentials,
} = require("./helpers/layout");

const routes = getRoutes();

function isPhoneProject(name) {
  return String(name || "").startsWith("phone-");
}

function authExists(role) {
  try {
    return fs.existsSync(authStatePath(role));
  } catch {
    return false;
  }
}

/**
 * Soft-fail on ERROR findings; always keep screenshot + annotation for reporter.
 */
for (const route of routes) {
  test.describe(`${route.id}`, () => {
    test.describe.configure({ mode: "default" });

    test(`responsive · ${route.path}`, async ({ page, browser, browserName }, testInfo) => {
      const viewportName = testInfo.project.name;
      if (viewportName === "setup") test.skip();

      const role = route.role || "personel";
      test.skip(
        !roleHasCredentials(role) && !authExists(role),
        `No auth for role=${role}`
      );
      test.skip(!authExists(role), `Missing storageState for role=${role} — run auth setup`);

      // Use role-specific storage when not the default personel project state
      let activePage = page;
      let extraContext = null;
      if (role !== "personel") {
        extraContext = await browser.newContext({
          baseURL: testInfo.project.use.baseURL || process.env.BASE_URL || "http://127.0.0.1:8000",
          storageState: authStatePath(role),
          viewport: testInfo.project.use.viewport,
        });
        activePage = await extraContext.newPage();
      }

      try {
        let response = await activePage.goto(route.path, {
          waitUntil: "domcontentloaded",
        });
        // One retry for transient local 5xx (SQLite lock / cold start under load)
        if (response && response.status() >= 500) {
          await activePage.waitForTimeout(750);
          response = await activePage.goto(route.path, {
            waitUntil: "domcontentloaded",
          });
        }

        // Redirected to login → auth failure
        if (activePage.url().includes("/giris")) {
          testInfo.annotations.push({
            type: "responsive-qa",
            description: JSON.stringify({
              route: route.id,
              path: route.path,
              viewport: viewportName,
              errorCount: 1,
              warningCount: 0,
              findings: [
                {
                  level: "ERROR",
                  type: "auth_redirect",
                  selector: "location",
                  detail: "redirected to /giris/",
                },
              ],
            }),
          });
          await activePage.screenshot({
            path: screenshotPath(viewportName, route.id),
            fullPage: true,
          });
          expect(activePage.url(), "should stay authenticated").not.toContain("/giris");
          return;
        }

        // Allow short settle for layout/JS freeze (read-only; no form submit)
        await activePage.waitForTimeout(400);
        await activePage.waitForLoadState("load").catch(() => {});

        const status = response ? response.status() : 0;
        const findingsBundle = await analyzePage(activePage, {
          isPhone: isPhoneProject(viewportName),
        });

        if (status >= 500) {
          findingsBundle.errors.unshift({
            level: "ERROR",
            type: "http_server_error",
            selector: "document",
            detail: `HTTP ${status}`,
            rect: {},
          });
        } else if (status === 403 || status === 404) {
          findingsBundle.warnings.unshift({
            level: "WARNING",
            type: "http_status",
            selector: "document",
            detail: `HTTP ${status}`,
            rect: {},
          });
        }

        const shot = screenshotPath(viewportName, route.id);
        await activePage.screenshot({ path: shot, fullPage: true });

        const payload = {
          route: route.id,
          path: route.path,
          role,
          viewport: viewportName,
          browser: browserName,
          httpStatus: status,
          errorCount: findingsBundle.errors.length,
          warningCount: findingsBundle.warnings.length,
          findings: [...findingsBundle.errors, ...findingsBundle.warnings].map((f) => ({
            level: f.level,
            type: f.type,
            selector: f.selector,
            detail: f.detail,
            rect: f.rect,
          })),
          screenshot: shot,
        };

        testInfo.annotations.push({
          type: "responsive-qa",
          description: JSON.stringify(payload),
        });

        // Attach JSON for HTML report
        await testInfo.attach(`qa-${route.id}-${viewportName}`, {
          body: JSON.stringify(payload, null, 2),
          contentType: "application/json",
        });

        expect
          .soft(
            findingsBundle.errors.length,
            `ERROR findings on ${route.id} @ ${viewportName}: ${findingsBundle.errors
              .slice(0, 5)
              .map((e) => e.type + ":" + e.selector)
              .join("; ")}`
          )
          .toBe(0);
      } finally {
        if (extraContext) await extraContext.close();
      }
    });
  });
}
