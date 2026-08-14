/**
 * Deferred loader for pdf.js.
 *
 * The library plus its bundled worker is ~1.6 MB — an order of magnitude larger than
 * the rest of the review workspace put together. Importing it at module scope pulled
 * it into the ReviewPage chunk, so a reviewer waited on the whole PDF engine before
 * the parsed-HTML pane, the toolbar or the annotation controls became interactive.
 * Going through a dynamic import gives pdf.js its own chunk that the browser fetches
 * in parallel and caches independently of the app code.
 */

let pdfjsPromise;

const importPdfjs = async () => {
    // Importing the worker evaluates it and sets globalThis.pdfjsWorker. pdf.js then
    // uses that in-process handler instead of fetching /assets/pdf.worker.min-*.mjs,
    // which the preview host returns as HTTP 500.
    const [pdfjsLib] = await Promise.all([
        import('pdfjs-dist'),
        import('pdfjs-dist/build/pdf.worker.min.mjs'),
    ]);
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'bundled';
    return pdfjsLib;
};

/**
 * Resolves to the pdf.js module namespace, fetching it at most once per session.
 *
 * A failed fetch clears the cache so the caller's retry can attempt it again;
 * caching the rejection would make a single flaky chunk request permanent.
 */
export const loadPdfjs = () => {
    pdfjsPromise ??= importPdfjs().catch((err) => {
        pdfjsPromise = undefined;
        throw err;
    });
    return pdfjsPromise;
};
