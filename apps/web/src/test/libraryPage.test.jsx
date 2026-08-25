import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({
    api: {
        get: vi.fn(),
        getDownloadUrl: vi.fn((path) => path),
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
import { useUiStore } from '../stores/uiStore';

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
        stats: { reviewed: 10, has_issues: 0 },
        health: { measured_at: '2025-01-01', gate_ok: true },
        provenance: { source_kind: 'native-digital', tags: ['native-digital'] },
        version_count: 1,
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
        stats: { reviewed: 0, has_issues: 3 },
        health: null,
        provenance: { source_kind: 'scanned-ocr', tags: ['scanned-ocr'] },
        version_count: 1,
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
        stats: { reviewed: 2, has_issues: 0 },
        health: { measured_at: '2024-01-01', gate_ok: false },
        provenance: { source_kind: 'mixed-ocr', tags: ['mixed-ocr'] },
        version_count: 1,
    },
];

function LocationSearch() {
    const location = useLocation();
    return <div data-testid="library-search">{location.search}</div>;
}

function renderLibrary(path = '/library') {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <DashboardPage />
            <LocationSearch />
        </MemoryRouter>,
    );
}

describe('Library toolbar', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        api.get.mockResolvedValue(DOCS);
        useDocumentStore.setState({
            documents: [],
            documentsError: null,
            loading: { documents: false },
        });
        useUiStore.setState({
            theme: 'dark',
            reviewerName: 'tester',
            commandPaletteOpen: false,
            toasts: [],
        });
        try {
            window.localStorage.removeItem('qa-portal-library-sort');
            window.localStorage.removeItem('qa-portal-library-view');
        } catch {
            // ignore
        }
        queryClient.clear();
    });

    it('shows kind chips and URL state, and hides nothing useful', async () => {
        renderLibrary();
        await screen.findByText(/3 of 3/);

        fireEvent.click(screen.getByRole('button', { name: /Scanned/ }));
        expect(await screen.findByRole('button', { name: 'Scanned' })).toBeInTheDocument();
        expect(screen.getByText(/1 of 3/)).toBeInTheDocument();
        await waitFor(() => {
            expect(screen.getByTestId('library-search')).toHaveTextContent('kind=scanned-ocr');
        });

        fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));
        await waitFor(() => {
            expect(screen.queryByRole('button', { name: 'Scanned' })).not.toBeInTheDocument();
            expect(screen.getByTestId('library-search')).toHaveTextContent('');
        });
        expect(screen.getByText(/3 of 3/)).toBeInTheDocument();
    });

    it('filters by filename after debounce and focuses search on /', async () => {
        renderLibrary();
        await screen.findByText(/3 of 3/);
        const input = screen.getByRole('searchbox', { name: 'Filter documents' });

        fireEvent.keyDown(window, { key: '/' });
        expect(input).toHaveFocus();

        fireEvent.change(input, { target: { value: 'secret-code' } });
        await waitFor(() => {
            expect(screen.getByText(/1 of 3/)).toBeInTheDocument();
            expect(screen.getByRole('button', { name: '“secret-code”' })).toBeInTheDocument();
        }, { timeout: 1500 });
        expect(screen.queryByText('Customs Act, 1969 as amended up to 30.06.2025')).not.toBeInTheDocument();
    });

    it('treats % reviewed as a complete-documents filter', async () => {
        renderLibrary();
        await screen.findByText(/3 of 3/);

        fireEvent.click(screen.getByRole('button', { name: /reviewed$/ }));
        expect(await screen.findByRole('button', { name: 'Complete' })).toBeInTheDocument();
        expect(screen.getByText(/1 of 3/)).toBeInTheDocument();
        expect(screen.queryByText('Manual upload')).not.toBeInTheDocument();
    });

    it('hides Health when every document is unmeasured', async () => {
        api.get.mockResolvedValue(DOCS.map((doc) => ({ ...doc, health: null })));
        renderLibrary();
        await screen.findByText(/3 of 3/);
        expect(screen.queryByRole('group', { name: 'Health' })).not.toBeInTheDocument();
        expect(screen.getByRole('group', { name: 'Kind' })).toBeInTheDocument();
    });

    it('opens the sort menu with named options', async () => {
        renderLibrary();
        await screen.findByText(/3 of 3/);
        fireEvent.click(screen.getByRole('button', { name: 'Sort documents' }));
        expect(screen.getByRole('menuitem', { name: 'Pages — largest' })).toBeInTheDocument();
        expect(screen.getByRole('menuitem', { name: 'Flagged sections' })).toBeInTheDocument();
        await act(async () => {
            fireEvent.click(screen.getByRole('menuitem', { name: 'Recently added' }));
        });
        expect(screen.getByRole('button', { name: 'Sort documents' })).toHaveTextContent('Recently added');
    });
});
