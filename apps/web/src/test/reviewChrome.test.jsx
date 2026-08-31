import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({
    api: {
        get: vi.fn(async () => ({})),
        post: vi.fn(async () => ({})),
        getDownloadUrl: vi.fn((path) => path),
        getFileUrl: vi.fn((filename) => `/uploads/${filename || 'doc.pdf'}`),
    },
}));

vi.mock('../components/review/SplitPane', () => ({
    default: ({ left, right }) => (
        <div data-testid="split-pane">{left}{right}</div>
    ),
}));

vi.mock('../components/review/PdfPanel', () => ({
    default: () => <div data-testid="pdf-panel" />,
}));

vi.mock('../components/review/HtmlPanel', () => ({
    default: () => <div data-testid="html-panel" />,
}));

vi.mock('../components/review/ReviewToolbar', () => ({
    default: () => <div data-testid="review-toolbar" />,
}));

vi.mock('../utils/clipboard', () => ({
    writeToClipboard: vi.fn(async () => {}),
}));

import ReviewPage from '../pages/ReviewPage';
import Sidebar from '../components/layout/Sidebar';
import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useUiStore } from '../stores/uiStore';
import { writeToClipboard } from '../utils/clipboard';

describe('issues chrome wording', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeDocument: {
                id: 'doc-1',
                name: 'Sample Act',
                pdf_filename: 'doc.pdf',
                total_sections: 10,
                total_pages: 5,
                source_type: 'acts_corpus',
                stats: {
                    approved: 3,
                    has_issues: 4,
                    flagged_sections: 4,
                    open_annotations: 0,
                    pending: 3,
                    reviewed: 7,
                },
            },
            sections: [
                {
                    id: 'sec-1',
                    section_code: '1',
                    section_heading: 'Short title',
                    review_status: 'has_issues',
                    quality_flags: [{ code: 'missing_table', reason: 'no table' }],
                    annotation_count: 0,
                    start_page: 1,
                    plain_text: 'body',
                },
                {
                    id: 'sec-2',
                    section_code: '2',
                    section_heading: 'Definitions',
                    review_status: 'pending',
                    quality_flags: [],
                    annotation_count: 0,
                    start_page: 2,
                    plain_text: 'defs',
                },
            ],
            activeSection: {
                id: 'sec-1',
                section_code: '1',
                section_heading: 'Short title',
                review_status: 'has_issues',
                quality_flags: [{ code: 'missing_table', reason: 'no table' }],
                start_page: 1,
                end_page: 1,
                plain_text: 'body',
                html_content: '<p>body</p>',
            },
            pageSections: [],
            fetchDocument: vi.fn(async () => useDocumentStore.getState().activeDocument),
            fetchSections: vi.fn(async () => {}),
            fetchSection: vi.fn(async () => {}),
            fetchSectionsByPage: vi.fn(async () => {}),
            loading: { search: false, activeSection: false },
            searchResults: [],
        });
        useReviewStore.setState({
            currentPage: 1,
            viewMode: 'section',
            setViewMode: vi.fn(),
            setCurrentPage: vi.fn(),
            globalAnnotations: [],
            fetchGlobalAnnotations: vi.fn(async () => []),
            annotations: [],
            fetchAnnotations: vi.fn(async () => []),
        });
        useUiStore.setState({ sidebarTab: 'toc', theme: 'light', sidebarOpen: true });
    });

    it('header uses flagged / open notes, not bare issues', async () => {
        render(
            <MemoryRouter initialEntries={['/review/doc-1/sec-1']}>
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                </Routes>
            </MemoryRouter>,
        );

        expect(await screen.findByText(/3\/10 approved · 4 flagged · 0 open notes/)).toBeInTheDocument();
        expect(screen.queryByText(/\d+ issues\)/)).not.toBeInTheDocument();
    });

    it('says so when the pipeline no longer produces the document', async () => {
        // Nothing used to remove a document whose JSON left `output/`, so a retired
        // parse sat in the Library beside current ones with its approvals intact.
        // The rows are deliberately kept (they are the audit trail); the reviewer is
        // told instead.
        useDocumentStore.setState({
            activeDocument: {
                ...useDocumentStore.getState().activeDocument,
                withdrawn_at: '2026-08-31T09:15:00Z',
            },
        });

        render(
            <MemoryRouter initialEntries={['/review/doc-1/sec-1']}>
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                </Routes>
            </MemoryRouter>,
        );

        const banner = await screen.findByTestId('withdrawn-banner');
        expect(banner).toHaveTextContent(/no longer in the corpus/i);
        expect(banner).toHaveTextContent(/last parse/i);
    });

    it('shows no withdrawal banner for a current document', async () => {
        render(
            <MemoryRouter initialEntries={['/review/doc-1/sec-1']}>
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                </Routes>
            </MemoryRouter>,
        );

        await screen.findByTestId('split-pane');
        expect(screen.queryByTestId('withdrawn-banner')).not.toBeInTheDocument();
    });

    it('sidebar tab is Notes with annotation count, not Issues', () => {
        useReviewStore.setState({
            globalAnnotations: [
                { id: 'a1', section_id: 'sec-1', status: 'open', highlighted_text: 'x', created_at: new Date().toISOString() },
            ],
        });

        render(
            <MemoryRouter>
                <Sidebar documentId="doc-1" />
            </MemoryRouter>,
        );

        expect(screen.getByRole('button', { name: /Notes \(1\)/ })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Issues \(/ })).not.toBeInTheDocument();
    });

    it('TOC flagged icon tooltip distinguishes auto quality flag vs reviewer flagged', () => {
        useDocumentStore.setState({
            sections: [
                {
                    id: 'sec-auto',
                    section_code: '1',
                    section_heading: 'Auto flagged',
                    review_status: 'has_issues',
                    quality_flags: [{ code: 'missing_table', reason: 'no table' }],
                    annotation_count: 0,
                    start_page: 1,
                },
                {
                    id: 'sec-reviewer',
                    section_code: '2',
                    section_heading: 'Reviewer flagged',
                    review_status: 'has_issues',
                    quality_flags: [],
                    annotation_count: 1,
                    start_page: 2,
                },
            ],
            activeSection: null,
        });

        render(
            <MemoryRouter>
                <Sidebar documentId="doc-1" />
            </MemoryRouter>,
        );

        const flags = screen.getAllByTitle(/Auto quality flag|Reviewer flagged/);
        expect(flags[0]).toHaveAttribute('title', 'Auto quality flag');
        expect(flags[1]).toHaveAttribute('title', 'Reviewer flagged');
    });
});

