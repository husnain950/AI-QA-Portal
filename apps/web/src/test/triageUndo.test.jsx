import React from 'react';
import { fireEvent, render, screen, waitFor, act, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const patchMock = vi.fn(async () => ({}));
const getMock = vi.fn();

vi.mock('../utils/api', () => ({
    api: {
        get: (...args) => getMock(...args),
        post: vi.fn(async () => ({})),
        patch: (...args) => patchMock(...args),
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

describe('triage bulk undo', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        useUiStore.setState({ toasts: [], reviewerName: 'tester' });
        getMock.mockImplementation(async () => ({
            findings: FINDINGS,
            stats: { total: 1, done: 0, left: 1, by_triage: { new: 1 } },
        }));
    });

    it('bulk triage then undo restores via PATCH and shows feedback toast', async () => {
        render(
            <MemoryRouter>
                <TriagePage />
                <ToastHost />
            </MemoryRouter>,
        );

        // Wait for the row to load.
        await screen.findByText(/Definitions/);

        // Select via checkbox.
        fireEvent.click(screen.getByRole('checkbox', { name: /Select finding/ }));

        // Bulk bar appears; click "Deliberate".
        const bulkBar = await screen.findByRole('toolbar', { name: 'Bulk actions' });
        expect(bulkBar).toBeInTheDocument();
        fireEvent.click(within(bulkBar).getByRole('button', { name: 'Deliberate' }));

        await waitFor(() => expect(patchMock).toHaveBeenCalledWith(
            '/findings/1/status',
            { triage: 'deliberate', note: '' },
        ));

        // Undo button in toast.
        const undoButton = await screen.findByRole('button', { name: 'Undo' });
        await act(async () => {
            fireEvent.click(undoButton);
        });

        await waitFor(() => expect(patchMock).toHaveBeenCalledWith(
            '/findings/1/status',
            { triage: 'new', note: '' },
        ));
        expect(await screen.findByText(/Restored 1 finding/)).toBeInTheDocument();
    });
});
