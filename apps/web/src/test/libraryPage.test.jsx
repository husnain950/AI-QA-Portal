import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({
    api: {
        get: vi.fn(),
        delete: vi.fn(async () => ({})),
        getDownloadUrl: vi.fn((path) => path),
        getFileUrl: vi.fn((name) => `/uploads/${name}`),
    },
    corpusApi: {
        status: vi.fn(async () => null),
        sync: vi.fn(async () => ({})),
    },
}));

vi.mock('../utils/auth', () => ({
    authApi: { logout: vi.fn(async () => {}) },
}));

vi.mock('../utils/reviewer', () => ({
    hasRole: () => true,
    getReviewerName: () => 'tester',
}));

import DashboardPage from '../pages/DashboardPage';
import { api } from '../utils/api';
import { queryClient } from '../queryClient';
import { useDocumentStore } from '../stores/documentStore';
import { useLibraryStore } from '../stores/libraryStore';
import { useUiStore } from '../stores/uiStore';
import { useFavorites } from '../utils/favorites';
import { useRecents } from '../utils/recents';

const DOCS = [
    {
        id: 'ito',
        name: 'Income Tax Ordinance 2001 - amended upto 30th June 2025',
        pdf_filename: 'ito.pdf',
        source_type: 'acts_corpus',
        corpus_lane: 'ordinance',
        total_pages: 400,
        total_sections: 10,
        uploaded_at: '2025-01-01T00:00:00Z',
        status: 'in_progress',
        stats: { reviewed: 10, approved: 10, has_issues: 0, pending: 0, open_annotations: 0 },
        health: { measured_at: '2025-01-01', gate_ok: true },
        provenance: { source_kind: 'native-digital', tags: ['native-digital'] },
        version_count: 1,
        active_version_no: 1,
        last_version_at: '2025-01-01T00:00:00Z',
    },
    {
        id: 'customs',
        name: 'Customs Act, 1969 as amended up to 30.06.2025',
        pdf_filename: 'customs.pdf',
        source_type: 'acts_corpus',
        corpus_lane: 'customs',
        total_pages: 200,
        total_sections: 20,
        uploaded_at: '2025-06-01T00:00:00Z',
        status: 'in_progress',
        stats: { reviewed: 5, approved: 0, has_issues: 3, pending: 15, open_annotations: 2 },
        health: { measured_at: '2025-06-01', gate_ok: false },
        provenance: { source_kind: 'scanned-ocr', tags: ['scanned-ocr'] },
        version_count: 2,
        active_version_no: 2,
        last_version_at: '2025-07-01T00:00:00Z',
    },
    {
        id: 'manual',
        name: 'Manual upload',
        pdf_filename: 'secret-code.pdf',
        source_type: 'upload',
        corpus_lane: 'manual',
        total_pages: 10,
        total_sections: 4,
        uploaded_at: '2024-01-01T00:00:00Z',
        status: 'pending',
        stats: { reviewed: 0, approved: 0, has_issues: 0, pending: 4, open_annotations: 0 },
        health: null,
        provenance: { source_kind: 'mixed-ocr', tags: ['mixed-ocr'] },
        version_count: 1,
        active_version_no: 1,
        last_version_at: '2024-01-01T00:00:00Z',
    },
];

function healthOf(doc) {
    if (!doc.health?.measured_at) return 'unmeasured';
    return doc.health.gate_ok ? 'within_gate' : 'outside_gate';
}

function reviewOf(doc) {
    const reviewed = doc.stats?.reviewed || 0;
    if (doc.total_sections <= 0 || reviewed <= 0) return 'untouched';
    return reviewed >= doc.total_sections ? 'complete' : 'in_progress';
}

