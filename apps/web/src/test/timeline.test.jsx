import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import React from 'react';

import {
    parseTimelineParams,
    timelineApiPath,
    timelinePath,
} from '../utils/timeline';

describe('timelinePath', () => {
    it('builds a query-param URL from a section id', () => {
        expect(timelinePath({ sectionId: '039ad16e-630b-518d-b80c-04fa670c06c1' })).toBe(
            '/timeline?section_id=039ad16e-630b-518d-b80c-04fa670c06c1',
        );
    });

    it('puts family names with spaces and commas in the query string', () => {
        const path = timelinePath({
            family: 'foreign assets act, 2018',
            code: '14',
        });
        expect(path.startsWith('/timeline?')).toBe(true);
        expect(path).not.toMatch(/\/timeline\/foreign/);
        const params = new URLSearchParams(path.slice(path.indexOf('?')));
        expect(params.get('family')).toBe('foreign assets act, 2018');
        expect(params.get('code')).toBe('14');
    });
});

describe('timelineApiPath', () => {
    it('prefers section_id over family/code', () => {
        expect(
            timelineApiPath({
                sectionId: 'sec-1',
                family: 'foreign assets act, 2018',
                code: '14',
            }),
        ).toBe('/timeline?section_id=sec-1');
    });
});

describe('parseTimelineParams', () => {
    it('reads search params', () => {
        const searchParams = new URLSearchParams(
            'section_id=sec-1&family=foreign+assets+act%2C+2018&code=14',
        );
        expect(parseTimelineParams({ searchParams })).toEqual({
            sectionId: 'sec-1',
            family: 'foreign assets act, 2018',
            code: '14',
        });
    });

    it('falls back to a leftover encoded path splat', () => {
        expect(
            parseTimelineParams({
                searchParams: new URLSearchParams(),
                splat: 'foreign%20assets%20act%2C%202018/14',
            }),
        ).toEqual({
            sectionId: '',
            family: 'foreign assets act, 2018',
            code: '14',
        });
    });
});

vi.mock('../utils/api', () => ({
    api: {
        get: vi.fn(async () => ({})),
        post: vi.fn(async () => ({})),
        getDownloadUrl: vi.fn((path) => path),
        getFileUrl: vi.fn((filename) => `/uploads/${filename || 'doc.pdf'}`),
    },
    versionsApi: {
        editions: vi.fn(async () => ({ editions: [] })),
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

import { api } from '../utils/api';
import ReviewPage from '../pages/ReviewPage';
import TimelinePage from '../pages/TimelinePage';
import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useUiStore } from '../stores/uiStore';

function LocationProbe() {
    const loc = useLocation();
    return <div data-testid="loc">{`${loc.pathname}${loc.search}`}</div>;
}

describe('Review Timeline button', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeDocument: {
                id: '5eb9247e-aee7-490f-8834-7f223f733731',
                name: 'Foreign Assets (Declaration and Repatriation) Act, 2018',
                pdf_filename: 'doc.pdf',
                total_sections: 1,
                total_pages: 8,
                source_type: 'acts_corpus',
                stats: {
                    approved: 0,
                    has_issues: 0,
                    flagged_sections: 0,
                    open_annotations: 0,
                    pending: 1,
                    reviewed: 0,
                },
            },
            sections: [
                {
                    id: '039ad16e-630b-518d-b80c-04fa670c06c1',
                    section_code: '14',
                    section_heading: 'Declaration of foreign assets',
                    review_status: 'pending',
                    quality_flags: [],
                    annotation_count: 0,
                    start_page: 8,
                },
            ],
            activeSection: {
                id: '039ad16e-630b-518d-b80c-04fa670c06c1',
                section_code: '14',
                section_heading: 'Declaration of foreign assets',
                review_status: 'pending',
                quality_flags: [],
                start_page: 8,
                end_page: 8,
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
            currentPage: 8,
            viewMode: 'section',
            setViewMode: vi.fn(),
            setCurrentPage: vi.fn(),
            globalAnnotations: [],
            fetchGlobalAnnotations: vi.fn(async () => []),
            annotations: [],
            fetchAnnotations: vi.fn(async () => []),
        });
        useUiStore.setState({ sidebarTab: 'toc', theme: 'light', sidebarOpen: true });
        vi.mocked(api.get).mockReset();
        vi.mocked(api.get).mockResolvedValue({});
    });

    it('navigates to /timeline?section_id= rather than a family path with spaces', async () => {
        render(
            <MemoryRouter
                initialEntries={[
                    '/review/5eb9247e-aee7-490f-8834-7f223f733731/039ad16e-630b-518d-b80c-04fa670c06c1',
                ]}
            >
                <LocationProbe />
                <Routes>
                    <Route path="/review/:documentId/:sectionId" element={<ReviewPage />} />
                    <Route path="/timeline" element={<div>timeline-page</div>} />
                </Routes>
            </MemoryRouter>,
        );

        fireEvent.click(await screen.findByRole('button', { name: /timeline/i }));
        expect(screen.getByTestId('loc').textContent).toBe(
            '/timeline?section_id=039ad16e-630b-518d-b80c-04fa670c06c1',
        );
        expect(screen.getByText('timeline-page')).toBeInTheDocument();
    });
});

