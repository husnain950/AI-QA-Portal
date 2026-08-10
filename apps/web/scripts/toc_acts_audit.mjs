/**
 * Audit TOC quality for every acts_corpus document.
 * Scores metadata via API; screenshots TOC pane for docs that still fail.
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.PORTAL_BASE || 'http://127.0.0.1:5174';
const API = process.env.PORTAL_API || 'http://127.0.0.1:8000/api';
const OUT = path.join(__dirname, 'toc_acts_audit_report.json');
const SHOT_DIR = path.join(__dirname, 'toc_acts_shots');

const GAZETTE_RE = /THE\s+GAZETTE\s+OF\s+PAKISTAN/i;
const CONTENTS_RE = /Section\s+Page\s+No\.?/i;
const DOT_LEADERS_RE = /(?:[.\u2026·•]{2,}|\u2026+)/;
const CONTAINER_CODE_RE = /^(PART|CHAPTER|SCHEDULE|DIVISION|PREAMBLE)\b/i;

function scoreSections(sections) {
  const issues = {
    orphan_blank_chapter: 0,
    gazette_heading: 0,
    contents_heading: 0,
    dot_leaders: 0,
    empty_heading: 0,
    container_as_section: 0,
  };

  for (const sec of sections) {
    if (sec.chapter_code === '' || sec.chapter_heading === '') {
      issues.orphan_blank_chapter += 1;
    }

    const heading = String(sec.section_heading || '');
    const code = String(sec.section_code || '').trim();
    if (GAZETTE_RE.test(heading)) issues.gazette_heading += 1;
    if (CONTENTS_RE.test(heading) || CONTENTS_RE.test(String(sec.plain_text || ''))) {
      issues.contents_heading += 1;
    }
    if (DOT_LEADERS_RE.test(heading)) issues.dot_leaders += 1;
    if (!heading.trim()) issues.empty_heading += 1;
    if (CONTAINER_CODE_RE.test(code) && (GAZETTE_RE.test(heading) || CONTENTS_RE.test(heading))) {
      issues.container_as_section += 1;
    }
  }

  const hardIssues =
    issues.orphan_blank_chapter +
    issues.gazette_heading +
    issues.contents_heading +
    issues.dot_leaders +
    issues.container_as_section;
  const totalIssues = hardIssues + issues.empty_heading;
  return { issues, hardIssues, totalIssues, sectionCount: sections.length };
}

async function getDocs() {
  const res = await fetch(`${API}/documents`);
  if (!res.ok) throw new Error(`documents HTTP ${res.status}`);
  return res.json();
}

async function getSections(docId) {
  const res = await fetch(`${API}/documents/${docId}/sections`);
  if (!res.ok) throw new Error(`sections HTTP ${res.status}`);
  return res.json();
}

async function shotToc(page, doc) {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  const url = `${BASE}/review/${doc.id}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(800);
  const toc = page.locator('.toc-content, .sidebar').first();
  const shot = path.join(SHOT_DIR, `${doc.id.slice(0, 8)}_toc.png`);
  if (await toc.count()) {
    await toc.screenshot({ path: shot }).catch(async () => {
      await page.screenshot({ path: shot, fullPage: false });
    });
  } else {
    await page.screenshot({ path: shot, fullPage: false });
  }
  return shot;
}

const docs = await getDocs();
const acts = docs.filter((d) => d.source_type === 'acts_corpus');
const results = [];

for (const doc of acts) {
  const row = { id: doc.id, name: doc.name, ok: true, errors: [] };
  try {
    const sections = await getSections(doc.id);
    const scored = scoreSections(sections);
    Object.assign(row, scored);
    if (scored.hardIssues > 0) {
      row.ok = false;
      row.errors.push(
        ...Object.entries(scored.issues)
          .filter(([k, n]) => n > 0 && k !== 'empty_heading')
          .map(([k, n]) => `${k}:${n}`),
      );
    }
    if (scored.issues.empty_heading > scored.sectionCount * 0.5) {
      row.soft_errors = [`empty_heading_majority:${scored.issues.empty_heading}`];
    }
  } catch (e) {
    row.ok = false;
    row.errors.push(String(e.message || e));
  }
  results.push(row);
}

const failing = results.filter((r) => !r.ok);
const soft = results.filter(
  (r) => r.ok && ((r.issues?.empty_heading || 0) > 0 || (r.soft_errors || []).length),
);
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const named = [
    'Finance Act 2024',
    'Finance Act 2025',
    'Customs Act, 1969 as amended up to 30th June, 2025',
    'Sales Tax Act 1990 amended upto 30-06-2025',
    'The Tax Laws (Amendment) Act, 2024',
    'Federal Excise Act, 2005 as amended upto 30-06-2025',
    'Benami Transactions (Prohibition) Act, 2017',
  ];
  const sampleRows = named
    .map((name) => results.find((r) => r.name.includes(name) || r.name === name))
    .filter(Boolean);
  const toShot = [...failing, ...sampleRows]
    .filter((row, index, arr) => arr.findIndex((r) => r.id === row.id) === index)
    .slice(0, 12);
  for (const row of toShot) {
    try {
      row.screenshot = await shotToc(page, row);
    } catch (e) {
      row.errors.push('screenshot:' + (e.message || e));
    }
  }
} catch (e) {
  console.error('screenshot_pass_failed', e.message || e);
} finally {
  if (browser) await browser.close();
}

const report = {
  generated_at: new Date().toISOString(),
  acts_total: acts.length,
  passed: results.filter((r) => r.ok).length,
  failed: failing.length,
  soft_empty_heading_docs: soft.length,
  results: results.sort(
    (a, b) => (b.hardIssues || 0) - (a.hardIssues || 0) || (b.totalIssues || 0) - (a.totalIssues || 0),
  ),
};

fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
console.log(
  JSON.stringify(
    {
      acts_total: report.acts_total,
      passed: report.passed,
      failed: report.failed,
      soft_empty_heading_docs: report.soft_empty_heading_docs,
      top_failures: failing.slice(0, 15).map((r) => ({
        name: r.name,
        hardIssues: r.hardIssues,
        totalIssues: r.totalIssues,
        errors: r.errors,
      })),
      report: OUT,
    },
    null,
    2,
  ),
);
process.exit(report.failed > 0 ? 1 : 0);
