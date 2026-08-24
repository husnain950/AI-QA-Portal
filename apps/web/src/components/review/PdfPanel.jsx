import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Loader2, ExternalLink, AlertTriangle } from 'lucide-react';
import { usePdfDocument, usePdfPageRenderer } from '../../hooks/usePdfRenderer';
import { useUiStore } from '../../stores/uiStore';
import { useReviewStore } from '../../stores/reviewStore';
import { useDocumentStore } from '../../stores/documentStore';
import { isTypingTarget } from '../../utils/keyboard';

const PLACEHOLDER_HEIGHT = 1100;

// Helper component to render a single PDF page (lazy via IntersectionObserver)
const PdfPage = ({ pdfDoc, pageNumber, zoom, pdfUrl }) => {
    const wrapperRef = useRef(null);
    const canvasRef = useRef(null);
    const [shouldRender, setShouldRender] = useState(false);
    const { loading, error, blank } = usePdfPageRenderer(
        shouldRender ? pdfDoc : null,
        pageNumber,
        zoom,
        canvasRef,
    );

    useEffect(() => {
        const el = wrapperRef.current;
        if (!el) return;

        if (typeof IntersectionObserver === 'undefined') {
            setShouldRender(true);
            return undefined;
        }

        const root = el.closest('.pdf-scroll-container');
        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setShouldRender(true);
                    observer.unobserve(el);
                }
            },
            { root: root || null, rootMargin: '400px 0px', threshold: 0 },
        );
        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    return (
        <div
            ref={wrapperRef}
            className="pdf-canvas-wrapper"
            data-pdf-page={pageNumber}
            style={{
                position: 'relative',
                marginBottom: '24px',
                minHeight: shouldRender ? undefined : PLACEHOLDER_HEIGHT,
            }}
        >
            {shouldRender && loading && (
                <div className="pdf-page-overlay is-loading">
                    <Loader2 className="animate-spin" style={{ color: 'var(--color-accent)' }} size={24} />
                </div>
            )}
            {shouldRender && error && (
                <div className="pdf-page-overlay is-error">
                    Error rendering page {pageNumber}
                </div>
            )}
            {/* A page that renders to nothing must say so. Some scanned Acts store each
                page as a 1-bit image that pdf.js draws blank without raising an error,
                and a silent white pane reads as "this page of the statute is empty". */}
            {shouldRender && !error && blank && (
                <div className="pdf-page-overlay is-blank" data-testid="pdf-page-blank">
                    <strong style={{ color: 'var(--color-error)' }}>
                        Page {pageNumber} did not render
                    </strong>
                    <span>
                        This page is a 1-bit scanned image the in-browser viewer cannot
                        draw. The source page is not blank — open it in the full PDF to
                        review it.
                    </span>
                    {pdfUrl ? (
                        <a className="btn btn-sm btn-secondary" href={`${pdfUrl}#page=${pageNumber}`}
                           target="_blank" rel="noreferrer">
                            Open page {pageNumber} in the complete PDF
                        </a>
                    ) : null}
                </div>
            )}
            {shouldRender ? (
                <canvas ref={canvasRef} className="pdf-canvas" />
            ) : (
                <div
                    className="pdf-page-placeholder"
                    style={{ width: 612, height: PLACEHOLDER_HEIGHT }}
                    aria-hidden="true"
                />
            )}
            <div className="pdf-page-badge">
                Page {pageNumber}
            </div>
        </div>
    );
};

