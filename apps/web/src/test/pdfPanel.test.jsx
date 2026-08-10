import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const usePdfDocumentMock = vi.fn();

vi.mock('../hooks/usePdfRenderer', () => ({
    usePdfDocument: (...args) => usePdfDocumentMock(...args),
    usePdfPageRenderer: () => ({ loading: false, error: null }),
}));

import PdfPanel from '../components/review/PdfPanel';
import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useUiStore } from '../stores/uiStore';

describe('section PDF rendering', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeSection: { id: 'section-1', start_page: 10, end_page: 14 },
        });
        useReviewStore.setState({
            currentPage: 10,
            viewMode: 'section',
        });
        useUiStore.setState({ pdfZoom: 1 });
        usePdfDocumentMock.mockReturnValue({
            pdfDoc: { id: 'pdf' },
            loading: false,
            error: null,
            numPages: 400,
            retry: vi.fn(),
        });
    });

    it('stacks placeholders/canvases for every page in the section range', () => {
        const { container } = render(<PdfPanel pdfUrl="/uploads/large.pdf" />);

        const pageNodes = container.querySelectorAll('[data-pdf-page]');
        expect(pageNodes).toHaveLength(5);
        expect([...pageNodes].map((node) => node.getAttribute('data-pdf-page'))).toEqual([
            '10', '11', '12', '13', '14',
        ]);
        // Without IntersectionObserver (jsdom), pages render eagerly → canvases.
        expect(container.querySelectorAll('canvas').length).toBeGreaterThanOrEqual(1);

        const selector = screen.getByRole('combobox', {
            name: 'PDF page within section',
        });
        expect(selector.querySelectorAll('option')).toHaveLength(5);

        fireEvent.change(selector, { target: { value: '14' } });
        expect(useReviewStore.getState().currentPage).toBe(14);
        expect(container.querySelectorAll('[data-pdf-page]')).toHaveLength(5);
    });

    it('keeps Page View as a single page', () => {
        useReviewStore.setState({
            currentPage: 42,
            viewMode: 'page',
        });
        useDocumentStore.setState({ activeSection: null });

        const { container } = render(<PdfPanel pdfUrl="/uploads/large.pdf" />);

        expect(container.querySelectorAll('[data-pdf-page]')).toHaveLength(1);
        expect(container.querySelector('[data-pdf-page="42"]')).toBeTruthy();
        expect(screen.queryByRole('combobox', { name: 'PDF page within section' })).toBeNull();
    });
});

describe('PDF load error UI', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeSection: { id: 'section-1', start_page: 1, end_page: 1 },
        });
        useReviewStore.setState({
            currentPage: 1,
            viewMode: 'section',
        });
        useUiStore.setState({ pdfZoom: 1 });
    });

    it('shows error UI (not spinner) when the document fails to load', () => {
        const retry = vi.fn();
        usePdfDocumentMock.mockReturnValue({
            pdfDoc: null,
            loading: false,
            error: new Error('PDF load timed out after 30s'),
            numPages: 0,
            retry,
        });

        const { container } = render(<PdfPanel pdfUrl="/uploads/hang.pdf" />);

        expect(screen.getByTestId('pdf-doc-error')).toBeInTheDocument();
        expect(screen.getByText(/failed to load pdf/i)).toBeInTheDocument();
        expect(screen.getByText(/timed out/i)).toBeInTheDocument();
        expect(screen.queryByTestId('pdf-doc-loading')).toBeNull();
        expect(container.querySelectorAll('[data-pdf-page]')).toHaveLength(0);

        fireEvent.click(screen.getByTestId('pdf-doc-retry'));
        expect(retry).toHaveBeenCalledTimes(1);
    });

    it('shows missing-URL error without a retry control or spinner', () => {
        usePdfDocumentMock.mockReturnValue({
            pdfDoc: null,
            loading: false,
            error: new Error('No PDF URL provided'),
            numPages: 0,
            retry: vi.fn(),
        });

        render(<PdfPanel pdfUrl="" />);

        expect(screen.getByTestId('pdf-doc-error')).toBeInTheDocument();
        expect(screen.getByText(/no pdf url provided/i)).toBeInTheDocument();
        expect(screen.queryByTestId('pdf-doc-retry')).toBeNull();
        expect(screen.queryByTestId('pdf-doc-loading')).toBeNull();
    });

    it('does not leave the error spinner showing forever while loading', () => {
        usePdfDocumentMock.mockReturnValue({
            pdfDoc: null,
            loading: true,
            error: null,
            numPages: 0,
            retry: vi.fn(),
        });

        render(<PdfPanel pdfUrl="/uploads/loading.pdf" />);

        expect(screen.getByTestId('pdf-doc-loading')).toBeInTheDocument();
        expect(screen.queryByTestId('pdf-doc-error')).toBeNull();
    });
});
