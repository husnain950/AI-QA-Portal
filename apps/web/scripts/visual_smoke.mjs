/**
 * Stratified visual smoke for PDF-QA Portal review pages.
 * Checks dashboard loads, opens representative acts, verifies PDF canvas + HTML pane.
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = 'http://127.0.0.1:5174';
const API = 'http://127.0.0.1:8000/api';
const OUT = path.join(__dirname, 'visual_smoke_report.json');

const TARGETS = [
  { nameIncludes: 'Finance Act 2024', page: 11 },
  { nameIncludes: 'Finance Act 2025', page: 50 },
  { nameIncludes: 'Finance Act, 2021', page: 40 },
  { nameIncludes: 'Sales Tax Act 1990 amended upto 30-06-2025', page: 50 },
  { nameIncludes: 'Customs Act, 1969 as amended up to 30th June, 2025', page: 40 },
  { nameIncludes: 'Federal Excise Act, 2005 as amended upto 30-06-2025', page: 30 },
  { nameIncludes: 'Benami Transactions', page: 5 },
  { nameIncludes: 'The Tax Laws (Amendment) Act, 2024', page: 8 },
];

async function getDocs() {
  const res = await fetch(`${API}/documents`);
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

  const bp = await fetch(`${API}/documents/${doc.id}/sections/by-page/${samplePage}`).then((r) => r.json());
  result.api_sections = bp.length;
  if (bp.length && !(bp[0].plain_text || bp[0].html_content)) {
    result.ok = false;
    result.errors.push('empty_section_content');
  }

  return result;
}

const docs = await getDocs();
const acts = docs.filter((d) => d.source_type === 'acts_corpus');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

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
  dashboard: dash,
  results,
  passed: results.filter((r) => r.ok).length,
  failed: results.filter((r) => !r.ok).length,
};
fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
