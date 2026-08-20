/**
 * Stratified visual smoke for the QA Portal review pages.
 * Checks the dashboard loads, opens representative acts, verifies PDF canvas + HTML pane.
 *
 * Needs a running API and web server:
 *   PORTAL_API   default http://127.0.0.1:8000/api
 *   PORTAL_BASE  default http://127.0.0.1:5173  (vite's default port)
 *
 * Targets come from a manifest so a fresh clone can run this against the generated
 * fixture corpus (`make seed-fixtures`) instead of the private one:
 *   SMOKE_TARGETS  default <repo>/data/fixtures/acts/smoke_targets.json
 *
 * The API requires a session, so credentials are needed too:
 *   SMOKE_EMAIL / SMOKE_PASSWORD  (default: ADMIN_EMAIL / ADMIN_PASSWORD)
 * When that file is absent the script falls back to the real corpus editions below, so
 * running against a synced private corpus behaves exactly as it always did.
 *
 * Exits non-zero when any target fails. It previously recorded failures and still
 * exited 0, which would have made it a no-op as a CI gate.
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '../../..');
const BASE = (process.env.PORTAL_BASE || 'http://127.0.0.1:5173').replace(/\/$/, '');
const API = (process.env.PORTAL_API || 'http://127.0.0.1:8000/api').replace(/\/$/, '');
const TARGETS_FILE = process.env.SMOKE_TARGETS
  || path.join(REPO_ROOT, 'data/fixtures/acts/smoke_targets.json');
const OUT = path.join(__dirname, 'visual_smoke_report.json');
const EMAIL = process.env.SMOKE_EMAIL || process.env.ADMIN_EMAIL || '';
const PASSWORD = process.env.SMOKE_PASSWORD || process.env.ADMIN_PASSWORD || '';

/**
 * Sign in once and return the session cookie, which both the script's own fetches and
 * the browser context need: every API path now requires a session.
 */
async function signIn() {
  if (!EMAIL || !PASSWORD) {
    throw new Error('set SMOKE_EMAIL/SMOKE_PASSWORD (or ADMIN_EMAIL/ADMIN_PASSWORD)');
  }
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!res.ok) {
    throw new Error(`sign-in failed (${res.status}): ${await res.text()}`);
  }
  const header = res.headers.getSetCookie?.().join('; ') || res.headers.get('set-cookie') || '';
  const match = /crx_session=([^;]+)/.exec(header);
  if (!match) throw new Error('sign-in returned no crx_session cookie');
  return { name: 'crx_session', value: match[1] };
}

let SESSION = null;

/** fetch() carrying the session cookie. */
function apiFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: { ...(options.headers || {}), cookie: `${SESSION.name}=${SESSION.value}` },
  });
}

/** Editions of the private corpus, used when no fixture manifest is present. */
const CORPUS_TARGETS = [
  { nameIncludes: 'Finance Act 2024', page: 11 },
  { nameIncludes: 'Finance Act 2025', page: 50 },
  { nameIncludes: 'Finance Act, 2021', page: 40 },
  { nameIncludes: 'Sales Tax Act 1990 amended upto 30-06-2025', page: 50 },
  { nameIncludes: 'Customs Act, 1969 as amended up to 30th June, 2025', page: 40 },
  { nameIncludes: 'Federal Excise Act, 2005 as amended upto 30-06-2025', page: 30 },
  { nameIncludes: 'Benami Transactions', page: 5 },
  { nameIncludes: 'The Tax Laws (Amendment) Act, 2024', page: 8 },
];

function loadTargets() {
  if (fs.existsSync(TARGETS_FILE)) {
    const manifest = JSON.parse(fs.readFileSync(TARGETS_FILE, 'utf-8'));
    const targets = manifest.targets || [];
    if (targets.length) return { targets, source: TARGETS_FILE };
  }
  return { targets: CORPUS_TARGETS, source: 'built-in corpus editions' };
}

async function getDocs() {
  let res;
  try {
    res = await apiFetch(`${API}/documents`);
  } catch (err) {
    throw new Error(
      `cannot reach the API at ${API} (${err.message}). Start it, or set PORTAL_API.`,
    );
  }
  if (!res.ok) throw new Error(`GET ${API}/documents returned HTTP ${res.status}`);
  return res.json();
}

