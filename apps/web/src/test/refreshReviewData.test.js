/**
 * Every key that gets refetched must first be invalidated.
 *
 * `refreshReviewData` invalidated two keys and refetched four. `invalidateQueries`
 * prefix-matches on array elements and `'sections' !== 'section'`, so
 * `['section', docId, id]` and `['sections-by-page', docId, page]` were never
 * touched -- and `fetchQuery` honours `staleTime: 30_000`, so those two "refetches"
 * returned the PRE-WRITE cached value and wrote it back into the store, reverting the
 * optimistic patch. Acting on a leaf within 30s of opening it left the TOC saying
 * `approved` while the section pane said the old status.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({
    api: { get: vi.fn(async () => ({})), patch: vi.fn(async () => ({})) },
}));

const invalidated = [];
vi.mock('../queryClient', () => ({
    queryClient: {
        invalidateQueries: vi.fn(async ({ queryKey }) => {
            invalidated.push(queryKey.join('|'));
        }),
        fetchQuery: vi.fn(async ({ queryFn }) => queryFn({ signal: undefined })),
    },
}));

import { useDocumentStore } from '../stores/documentStore';

describe('refreshReviewData', () => {
    beforeEach(() => {
        invalidated.length = 0;
        useDocumentStore.setState({
            activeDocument: { id: 'doc-1' },
            activeSection: { id: 'sec-1' },
            sections: [],
            pageSections: [],
        });
    });

    it('invalidates the active section, not just the section LIST', async () => {
        await useDocumentStore.getState().refreshReviewData({ sectionId: 'sec-1' });
        expect(invalidated).toContain('sections|doc-1');
        expect(invalidated).toContain('section|doc-1|sec-1');
    });

    it('invalidates the page slice when a page is refreshed', async () => {
        await useDocumentStore.getState().refreshReviewData({ sectionId: 'sec-1', page: 4 });
        expect(invalidated).toContain('sections-by-page|doc-1|4');
    });

    it('invalidates exactly the keys it refetches, and no more', async () => {
        await useDocumentStore.getState().refreshReviewData({ sectionId: 'sec-1', page: 2 });
        expect([...invalidated].sort()).toEqual([
            'document|doc-1',
            'section|doc-1|sec-1',
            'sections-by-page|doc-1|2',
            'sections|doc-1',
        ].sort());
    });

    it('falls back to the active section when none is named', async () => {
        await useDocumentStore.getState().refreshReviewData();
        expect(invalidated).toContain('section|doc-1|sec-1');
    });

    it('does nothing without an active document', async () => {
        useDocumentStore.setState({ activeDocument: null });
        await useDocumentStore.getState().refreshReviewData({ sectionId: 'sec-1' });
        expect(invalidated).toEqual([]);
    });
});