describe('TimelinePage', () => {
    beforeEach(() => {
        useUiStore.setState({
            theme: 'light',
            sidebarOpen: true,
            commandPaletteOpen: false,
            shortcutsHelpOpen: false,
        });
        vi.mocked(api.get).mockReset();
    });

    it('renders events for a section_id query', async () => {
        vi.mocked(api.get).mockResolvedValue({
            family: 'foreign assets (declaration and repatriation) act',
            family_label: 'Foreign Assets (Declaration and Repatriation) Act, 2018',
            section_code: '14',
            section_heading: 'Declaration of foreign assets',
            editions: 2,
            events: [
                {
                    kind: 'first',
                    year: '2017',
                    year_label: '2017',
                    count: 1,
                    document_id: 'fa-2017',
                    section_id: 'fa-sec-2017',
                },
                {
                    kind: 'changed',
                    year: '2018',
                    year_label: '2018',
                    count: 1,
                    word_delta: '+2 / −2 words',
                    document_id: 'fa-2018',
                    section_id: 'fa-sec-2018',
                },
            ],
        });

        render(
            <MemoryRouter initialEntries={['/timeline?section_id=fa-sec-2018']}>
                <Routes>
                    <Route path="/timeline" element={<TimelinePage />} />
                </Routes>
            </MemoryRouter>,
        );

        expect(await screen.findByText(/First edition/)).toBeInTheDocument();
        expect(screen.getByText(/Changed/)).toBeInTheDocument();
        expect(api.get).toHaveBeenCalledWith('/timeline?section_id=fa-sec-2018');
    });

    it('shows the empty state instead of crashing for a leftover encoded family path', async () => {
        vi.mocked(api.get).mockResolvedValue({
            family: 'foreign assets act',
            family_label: 'foreign assets act, 2018',
            section_code: '14',
            events: [],
            editions: 0,
        });

        render(
            <MemoryRouter
                initialEntries={['/timeline/foreign%20assets%20act%2C%202018/14']}
            >
                <Routes>
                    <Route path="/timeline/:family/:sectionCode" element={<TimelinePage />} />
                    <Route path="/timeline/*" element={<TimelinePage />} />
                </Routes>
            </MemoryRouter>,
        );

        expect(await screen.findByText('No timeline events')).toBeInTheDocument();
        await waitFor(() => {
            expect(api.get).toHaveBeenCalled();
        });
        const called = vi.mocked(api.get).mock.calls[0][0];
        expect(called.startsWith('/timeline?')).toBe(true);
        expect(called).toContain('section_code=14');
    });
});
