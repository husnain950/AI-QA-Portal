/**
 * Login and Library must not wait on PDF.js. A vendor-pdf manualChunk used to
 * swallow Vite's module-preload helper, so index.html preloaded 1.6 MB of
 * pdfjs-dist before the sign-in screen could run.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist');
const htmlPath = path.join(dist, 'index.html');
if (!fs.existsSync(htmlPath)) {
    console.error('dist/index.html missing; run vite build first');
    process.exit(1);
}

const html = fs.readFileSync(htmlPath, 'utf8');
const preloads = [...html.matchAll(/modulepreload[^>]+href="([^"]+)"/g)].map((match) => match[1]);
const pdfPreloads = preloads.filter((href) => /pdf/i.test(href));
if (pdfPreloads.length) {
    console.error('index.html must not preload PDF.js on login/Library:', pdfPreloads);
    process.exit(1);
}

const assets = path.join(dist, 'assets');
const indexJs = fs.readdirSync(assets).find((name) => /^index-.*\.js$/.test(name));
if (!indexJs) {
    console.error('no dist/assets/index-*.js');
    process.exit(1);
}
const src = fs.readFileSync(path.join(assets, indexJs), 'utf8');
if (/from\s*["']\.\/[^"']*pdf[^"']*["']/.test(src)) {
    console.error(`${indexJs} statically imports a pdf chunk; PDF.js must stay on the Review page`);
    process.exit(1);
}

console.log('entry bundle does not preload PDF.js');
