/** Server-driven Library list state: one filter state (keyed by its serialized
 * API params) plus the pages loaded for it so far. The page never holds the whole
 * corpus — it accumulates cursor pages and re-queries on every filter change.
 *
 * Race discipline: every request captures the sequence counter; a slow response
 * from an abandoned filter state is dropped instead of clobbering the new one.
 */
import { create } from 'zustand';
import { api } from '../utils/api';

let requestSeq = 0;

export const useLibraryStore = create((set, get) => ({
    items: [],
    total: 0,
    nextCursor: null,
    facets: null,
    // Library-wide aggregates (unfiltered), kept sticky across views for the header.
    library: null,
    status: 'idle', // idle | loading | ready | error
    error: null,
    loadingMore: false,
    key: '',
    params: null,
    facetsParams: null,

    /**
     * Reset and load page 1 + facet counts for a filter state.
     * `pageParams` null means an empty favorites/recents view: render zero results
     * without a documents request, but still fetch facets for the header totals.
     */
    load: async (key, { page: pageParams, facets: facetsParams } = {}) => {
        const seq = ++requestSeq;
        set({
            key,
            params: pageParams ? String(pageParams) : null,
            facetsParams: facetsParams ? String(facetsParams) : null,
            status: 'loading', error: null,
            items: [], total: 0, nextCursor: null,
        });
        try {
            const pagePromise = pageParams
                ? api.get(`/v2/documents?${pageParams}`)
                : Promise.resolve({ items: [], total: 0, next_cursor: null });
            // Facet counts are advisory: a failure must not take the list down.
            const facetsPromise = facetsParams
                ? api.get(`/v2/documents/facets?${facetsParams}`).catch(() => null)
                : Promise.resolve(null);
            const [page, facets] = await Promise.all([pagePromise, facetsPromise]);
            if (seq !== requestSeq) return;
            set((state) => ({
                items: page.items,
                total: page.total,
                nextCursor: page.next_cursor,
                facets,
                library: facets?.library || state.library,
                status: 'ready',
            }));
        } catch (e) {
            if (seq !== requestSeq) return;
            set({ status: 'error', error: e?.message || 'Request failed' });
        }
    },

    /** Append the next cursor page for the current filter state. */
    loadMore: async () => {
        const { key, params, nextCursor, loadingMore, status } = get();
        // params may legitimately be '' (unfiltered library) — only null means
        // "no request backing this view" (empty favorites/recents).
        if (params === null || !nextCursor || loadingMore || status !== 'ready') return;
        const seq = requestSeq;
        set({ loadingMore: true });
        try {
            const query = params
                ? `${params}&cursor=${encodeURIComponent(nextCursor)}`
                : `cursor=${encodeURIComponent(nextCursor)}`;
            const page = await api.get(`/v2/documents?${query}`);
            if (seq !== requestSeq || get().key !== key) return;
            set((state) => ({
                items: [...state.items, ...page.items],
                total: page.total,
                nextCursor: page.next_cursor,
            }));
        } catch {
            // A failed page fetch leaves the loaded prefix intact; the sentinel
            // offers a manual retry via the same call.
        } finally {
            if (seq === requestSeq) set({ loadingMore: false });
        }
    },

    /** Reload the current filter state (after deletes, sync, new version). */
    reload: async () => {
        const { key, params, facetsParams } = get();
        if (!key) return;
        await get().load(key, { page: params, facets: facetsParams });
    },
}));