describe('leaf-index chrome', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeDocument: {
                id: 'doc-1',
                name: 'Sample Act',
                pdf_filename: 'doc.pdf',
                total_sections: 2,
                total_pages: 5,
                source_type: 'acts_corpus',
                stats: {
                    approved: 0,
                    has_issues: 0,
                    flagged_sections: 0,
                    open_annotations: 0,
                    pending: 2,
                    reviewed: 0,
                },
            },
            sections: [
                {
                    id: 'sec-1',
                    section_code: '1',
                    section_heading: 'Short title',
                    review_status: 'pending',
                    start_page: 1,
                    end_page: 1,
                    plain_text: 'a',
                },
                {
                    id: 'sec-2',
                    section_code: '2',
                    section_heading: 'Definitions',
                    review_status: 'pending',
                    start_page: 2,
                    end_page: 2,
                    plain_text: 'b',
                },
            ],
            activeSection: {
                id: 'sec-2',
                section_code: '2',
                section_heading: 'Definitions',
                chapter_code: 'I',
                chapter_heading: 'PRELIMINARY',
                hierarchy_kind: 'chapter',
                source_key: '/chapters/0/sections/1',
                review_status: 'pending',
                start_page: 2,
                end_page: 2,
                plain_text: 'b',
                html_content: '<p>b</p>',
            },
            pageSections: [],
            fetchDocument: vi.fn(async () => useDocumentStore.getState().activeDocument),
            fetchSections: vi.fn(async () => {}),
            fetchSection: vi.fn(async () => {}),
            fetchSectionsByPage: vi.fn(async () => {}),
            loading: { search: false, activeSection: false },
            searchResults: [],
        });
        useReviewStore.setState({
            currentPage: 2,
            viewMode: 'section',
            setViewMode: vi.fn(),
            setCurrentPage: vi.fn(),
            globalAnnotations: [],
            fetchGlobalAnnotations: vi.fn(async () => []),
            annotations: [],
            fetchAnnotations: vi.fn(async () => []),
        });
        useUiStore.setState({ sidebarTab: 'toc', theme: 'light', sidebarOpen: true });
    });

    it('facts bar says Leaf N of M with statute identity, never Section N of M', async () => {
        render(
            <MemoryRouter initialEntries={['/review/doc-1/sec-2']}>
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                </Routes>
            </MemoryRouter>,
        );

        const facts = await screen.findByLabelText('Section facts');
        expect(facts).toHaveTextContent(/Leaf\s*2\s*of\s*2/);
        expect(facts).toHaveTextContent(/Section 2: Definitions/);
        expect(facts).not.toHaveTextContent(/Section\s*2\s*of\s*2/);
        expect(screen.getByRole('button', { name: 'Copy leaf JSON path' })).toBeInTheDocument();
    });

    it('copy path writes document, hierarchy, leaf index, and JSON pointer', async () => {
        writeToClipboard.mockClear();
        render(
            <MemoryRouter initialEntries={['/review/doc-1/sec-2']}>
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                </Routes>
            </MemoryRouter>,
        );

        fireEvent.click(await screen.findByRole('button', { name: 'Copy leaf JSON path' }));
        expect(writeToClipboard).toHaveBeenCalledTimes(1);
        expect(writeToClipboard).toHaveBeenCalledWith(
            [
                'Sample Act',
                'Chapter I · PRELIMINARY',
                'Section 2 · Definitions',
                'Leaf 2 of 2',
                '/chapters/0/sections/1',
            ].join('\n'),
        );
    });

    it('shows em dash when active leaf is not in the TOC list', async () => {
        useDocumentStore.setState({
            activeSection: {
                id: 'missing-sec',
                section_code: '99',
                section_heading: 'Orphan',
                review_status: 'pending',
                start_page: 9,
                end_page: 9,
                plain_text: 'x',
                html_content: '<p>x</p>',
            },
        });

        render(
            <MemoryRouter initialEntries={['/review/doc-1/missing-sec']}>
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                </Routes>
            </MemoryRouter>,
        );

        const facts = await screen.findByLabelText('Section facts');
        expect(facts).toHaveTextContent(/Leaf\s*—\s*of\s*2/);
        expect(facts).not.toHaveTextContent(/Leaf\s*1\s*of/);
    });

    it('blank heading leaves show Untitled leaf, not empty statute title', async () => {
        useDocumentStore.setState({
            sections: [
                {
                    id: 'sec-blank',
                    section_code: '',
                    section_heading: '',
                    review_status: 'pending',
                    start_page: 1,
                    end_page: 1,
                    plain_text: 'table only',
                },
            ],
            activeSection: {
                id: 'sec-blank',
                section_code: '',
                section_heading: '',
                review_status: 'pending',
                start_page: 1,
                end_page: 1,
                plain_text: 'table only',
                html_content: '<table></table>',
            },
        });

        render(
            <MemoryRouter initialEntries={['/review/doc-1/sec-blank']}>
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                </Routes>
            </MemoryRouter>,
        );

        const facts = await screen.findByLabelText('Section facts');
        expect(facts).toHaveTextContent('Untitled leaf');
    });
});