/** A fake v2 Library server: applies the query params the way the real API would. */
function installFakeServer(docs, { pageSize = 50 } = {}) {
    api.get.mockImplementation(async (path) => {
        const [route, query = ''] = path.split('?');
        const params = new URLSearchParams(query);

        const filtered = docs.filter((doc) => {
            const q = (params.get('q') || '').toLowerCase();
            if (q && !`${doc.name} ${doc.pdf_filename}`.toLowerCase().includes(q)) return false;
            const lanes = (params.get('lane') || '').split(',').filter(Boolean);
            if (lanes.length && !lanes.includes(doc.corpus_lane)) return false;
            const kinds = (params.get('kind') || '').split(',').filter(Boolean);
            if (kinds.length && !kinds.includes(doc.provenance?.source_kind || 'unknown')) return false;
            const health = (params.get('health') || '').split(',').filter(Boolean);
            if (health.length && !health.includes(healthOf(doc))) return false;
            const review = (params.get('review') || '').split(',').filter(Boolean);
            if (review.length && !review.includes(reviewOf(doc))) return false;
            if (params.get('flagged') === '1' && !(doc.stats?.has_issues > 0)) return false;
            const ids = (params.get('ids') || '').split(',').filter(Boolean);
            if (ids.length && !ids.includes(doc.id)) return false;
            if (params.get('ids') === '-') return false;
            return true;
        });

        if (route === '/v2/documents/facets') {
            const countBy = (fn) => {
                const counts = {};
                for (const doc of filtered) {
                    const key = fn(doc);
                    counts[key] = (counts[key] || 0) + 1;
                }
                return counts;
            };
            return {
                lanes: countBy((doc) => doc.corpus_lane),
                kinds: countBy((doc) => doc.provenance?.source_kind || 'unknown'),
                health: countBy(healthOf),
                review: countBy(reviewOf),
                years: [],
                tags: [],
                totals: {
                    documents: filtered.length,
                    flagged: filtered.filter((doc) => doc.stats?.has_issues > 0).length,
                    annotated: 0,
                    complete: filtered.filter((doc) => reviewOf(doc) === 'complete').length,
                },
                library: {
                    documents: docs.length,
                    flagged: docs.filter((doc) => doc.stats?.has_issues > 0).length,
                    complete: docs.filter((doc) => reviewOf(doc) === 'complete').length,
                },
                library_total: docs.length,
            };
        }

        if (route === '/v2/documents') {
            const sort = params.get('sort') || 'name';
            const sorted = [...filtered].sort((a, b) => {
                if (sort === 'name_desc') return b.name.localeCompare(a.name);
                if (sort === 'newest') return b.uploaded_at.localeCompare(a.uploaded_at);
                if (sort === 'oldest') return a.uploaded_at.localeCompare(b.uploaded_at);
                if (sort === 'pages') return b.total_pages - a.total_pages;
                if (sort === 'updated') return (b.last_version_at || '').localeCompare(a.last_version_at || '');
                return a.name.localeCompare(b.name);
            });
            const offset = Number(params.get('cursor') || 0);
            const page = sorted.slice(offset, offset + pageSize);
            const nextOffset = offset + page.length;
            return {
                items: page,
                total: sorted.length,
                next_cursor: nextOffset < sorted.length ? String(nextOffset) : null,
            };
        }

        throw new Error(`unexpected request: ${path}`);
    });
}

function LocationProbe() {
    const location = useLocation();
    return <div data-testid="location">{location.pathname}{location.search}</div>;
}

function renderLibrary(path = '/library') {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <DashboardPage />
            <LocationProbe />
        </MemoryRouter>,
    );
}

