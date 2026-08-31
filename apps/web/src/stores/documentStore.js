import { create } from 'zustand';
import { api } from '../utils/api';
import { queryClient } from '../queryClient';

let searchController = null;
let searchSequence = 0;

const query = (queryKey, path, options = {}) => queryClient.fetchQuery({
    queryKey,
    queryFn: ({ signal }) => api.get(path, { signal }),
    ...options,
});

// A section appears in three slices at once: `activeSection`, the `sections` list the
// sidebar reads, and `pageSections` in page view. Every write used to patch all three
// inline, and three different actions across two stores had their own copy of that --
// which is how a status could land in one slice and not the others.
const applyToSection = (state, sectionId, changes) => {
    const patch = (s) => (s.id === sectionId ? { ...s, ...changes } : s);
    return {
        activeSection:
            state.activeSection?.id === sectionId
                ? { ...state.activeSection, ...changes }
                : state.activeSection,
        sections: state.sections.map(patch),
        pageSections: state.pageSections.map(patch),
    };
};

const applyToFootnote = (state, footnoteId, changes) => {
    const patchFootnotes = (s) =>
        s?.footnotes?.some((f) => f.id === footnoteId)
            ? {
                ...s,
                footnotes: s.footnotes.map((f) =>
                    f.id === footnoteId ? { ...f, ...changes } : f,
                ),
                // a footnote raising an issue raises it on its parent too
                review_status:
                    changes.review_status === 'has_issues' ? 'has_issues' : s.review_status,
            }
            : s;
    return {
        activeSection: patchFootnotes(state.activeSection),
        pageSections: state.pageSections.map(patchFootnotes),
        sections:
            changes.review_status === 'has_issues'
                ? state.sections.map((s) =>
                    s.id === state.activeSection?.id && patchFootnotes(state.activeSection) !== state.activeSection
                        ? { ...s, review_status: 'has_issues' }
                        : s,
                )
                : state.sections,
    };
};

