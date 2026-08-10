import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const pageRendererMock = vi.fn();

vi.mock('../hooks/usePdfRenderer', () => ({
    usePdfDocument: () => ({
        pdfDoc: { id: 'pdf' }, loading: false, error: null, numPages: 20,
        retry: vi.fn(),
    }),
    usePdfPageRenderer: (...args) => pageRendererMock(...args),
}));

import PdfPanel from '../components/review/PdfPanel';
import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useUiStore } from '../stores/uiStore';

// Several scanned Acts store each page as one 1-bit DeviceGray image (CCITTFaxDecode
// or FlateDecode). pdf.js draws those blank on 6.0.227 and 6.2.108 alike — no error,
// no rejected promise — while other rasterisers reproduce them fine. A silent white
// pane reads as "this page of the statute is empty", which for a legal review tool is
// the most dangerous way to fail.
describe('a page that renders to nothing says so', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeSection: { id: 's1', start_page: 1, end_page: 1 },
        });
        useReviewStore.setState({ currentPage: 1, viewMode: 'section' });
        useUiStore.setState({ pdfZoom: 1 });
        // Fire on observe(), not in the constructor: PdfPanel's callback calls
        // observer.unobserve(), and the const is not bound until construction returns.
        global.IntersectionObserver = class {
            constructor(cb) { this.cb = cb; }
            observe() { this.cb([{ isIntersecting: true }]); }
            unobserve() {} disconnect() {}
        };
    });

    it('warns, and offers the full PDF, when the canvas came out blank', () => {
        pageRendererMock.mockReturnValue({ loading: false, error: null, blank: true });
        render(<PdfPanel pdfUrl="http://x/uploads/a.pdf" />);

        const notice = screen.getByTestId('pdf-page-blank');
        expect(notice).toBeInTheDocument();
        expect(notice.textContent).toMatch(/did not render/i);
        expect(notice.textContent).toMatch(/source page is not blank/i);
        // Scoped to the notice: the toolbar carries its own icon link to the same URL.
        const escapeHatch = within(notice).getByRole('link', { name: /complete PDF/i });
        expect(escapeHatch).toHaveAttribute('href', 'http://x/uploads/a.pdf#page=1');
    });

    it('stays out of the way when the page rendered', () => {
        pageRendererMock.mockReturnValue({ loading: false, error: null, blank: false });
        render(<PdfPanel pdfUrl="http://x/uploads/a.pdf" />);
        expect(screen.queryByTestId('pdf-page-blank')).toBeNull();
    });

    it('defers to a real render error rather than double-reporting', () => {
        pageRendererMock.mockReturnValue({
            loading: false, error: new Error('boom'), blank: true,
        });
        render(<PdfPanel pdfUrl="http://x/uploads/a.pdf" />);
        expect(screen.queryByTestId('pdf-page-blank')).toBeNull();
    });
});
