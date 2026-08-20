import React from 'react';
import { fireEvent, render, screen, waitFor, act, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const postMock = vi.fn(async () => ({ applied: 1 }));
const getMock = vi.fn();

vi.mock('../utils/api', () => ({
    api: {
        get: (...args) => getMock(...args),
        post: (...args) => postMock(...args),
        patch: vi.fn(async () => ({})),
        delete: vi.fn(async () => ({})),
        getDownloadUrl: vi.fn((p) => p),
        getFileUrl: vi.fn((f) => `/uploads/${f}`),
    },
    getReviewerName: () => 'tester',
    setReviewerName: vi.fn(),
    corpusApi: { status: vi.fn(async () => ({})), sync: vi.fn(async () => ({})) },
}));

import TriagePage from '../pages/TriagePage';
import ToastHost from '../components/ui/ToastHost';
import { useUiStore } from '../stores/uiStore';

const FINDINGS = [
    {
        id: 1,
        detector: 'glyph_split',
        document_id: 'doc-1',
        section_id: 'sec-1',
        section_code: '2',
        section_heading: 'Definitions',
        document_name: 'Sample Act, 2001',
        triage: 'new',
        score: 70,
        blast_radius: 1,
    },
];

const page = {
    items: FINDINGS,
    total: FINDINGS.length,
    next_cursor: null,
    refreshed_at: '2026-08-20T00:00:00Z',
    stats: { total: 1, done: 0, left: 1, by_triage: { new: 1 } },
};

function renderTriage() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <MemoryRouter>
                <TriagePage />
                <ToastHost />
            </MemoryRouter>
        </QueryClientProvider>,
    );
}

/** The one bulk-triage POST, ignoring the per-request idempotency key. */
function bulkCalls() {
    return postMock.mock.calls.filter((call) => call[0] === '/v2/findings/bulk-triage');
}

describe('triage bulk undo', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        postMock.mockImplementation(async () => ({ applied: 1 }));
        useUiStore.setState({ toasts: [], reviewerName: 'tester' });
        getMock.mockImplementation(async () => page);
    });

    it('bulk triage posts one atomic batch, and undo posts the inverse', async () => {
        renderTriage();

        await screen.findByText(/Definitions/);
        fireEvent.click(screen.getByRole('checkbox', { name: /Select finding/ }));

        const bulkBar = await screen.findByRole('toolbar', { name: 'Bulk actions' });
        fireEvent.click(within(bulkBar).getByRole('button', { name: 'Deliberate' }));

        await waitFor(() => expect(bulkCalls()).toHaveLength(1));
        // One request for the whole selection, carrying the prior state each row is
        // expected to be in, so a concurrent change fails the batch instead of
        // half-applying it.
        expect(bulkCalls()[0][1]).toEqual({
            items: [{ id: 1, triage: 'deliberate', expected_prior: 'new', note: '' }],
        });
        expect(bulkCalls()[0][3].headers['Idempotency-Key']).toBeTruthy();

        const undoButton = await screen.findByRole('button', { name: 'Undo' });
        await act(async () => {
            fireEvent.click(undoButton);
        });

        await waitFor(() => expect(bulkCalls()).toHaveLength(2));
        expect(bulkCalls()[1][1]).toEqual({
            items: [{ id: 1, triage: 'new', expected_prior: 'deliberate', note: '' }],
        });
        expect(await screen.findByText(/Restored 1 finding/)).toBeInTheDocument();
    });

    it('a rejected batch restores the rows and says so', async () => {
        renderTriage();
        await screen.findByText(/Definitions/);
        postMock.mockImplementation(async () => {
            throw new Error('finding 1 changed under you');
        });

        fireEvent.click(screen.getByRole('checkbox', { name: /Select finding/ }));
        const bulkBar = await screen.findByRole('toolbar', { name: 'Bulk actions' });
        fireEvent.click(within(bulkBar).getByRole('button', { name: 'Deliberate' }));

        expect(await screen.findByText(/finding 1 changed under you/)).toBeInTheDocument();
    });
});