describe('Library page', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        window.localStorage.clear();
        installFakeServer(DOCS);
        useDocumentStore.setState({
            documents: [],
            documentsError: null,
            loading: { documents: false },
        });
        useLibraryStore.setState({
            items: [], total: 0, nextCursor: null, facets: null, library: null,
            status: 'idle', error: null, loadingMore: false, key: '', params: null, facetsParams: null,
        });
        useFavorites.setState({ ids: [] });
        useRecents.setState({ ids: [] });
        useUiStore.setState({
            theme: 'dark',
            reviewerName: 'tester',
            commandPaletteOpen: false,
            shortcutsHelpOpen: false,
            toasts: [],
        });
        queryClient.clear();
    });

    it('renders the server page with header totals and a results count', async () => {
        renderLibrary();
        await screen.findByText('Customs Act, 1969 as amended up to 30.06.2025');
        expect(screen.getByText('3 documents')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /1 flagged/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /1 complete/ })).toBeInTheDocument();
        // Default is grouped by family: one group per statute here.
        expect(document.querySelectorAll('.family-group').length).toBe(3);
    });

    it('searches server-side after a debounce and reflects q in the URL', async () => {
        renderLibrary();
        await screen.findByText('3 documents');
        const input = screen.getByRole('searchbox', { name: 'Search documents' });

        fireEvent.keyDown(window, { key: '/' });
        expect(input).toHaveFocus();

        fireEvent.change(input, { target: { value: 'secret-code' } });
        await waitFor(() => {
            expect(screen.getByTestId('location')).toHaveTextContent('q=secret-code');
        }, { timeout: 1500 });
        await screen.findByText('1 of 3');
        expect(screen.getAllByText('Manual upload').length).toBeGreaterThan(0);
        expect(screen.queryByText(/Income Tax Ordinance/)).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: /“secret-code”/ })).toBeInTheDocument();
    });

    it('filters via the panel: counts, URL, chips, clear-all', async () => {
        renderLibrary();
        await screen.findByText('3 documents');

        fireEvent.click(screen.getByRole('button', { name: /Filters/ }));
        const checkbox = await screen.findByRole('checkbox', { name: /Scanned \(OCR\)/ });
        fireEvent.click(checkbox);

        await waitFor(() => {
            expect(screen.getByTestId('location')).toHaveTextContent('kind=scanned-ocr');
        });
        await screen.findByText('1 of 3');
        expect(screen.getByRole('button', { name: /Format: Scanned/ })).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));
        await screen.findByText('3 documents');
        expect(screen.getByTestId('location')).not.toHaveTextContent('kind=');
    });

    it('offers grouped sort options and commits the choice to the URL', async () => {
        renderLibrary();
        await screen.findByText('3 documents');

        fireEvent.click(screen.getByRole('button', { name: 'Sort documents' }));
        expect(screen.getByRole('menuitem', { name: 'Recently updated' })).toBeInTheDocument();
        expect(screen.getByRole('menuitem', { name: 'Pages — most first' })).toBeInTheDocument();

        await act(async () => {
            fireEvent.click(screen.getByRole('menuitem', { name: 'Recently added' }));
        });
        expect(screen.getByRole('button', { name: 'Sort documents' })).toHaveTextContent('Recently added');
        expect(screen.getByTestId('location')).toHaveTextContent('sort=newest');
        // newest first: customs (2025-06) leads in flat… grouped keeps family order by first hit.
        await waitFor(() => {
            expect(api.get).toHaveBeenCalledWith(
                expect.stringContaining('sort=newest'),
                expect.objectContaining({ timeoutMs: 30_000 }),
            );
        });
    });

    it('toggles between grouped and flat lists', async () => {
        renderLibrary();
        await screen.findByText('3 documents');
        expect(document.querySelectorAll('.family-group').length).toBe(3);

        fireEvent.click(screen.getByRole('button', { name: /Grouped by statute family/ }));
        await waitFor(() => {
            expect(document.querySelectorAll('.family-group').length).toBe(0);
        });
        expect(screen.getByTestId('location')).toHaveTextContent('group=0');
    });

    it('favorites a document and finds it under the Favorites view', async () => {
        renderLibrary();
        await screen.findByText('3 documents');

        fireEvent.click(screen.getByRole('button', { name: /Add Customs Act, 1969.* to favorites/ }));
        fireEvent.click(screen.getByRole('button', { name: /Favorites/ }));

        await screen.findByText('1 of 3');
        await waitFor(() => {
            expect(screen.getByTestId('location')).toHaveTextContent('view=favorites');
        });
        expect(screen.queryByText(/Income Tax Ordinance/)).not.toBeInTheDocument();
    });

    it('shows an actionable empty state for an empty Favorites view', async () => {
        renderLibrary('/library?view=favorites');
        await screen.findByText('No favorites yet');
        fireEvent.click(screen.getByRole('button', { name: 'Browse all documents' }));
        await screen.findByText('3 documents');
    });

    it('bulk-selects rows and clears the selection with the bar', async () => {
        renderLibrary();
        await screen.findByText('3 documents');

        fireEvent.click(screen.getByRole('checkbox', { name: 'Select Manual upload' }));
        fireEvent.click(screen.getByRole('checkbox', { name: /Select Customs Act/ }));

        const bar = await screen.findByRole('toolbar', { name: '2 documents selected' });
        expect(bar).toHaveTextContent('2 selected');

        fireEvent.click(screen.getByRole('button', { name: 'Clear selection (Esc)' }));
        expect(screen.queryByRole('toolbar')).not.toBeInTheDocument();
    });

    it('navigates the list with j/k and opens with Enter', async () => {
        renderLibrary();
        await screen.findByText('3 documents');

        fireEvent.keyDown(window, { key: 'j' });
        fireEvent.keyDown(window, { key: 'Enter' });
        await waitFor(() => {
            expect(screen.getByTestId('location')).toHaveTextContent('/review/customs');
        });
    });

    it('loads the next cursor page from the footer button', async () => {
        installFakeServer(DOCS, { pageSize: 2 });
        renderLibrary();
        await screen.findByText(/Showing 2 of 3/);

        fireEvent.click(screen.getByRole('button', { name: /Load more/ }));
        await screen.findByText(/Showing 3 of 3/);
        expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument();
    });

    it('shows the empty-library state when the corpus is empty', async () => {
        installFakeServer([]);
        renderLibrary();
        await screen.findByText('Corpus is empty');
        expect(screen.getByRole('button', { name: /Upload PDF \+ JSON/ })).toBeInTheDocument();
    });

    it('shows a targeted no-results state for a search', async () => {
        renderLibrary('/library?q=zzz');
        await screen.findByText('No documents match “zzz”');
        fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
        await screen.findByText('3 documents');
    });

    it('switches density to compact rows', async () => {
        renderLibrary();
        await screen.findByText('3 documents');
        fireEvent.click(screen.getByRole('button', { name: 'Compact' }));
        await waitFor(() => {
            expect(document.querySelectorAll('.doc-compact-row').length).toBe(3);
        });
        expect(window.localStorage.getItem('qa-portal-library-view')).toBe('compact');
    });
});
