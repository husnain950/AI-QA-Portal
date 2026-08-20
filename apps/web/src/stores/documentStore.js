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

    updateSectionStatus: async (docId, sectionId, status) => {
        try {
            const res = await api.patch(`/documents/${docId}/sections/${sectionId}/status`, {
                review_status: status
            });
            await queryClient.invalidateQueries({ queryKey: ['document', docId] });
            await queryClient.invalidateQueries({ queryKey: ['sections', docId] });
            
            // Update active section status
            const activeSection = get().activeSection;
            if (activeSection && activeSection.id === sectionId) {
                set({ activeSection: { ...activeSection, review_status: status } });
            }

            // Update page sections status
            const pageSections = get().pageSections;
            set({
                pageSections: pageSections.map(s => s.id === sectionId ? { ...s, review_status: status } : s)
            });

            // Update sections list
            const sections = get().sections;
            set({
                sections: sections.map(s => s.id === sectionId ? { ...s, review_status: status } : s)
            });

            // Refresh document meta/stats
            get().fetchDocument(docId);
            
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
