import { useCallback, useEffect, useRef, useState } from 'react';
import { loadPdfjs } from './pdfjsLoader';

export const PDF_LOAD_TIMEOUT_MS = 30_000;

const destroyPdfResource = (document, loadingTask) => {
    if (document) {
        if (typeof document.destroy === 'function') {
            document.destroy();
        } else if (typeof document.cleanup === 'function') {
            document.cleanup();
        }
        return;
    }
    if (loadingTask && typeof loadingTask.destroy === 'function') {
        try {
            loadingTask.destroy();
        } catch {
            // Ignore destroy races while a load is still settling.
        }
    }
};

// Hook to load the PDF document once
export const usePdfDocument = (pdfUrl, { timeoutMs = PDF_LOAD_TIMEOUT_MS } = {}) => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [numPages, setNumPages] = useState(0);
    const [pdfDoc, setPdfDoc] = useState(null);
    const [retryToken, setRetryToken] = useState(0);

    const retry = useCallback(() => {
        setRetryToken((token) => token + 1);
    }, []);

    useEffect(() => {
        if (!pdfUrl) {
            setLoading(false);
            setError(new Error('No PDF URL provided'));
            setNumPages(0);
            setPdfDoc(null);
            return undefined;
        }

        let isCancelled = false;
        let loadedDocument = null;
        let loadingTask = null;
        let timeoutId = null;

        const loadPdf = async () => {
            setLoading(true);
            setError(null);
            setPdfDoc(null);
            setNumPages(0);

            try {
                const pdfjsLib = await loadPdfjs();
                // The engine chunk can outlive the effect that asked for it.
                if (isCancelled) return;

                loadingTask = pdfjsLib.getDocument({ url: pdfUrl });
                const timeoutPromise = new Promise((_, reject) => {
                    timeoutId = setTimeout(() => {
                        reject(
                            new Error(
                                `PDF load timed out after ${Math.round(timeoutMs / 1000)}s`,
                            ),
                        );
                    }, timeoutMs);
                });

                const pdf = await Promise.race([loadingTask.promise, timeoutPromise]);
                loadedDocument = pdf;

                if (!isCancelled) {
                    setPdfDoc(pdf);
                    setNumPages(pdf.numPages);
                } else {
                    destroyPdfResource(pdf, null);
                }
            } catch (err) {
                destroyPdfResource(null, loadingTask);
                loadingTask = null;
                if (!isCancelled) {
                    console.error('Error loading PDF:', err);
                    setError(err instanceof Error ? err : new Error(String(err)));
                    setPdfDoc(null);
                    setNumPages(0);
                }
            } finally {
                if (timeoutId != null) {
                    clearTimeout(timeoutId);
                    timeoutId = null;
                }
                if (!isCancelled) {
                    setLoading(false);
                }
            }
        };

        loadPdf();

        return () => {
            isCancelled = true;
            if (timeoutId != null) {
                clearTimeout(timeoutId);
            }
            destroyPdfResource(loadedDocument, loadingTask);
            setPdfDoc(null);
        };
    }, [pdfUrl, retryToken, timeoutMs]);

    return { pdfDoc, loading, error, numPages, retry };
};

/**
 * True when the canvas came out a single flat colour — nothing was drawn.
 *
 * Some scanned Acts in this corpus store each page as one 1-bit-per-component
 * DeviceGray image (CCITTFaxDecode or FlateDecode). pdf.js renders those blank, with
 * no error and no rejected promise, on 6.0.227 and 6.2.108 alike, while other
 * rasterisers reproduce them fine. Without this check the pane just goes white and a
 * reviewer cannot tell "the source page is blank" from "the viewer failed".
 */
const canvasIsBlank = (canvas) => {
    try {
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const first = `${data[0]},${data[1]},${data[2]}`;
        const step = Math.max(4, Math.floor(data.length / 4 / 5000) * 4);
        for (let i = 0; i < data.length; i += step) {
            if (`${data[i]},${data[i + 1]},${data[i + 2]}` !== first) return false;
        }
        return true;
    } catch {
        return false;  // cannot inspect — never claim a failure we did not observe
    }
};

// Hook to render a single PDF page given a loaded pdfDoc object
export const usePdfPageRenderer = (pdfDoc, pageNumber, zoom, canvasRef) => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [blank, setBlank] = useState(false);
    const renderTaskRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !pdfDoc) return;

        let isCancelled = false;

        const renderPage = async () => {
            setLoading(true);
            setError(null);
            setBlank(false);
            try {
                if (renderTaskRef.current) {
                    renderTaskRef.current.cancel();
                }

                const page = await pdfDoc.getPage(pageNumber);
                if (isCancelled) return;

                const viewport = page.getViewport({ scale: zoom });
                const context = canvas.getContext('2d');
                
                canvas.height = viewport.height;
                canvas.width = viewport.width;

                const renderContext = {
                    canvasContext: context,
                    viewport: viewport
                };

                const renderTask = page.render(renderContext);
                renderTaskRef.current = renderTask;

                await renderTask.promise;
                if (!isCancelled) setBlank(canvasIsBlank(canvas));
            } catch (err) {
                if (err.name !== 'RenderingCancelledException' && !isCancelled) {
                    console.error('Error rendering page:', err);
                    setError(err);
                }
            } finally {
                if (!isCancelled) {
                    setLoading(false);
                }
            }
        };

        renderPage();

        return () => {
            isCancelled = true;
            if (renderTaskRef.current) {
                renderTaskRef.current.cancel();
            }
        };
    }, [pageNumber, zoom, pdfDoc, canvasRef]);

    return { loading, error, blank };
};

// Backward-compatible original hook
export const usePdfRenderer = (pdfUrl, pageNumber, zoom, canvasRef) => {
    const { pdfDoc, loading: docLoading, error: docError, numPages, retry } = usePdfDocument(pdfUrl);
    const { loading: pageLoading, error: pageError } = usePdfPageRenderer(pdfDoc, pageNumber, zoom, canvasRef);

    return {
        loading: docLoading || pageLoading,
        error: docError || pageError,
        numPages,
        retry,
    };
};