async function checkDoc(page, doc, samplePage) {
  const result = {
    name: doc.name,
    id: doc.id,
    samplePage,
    ok: true,
    errors: [],
  };
  const url = `${BASE}/review/${doc.id}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(1500);

  const bodyText = await page.locator('body').innerText();
  if (!bodyText || bodyText.length < 20) {
    result.ok = false;
    result.errors.push('empty_body');
  }

  const canvas = page.locator('canvas').first();
  try {
    await canvas.waitFor({ timeout: 20000 });
    const box = await canvas.boundingBox();
    if (!box || box.width < 50 || box.height < 50) {
      result.ok = false;
      result.errors.push('pdf_canvas_too_small');
    }
  } catch (e) {
    result.ok = false;
    result.errors.push('pdf_canvas_missing:' + e.message);
  }

  // A page pdf.js draws blank is reported by the UI rather than thrown, so the canvas
  // existing is not on its own proof the PDF rendered.
  if (await page.getByTestId('pdf-page-blank').count()) {
    result.ok = false;
    result.errors.push('pdf_page_blank');
  }
  if (await page.getByTestId('pdf-doc-error').count()) {
    result.ok = false;
    result.errors.push('pdf_doc_error');
  }

  const main = page.locator('main, .review-layout, #root').first();
  const text = await main.innerText().catch(() => '');
  if (text.length < 40) {
    result.ok = false;
    result.errors.push('thin_ui_text');
  }

  const pageView = page.getByRole('button', { name: /page view/i }).first();
  if (await pageView.count()) {
    await pageView.click();
    await page.waitForTimeout(500);
  }

  const pageInput = page.locator('input[type="number"]').first();
  if (await pageInput.count()) {
    await pageInput.fill(String(samplePage));
    await pageInput.press('Enter');
    await page.waitForTimeout(1200);
  }

  const shotDir = path.join(__dirname, 'visual_shots');
  fs.mkdirSync(shotDir, { recursive: true });
  const shot = path.join(shotDir, `${doc.id.slice(0, 8)}_p${samplePage}.png`);
  await page.screenshot({ path: shot, fullPage: false });
  result.screenshot = shot;

  const bp = await apiFetch(`${API}/documents/${doc.id}/sections/by-page/${samplePage}`).then((r) => r.json());
  result.api_sections = bp.length;
  if (bp.length && !(bp[0].plain_text || bp[0].html_content)) {
    result.ok = false;
    result.errors.push('empty_section_content');
  }

  return result;
}

const { targets: TARGETS, source: targetsSource } = loadTargets();
console.error(`targets: ${TARGETS.length} from ${targetsSource}`);
console.error(`web: ${BASE}  api: ${API}`);

SESSION = await signIn();
const docs = await getDocs();
const acts = docs.filter((d) => d.source_type === 'acts_corpus');
if (!acts.length) {
  throw new Error(
    `the API has no acts_corpus documents (${docs.length} document(s) total). `
    + 'Run `make seed-fixtures` for a generated corpus, or `make sync` for the real one.',
  );
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
// The app renders a sign-in screen without this, so every target would fail.
await context.addCookies([
  { ...SESSION, url: BASE },
  { ...SESSION, url: API.replace(/\/api$/, '') },
]);
const page = await context.newPage();

const dash = { ok: true, errors: [] };
await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 });
const dashText = await page.locator('body').innerText();
if (!/upload|document|act|finance|customs/i.test(dashText)) {
  dash.ok = false;
  dash.errors.push('dashboard_missing_expected_labels');
}
dash.doc_count_hint = (dashText.match(/\d+/g) || []).slice(0, 5);

const results = [];
for (const t of TARGETS) {
  const doc = acts.find((d) => d.name.toLowerCase().includes(t.nameIncludes.toLowerCase()));
  if (!doc) {
    results.push({ name: t.nameIncludes, ok: false, errors: ['doc_not_found'] });
    continue;
  }
  try {
    results.push(await checkDoc(page, doc, t.page));
  } catch (e) {
    results.push({ name: doc.name, ok: false, errors: ['exception:' + e.message] });
  }
}

await browser.close();
const report = {
  base: BASE,
  api: API,
  targets_source: targetsSource,
  dashboard: dash,
  results,
  passed: results.filter((r) => r.ok).length,
  failed: results.filter((r) => !r.ok).length,
};
fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));

const failed = report.failed + (dash.ok ? 0 : 1);
if (failed) {
  console.error(`\nvisual smoke FAILED: ${report.failed}/${results.length} target(s)`
    + `${dash.ok ? '' : ' plus the dashboard check'}`);
}
process.exit(failed ? 1 : 0);