export const useDocumentStore = create((set, get) => ({
    documents: [],
    activeDocument: null,
    sections: [],
    activeSection: null,
    pageSections: [], // Used in Page View mode
    searchResults: [],
    searchQuery: '',
    // Set when a fetch fails, so an empty result can be told apart from a failed load.
    // Every one of these used to be a bare `console.error`, and the UI rendered the
    // failure as a fact: "No sections found.", "No open notes.", "Select a section
    // from the Table of Contents". `documentsError` was added for exactly this and
    // had no reader.
    documentsError: null,
    sectionsError: null,
    // 'removed' when the section 404s (a resync retired the id) and 'failed' for
    // anything else. The two must not render as the same thing.
    activeSectionError: null,
    
    loading: {
        documents: false,
        activeDocument: false,
        sections: false,
        activeSection: false,
        search: false
    },

    fetchDocuments: async () => {
        set((state) => ({ loading: { ...state.loading, documents: true } }));
        try {
            const data = await query(['documents'], '/documents');
            set({ documents: data, documentsError: null });
        } catch (e) {
            console.error('Failed to fetch documents', e);
            set({ documentsError: e.message || 'Request failed' });
        } finally {
            set((state) => ({ loading: { ...state.loading, documents: false } }));
        }
    },

    fetchDocument: async (docId) => {
        set((state) => ({ loading: { ...state.loading, activeDocument: true } }));
        try {
            const data = await query(['document', docId], `/documents/${docId}`);
            set({ activeDocument: data });
            return data;
        } catch (e) {
            console.error('Failed to fetch document', e);
            return null;
        } finally {
            set((state) => ({ loading: { ...state.loading, activeDocument: false } }));
        }
    },

    fetchSections: async (docId) => {
        set((state) => ({ loading: { ...state.loading, sections: true } }));
        try {
            const data = await query(['sections', docId], `/documents/${docId}/sections`);
            set({ sections: data, sectionsError: null });
        } catch (e) {
            // Written down rather than swallowed: with nothing recorded, the TOC
            // rendered "No sections found." for a failed request, which reads as a
            // fact about the document.
            console.error('Failed to fetch sections', e);
            set({ sectionsError: e?.message || 'Request failed' });
        } finally {
            set((state) => ({ loading: { ...state.loading, sections: false } }));
        }
    },

    fetchSection: async (docId, sectionId) => {
        set((state) => ({ loading: { ...state.loading, activeSection: true } }));
        try {
            const data = await query(['section', docId, sectionId], `/documents/${docId}/sections/${sectionId}`);
            set({ activeSection: data, activeSectionError: null });
            return data;
        } catch (e) {
            console.error('Failed to fetch section', e);
            // Clearing it is the whole point. Leaving the previous leaf mounted is
            // how a reviewer could approve or annotate the WRONG provision after a
            // resync: sections are hard-deleted, so a URL naming a retired id 404s,
            // and the pane went on rendering the last leaf's HTML, footnotes and
            // toolbar while the URL and "Leaf N of M" referred to the dead one.
            // A 404 is "this leaf is gone"; anything else is "the request failed",
            // and the two must not render as the same empty state.
            set({
                activeSection: null,
                activeSectionError: e?.status === 404 ? 'removed' : 'failed',
            });
            return null;
        } finally {
            set((state) => ({ loading: { ...state.loading, activeSection: false } }));
        }
    },

    fetchSectionsByPage: async (docId, pageNumber) => {
        try {
            const data = await query(
                ['sections-by-page', docId, pageNumber],
                `/documents/${docId}/sections/by-page/${pageNumber}`,
            );
            set({ pageSections: data });
            return data;
        } catch (e) {
            console.error('Failed to fetch sections by page', e);
            return [];
        }
    },

    /** Patch a section across every slice it appears in. */
    patchSection: (sectionId, changes) => set((state) => applyToSection(state, sectionId, changes)),

    /** Patch a footnote, and its parent section's status, across every slice. */
    patchFootnote: (footnoteId, changes) => set((state) => applyToFootnote(state, footnoteId, changes)),

    /** Reconcile the review workspace with the server after a write.
     *
     * One strategy, in one place. `updateSectionStatus` used to invalidate two query
     * keys, hand-patch three slices, AND refetch the document -- three overlapping
     * caches for one PATCH -- while `reviewStore` did its own version of the same
     * thing twice more.
     */
    refreshReviewData: async ({ sectionId = null, page = null } = {}) => {
        const docId = get().activeDocument?.id;
        if (!docId) return;
        const target = sectionId ?? get().activeSection?.id;
        // Invalidate exactly what is about to be refetched.
        //
        // This used to invalidate two keys and refetch four. `invalidateQueries`
        // prefix-matches on array elements and `'sections' !== 'section'`, so
        // `['section', docId, id]` and `['sections-by-page', docId, page]` were
        // never touched -- and `fetchQuery` honours `staleTime: 30_000`, so those
        // two "refetches" returned the PRE-WRITE cached value and wrote it back into
        // the store, reverting the optimistic patch. Acting on a leaf within 30s of
        // opening it left the TOC saying `approved` and the section pane saying the
        // old status: precisely the split the consolidation comment claims to have
        // fixed. Server-derived fields (`effective_status`, `reviewer_verdict`,
        // `annotation_count`, quality-flag elevation) never arrived at all until the
        // cache aged out.
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['document', docId] }),
            queryClient.invalidateQueries({ queryKey: ['sections', docId] }),
            ...(target
                ? [queryClient.invalidateQueries({ queryKey: ['section', docId, target] })]
                : []),
            ...(page != null
                ? [queryClient.invalidateQueries({
                    queryKey: ['sections-by-page', docId, page],
                })]
                : []),
        ]);
        await Promise.all([
            get().fetchDocument(docId),
            get().fetchSections(docId),
            ...(target ? [get().fetchSection(docId, target)] : []),
            ...(page != null ? [get().fetchSectionsByPage(docId, page)] : []),
        ]);
    },

    updateSectionStatus: async (docId, sectionId, status) => {
        try {
            const res = await api.patch(`/documents/${docId}/sections/${sectionId}/status`, {
                review_status: status
            });
            get().patchSection(sectionId, { review_status: status });
            await get().refreshReviewData({ sectionId });
            return res;
        } catch (e) {
            console.error('Failed to update section status', e);
            throw e;
        }
    },

    search: async (docId, q) => {
        if (!q.trim()) {
            set({ searchResults: [], searchQuery: '' });
            return;
        }
        set((state) => ({ searchQuery: q, loading: { ...state.loading, search: true } }));
        searchController?.abort();
        searchController = new AbortController();
        const sequence = ++searchSequence;
        try {
            const data = await api.get(
                `/documents/${docId}/search?q=${encodeURIComponent(q)}`,
                { signal: searchController.signal, timeoutMs: 10_000 },
            );
            if (sequence === searchSequence) set({ searchResults: data });
        } catch (e) {
            if (e.code !== 'cancelled') console.error('Search failed', e);
        } finally {
            if (sequence === searchSequence) {
                set((state) => ({ loading: { ...state.loading, search: false } }));
            }
        }
    },

    clearSearch: () => {
        searchController?.abort();
        searchSequence += 1;
        set({ searchResults: [], searchQuery: '' });
    },

    deleteDocument: async (docId) => {
        try {
            await api.delete(`/documents/${docId}`);
            await queryClient.invalidateQueries({ queryKey: ['documents'] });
            set((state) => ({
                documents: state.documents.filter(d => d.id !== docId),
                activeDocument: state.activeDocument?.id === docId ? null : state.activeDocument
            }));
        } catch (e) {
            console.error('Failed to delete document', e);
            throw e;
        }
    }
}));