const PdfPanel = ({ pdfUrl }) => {
    const { pdfZoom, zoomIn, zoomOut, resetZoom } = useUiStore();
    const { currentPage, setCurrentPage, viewMode } = useReviewStore();
    const { activeSection } = useDocumentStore();
    const lastSectionIdRef = useRef(null);
    const scrollContainerRef = useRef(null);

    const { pdfDoc, loading: docLoading, error: docError, numPages, retry } = usePdfDocument(pdfUrl);

    const isSectionView = viewMode === 'section' && activeSection;
    const startPage = isSectionView ? (activeSection.start_page || 1) : currentPage;
    const endPage = isSectionView ? (activeSection.end_page || startPage) : currentPage;
    const multiPageSection = isSectionView && startPage !== endPage;

    // On every section change, force PDF to the leaf start (never keep a stale in-range page).
    useEffect(() => {
        if (!isSectionView || !activeSection?.id) {
            lastSectionIdRef.current = null;
            return;
        }
        if (lastSectionIdRef.current !== activeSection.id) {
            lastSectionIdRef.current = activeSection.id;
            setCurrentPage(activeSection.start_page || 1);
        }
    }, [isSectionView, activeSection?.id, activeSection?.start_page, setCurrentPage]);

    const displayedPage = isSectionView
        ? Math.max(startPage, Math.min(currentPage || startPage, endPage))
        : (currentPage || 1);

    // A leaf can declare a page the PDF cannot have -- two live corpus editions do
    // (a year read as a folio, a section past the last page). The clamping below then
    // yields no pages at all, so say why rather than showing an unexplained blank pane.
    const pageRangeOutOfBounds = Boolean(
        pdfDoc
        && isSectionView
        && numPages > 0
        && (startPage < 1 || startPage > numPages || endPage > numPages),
    );

    // Section view: stack every page in [start, end]. Page view: single page.
    const pagesToRender = [];
    if (pdfDoc) {
        if (isSectionView) {
            const clampedStart = Math.max(1, startPage);
            const clampedEnd = Math.min(numPages, endPage);
            for (let page = clampedStart; page <= clampedEnd; page += 1) {
                pagesToRender.push(page);
            }
        } else if (displayedPage >= 1 && displayedPage <= numPages) {
            pagesToRender.push(displayedPage);
        }
    }

    // Scroll helpers (prev/next/jump) bring the target page into view within the stack.
    useEffect(() => {
        if (!isSectionView || !multiPageSection) return;
        const container = scrollContainerRef.current;
        if (!container) return;
        const target = container.querySelector(`[data-pdf-page="${displayedPage}"]`);
        target?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
    }, [displayedPage, isSectionView, multiPageSection, activeSection?.id]);

    const handlePrevPage = useCallback(() => {
        const lowerBound = isSectionView ? startPage : 1;
        if (displayedPage > lowerBound) {
            setCurrentPage(displayedPage - 1);
        }
    }, [isSectionView, startPage, displayedPage, setCurrentPage]);

    const handleNextPage = useCallback(() => {
        const upperBound = isSectionView ? endPage : numPages;
        if (displayedPage < upperBound) {
            setCurrentPage(displayedPage + 1);
        }
    }, [isSectionView, endPage, numPages, displayedPage, setCurrentPage]);

    const pageChromeText = isSectionView
        ? multiPageSection
            ? `PDF pages ${startPage}–${endPage} · scrolled to ${displayedPage} · parsed HTML is the full leaf (scroll)`
            : `PDF page ${displayedPage} · parsed HTML is the full leaf (scroll)`
        : `Page ${displayedPage} of ${numPages || '...'}`;

    useEffect(() => {
        const handlePageShortcut = (event) => {
            if (isTypingTarget(event)) return;
            if (event.key === '[') {
                event.preventDefault();
                handlePrevPage();
            } else if (event.key === ']') {
                event.preventDefault();
                handleNextPage();
            }
        };
        document.addEventListener('keydown', handlePageShortcut);
        return () => document.removeEventListener('keydown', handlePageShortcut);
    }, [handlePrevPage, handleNextPage]);

    return (
        <div className="flex flex-col" style={{ height: '100%' }}>
            {/* Header / Controls */}
            <div className="panel-header pdf-panel-header">
                <span className="panel-title">PDF Original</span>

                {/* Page Navigation */}
                <div className="flex align-center gap-2 pdf-page-nav">
                    <button
                        className="btn btn-secondary btn-icon"
                        onClick={handlePrevPage}
                        disabled={displayedPage <= (isSectionView ? startPage : 1) || docLoading}
                        title="Previous PDF page ([)"
                        aria-label="Previous PDF page"
                    >
                        <ChevronLeft size={16} />
                    </button>
                    {multiPageSection ? (
                        <select
                            className="pdf-page-select"
                            value={displayedPage}
                            onChange={(event) => setCurrentPage(Number(event.target.value))}
                            aria-label="PDF page within section"
                        >
                            {Array.from(
                                { length: endPage - startPage + 1 },
                                (_, index) => startPage + index,
                            ).map((page) => (
                                <option key={page} value={page}>Page {page}</option>
                            ))}
                        </select>
                    ) : null}
                    <span className="pdf-page-label" data-testid="pdf-page-chrome">
                        {pageChromeText}
                    </span>
                    <button
                        className="btn btn-secondary btn-icon"
                        onClick={handleNextPage}
                        disabled={displayedPage >= (isSectionView ? endPage : numPages) || docLoading}
                        title="Next PDF page (])"
                        aria-label="Next PDF page"
                    >
                        <ChevronRight size={16} />
                    </button>
                    {multiPageSection && (
                        <>
                            <button
                                type="button"
                                className="btn btn-xs btn-secondary"
                                onClick={() => setCurrentPage(startPage)}
                                disabled={displayedPage === startPage || docLoading}
                                title="Jump PDF to section start"
                            >
                                Start
                            </button>
                            <button
                                type="button"
                                className="btn btn-xs btn-secondary"
                                onClick={() => setCurrentPage(endPage)}
                                disabled={displayedPage === endPage || docLoading}
                                title="Jump PDF to section end"
                            >
                                End
                            </button>
                        </>
                    )}
                    {pdfUrl ? (
                        <a
                            className="btn btn-secondary btn-icon"
                            href={`${pdfUrl}#page=${displayedPage}`}
                            target="_blank"
                            rel="noreferrer"
                            title="Open this page in the complete PDF"
                            aria-label="Open page in complete PDF"
                        >
                            <ExternalLink size={15} />
                        </a>
                    ) : null}
                </div>

                {/* Zoom Controls */}
                <div className="flex align-center gap-1">
                    <button
                        className="btn btn-secondary btn-icon"
                        onClick={zoomOut}
                        disabled={pdfZoom <= 0.5 || docLoading}
                        title="Zoom out"
                        aria-label="Zoom out"
                    >
                        <ZoomOut size={16} />
                    </button>
                    <span className="pdf-zoom-label">
                        {Math.round(pdfZoom * 100)}%
                    </span>
                    <button
                        className="btn btn-secondary btn-icon"
                        onClick={zoomIn}
                        disabled={pdfZoom >= 3.0 || docLoading}
                        title="Zoom in"
                        aria-label="Zoom in"
                    >
                        <ZoomIn size={16} />
                    </button>
                    <button
                        className="btn btn-secondary btn-icon"
                        onClick={resetZoom}
                        disabled={pdfZoom === 1.0 || docLoading}
                        title="Reset zoom"
                        aria-label="Reset zoom"
                    >
                        <Maximize2 size={16} />
                    </button>
                </div>
            </div>

            {/* Canvas Body */}
            <div className="panel-body">
                {docLoading && (
                    <div className="pdf-doc-loading-overlay" data-testid="pdf-doc-loading">
                        <Loader2 className="animate-spin" style={{ color: 'var(--color-accent)' }} size={32} />
                    </div>
                )}

                {docError && !docLoading && (
                    <div
                        className="p-6 flex flex-col justify-center align-center gap-3"
                        data-testid="pdf-doc-error"
                        style={{ color: 'var(--color-error)', height: '100%' }}
                    >
                        <p style={{ fontWeight: 600 }}>Failed to load PDF</p>
                        <p style={{ fontSize: '0.8rem' }}>{docError.message || 'Check browser console'}</p>
                        {pdfUrl ? (
                            <button
                                type="button"
                                className="btn btn-secondary"
                                data-testid="pdf-doc-retry"
                                onClick={retry}
                            >
                                Retry
                            </button>
                        ) : null}
                    </div>
                )}

                <div className="pdf-scroll-container" ref={scrollContainerRef}>
                    {!docError && pageRangeOutOfBounds && pagesToRender.length === 0 && (
                        <div className="pdf-out-of-range" role="status">
                            <AlertTriangle size={18} />
                            <div>
                                <strong>
                                    This leaf declares pages {startPage}–{endPage}, but the
                                    PDF has {numPages}.
                                </strong>
                                <p>
                                    The page number came from the conversion, so there is
                                    nothing to render here. It is flagged on the leaf as
                                    <code> page_range_out_of_bounds</code> — report it
                                    against the pipeline rather than the document.
                                </p>
                            </div>
                        </div>
                    )}

                    {!docError && pdfDoc && pagesToRender.map((pageNumber) => (
                        <PdfPage
                            key={pageNumber}
                            pdfDoc={pdfDoc}
                            pageNumber={pageNumber}
                            zoom={pdfZoom}
                            pdfUrl={pdfUrl}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
};

export default PdfPanel;
