const pw = require("@playwright/test");
const setup = pw.test;
const expect = pw.expect;
const {
  loadDotenv,
  ensureDirs,
  authStatePath,
  credentialsForRole,
  roleHasCredentials,
  assertSafeBaseUrl,
} = require("./helpers/layout");

loadDotenv();
ensureDirs();

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8000";
assertSafeBaseUrl(BASE_URL);

const ROLES = ["personel", "ogretmen", "veli", "talebe"];

async function loginAs(page, role) {
  const { username, password } = credentialsForRole(role);
  if (!username || !password) {
    throw new Error(
      `Missing credentials for role "${role}". Set QA_${role.toUpperCase()}_USERNAME/PASSWORD or QA_USERNAME/QA_PASSWORD.`
    );
  }

  await page.goto("/giris/", { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await Promise.all([
    page.waitForURL((url) => !String(url.pathname || "").includes("/giris"), {
      timeout: 60000,
    }),
    page.locator('button[type="submit"], .gate-submit').first().click(),
  ]);

  const cookies = await page.context().cookies();
  const session = cookies.find((c) => /session/i.test(c.name));
  expect(session, `session cookie after login (${role})`).toBeTruthy();
  await page.context().storageState({ path: authStatePath(role) });
}

setup.describe.configure({ mode: "serial" });

for (const role of ROLES) {
  setup(`authenticate ${role}`, async ({ page }) => {
    if (!roleHasCredentials(role)) {
      setup.skip(true, `No credentials for ${role}`);
      return;
    }
    await loginAs(page, role);
  });
}
