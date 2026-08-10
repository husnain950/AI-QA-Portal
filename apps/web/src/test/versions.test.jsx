import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// vi.mock is hoisted above the imports, so the doubles have to be created inside it.
vi.mock('../utils/api', () => ({
    api: {
        get: vi.fn(async () => []),
        post: vi.fn(async () => ({})),
        patch: vi.fn(async () => ({})),
        delete: vi.fn(async () => ({})),
        getFileUrl: (name) => `http://static/uploads/${name}`,
    },
    versionsApi: {
        list: vi.fn(),
        diff: vi.fn(),
        activate: vi.fn(),
        create: vi.fn(),
    },
}));

import { versionsApi } from '../utils/api';
import DocumentHealth from '../components/dashboard/DocumentHealth';
import VersionPanel from '../components/review/VersionPanel';
import { contextAround } from '../hooks/useTextSelection';
import {
    conservationState,
    formatConserved,
    gateState,
    healthSummary,
    invariantLabel,
    metricsDelta,
} from '../utils/versionHealth';

const GREEN = {
    invariants_passed: 53,
    invariants_total: 53,
    body_conserved: 100,
    body_missing: 0,
    footnote_conserved: 100,
    footnote_missing: 0,
    gate_ok: true,
    measured_at: '2026-08-09T00:00:00Z',
    failing_invariants: [],
};

// Finance Act 2022 in the live corpus: 53/53 and 100% body, but outside the
// footnote gate at 99.843%.
const FINANCE_2022 = {
    ...GREEN,
    footnote_conserved: 99.843,
    footnote_missing: 135,
    gate_ok: false,
};

describe('pipeline health presentation', () => {
    it('reports the gate the pipeline decided, not one it recomputes', () => {
        expect(gateState(GREEN)).toBe('pass');
        expect(gateState(FINANCE_2022)).toBe('fail');
    });

    it('says nothing at all when a version was never measured', () => {
        expect(gateState(null)).toBe('unknown');
        expect(healthSummary(null)).toBeNull();
        expect(formatConserved(undefined)).toBeNull();
        expect(invariantLabel({ invariants_total: 0 })).toBeNull();
    });

    it('quotes conservation to the precision the gate uses', () => {
        expect(formatConserved(99.843)).toBe('99.843%');
        expect(formatConserved(100)).toBe('100.000%');
        expect(conservationState(99.843, 100.0)).toBe('fail');
        expect(conservationState(99.995, 99.99)).toBe('pass');
    });

    it('summarises invariants and both conservation figures', () => {
        expect(healthSummary(FINANCE_2022)).toBe(
            'invariants 53/53 · body 100.000% · footnotes 99.843%',
        );
    });

    it('reports what a new version bought, and ignores noise below the gate', () => {
        const delta = metricsDelta(GREEN, {
            ...FINANCE_2022,
            invariants_passed: 50,
        });
        expect(delta).toContainEqual({
            label: 'invariants passing',
            delta: 3,
            better: true,
        });
        expect(delta).toContainEqual({
            label: 'footnotes conserved',
            delta: '+0.157%',
            better: true,
        });
        // Body was already 100% in both, so it is not reported as a change.
        expect(delta.map((row) => row.label)).not.toContain('body conserved');
    });

    it('has no delta to report without a previous measurement', () => {
        expect(metricsDelta(GREEN, null)).toEqual([]);
    });
});

describe('DocumentHealth', () => {
    it('renders nothing for an unmeasured document rather than implying a pass', () => {
        const { container } = render(<DocumentHealth health={null} />);
        expect(container).toBeEmptyDOMElement();

        const unmeasured = render(
            <DocumentHealth health={{ invariants_total: 53, measured_at: null }} />,
        );
        expect(unmeasured.container).toBeEmptyDOMElement();
    });

    it('shows the failing gate and names the failing invariants in the tooltip', () => {
        render(
            <DocumentHealth
                health={{
                    ...FINANCE_2022,
                    invariants_passed: 52,
                    failing_invariants: ['no_jammed_words'],
                }}
            />,
        );
        expect(screen.getByText('outside gate')).toBeInTheDocument();
        expect(screen.getByText('footnotes 99.843%')).toBeInTheDocument();
        expect(screen.getByTitle(/Failing: no_jammed_words/)).toBeInTheDocument();
    });
});

