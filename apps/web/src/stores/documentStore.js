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
    // Set when /documents fails, so an empty list can be told apart from a failed load.
    documentsError: null,
    
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
            set({ sections: data });
        } catch (e) {
            console.error('Failed to fetch sections', e);
        } finally {
            set((state) => ({ loading: { ...state.loading, sections: false } }));
        }
    },

    fetchSection: async (docId, sectionId) => {
        set((state) => ({ loading: { ...state.loading, activeSection: true } }));
        try {
            const data = await query(['section', docId, sectionId], `/documents/${docId}/sections/${sectionId}`);
            set({ activeSection: data });
            return data;
        } catch (e) {
            console.error('Failed to fetch section', e);
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
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['document', docId] }),
            queryClient.invalidateQueries({ queryKey: ['sections', docId] }),
        ]);
        const target = sectionId ?? get().activeSection?.id;
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
