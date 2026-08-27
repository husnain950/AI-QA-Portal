import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({
    api: { get: vi.fn() },
}));

import { api } from '../utils/api';
import { useLibraryStore } from '../stores/libraryStore';

const DOC = (id) => ({ id, name: `Act ${id}` });

function page(items, total, next = null) {
    return { items, total, next_cursor: next, refreshed_at: 'now' };
}

const FACETS = {
    lanes: {}, kinds: {}, health: {}, review: {}, years: [], tags: [],
    totals: { documents: 2, flagged: 0, annotated: 0, complete: 0 },
    library: { documents: 9, flagged: 1, complete: 2 },
    library_total: 9,
};

function resetStore() {
    useLibraryStore.setState({
        items: [], total: 0, nextCursor: null, facets: null, library: null,
        status: 'idle', error: null, loadingMore: false, key: '', params: null, facetsParams: null,
    });
}

describe('libraryStore', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        resetStore();
    });

    it('loads page one plus facets and keeps library totals sticky', async () => {
        api.get.mockImplementation(async (path) => (
            path.startsWith('/v2/documents/facets') ? FACETS : page([DOC('a'), DOC('b')], 5, 'cursor-2')
        ));

        await useLibraryStore.getState().load('k1', { page: new URLSearchParams(), facets: new URLSearchParams() });

        const state = useLibraryStore.getState();
        expect(state.status).toBe('ready');
        expect(state.items.map((doc) => doc.id)).toEqual(['a', 'b']);
        expect(state.total).toBe(5);
        expect(state.nextCursor).toBe('cursor-2');
        expect(state.facets.library_total).toBe(9);
        expect(state.library.documents).toBe(9);
    });

    it('loadMore appends the cursor page instead of replacing it', async () => {
        api.get
            .mockResolvedValueOnce(page([DOC('a')], 3, 'c2'))
            .mockResolvedValueOnce(FACETS)
            .mockResolvedValueOnce(page([DOC('b')], 3, 'c3'));

        await useLibraryStore.getState().load('k1', { page: new URLSearchParams('lane=customs'), facets: new URLSearchParams() });
        await useLibraryStore.getState().loadMore();

        const state = useLibraryStore.getState();
        expect(state.items.map((doc) => doc.id)).toEqual(['a', 'b']);
        expect(state.nextCursor).toBe('c3');
        expect(api.get.mock.calls[2][0]).toContain('cursor=c2');
    });

    it('loadMore is a no-op without a cursor or with an empty-params page', async () => {
        api.get.mockResolvedValue(page([], 0));
        await useLibraryStore.getState().load('k1', { page: null, facets: new URLSearchParams() });
        await useLibraryStore.getState().loadMore();
        expect(api.get).toHaveBeenCalledTimes(1, 'only the facets request ran');
    });

    it('drops a slow response from an abandoned filter state', async () => {
        let releaseFirst;
        const first = new Promise((resolve) => { releaseFirst = resolve; });
        api.get.mockImplementationOnce(() => first);
        api.get.mockResolvedValueOnce(FACETS);
        api.get.mockImplementation(async (path) => (
            path.startsWith('/v2/documents/facets') ? FACETS : page([DOC('new')], 1)
        ));

        const stale = useLibraryStore.getState().load('k1', { page: new URLSearchParams('q=old'), facets: new URLSearchParams() });
        await useLibraryStore.getState().load('k2', { page: new URLSearchParams('q=new'), facets: new URLSearchParams() });
        releaseFirst(page([DOC('stale')], 1));
        await stale;

        const state = useLibraryStore.getState();
        expect(state.key).toBe('k2');
        expect(state.items.map((doc) => doc.id)).toEqual(['new']);
    });

    it('a failed load sets the error state and keeps the key', async () => {
        api.get.mockRejectedValue(new Error('API returned 500'));
        await useLibraryStore.getState().load('k1', { page: new URLSearchParams(), facets: new URLSearchParams() });
        const state = useLibraryStore.getState();
        expect(state.status).toBe('error');
        expect(state.error).toContain('500');
        expect(state.key).toBe('k1');
    });

    it('a failed facets fetch does not take the list down', async () => {
        api.get.mockImplementation(async (path) => {
            if (path.startsWith('/v2/documents/facets')) throw new Error('boom');
            return page([DOC('a')], 1);
        });
        await useLibraryStore.getState().load('k1', { page: new URLSearchParams(), facets: new URLSearchParams() });
        const state = useLibraryStore.getState();
        expect(state.status).toBe('ready');
        expect(state.items).toHaveLength(1);
        expect(state.facets).toBeNull();
    });
});