describe('VersionPanel', () => {
    const VERSIONS = [
        {
            id: 'v2',
            document_id: 'doc-1',
            version_no: 2,
            json_filename: 'json/bbb.json',
            json_sha256: 'bbb',
            created_at: '2026-08-09T10:00:00Z',
            created_by: 'sync_acts',
            note: 'fixed footnote table columns',
            total_sections: 325,
            is_active: true,
            stats: {
                sections_changed: 4,
                reanchored: 1,
                needs_recheck: 1,
                orphaned: 0,
                approvals_reset: 2,
                sections_added: 0,
                sections_removed: 0,
                approvals_lost: 0,
            },
            metrics: GREEN,
        },
        {
            id: 'v1',
            document_id: 'doc-1',
            version_no: 1,
            json_filename: 'json/aaa.json',
            json_sha256: 'aaa',
            created_at: '2026-08-01T10:00:00Z',
            note: 'Initial upload.',
            total_sections: 324,
            is_active: false,
            stats: null,
            metrics: FINANCE_2022,
        },
    ];

    beforeEach(() => {
        versionsApi.list.mockReset().mockResolvedValue(VERSIONS);
        versionsApi.diff.mockReset();
        versionsApi.activate.mockReset().mockResolvedValue({});
    });

    it('renders nothing while closed and does not fetch', () => {
        const { container } = render(
            <VersionPanel documentId="doc-1" open={false} onClose={() => {}} />,
        );
        expect(container).toBeEmptyDOMElement();
        expect(versionsApi.list).not.toHaveBeenCalled();
    });

    it('lists versions newest first, marks the active one, and reports carry-over', async () => {
        render(<VersionPanel documentId="doc-1" open onClose={() => {}} />);

        expect(await screen.findByText('v2')).toBeInTheDocument();
        expect(screen.getByText('active')).toBeInTheDocument();
        expect(screen.getByText('fixed footnote table columns')).toBeInTheDocument();

        // The carry-over report is the thing that replaced the old hard refusal.
        expect(screen.getByText(/findings re-anchored/)).toBeInTheDocument();
        expect(screen.getByText(/findings needing recheck/)).toBeInTheDocument();
        expect(screen.getByText(/approvals reset/)).toBeInTheDocument();
        // Zero-valued rows are not listed as noise.
        expect(screen.queryByText(/findings orphaned/)).not.toBeInTheDocument();
    });

    it('shows the improvement the new version delivered', async () => {
        render(<VersionPanel documentId="doc-1" open onClose={() => {}} />);
        expect(
            await screen.findByText(/footnotes conserved \+0\.157%/),
        ).toBeInTheDocument();
    });

    it('fetches and renders the leaf-level diff on demand', async () => {
        versionsApi.diff.mockResolvedValue({
            base: { id: 'v1', version_no: 1 },
            target: { id: 'v2', version_no: 2 },
            summary: { added: 1, removed: 0, changed: 1, unchanged: 323 },
            sections: [
                {
                    source_key: '/chapters/0/sections/3',
                    change: 'changed',
                    section_code: '18',
                    section_heading: 'Goods dutiable',
                    start_page: 21,
                    diff: ['@@ -1 +1 @@', '-old text', '+new text'],
                },
            ],
        });
        render(<VersionPanel documentId="doc-1" open onClose={() => {}} />);

        fireEvent.click((await screen.findAllByText('What changed'))[0]);

        await waitFor(() => expect(versionsApi.diff).toHaveBeenCalledWith('doc-1', 'v2'));
        expect(await screen.findByText('changed')).toBeInTheDocument();
        expect(screen.getByText(/18\. Goods dutiable/)).toBeInTheDocument();
        expect(screen.getByText(/\+new text/)).toBeInTheDocument();
    });

    it('explains rather than errors when the first version has nothing to compare with', async () => {
        versionsApi.diff.mockResolvedValue({
            base: null,
            target: { id: 'v1', version_no: 1 },
            summary: { added: 0, removed: 0, changed: 0, unchanged: 0 },
            sections: [],
            note: 'This is the first version; there is nothing to compare it with.',
        });
        render(<VersionPanel documentId="doc-1" open onClose={() => {}} />);

        const buttons = await screen.findAllByText('What changed');
        fireEvent.click(buttons[1]);

        expect(await screen.findByText(/nothing to compare it with/)).toBeInTheDocument();
    });

    it('rolls back to an older version after confirmation, then reloads', async () => {
        const { useUiStore } = await import('../stores/uiStore');
        useUiStore.setState({
            confirmDialog: vi.fn().mockResolvedValue(true),
        });
        const onChanged = vi.fn();
        render(
            <VersionPanel documentId="doc-1" open onClose={() => {}} onChanged={onChanged} />,
        );

        fireEvent.click(await screen.findByText('Make active'));

        await waitFor(() =>
            expect(versionsApi.activate).toHaveBeenCalledWith('doc-1', 'v1'),
        );
        await waitFor(() => expect(onChanged).toHaveBeenCalled());
        // Only the non-active version offers rollback.
        expect(screen.getAllByText('Make active')).toHaveLength(1);
    });

    it('does not roll back when the reviewer cancels', async () => {
        const { useUiStore } = await import('../stores/uiStore');
        useUiStore.setState({
            confirmDialog: vi.fn().mockResolvedValue(false),
        });
        render(<VersionPanel documentId="doc-1" open onClose={() => {}} />);
        fireEvent.click(await screen.findByText('Make active'));
        await waitFor(() => {
            expect(versionsApi.activate).not.toHaveBeenCalled();
        });
    });

    it('surfaces a failed load instead of showing an empty history', async () => {
        versionsApi.list.mockRejectedValue(new Error('backend is down'));
        render(<VersionPanel documentId="doc-1" open onClose={() => {}} />);
        expect(await screen.findByText('backend is down')).toBeInTheDocument();
    });
});

describe('annotation anchoring context', () => {
    it('captures the characters either side of the highlight', () => {
        const element = document.createElement('div');
        element.innerHTML = '<p>alpha bravo charlie delta</p>';
        const text = element.textContent;
        const start = text.indexOf('charlie');
        const end = start + 'charlie'.length;

        const { contextBefore, contextAfter } = contextAround(element, start, end);
        expect(contextBefore).toBe('alpha bravo ');
        expect(contextAfter).toBe(' delta');
    });

    it('is safe at the very start and end of a leaf', () => {
        const element = document.createElement('div');
        element.textContent = 'only';
        expect(contextAround(element, 0, 4)).toEqual({
            contextBefore: '',
            contextAfter: '',
        });
        expect(contextAround(null, 0, 1).contextBefore).toBe('');
    });
});
