/**
 * Stale review state, and a dead section id.
 *
 * Both let a reviewer act on something other than what the screen said it was.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({
    api: {
        get: vi.fn(async () => ({})),
        post: vi.fn(async () => ({})),
        getDownloadUrl: vi.fn((p) => p),
        getFileUrl: vi.fn((f) => `/uploads/${f || 'doc.pdf'}`),
    },
}));
vi.mock('../components/review/SplitPane', () => ({
    default: ({ left, right }) => <div data-testid="split-pane">{left}{right}</div>,
}));
vi.mock('../components/review/PdfPanel', () => ({ default: () => <div /> }));
vi.mock('../components/review/HtmlPanel', () => ({
    default: ({ sectionId }) => <div data-testid="html-panel">{sectionId}</div>,
}));
vi.mock('../components/review/ReviewToolbar', () => ({ default: () => <div /> }));
vi.mock('../utils/clipboard', () => ({ writeToClipboard: vi.fn(async () => {}) }));

import ReviewPage from '../pages/ReviewPage';
import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useUiStore } from '../stores/uiStore';

const SECTIONS = [
    { id: 'sec-1', section_code: '1', section_heading: 'Short title',
      review_status: 'pending', quality_flags: [], annotation_count: 0,
      start_page: 1, plain_text: 'body' },
];

const renderAt = (sectionId) => render(
    <MemoryRouter initialEntries={[`/review/doc-1/${sectionId}`]}>
        <Routes>
            <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
        </Routes>
    </MemoryRouter>,
);

describe('a section id that no longer resolves', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeDocument: {
                id: 'doc-1', name: 'Sample Act', pdf_filename: 'doc.pdf',
                total_sections: 1, total_pages: 5, source_type: 'acts_corpus',
                stats: { approved: 0, has_issues: 0, open_annotations: 0,
                         pending: 1, reviewed: 0 },
            },
            sections: SECTIONS,
            activeSection: null,
            activeSectionError: null,
            pageSections: [],
            fetchDocument: vi.fn(async () => useDocumentStore.getState().activeDocument),
            fetchSections: vi.fn(async () => {}),
            fetchSection: vi.fn(async () => null),
            fetchSectionsByPage: vi.fn(async () => {}),
            loading: { search: false, activeSection: false },
            searchResults: [],
        });
        useReviewStore.setState({
            currentPage: 1, viewMode: 'section', setViewMode: vi.fn(),
            setCurrentPage: vi.fn(), globalAnnotations: [],
            fetchGlobalAnnotations: vi.fn(async () => []), annotations: [],
            fetchAnnotations: vi.fn(async () => []),
        });
        useUiStore.setState({ sidebarTab: 'toc', theme: 'light', sidebarOpen: true });
    });

    it('says the leaf was removed instead of rendering another one', async () => {
        // Sections are hard-deleted, so a resync retires ids. This used to leave the
        // PREVIOUS leaf mounted -- its HTML, its footnotes, its toolbar -- while the
        // URL referred to the dead one, so a reviewer could approve the wrong
        // provision.
        useDocumentStore.setState({ activeSectionError: 'removed' });
        renderAt('sec-gone');

        const panel = await screen.findByTestId('section-removed');
        expect(panel).toHaveTextContent(/no longer in the document/i);
        expect(screen.queryByTestId('html-panel')).not.toBeInTheDocument();
    });

    it('tells a failed request apart from an empty one', async () => {
        useDocumentStore.setState({ activeSectionError: 'failed' });
        renderAt('sec-1');

        const panel = await screen.findByTestId('section-failed');
        expect(panel).toHaveTextContent(/request failure, not an empty section/i);
        expect(screen.queryByTestId('section-removed')).not.toBeInTheDocument();
    });

    it('shows the plain invitation when nothing failed', async () => {
        renderAt('sec-1');
        await screen.findByTestId('split-pane');
        expect(screen.queryByTestId('section-removed')).not.toBeInTheDocument();
        expect(screen.queryByTestId('section-failed')).not.toBeInTheDocument();
    });
});
