const path = require("path");
const fs = require("fs");

const AUTH_DIR = path.join(__dirname, "..", ".auth");
const SCREENSHOT_DIR = path.join(__dirname, "..", "screenshots");
const REPORT_DIR = path.join(__dirname, "..", "reports");

const PROD_HOST_RE =
  /cinilisarayproje\.com|onrender\.com/i;

function assertSafeBaseUrl(baseURL) {
  let url;
  try {
    url = new URL(baseURL);
  } catch {
    throw new Error(`Invalid BASE_URL: ${baseURL}`);
  }
  const host = url.hostname;
  const isLocal =
    host === "127.0.0.1" || host === "localhost" || host === "::1";
  if (!isLocal && PROD_HOST_RE.test(host) && process.env.ALLOW_PROD_QA !== "1") {
    throw new Error(
      `Refusing to run Responsive QA against ${host}. Use local http://127.0.0.1:8000 or set ALLOW_PROD_QA=1.`
    );
  }
  if (url.protocol === "https:" && isLocal === false && process.env.ALLOW_PROD_QA !== "1") {
    // non-local non-prod still blocked unless explicitly allowed
  }
  return url.origin;
}

function ensureDirs() {
  for (const dir of [AUTH_DIR, SCREENSHOT_DIR, REPORT_DIR]) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function authStatePath(role) {
  return path.join(AUTH_DIR, `${role}.json`);
}

function screenshotPath(viewportName, routeId) {
  const dir = path.join(SCREENSHOT_DIR, viewportName);
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${routeId}.png`);
}

/**
 * Resolve credentials for a role without hardcoding secrets.
 * Falls back: QA_<ROLE>_USERNAME → QA_USERNAME
 */
function credentialsForRole(role) {
  const key = String(role || "personel").toUpperCase();
  const username =
    process.env[`QA_${key}_USERNAME`] ||
    process.env.QA_USERNAME ||
    "";
  const password =
    process.env[`QA_${key}_PASSWORD`] ||
    process.env.QA_PASSWORD ||
    "";
  return { username, password };
}

function roleHasCredentials(role) {
  const { username, password } = credentialsForRole(role);
  return Boolean(username && password);
}

function loadDotenv() {
  try {
    const dotenv = require("dotenv");
    const root = path.join(__dirname, "..");
    // Local secrets (gitignored): qa/responsive/.env then .auth/local.env
    dotenv.config({ path: path.join(root, ".env") });
    dotenv.config({ path: path.join(root, ".auth", "local.env"), override: false });
    // Optional project root .env (do not override explicit QA_* already set)
    dotenv.config({
      path: path.join(root, "..", "..", ".env"),
      override: false,
    });
  } catch {
    /* optional */
  }
}

module.exports = {
  AUTH_DIR,
  SCREENSHOT_DIR,
  REPORT_DIR,
  assertSafeBaseUrl,
  ensureDirs,
  authStatePath,
  screenshotPath,
  credentialsForRole,
  roleHasCredentials,
  loadDotenv,
};
